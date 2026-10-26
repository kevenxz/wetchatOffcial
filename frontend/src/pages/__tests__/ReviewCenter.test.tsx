import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { Route, Routes, useLocation } from 'react-router-dom'
import type { ReviewDecision } from '@/api'
import ReviewCenter from '@/pages/ReviewCenter'
import { renderWithRouter } from '@/test/renderWithRouter'

const {
  approveReviewMock,
  listReviewsMock,
  rejectReviewMock,
  requestReviewRevisionMock,
} = vi.hoisted(() => ({
  approveReviewMock: vi.fn(),
  listReviewsMock: vi.fn<() => Promise<ReviewDecision[]>>(),
  rejectReviewMock: vi.fn(),
  requestReviewRevisionMock: vi.fn(),
}))

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api')
  return {
    ...actual,
    approveReview: approveReviewMock,
    listReviews: listReviewsMock,
    rejectReview: rejectReviewMock,
    requestReviewRevision: requestReviewRevisionMock,
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
  listReviewsMock.mockResolvedValue([
    {
      review_id: 'review-1',
      task_id: 'task-1',
      target_type: 'article',
      status: 'pending',
      risk_summary: '事实支撑不足，需要人工确认引用来源。',
      risk_issues: [
        {
          severity: 'high',
          message: '缺少关键数据来源',
        },
      ],
      article_score: 64,
      visual_score: 82,
      blocking_reasons: ['article_score_below_threshold'],
      revision_guidance: ['补充可验证来源'],
    },
  ])
  approveReviewMock.mockResolvedValue({})
  rejectReviewMock.mockResolvedValue({})
  requestReviewRevisionMock.mockResolvedValue({})
})

test('renders review queue and approves a review', async () => {
  const user = userEvent.setup()

  renderWithRouter(<ReviewCenter />, { route: '/reviews' })

  expect(await screen.findAllByText('事实支撑不足，需要人工确认引用来源。')).toHaveLength(2)
  expect(screen.getByText('缺少关键数据来源')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: /通过/ }))

  await waitFor(() => {
    expect(approveReviewMock).toHaveBeenCalledWith('review-1')
  })
})

test('renders empty review state', async () => {
  listReviewsMock.mockResolvedValue([])

  renderWithRouter(<ReviewCenter />, { route: '/reviews' })

  expect(await screen.findByText('暂无待审核内容')).toBeInTheDocument()
})

test('offers task detail and article entry points for each review row', async () => {
  const user = userEvent.setup()
  const LocationProbe = () => <p data-testid="current-path">{useLocation().pathname}</p>

  renderWithRouter(
    <>
      <Routes>
        {/* Keep the queue mounted on every route so both entry points stay clickable. */}
        <Route path="/reviews" element={<ReviewCenter />} />
        <Route path="/task/:id" element={<ReviewCenter />} />
        <Route path="/articles" element={<ReviewCenter />} />
      </Routes>
      <LocationProbe />
    </>,
    { route: '/reviews' },
  )

  expect(await screen.findByText('缺少关键数据来源')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: '查看任务详情' }))

  await waitFor(() => {
    expect(screen.getByTestId('current-path')).toHaveTextContent('/task/task-1')
  })

  await user.click(screen.getByRole('button', { name: '查看文章' }))

  await waitFor(() => {
    expect(screen.getByTestId('current-path')).toHaveTextContent('/articles')
  })
})
