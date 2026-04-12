import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import type { ModelConfig, TaskResponse } from '@/api'
import History from '@/pages/History'
import ModelConfigPage from '@/pages/ModelConfig'

const { listTasksMock, deleteTaskMock, getModelConfigMock, updateModelConfigMock } = vi.hoisted(() => ({
  listTasksMock: vi.fn<() => Promise<TaskResponse[]>>(),
  deleteTaskMock: vi.fn(),
  getModelConfigMock: vi.fn<() => Promise<ModelConfig>>(),
  updateModelConfigMock: vi.fn(),
}))

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api')
  return {
    ...actual,
    listTasks: listTasksMock,
    deleteTask: deleteTaskMock,
    getModelConfig: getModelConfigMock,
    updateModelConfig: updateModelConfigMock,
  }
})

beforeEach(() => {
  vi.clearAllMocks()
  listTasksMock.mockResolvedValue([])
  deleteTaskMock.mockResolvedValue(undefined)
  getModelConfigMock.mockResolvedValue({
    text: {
      api_key: '',
      base_url: '',
      model: 'gpt-4o',
    },
    image: {
      enabled: false,
      api_key: '',
      base_url: '',
      model: 'dall-e-3',
    },
  })
  updateModelConfigMock.mockResolvedValue({
    text: {
      api_key: '',
      base_url: '',
      model: 'gpt-4o',
    },
    image: {
      enabled: false,
      api_key: '',
      base_url: '',
      model: 'dall-e-3',
    },
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

test('renders the model backstage page with readable shared copy', async () => {
  render(<ModelConfigPage />)

  expect(await screen.findByText('模型接入台')).toBeInTheDocument()
  expect(screen.getByText('统一管理文本与图像模型的密钥、网关和默认型号。')).toBeInTheDocument()
  expect(screen.getByText('文本生成模型')).toBeInTheDocument()
  expect(screen.queryByText(/鍔犺浇|妯″瀷|閰嶇疆/)).not.toBeInTheDocument()
})
