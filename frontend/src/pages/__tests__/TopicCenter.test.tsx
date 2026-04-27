import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import type { HotspotPreviewResponse, TopicCandidate } from '@/api'
import TopicCenter from '@/pages/TopicCenter'

const { convertTopicToTaskMock, ignoreTopicMock, listTopicsMock, previewHotspotsMock } = vi.hoisted(() => ({
  convertTopicToTaskMock: vi.fn(),
  ignoreTopicMock: vi.fn(),
  listTopicsMock: vi.fn<() => Promise<TopicCandidate[]>>(),
  previewHotspotsMock: vi.fn<() => Promise<HotspotPreviewResponse>>(),
}))

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api')
  return {
    ...actual,
    convertTopicToTask: convertTopicToTaskMock,
    ignoreTopic: ignoreTopicMock,
    listTopics: listTopicsMock,
    previewHotspots: previewHotspotsMock,
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
      summary: 'AI 搜索正在重塑用户入口，内容生产需要更快响应。',
      angle: '从用户入口变化看内容生产机会',
      hot_score: 86,
      account_fit_score: 78,
      risk_score: 22,
      status: 'pending',
      source: '36氪',
      category: '科技',
      tags: ['AI', '搜索'],
      created_at: '2026-04-27T10:00:00Z',
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
    created_at: '2026-04-27T10:00:00Z',
  })
  convertTopicToTaskMock.mockResolvedValue({
    task_id: 'task-1',
    keywords: 'AI 搜索产品进入新一轮竞争',
    generation_config: {},
    status: 'pending',
    created_at: '2026-04-27T10:00:00Z',
    updated_at: null,
    error: null,
  })
  previewHotspotsMock.mockResolvedValue({
    keywords: '热点监控',
    original_keywords: '热点监控',
    hotspot_capture_config: {
      enabled: true,
      source: 'tophub',
      categories: ['科技'],
      platforms: [],
      filters: {
        top_n_per_platform: 10,
        min_selection_score: 45,
        exclude_keywords: [],
        prefer_keywords: [],
      },
      fallback_topics: [],
    },
    hotspot_candidates: [],
    selected_hotspot: null,
    hotspot_capture_error: null,
  })
})

test('renders hotspot cards and converts a recommended topic to task', async () => {
  const user = userEvent.setup()

  render(<TopicCenter />)

  expect(await screen.findByText('AI 搜索产品进入新一轮竞争')).toBeInTheDocument()
  expect(screen.getByText('推荐选题')).toBeInTheDocument()
  expect(screen.getByText('账号匹配')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: /立即生成文章/ }))

  await waitFor(() => {
    expect(convertTopicToTaskMock).toHaveBeenCalledWith('topic-1')
  })
})

test('captures hotspots through the preview endpoint and refreshes the list', async () => {
  const user = userEvent.setup()

  render(<TopicCenter />)

  await screen.findByText('AI 搜索产品进入新一轮竞争')
  await user.click(screen.getByRole('button', { name: /立即抓取/ }))

  await waitFor(() => {
    expect(previewHotspotsMock).toHaveBeenCalledWith(
      expect.objectContaining({
        keywords: '热点监控',
        hotspot_capture: expect.objectContaining({ enabled: true, source: 'tophub' }),
      }),
    )
  })
  expect(listTopicsMock).toHaveBeenCalledTimes(2)
})

test('renders empty state when backend returns no topics', async () => {
  listTopicsMock.mockResolvedValue([])

  render(<TopicCenter />)

  expect(await screen.findByText('暂无热点候选')).toBeInTheDocument()
})
