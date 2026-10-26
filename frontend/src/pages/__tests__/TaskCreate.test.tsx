import userEvent from '@testing-library/user-event'
import { act, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import type { AccountConfig } from '@/api'
import TaskCreate from '@/pages/TaskCreate'
import { renderWithRouter } from '@/test/renderWithRouter'

/**
 * Render and let the hotspot-catalogue effect settle.
 *
 * The page fetches the platform catalogue on mount; without flushing that promise the
 * resulting state updates land outside `act()` and React logs warnings that would otherwise
 * mask real ones.
 */
const renderTaskCreate = async () => {
  const result = renderWithRouter(<TaskCreate />, { route: '/task/new' })
  await act(async () => {
    await Promise.resolve()
  })
  return result
}

const { listAccountsMock, createTaskMock, getHotspotPlatformsMock } = vi.hoisted(() => ({
  listAccountsMock: vi.fn<() => Promise<AccountConfig[]>>(),
  createTaskMock: vi.fn<(payload: Record<string, unknown>) => Promise<unknown>>(),
  getHotspotPlatformsMock: vi.fn<() => Promise<unknown>>(),
}))

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api')
  return {
    ...actual,
    listAccounts: listAccountsMock,
    createTask: createTaskMock,
    // Must be mocked: the real call would leave the page's catalogue effect pending and
    // attempt a network request from a unit test.
    getHotspotPlatforms: getHotspotPlatformsMock,
  }
})

/** Two newsnow platforms plus a TopHub one, mirroring the real catalogue's shape. */
const PLATFORM_CATALOG = {
  items: [
    { name: '微博热搜', path: 'weibo', source: 'newsnow', provider_id: 'weibo', category: '社会', weight: 1.1, enabled: true },
    { name: '知乎热榜', path: 'zhihu', source: 'newsnow', provider_id: 'zhihu', category: 'AI', weight: 1.1, enabled: true },
    { name: '知乎热榜(TopHub)', path: '/n/mproPpoq6O', source: 'tophub', provider_id: 'tophub', category: 'AI', weight: 1.1, enabled: true },
  ],
  updated_at: '2026-10-25T00:00:00Z',
  source: 'newsnow',
}

beforeEach(() => {
  vi.clearAllMocks()
  createTaskMock.mockResolvedValue({ task_id: 'task-1' })
  getHotspotPlatformsMock.mockResolvedValue(PLATFORM_CATALOG)
  listAccountsMock.mockResolvedValue([
    {
      account_id: 'wechat-1',
      name: '测试公众号',
      platform: 'wechat_mp',
      app_id: 'appid',
      app_secret: 'secret',
      enabled: true,
      created_at: '2026-04-01T00:00:00Z',
      updated_at: null,
    },
  ])

  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  })
})

test('renders grouped form sections with list-style guidance', async () => {
  const { container } = await renderTaskCreate()

  expect(screen.getByText('启动一次完整创作流程')).toBeInTheDocument()
  expect(screen.getByText('先点灵感标签补齐关键词，再继续填写表单。')).toBeInTheDocument()
  expect(screen.getByRole('heading', { level: 3, name: '主题与热点' })).toBeInTheDocument()
  // 步骤标题与步骤内容都会出现同名文案，因此这里断言出现次数而不是唯一匹配。
  expect(screen.getAllByText('受众与策略').length).toBeGreaterThan(0)
  expect(screen.getAllByText('发布与审核').length).toBeGreaterThan(0)
  expect(screen.queryByText('基础输入')).not.toBeInTheDocument()
  const guidanceList = screen.getByRole('list', { name: '创作提示' })
  expect(guidanceList).toBeInTheDocument()
  expect(screen.getAllByRole('listitem')).toHaveLength(3)
  expect(getComputedStyle(guidanceList).listStyleType).toBe('disc')
  expect(container.querySelector('[aria-label="创作提示"]')).toBe(guidanceList)
})

test('clicking a hot-topic chip fills the keywords field', async () => {
  const user = userEvent.setup()

  await renderTaskCreate()

  await user.click(screen.getByText('人工智能'))

  expect(screen.getByLabelText('关键词')).toHaveValue('人工智能')
})

test('blocks the next step until the keywords are filled in', async () => {
  const user = userEvent.setup()

  await renderTaskCreate()

  await user.click(screen.getByRole('button', { name: '下一步' }))

  expect(await screen.findByText('请输入关键词')).toBeInTheDocument()
  // 后续步骤的字段必须保持挂载（否则提交时会丢失前面步骤的值），
  // 但当前不可见。断言「不可见」而不是「不在文档中」。
  expect(screen.getByLabelText('受众角色')).not.toBeVisible()

  await user.type(screen.getByLabelText('关键词'), '人工智能 最新进展')
  await user.click(screen.getByRole('button', { name: '下一步' }))

  expect(await screen.findByLabelText('受众角色')).toBeVisible()
  // 第一步的字段仍然注册着，只是被隐藏了。
  expect(screen.getByLabelText('关键词')).not.toBeVisible()
})

test('walks to the publish step, exposes the advanced fields and allows stepping back', async () => {
  const user = userEvent.setup()

  await renderTaskCreate()

  await user.type(screen.getByLabelText('关键词'), '大模型')
  await user.click(screen.getByRole('button', { name: '下一步' }))
  expect(await screen.findByLabelText('受众角色')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: '下一步' }))

  expect(await screen.findByRole('button', { name: '启动创作流程' })).toBeInTheDocument()
  expect(screen.getByLabelText('检索深度')).toBeInTheDocument()
  expect(screen.getByLabelText('内容时效窗口')).toBeInTheDocument()
  expect(screen.getByLabelText('最少来源数')).toBeInTheDocument()
  expect(screen.getByLabelText('最少官方来源数')).toBeInTheDocument()
  expect(screen.getByLabelText('最少来源域名数')).toBeInTheDocument()
  expect(screen.getByLabelText('要求风险与反向观点')).toBeInTheDocument()
  expect(screen.getByLabelText('敏感题材自动加深检索')).toBeInTheDocument()
  expect(screen.getByLabelText('直接发布到公众号')).toBeInTheDocument()
  expect(screen.getByLabelText('自动入公众号草稿箱')).toBeInTheDocument()
  expect(screen.getByLabelText('发布账号（可选）')).toBeInTheDocument()
  expect(screen.queryByText('Research depth')).not.toBeInTheDocument()
  expect(screen.queryByText('Minimum sources')).not.toBeInTheDocument()

  await waitFor(() => {
    expect(listAccountsMock).toHaveBeenCalled()
  })

  await user.click(screen.getByRole('button', { name: '上一步' }))
  expect(await screen.findByLabelText('受众角色')).toBeInTheDocument()
})

test('submitting from the last step still carries the values from earlier steps', async () => {
  // 回归测试：早期版本按步骤卸载表单，导致在第三步提交时
  // values.keywords 为 undefined，抛出 "Cannot read properties of undefined (reading 'trim')"。
  const user = userEvent.setup()

  await renderTaskCreate()

  await user.type(screen.getByLabelText('关键词'), '大模型 推理成本')
  await user.click(screen.getByRole('button', { name: '下一步' }))
  await user.click(await screen.findByRole('button', { name: '下一步' }))
  await user.click(await screen.findByRole('button', { name: '启动创作流程' }))

  await waitFor(() => {
    expect(createTaskMock).toHaveBeenCalledTimes(1)
  })

  const payload = createTaskMock.mock.calls[0][0]
  expect(payload.keywords).toBe('大模型 推理成本')
  // 第二步的选择同样必须保留下来。
  const generationConfig = payload.generation_config as Record<string, unknown> | undefined
  expect(generationConfig?.audience_roles).toBeTruthy()
  expect(generationConfig?.article_strategy).toBeTruthy()
})

test('navigating back and forward keeps the values entered on earlier steps', async () => {
  // 同一个根因的另一面：按步骤卸载表单时，回到第一步会重新挂载并丢失已填内容。
  const user = userEvent.setup()

  await renderTaskCreate()

  await user.type(screen.getByLabelText('关键词'), '机器人 商业化')
  await user.click(screen.getByRole('button', { name: '下一步' }))
  await screen.findByLabelText('受众角色')

  await user.click(screen.getByRole('button', { name: '上一步' }))

  expect(screen.getByLabelText('关键词')).toBeVisible()
  expect(screen.getByLabelText('关键词')).toHaveValue('机器人 商业化')

  await user.click(screen.getByRole('button', { name: '下一步' }))
  await user.click(await screen.findByRole('button', { name: '下一步' }))
  await user.click(await screen.findByRole('button', { name: '启动创作流程' }))

  await waitFor(() => {
    expect(createTaskMock).toHaveBeenCalledTimes(1)
  })
  const payload = createTaskMock.mock.calls[0][0] as { keywords: string }
  expect(payload.keywords).toBe('机器人 商业化')
})

test('submits the newsnow platforms by default, not an empty list', async () => {
  // The hotspot switch used to submit `platforms: []`, so the backend auto-discovered every
  // builtin platform and live-scraped the TopHub ones — the unreliable path. The picker now
  // defaults to the snapshot-backed newsnow entries.
  const user = userEvent.setup()

  await renderTaskCreate()

  await user.type(screen.getByLabelText('关键词'), '大模型')
  await user.click(screen.getByRole('button', { name: '下一步' }))
  await screen.findByLabelText('受众角色')
  await user.click(await screen.findByRole('button', { name: '下一步' }))
  await user.click(await screen.findByRole('button', { name: '启动创作流程' }))

  await waitFor(() => {
    expect(createTaskMock).toHaveBeenCalledTimes(1)
  })

  const payload = createTaskMock.mock.calls[0][0] as { hotspot_capture_config?: Record<string, unknown> }
  const hotspot = payload.hotspot_capture_config
  expect(hotspot).toBeTruthy()
  expect(hotspot?.enabled).toBe(true)

  const platforms = hotspot?.platforms as Array<Record<string, unknown>>
  expect(platforms.map((item) => item.path)).toEqual(['weibo', 'zhihu'])
  // `provider_id` and `source` must come from the catalogue, or a newsnow platform would be
  // silently downgraded to a TopHub path scrape.
  expect(platforms.every((item) => item.source === 'newsnow')).toBe(true)
  expect(platforms.every((item) => Boolean(item.provider_id))).toBe(true)
  expect(hotspot?.source).toBe('newsnow')
})

test('loads the hotspot catalogue once so the picker has options', async () => {
  await renderTaskCreate()

  await waitFor(() => {
    expect(getHotspotPlatformsMock).toHaveBeenCalled()
  })
})
