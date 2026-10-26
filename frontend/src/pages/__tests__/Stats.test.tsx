import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import type {
  ArticleStats,
  StatsArticlesResponse,
  StatsOverview,
  UpdateArticleStatsRequest,
} from '@/api'
import Stats from '@/pages/Stats'

const {
  getArticleStatsMock,
  getStatsArticlesMock,
  getStatsOverviewMock,
  syncArticleStatsMock,
  updateArticleStatsMock,
} = vi.hoisted(() => ({
  getArticleStatsMock: vi.fn<(taskId: string) => Promise<ArticleStats>>(),
  getStatsArticlesMock: vi.fn<(range: 7 | 30) => Promise<StatsArticlesResponse>>(),
  getStatsOverviewMock: vi.fn<() => Promise<StatsOverview>>(),
  syncArticleStatsMock: vi.fn(),
  updateArticleStatsMock:
    vi.fn<(taskId: string, payload: UpdateArticleStatsRequest) => Promise<ArticleStats>>(),
}))

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api')
  return {
    ...actual,
    getArticleStats: getArticleStatsMock,
    getStatsArticles: getStatsArticlesMock,
    getStatsOverview: getStatsOverviewMock,
    syncArticleStats: syncArticleStatsMock,
    updateArticleStats: updateArticleStatsMock,
  }
})

const overview: StatsOverview = {
  total_articles: 42,
  total_published: 18,
  total_drafts: 24,
  total_reads: 12345,
  total_shares: 321,
  total_collects: 456,
  total_likes: 789,
}

function articlesFor(range: 7 | 30): StatsArticlesResponse {
  return {
    range_days: range,
    trend: [
      { date: '2026-09-01', published: 2, reads: 1200 },
      { date: '2026-09-02', published: 3, reads: 2400 },
      { date: '2026-09-03', published: 1, reads: 900 },
    ],
    top_articles: [
      {
        task_id: 'task-alpha',
        title: 'Alpha 深度解读',
        reads: 8800,
        shares: 210,
        collects: 130,
        likes: 96,
        published_at: '2026-09-02T08:00:00Z',
      },
      {
        task_id: 'task-beta',
        title: 'Beta 趋势观察',
        reads: 4200,
        shares: 80,
        collects: 60,
        likes: 40,
        published_at: null,
      },
    ],
  }
}

function articleStats(taskId: string): ArticleStats {
  return {
    task_id: taskId,
    article_id: `article-${taskId}`,
    title: 'Alpha 深度解读',
    published_at: '2026-09-02T08:00:00Z',
    read_num: 8800,
    like_num: 96,
    share_num: 210,
    collect_num: 130,
    fav_num: 12,
    source: 'manual',
    updated_at: '2026-09-03T00:00:00Z',
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  getStatsOverviewMock.mockResolvedValue(overview)
  getStatsArticlesMock.mockImplementation((range) => Promise.resolve(articlesFor(range)))
  getArticleStatsMock.mockImplementation((taskId) => Promise.resolve(articleStats(taskId)))
  syncArticleStatsMock.mockResolvedValue({ synced: 3, failed: 1, message: '同步完成：成功 3，失败 1' })
  updateArticleStatsMock.mockImplementation((taskId) => Promise.resolve(articleStats(taskId)))

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

test('renders the overview cards and the top-articles ranking from the API', async () => {
  render(<Stats />)

  expect(await screen.findByText('累计文章')).toBeInTheDocument()
  expect(screen.getByText('累计发布')).toBeInTheDocument()
  expect(screen.getByText('累计草稿')).toBeInTheDocument()
  expect(screen.getByText('总阅读')).toBeInTheDocument()
  expect(screen.getByText('总分享')).toBeInTheDocument()
  expect(screen.getByText('总收藏')).toBeInTheDocument()
  expect(screen.getByText('总点赞')).toBeInTheDocument()

  expect(await screen.findByText('42')).toBeInTheDocument()
  expect(screen.getByText('18')).toBeInTheDocument()
  expect(screen.getByText('12,345')).toBeInTheDocument()

  const ranking = screen.getByRole('table')
  expect(within(ranking).getByText('Alpha 深度解读')).toBeInTheDocument()
  expect(within(ranking).getByText('Beta 趋势观察')).toBeInTheDocument()
  expect(within(ranking).getByText('8800')).toBeInTheDocument()
  expect(within(ranking).getAllByText('-').length).toBeGreaterThan(0)

  expect(getStatsArticlesMock).toHaveBeenCalledWith(7)
})

test('switches the trend range and refetches article statistics', async () => {
  const user = userEvent.setup()

  render(<Stats />)

  expect(await screen.findByRole('table')).toBeInTheDocument()
  expect(getStatsArticlesMock).toHaveBeenCalledWith(7)

  await user.click(screen.getByText('近 30 天'))

  await waitFor(() => {
    expect(getStatsArticlesMock).toHaveBeenCalledWith(30)
  })
})

test('submits manually entered reading numbers through the modal', async () => {
  const user = userEvent.setup()

  render(<Stats />)

  const ranking = await screen.findByRole('table')
  await user.click(within(ranking).getAllByRole('button', { name: '手动录入' })[0])

  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByText('手动录入阅读数据')).toBeInTheDocument()

  const readInput = await within(dialog).findByLabelText('阅读数')
  await waitFor(() => {
    expect(readInput).toHaveValue('8800')
  })
  await user.clear(readInput)
  await user.type(readInput, '9999')

  await user.click(within(dialog).getByRole('button', { name: /保\s*存/ }))

  await waitFor(() => {
    expect(updateArticleStatsMock).toHaveBeenCalledWith('task-alpha', {
      read_num: 9999,
      like_num: 96,
      share_num: 210,
      collect_num: 130,
      fav_num: 12,
    })
  })
})

test('syncs wechat statistics on demand', async () => {
  const user = userEvent.setup()

  render(<Stats />)

  expect(await screen.findByRole('table')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: /同步微信数据/ }))

  await waitFor(() => {
    expect(syncArticleStatsMock).toHaveBeenCalledTimes(1)
  })
  expect(await screen.findByText('同步完成：成功 3，失败 1')).toBeInTheDocument()
})
