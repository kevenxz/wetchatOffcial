import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import type { TaskResponse } from '@/api'
import History from '@/pages/History'

const { listTasksMock, deleteTaskMock } = vi.hoisted(() => ({
  listTasksMock: vi.fn<() => Promise<TaskResponse[]>>(),
  deleteTaskMock: vi.fn(),
}))

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api')
  return {
    ...actual,
    listTasks: listTasksMock,
    deleteTask: deleteTaskMock,
  }
})

beforeEach(() => {
  vi.clearAllMocks()
  listTasksMock.mockResolvedValue([])
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

  const originalGetComputedStyle = window.getComputedStyle.bind(window)
  Object.defineProperty(window, 'getComputedStyle', {
    writable: true,
    value: (element: Element) => originalGetComputedStyle(element),
  })
})

test('renders the history page with paginated card history', async () => {
  listTasksMock.mockResolvedValue(
    Array.from({ length: 9 }, (_, index) => ({
      task_id: `task-${index}`,
      keywords: `task-${index}`,
      generation_config: {
        audience_roles: ['开发者'],
        article_strategy: 'auto',
        style_hint: '',
      },
      status: 'done',
      created_at: '2026-04-12T00:00:00Z',
      updated_at: '2026-04-12T00:00:00Z',
      error: null,
      push_records: [],
    })),
  )

  render(
    <MemoryRouter
      initialEntries={['/history']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/history" element={<History />} />
      </Routes>
    </MemoryRouter>,
  )

  expect(await screen.findByText('内容资产')).toBeInTheDocument()
  expect(screen.getByText('卡片视图')).toBeInTheDocument()
  expect(screen.getByText('task-0')).toBeInTheDocument()
  expect(screen.queryByText('task-8')).not.toBeInTheDocument()
})
