import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import type { StyleConfig, TaskResponse } from '@/api'
import ArticleManage from '@/pages/ArticleManage'

const {
  deleteTaskMock,
  getCustomThemesMock,
  getPresetThemesMock,
  getStyleConfigMock,
  listArticlesMock,
} = vi.hoisted(() => ({
  deleteTaskMock: vi.fn(),
  getCustomThemesMock: vi.fn<() => Promise<Record<string, StyleConfig>>>(),
  getPresetThemesMock: vi.fn<() => Promise<Record<string, StyleConfig>>>(),
  getStyleConfigMock: vi.fn<() => Promise<StyleConfig>>(),
  listArticlesMock: vi.fn<() => Promise<TaskResponse[]>>(),
}))

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api')
  return {
    ...actual,
    deleteTask: deleteTaskMock,
    getCustomThemes: getCustomThemesMock,
    getPresetThemes: getPresetThemesMock,
    getStyleConfig: getStyleConfigMock,
    listArticles: listArticlesMock,
  }
})

beforeEach(() => {
  vi.clearAllMocks()
  listArticlesMock.mockResolvedValue([])
  getStyleConfigMock.mockResolvedValue({})
  getPresetThemesMock.mockResolvedValue({})
  getCustomThemesMock.mockResolvedValue({})
  deleteTaskMock.mockResolvedValue(undefined)

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
