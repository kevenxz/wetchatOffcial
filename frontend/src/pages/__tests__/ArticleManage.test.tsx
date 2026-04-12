import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import type { AccountConfig, StyleConfig, TaskResponse } from '@/api'
import ArticleManage from '@/pages/ArticleManage'

const {
  batchPushArticlesMock,
  getCustomThemesMock,
  getPresetThemesMock,
  getStyleConfigMock,
  listAccountsMock,
  listArticlesMock,
  pushArticleMock,
  updateArticleThemeMock,
} = vi.hoisted(() => ({
  batchPushArticlesMock: vi.fn(),
  getCustomThemesMock: vi.fn<() => Promise<Record<string, StyleConfig>>>(),
  getPresetThemesMock: vi.fn<() => Promise<Record<string, StyleConfig>>>(),
  getStyleConfigMock: vi.fn<() => Promise<StyleConfig>>(),
  listAccountsMock: vi.fn<() => Promise<AccountConfig[]>>(),
  listArticlesMock: vi.fn<() => Promise<TaskResponse[]>>(),
  pushArticleMock: vi.fn(),
  updateArticleThemeMock: vi.fn(),
}))

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api')
  return {
    ...actual,
    batchPushArticles: batchPushArticlesMock,
    getCustomThemes: getCustomThemesMock,
    getPresetThemes: getPresetThemesMock,
    getStyleConfig: getStyleConfigMock,
    listAccounts: listAccountsMock,
    listArticles: listArticlesMock,
    pushArticle: pushArticleMock,
    updateArticleTheme: updateArticleThemeMock,
  }
})

beforeEach(() => {
  vi.clearAllMocks()
  listArticlesMock.mockResolvedValue([])
  listAccountsMock.mockResolvedValue([])
  getStyleConfigMock.mockResolvedValue({})
  getPresetThemesMock.mockResolvedValue({})
  getCustomThemesMock.mockResolvedValue({})
  batchPushArticlesMock.mockResolvedValue({ total: 0, success: 0, failed: 0, results: [] })
  pushArticleMock.mockResolvedValue({ total: 0, success: 0, failed: 0, results: [] })
  updateArticleThemeMock.mockImplementation(async (taskId: string, themeName: string) => ({
    task_id: taskId,
    keywords: '',
    generation_config: {
      audience_roles: [],
      article_strategy: 'auto',
      style_hint: '',
    },
    status: 'done',
    created_at: '2026-04-12T00:00:00Z',
    updated_at: '2026-04-12T00:00:00Z',
    error: null,
    article_theme: themeName,
  }))

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

test('renders a list-first article workspace with inline preview', async () => {
  const user = userEvent.setup()
  const originalInnerWidth = window.innerWidth

  Object.defineProperty(window, 'innerWidth', {
    writable: true,
    value: 900,
  })

  listArticlesMock.mockResolvedValue([
    {
      task_id: 'article-1',
      keywords: '增长,发布',
      generated_article: {
        title: '首篇文章',
        content: '# 首篇文章\n\n这是一段预览内容。',
      },
      generation_config: {
        audience_roles: ['编辑'],
        article_strategy: 'auto',
        style_hint: '',
      },
      status: 'done',
      created_at: '2026-04-12T00:00:00Z',
      updated_at: '2026-04-12T00:00:00Z',
      error: null,
      article_theme: '__current__',
      push_records: [],
    },
  ])

  render(
    <MemoryRouter
      initialEntries={['/articles']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/articles" element={<ArticleManage />} />
      </Routes>
    </MemoryRouter>,
  )

  expect(await screen.findByRole('heading', { name: '文章库' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '批量推送' })).toBeInTheDocument()
  expect(screen.getByText('文章标题')).toBeInTheDocument()
  expect(screen.getByText('选择一篇文章查看预览', { selector: '.ant-empty-description' })).toBeInTheDocument()
  expect(screen.getByTestId('article-manage-grid')).toHaveStyle({ gridTemplateColumns: 'minmax(0, 1fr)' })

  await user.click(screen.getByRole('button', { name: /查\s*看/ }))

  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '文章预览' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { level: 4, name: '首篇文章' })).toBeInTheDocument()
  expect(screen.getByText('这是一段预览内容。')).toBeInTheDocument()

  Object.defineProperty(window, 'innerWidth', {
    writable: true,
    value: originalInnerWidth,
  })
})
