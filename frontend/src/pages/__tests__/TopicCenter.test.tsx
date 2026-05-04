import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import type { HotspotMonitorResponse, HotspotPlatformCatalogResponse } from '@/api'
import TopicCenter from '@/pages/TopicCenter'

const { captureHotspotMonitorMock, convertTopicToTaskMock, getHotspotMonitorMock, getHotspotPlatformsMock, ignoreTopicMock } = vi.hoisted(() => ({
  captureHotspotMonitorMock: vi.fn<() => Promise<HotspotMonitorResponse>>(),
  convertTopicToTaskMock: vi.fn(),
  getHotspotMonitorMock: vi.fn<() => Promise<HotspotMonitorResponse>>(),
  getHotspotPlatformsMock: vi.fn<() => Promise<HotspotPlatformCatalogResponse>>(),
  ignoreTopicMock: vi.fn(),
}))

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api')
  return {
    ...actual,
    captureHotspotMonitor: captureHotspotMonitorMock,
    convertTopicToTask: convertTopicToTaskMock,
    getHotspotMonitor: getHotspotMonitorMock,
    getHotspotPlatforms: getHotspotPlatformsMock,
    ignoreTopic: ignoreTopicMock,
  }
})

beforeEach(() => {
  vi.clearAllMocks()
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
  Object.defineProperty(window, 'getComputedStyle', {
    writable: true,
    value: () => ({
      getPropertyValue: () => '',
      overflow: 'visible',
      overflowX: 'visible',
      overflowY: 'visible',
    }),
  })
  getHotspotMonitorMock.mockResolvedValue(buildMonitorResponse())
  getHotspotPlatformsMock.mockResolvedValue(buildPlatformCatalogResponse())
  ignoreTopicMock.mockResolvedValue({
    topic_id: 'topic-1',
    source_cluster: [],
    title: 'AI 搜索产品进入新一轮竞争',
    angle: '',
    hot_score: 0,
    account_fit_score: 0,
    risk_score: 0,
    status: 'ignored',
    created_at: '2026-04-27T10:00:00Z',
  })
  convertTopicToTaskMock.mockResolvedValue({
    task_id: 'task-1',
    keywords: 'AI 搜索产品进入新一轮竞争',
    generation_config: {},
    status: 'pending',
    created_at: '2026-04-27T10:00:00Z',
    updated_at: null,
    error: null,
  })
  captureHotspotMonitorMock.mockResolvedValue(buildMonitorResponse())
})

function buildMonitorResponse(items = [{
  topic_id: 'topic-1',
  title: 'AI 搜索产品进入新一轮竞争',
  summary: 'AI 搜索正在重塑用户入口，内容生产需要更快响应。',
  source: '36氪',
  url: 'https://example.com/news',
  category: '科技',
  tags: ['AI', '搜索'],
  status: 'pending' as const,
  task_id: null,
  hot_score: 86,
  account_fit_score: 78,
  risk_score: 22,
  channel_count: 1,
  recommended: true,
  captured_at: '2026-04-27T10:00:00Z',
  updated_at: null,
  metadata: {},
}]): HotspotMonitorResponse {
  return {
    items,
    stats: {
      total: items.length,
      recommended: items.filter((item) => item.recommended).length,
      high_risk: items.filter((item) => item.risk_score >= 70).length,
      source_count: new Set(items.map((item) => item.source)).size,
      latest_captured_at: items[0]?.captured_at ?? null,
    },
    updated_at: '2026-04-27T10:00:00Z',
    capture_error: null,
  }
}

function buildPlatformCatalogResponse(): HotspotPlatformCatalogResponse {
  return {
    items: [
      { name: '36姘?', path: '/n/Q1Vd5Ko85R', category: '绉戞妧', weight: 1, enabled: true },
      { name: '鐭ヤ箮鐑', path: '/n/mproPpoq6O', category: 'AI', weight: 1, enabled: true },
    ],
    updated_at: '2026-04-27T10:00:00Z',
    source: 'tophub',
  }
}

test('renders hotspot cards and converts a recommended topic to task', async () => {
  const user = userEvent.setup()

  render(<TopicCenter />)

  expect(await screen.findByText('AI 搜索产品进入新一轮竞争')).toBeInTheDocument()
  expect(screen.getByText('推荐选题')).toBeInTheDocument()
  expect(screen.getByText('账号匹配')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: /立即生成文章/ }))

  await waitFor(() => {
    expect(convertTopicToTaskMock).toHaveBeenCalledWith('topic-1')
  })
})

test('captures hotspots through the monitor endpoint and refreshes the list', async () => {
  const user = userEvent.setup()

  render(<TopicCenter />)

  await screen.findByText('AI 搜索产品进入新一轮竞争')
  await user.click(screen.getByRole('button', { name: /立即抓取/ }))

  await waitFor(() => {
    expect(captureHotspotMonitorMock).toHaveBeenCalledWith(
      expect.objectContaining({
        keywords: '热点监控',
        hotspot_capture: expect.objectContaining({
          enabled: true,
          source: 'tophub',
          platforms: expect.arrayContaining([
            expect.objectContaining({ path: '/n/Q1Vd5Ko85R' }),
            expect.objectContaining({ path: '/n/mproPpoq6O' }),
          ]),
        }),
      }),
    )
  })
  expect(getHotspotMonitorMock).toHaveBeenCalledTimes(1)
})

test('renders empty state when backend returns no topics', async () => {
  getHotspotMonitorMock.mockResolvedValue(buildMonitorResponse([]))

  render(<TopicCenter />)

  expect(await screen.findByText('暂无热点候选')).toBeInTheDocument()
})
