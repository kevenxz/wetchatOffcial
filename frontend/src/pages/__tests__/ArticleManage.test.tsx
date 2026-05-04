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
} = vi.hoisted(() => ({
  deleteTaskMock: vi.fn(),
  getCustomThemesMock: vi.fn<() => Promise<Record<string, StyleConfig>>>(),
  getPresetThemesMock: vi.fn<() => Promise<Record<string, StyleConfig>>>(),
  getStyleConfigMock: vi.fn<() => Promise<StyleConfig>>(),
  listAccountsMock: vi.fn<() => Promise<AccountConfig[]>>(),
  listArticlesMock: vi.fn<() => Promise<TaskResponse[]>>(),
  pushArticleMock: vi.fn(),
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
    expect(pushArticleMock).toHaveBeenCalledWith('article-1', ['wechat-1'], '__current__')
  })
})
