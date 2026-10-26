import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import type { AccountConfig, StyleConfig, TaskResponse } from '@/api'
import ArticleManage from '@/pages/ArticleManage'

const {
  deleteTaskMock,
  getCustomThemesMock,
  getPresetThemesMock,
  getStyleConfigMock,
  listAccountsMock,
  listArticlesMock,
  pushArticleMock,
  updateArticleContentMock,
} = vi.hoisted(() => ({
  deleteTaskMock: vi.fn(),
  getCustomThemesMock: vi.fn<() => Promise<Record<string, StyleConfig>>>(),
  getPresetThemesMock: vi.fn<() => Promise<Record<string, StyleConfig>>>(),
  getStyleConfigMock: vi.fn<() => Promise<StyleConfig>>(),
  listAccountsMock: vi.fn<() => Promise<AccountConfig[]>>(),
  listArticlesMock: vi.fn<() => Promise<TaskResponse[]>>(),
  pushArticleMock: vi.fn(),
  updateArticleContentMock: vi.fn(),
}))

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api')
  return {
    ...actual,
    deleteTask: deleteTaskMock,
    getCustomThemes: getCustomThemesMock,
    getPresetThemes: getPresetThemesMock,
    getStyleConfig: getStyleConfigMock,
    listAccounts: listAccountsMock,
    listArticles: listArticlesMock,
    pushArticle: pushArticleMock,
    updateArticleContent: updateArticleContentMock,
  }
})

beforeEach(() => {
  vi.clearAllMocks()
  listArticlesMock.mockResolvedValue([])
  getStyleConfigMock.mockResolvedValue({})
  getPresetThemesMock.mockResolvedValue({})
  getCustomThemesMock.mockResolvedValue({})
  listAccountsMock.mockResolvedValue([])
  deleteTaskMock.mockResolvedValue(undefined)
  pushArticleMock.mockResolvedValue({ total: 1, success: 1, failed: 0, results: [] })
  updateArticleContentMock.mockResolvedValue(undefined)

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

  const originalGetComputedStyle = window.getComputedStyle.bind(window)
  Object.defineProperty(window, 'getComputedStyle', {
    writable: true,
    value: (element: Element) => originalGetComputedStyle(element),
  })
})

function mockArticleList() {
  listArticlesMock.mockResolvedValue([
    {
      task_id: 'article-1',
      keywords: '增长,发布',
      generated_article: {
        title: '首篇文章',
        summary: '本文从技术参数和市场影响解读文章生成链路。',
        content: '# 首篇文章\n\n这是一段预览内容。',
        illustrations: ['generated://skip'],
      },
      generation_config: {
        audience_roles: ['编辑'],
        article_strategy: 'tech_breakdown',
        style_hint: '',
        account_profile: {
          positioning: '',
          target_readers: [],
          fit_tags: ['科技'],
          avoid_topics: [],
        },
      },
      status: 'done',
      created_at: '2026-04-12T00:00:00Z',
      updated_at: '2026-04-12T00:00:00Z',
      error: null,
      article_theme: '__current__',
      push_records: [{ push_id: 'p-1', account_id: 'a-1', account_name: '公众号', platform: 'wechat_mp', pushed_at: '2026-04-12T01:00:00Z', status: 'success' }],
    },
  ])
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
}

function renderArticleManage() {
  return render(
    <MemoryRouter
      initialEntries={['/articles']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/articles" element={<ArticleManage />} />
      </Routes>
    </MemoryRouter>,
  )
}

test('renders content cards without export action and keeps preview available', async () => {
  const user = userEvent.setup()
  mockArticleList()

  renderArticleManage()

  expect(await screen.findByText('首篇文章')).toBeInTheDocument()
  expect(screen.getByText('A-1024')).toBeInTheDocument()
  expect(screen.getAllByText('已发布').length).toBeGreaterThan(0)
  expect(screen.queryByRole('button', { name: /导出/ })).not.toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: '预览文章' }))

  const dialog = await screen.findByRole('dialog')
  expect(dialog).toBeInTheDocument()
  expect(within(dialog).getByRole('heading', { name: '首篇文章' })).toBeInTheDocument()
  expect(within(dialog).getByText('这是一段预览内容。')).toBeInTheDocument()
})

test('filters articles by status and keyword', async () => {
  mockArticleList()
  renderArticleManage()

  expect(await screen.findByText('首篇文章')).toBeInTheDocument()

  await userEvent.type(screen.getByPlaceholderText('搜索文章...'), '不存在')

  await waitFor(() => {
    expect(screen.getByText('暂无文章')).toBeInTheDocument()
  })
})

test('pushes an article to the selected wechat draft box', async () => {
  const user = userEvent.setup()
  mockArticleList()

  renderArticleManage()

  expect(await screen.findByText('首篇文章')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: '推送到公众号草稿箱' }))

  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByText('指定推送到微信公众号草稿箱')).toBeInTheDocument()
  expect(within(dialog).getByText('测试公众号')).toBeInTheDocument()

  await user.click(within(dialog).getByRole('button', { name: '推送到草稿箱' }))

  await waitFor(() => {
    expect(pushArticleMock).toHaveBeenCalledWith('article-1', ['wechat-1'], '__current__', false)
  })
})

test('publishes directly to the official account when the switch is enabled', async () => {
  const user = userEvent.setup()
  mockArticleList()

  renderArticleManage()

  expect(await screen.findByText('首篇文章')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: '推送到公众号草稿箱' }))

  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).queryByText('该操作不可撤回')).not.toBeInTheDocument()

  await user.click(within(dialog).getByRole('switch'))

  expect(await within(dialog).findByText('该操作不可撤回')).toBeInTheDocument()

  await user.click(within(dialog).getByRole('button', { name: '直接发布到公众号' }))

  await waitFor(() => {
    expect(pushArticleMock).toHaveBeenCalledWith('article-1', ['wechat-1'], '__current__', true)
  })
})

test('edits the article content inline and saves it through the api', async () => {
  const user = userEvent.setup()
  mockArticleList()

  renderArticleManage()

  expect(await screen.findByText('首篇文章')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: '编辑文章' }))

  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByText('编辑文章内容')).toBeInTheDocument()

  const titleInput = within(dialog).getByLabelText('标题')
  expect(titleInput).toHaveValue('首篇文章')

  await user.clear(titleInput)
  await user.type(titleInput, '修改后的标题')
  await user.clear(within(dialog).getByLabelText('摘要'))
  await user.type(within(dialog).getByLabelText('摘要'), '修改后的摘要')

  await user.click(within(dialog).getByRole('button', { name: '添加插图' }))
  const illustrationInput = within(dialog).getByLabelText('插图 1')
  await user.clear(illustrationInput)
  await user.type(illustrationInput, 'https://cdn.example.com/one.png')

  await user.click(within(dialog).getByRole('button', { name: /保\s*存/ }))

  await waitFor(() => {
    expect(updateArticleContentMock).toHaveBeenCalledWith('article-1', {
      title: '修改后的标题',
      summary: '修改后的摘要',
      content: '# 首篇文章\n\n这是一段预览内容。',
      cover_image: '',
      illustrations: ['https://cdn.example.com/one.png'],
    })
  })
})
