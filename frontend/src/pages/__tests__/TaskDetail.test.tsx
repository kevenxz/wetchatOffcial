import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import type { TaskResponse } from '@/api'
import TaskDetail from '@/pages/TaskDetail'
import statusRailStylesSource from '@/components/workbench/StatusRail.module.css?inline'
import taskDetailStylesSource from '@/pages/TaskDetail.module.css?inline'
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
  expect(screen.getByRole('heading', { name: '执行轨迹' })).toBeInTheDocument()
  expect(screen.getByRole('complementary', { name: '执行轨道' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '任务信息' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '发布状态' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '开发者诊断' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /编\s*辑\s*文\s*章/ })).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: '结构信号' })).not.toBeInTheDocument()
})

test('offers task cancellation while the task is still running', async () => {
  getTaskMock.mockResolvedValue({
    ...demoTask,
    status: 'queued',
    push_records: [
      {
        push_id: 'p-1',
        account_id: 'a-1',
        account_name: '测试公众号',
        platform: 'wechat_mp',
        pushed_at: '2026-04-11T12:30:00Z',
        status: 'success',
        publish_status: 'publishing',
        publish_id: 'pub-9',
        theme_name: '__current__',
        attempt: 1,
        draft_info: { url: 'https://mp.weixin.qq.com/s/demo' },
      },
    ],
  })

  renderWithRouter(
    <Routes>
      <Route path="/task/:id" element={<TaskDetail />} />
    </Routes>,
    { route: '/task/demo-id' },
  )

  expect(await screen.findByText('测试公众号')).toBeInTheDocument()
  expect(screen.getByText('发布中')).toBeInTheDocument()
  expect(screen.getByText('pub-9')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '查看草稿' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /取\s*消\s*任\s*务/ })).toBeInTheDocument()
})

test('uses light-theme surfaces for execution trace sections instead of hard-coded dark panels', () => {
  expect(statusRailStylesSource).toContain('var(--app-surface)')
  expect(statusRailStylesSource).toContain('var(--app-surface-muted)')
  expect(statusRailStylesSource).toContain('var(--app-border)')
  expect(statusRailStylesSource).not.toContain('rgba(15, 23, 42, 0.88)')
  expect(statusRailStylesSource).not.toContain('background: rgba(2, 6, 23, 0.36)')

  // TaskDetail now uses the semantic token layer; StatusRail is still on the legacy
  // aliases, so its assertions still reference those names.
  expect(taskDetailStylesSource).toContain('background: var(--surface-raised);')
  expect(taskDetailStylesSource).toContain('background: var(--surface-sunken);')
  expect(taskDetailStylesSource).toContain('color: var(--text-secondary);')
  expect(taskDetailStylesSource).not.toContain('background: rgba(15, 23, 42, 0.62);')
  expect(taskDetailStylesSource).not.toContain('background: rgba(2, 6, 23, 0.26);')
})
