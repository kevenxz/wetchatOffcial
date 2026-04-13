import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, afterEach, expect, test, vi } from 'vitest'
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

let originalInnerWidth = window.innerWidth

beforeEach(() => {
  vi.clearAllMocks()
  originalInnerWidth = window.innerWidth
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

afterEach(() => {
  Object.defineProperty(window, 'innerWidth', {
    writable: true,
    value: originalInnerWidth,
  })
})

function mockArticleList() {
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

test('renders narrow layout on the first paint', async () => {
  const user = userEvent.setup()
  Object.defineProperty(window, 'innerWidth', {
    writable: true,
    value: 900,
  })
  mockArticleList()

  renderArticleManage()

  expect(screen.getByTestId('article-manage-grid')).toHaveStyle({ gridTemplateColumns: 'minmax(0, 1fr)' })
  expect(await screen.findByRole('heading', { name: '文章库' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '批量推送' })).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: /查\s*看/ }))

  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '文章预览' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { level: 4, name: '首篇文章' })).toBeInTheDocument()
  expect(screen.getByText('这是一段预览内容。')).toBeInTheDocument()
})

test('updates the grid when the viewport resizes', async () => {
  mockArticleList()
  Object.defineProperty(window, 'innerWidth', {
    writable: true,
    value: 1400,
  })

  renderArticleManage()

  expect(screen.getByTestId('article-manage-grid')).toHaveStyle({
    gridTemplateColumns: 'minmax(0, 1.4fr) minmax(320px, 0.9fr)',
  })

  await act(async () => {
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      value: 900,
    })
    window.dispatchEvent(new Event('resize'))
  })

  await waitFor(() => {
    expect(screen.getByTestId('article-manage-grid')).toHaveStyle({ gridTemplateColumns: 'minmax(0, 1fr)' })
  })

  await act(async () => {
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      value: 1400,
    })
    window.dispatchEvent(new Event('resize'))
  })

  await waitFor(() => {
    expect(screen.getByTestId('article-manage-grid')).toHaveStyle({
      gridTemplateColumns: 'minmax(0, 1.4fr) minmax(320px, 0.9fr)',
    })
  })
})
