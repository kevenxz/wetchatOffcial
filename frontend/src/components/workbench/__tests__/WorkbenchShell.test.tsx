import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import type { SearchResponse, TaskResponse } from '@/api'
import WorkbenchShell from '@/components/workbench/WorkbenchShell'
import useAuthStore from '@/store/authStore'
import { renderWithRouter } from '@/test/renderWithRouter'

const { listTasksMock, searchAllMock } = vi.hoisted(() => ({
  listTasksMock: vi.fn<() => Promise<TaskResponse[]>>(),
  searchAllMock: vi.fn<(query: string, limit?: number) => Promise<SearchResponse>>(),
}))

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api')
  return {
    ...actual,
    listTasks: listTasksMock,
    searchAll: searchAllMock,
  }
})

function taskFixture(overrides: Partial<TaskResponse>): TaskResponse {
  return {
    task_id: 'task-1',
    keywords: '主题一',
    generation_config: { audience_roles: ['开发者'], article_strategy: 'auto', style_hint: '' },
    status: 'done',
    created_at: '2026-04-12T00:00:00Z',
    updated_at: '2026-04-12T00:00:00Z',
    error: null,
    push_records: [],
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  listTasksMock.mockResolvedValue([])
  searchAllMock.mockResolvedValue({ tasks: [], articles: [], topics: [] })

  useAuthStore.setState({
    token: 'test-token',
    user: {
      user_id: 'u-1',
      username: 'admin',
      display_name: '管理员',
      role: 'admin',
      enabled: true,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: null,
      last_login_at: null,
    },
    initialized: true,
  })

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

test('renders the AI content factory shell for task management', () => {
  renderWithRouter(<WorkbenchShell />, { route: '/task' })

  expect(screen.getByText('AI 内容工厂')).toBeInTheDocument()
  expect(screen.getByText('智能公众号生产系统')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '任务管理' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '任务管理' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '数据看板' })).toHaveAttribute('href', '/stats')
  expect(screen.getByRole('link', { name: '定时计划' })).toHaveAttribute('href', '/schedules')
  expect(screen.getByRole('link', { name: '工作台' })).toHaveAttribute('href', '/history')
})

test('keeps system accounts as a standalone navigation entry', () => {
  renderWithRouter(<WorkbenchShell />, { route: '/task' })

  const systemAccountLink = screen.getByRole('link', { name: '系统账号' })

  expect(systemAccountLink).toHaveAttribute('href', '/users')
  expect(screen.queryByRole('link', { name: '系统管理' })).not.toBeInTheDocument()
})

test('searches tasks, articles and topics with a debounced query', async () => {
  const user = userEvent.setup()
  searchAllMock.mockResolvedValue({
    tasks: [taskFixture({ task_id: 'task-a', keywords: 'Agentic AI 任务' })],
    articles: [taskFixture({ task_id: 'task-b', keywords: 'Agentic AI 文章' })],
    topics: [
      {
        topic_id: 'topic-1',
        title: 'Agentic AI 热点',
        status: 'pending',
      },
    ],
  })

  renderWithRouter(<WorkbenchShell />, { route: '/task' })

  await user.type(screen.getByPlaceholderText('搜索文章、任务、热点...'), 'Agentic')

  await waitFor(() => {
    expect(searchAllMock).toHaveBeenCalledWith('Agentic')
  })

  expect(await screen.findByText('任务（1）')).toBeInTheDocument()
  expect(screen.getByText('文章（1）')).toBeInTheDocument()
  expect(screen.getByText('热点（1）')).toBeInTheDocument()
  expect(screen.getByText('Agentic AI 任务')).toBeInTheDocument()
  expect(screen.getByText('Agentic AI 文章')).toBeInTheDocument()
  expect(screen.getByText('Agentic AI 热点')).toBeInTheDocument()
})

test('clears the search results when the query is emptied', async () => {
  const user = userEvent.setup()
  searchAllMock.mockResolvedValue({
    tasks: [taskFixture({ task_id: 'task-a', keywords: 'Agentic AI 任务' })],
    articles: [],
    topics: [],
  })

  renderWithRouter(<WorkbenchShell />, { route: '/task' })

  const input = screen.getByPlaceholderText('搜索文章、任务、热点...')
  await user.type(input, 'Agentic')
  expect(await screen.findByText('Agentic AI 任务')).toBeInTheDocument()

  await user.clear(input)

  await waitFor(() => {
    expect(screen.getByPlaceholderText('搜索文章、任务、热点...')).toHaveValue('')
  })
  // An empty query must not trigger another search request.
  expect(searchAllMock).toHaveBeenCalledTimes(1)
})

test('shows the pending review and failed task count on the notification bell', async () => {
  listTasksMock.mockResolvedValue([
    taskFixture({ task_id: 'task-review', human_review_required: true }),
    taskFixture({ task_id: 'task-failed', status: 'failed' }),
    taskFixture({ task_id: 'task-done', status: 'done' }),
  ])

  renderWithRouter(<WorkbenchShell />, { route: '/task' })

  expect(await screen.findByText('2')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '通知' })).toBeInTheDocument()
})
