import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import type { TopicCandidate } from '@/api'
import TopicCenter from '@/pages/TopicCenter'

const { convertTopicToTaskMock, ignoreTopicMock, listTopicsMock } = vi.hoisted(() => ({
  convertTopicToTaskMock: vi.fn(),
  ignoreTopicMock: vi.fn(),
  listTopicsMock: vi.fn<() => Promise<TopicCandidate[]>>(),
}))

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api')
  return {
    ...actual,
    convertTopicToTask: convertTopicToTaskMock,
    ignoreTopic: ignoreTopicMock,
    listTopics: listTopicsMock,
  }
})

beforeEach(() => {
  vi.clearAllMocks()
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
  Object.defineProperty(window, 'getComputedStyle', {
    writable: true,
    value: () => ({
      getPropertyValue: () => '',
      overflow: 'visible',
      overflowX: 'visible',
      overflowY: 'visible',
    }),
  })
  listTopicsMock.mockResolvedValue([
    {
      topic_id: 'topic-1',
      source_cluster: ['https://example.com/news'],
      title: 'AI 搜索产品进入新一轮竞争',
      angle: '从用户入口变化看内容生产机会',
      hot_score: 86,
      account_fit_score: 78,
      risk_score: 22,
      status: 'pending',
      source: 'tophub',
      category: '科技',
    },
  ])
  ignoreTopicMock.mockResolvedValue({
    topic_id: 'topic-1',
    source_cluster: [],
    title: 'AI 搜索产品进入新一轮竞争',
    angle: '',
    hot_score: 0,
    account_fit_score: 0,
    risk_score: 0,
    status: 'ignored',
  })
  convertTopicToTaskMock.mockResolvedValue({ topic: {}, task: {} })
})

test('renders topic candidates and triggers ignore action', async () => {
  const user = userEvent.setup()

  render(<TopicCenter />)

  expect(await screen.findByText('AI 搜索产品进入新一轮竞争')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /忽略/ })).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: /忽略/ }))

  await waitFor(() => {
    expect(ignoreTopicMock).toHaveBeenCalledWith('topic-1')
  })
})

test('renders empty state when backend returns no topics', async () => {
  listTopicsMock.mockResolvedValue([])

  render(<TopicCenter />)

  expect(await screen.findByText('暂无候选选题')).toBeInTheDocument()
})
