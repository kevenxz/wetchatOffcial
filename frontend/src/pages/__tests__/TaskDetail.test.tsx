import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import type { TaskResponse } from '@/api'
import TaskDetail from '@/pages/TaskDetail'
import { renderWithRouter } from '@/test/renderWithRouter'

const { getTaskMock, retryTaskMock } = vi.hoisted(() => ({
  getTaskMock: vi.fn<() => Promise<TaskResponse>>(),
  retryTaskMock: vi.fn(),
}))

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api')
  return {
    ...actual,
    getTask: getTaskMock,
    retryTask: retryTaskMock,
  }
})

class MockWebSocket {
  static instances: MockWebSocket[] = []

  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent<string>) => void) | null = null
  onclose: (() => void) | null = null

  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }

  close() {
    this.onclose?.()
  }
}

const demoTask: TaskResponse = {
  task_id: 'demo-id',
  keywords: 'Agentic AI',
  original_keywords: 'Agentic AI',
  generation_config: {
    audience_roles: ['Developer'],
    article_strategy: 'auto',
    style_hint: '',
  },
  status: 'running',
  created_at: '2026-04-11T12:00:00Z',
  updated_at: '2026-04-11T12:00:00Z',
  error: null,
  article_plan: {
    resolved_strategy: 'auto',
    resolved_strategy_label: 'Auto',
  },
}

beforeEach(() => {
  vi.clearAllMocks()
  MockWebSocket.instances = []
  getTaskMock.mockResolvedValue(demoTask)
  retryTaskMock.mockResolvedValue(demoTask)

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

  vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
  window.history.replaceState({}, '', '/task/demo-id')
})

test('renders a compact task detail header and sectioned detail blocks', async () => {
  renderWithRouter(
    <Routes>
      <Route path="/task/:id" element={<TaskDetail />} />
    </Routes>,
    { route: '/task/demo-id' },
  )

  expect(await screen.findByRole('heading', { name: 'Agentic AI' })).toBeInTheDocument()
  expect(screen.getByRole('toolbar', { name: '任务操作' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '执行轨道' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '任务信息' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '结构信号' })).toBeInTheDocument()
})
