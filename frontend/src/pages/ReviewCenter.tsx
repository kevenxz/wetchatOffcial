import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Empty, Select, Space, Statistic, Typography, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import {
  approveReview,
  listReviews,
  rejectReview,
  requestReviewRevision,
  type ReviewDecision,
  type ReviewStatus,
} from '@/api'
import { ReviewQueueTable, RiskIssueList } from '@/components/reviews'
import styles from './ReviewCenter.module.css'

const { Paragraph, Title } = Typography

type ReviewFilter = ReviewStatus | 'all'

const filterOptions: Array<{ label: string; value: ReviewFilter }> = [
  { label: '全部状态', value: 'all' },
  { label: '待审核', value: 'pending' },
  { label: '已通过', value: 'approved' },
  { label: '已驳回', value: 'rejected' },
  { label: '退回改写', value: 'revision_requested' },
]

export default function ReviewCenter() {
  const [reviews, setReviews] = useState<ReviewDecision[]>([])
  const [status, setStatus] = useState<ReviewFilter>('pending')
  const [loading, setLoading] = useState(false)
  const [actionLoadingId, setActionLoadingId] = useState('')

  const fetchReviews = async (nextStatus = status) => {
    setLoading(true)
    try {
      const data = await listReviews({ status: nextStatus, limit: 50 })
      setReviews(Array.isArray(data) ? data : [])
    } catch (error) {
      setReviews([])
      message.error(error instanceof Error ? error.message : '获取审核列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchReviews()
  }, [])

  const selectedReview = useMemo(() => reviews[0] ?? null, [reviews])
  const selectedPayload = selectedReview?.payload ?? {}
  const riskIssues = selectedReview?.risk_issues ?? selectedPayload.risk_issues ?? []
  const pendingCount = reviews.filter((item) => item.status === 'pending').length

  const handleStatusChange = (nextStatus: ReviewFilter) => {
    setStatus(nextStatus)
    void fetchReviews(nextStatus)
  }

  const runReviewAction = async (reviewId: string, action: 'approve' | 'reject' | 'revision') => {
    setActionLoadingId(`${reviewId}:${action}`)
    try {
      if (action === 'approve') {
        await approveReview(reviewId)
        message.success('审核已通过')
      } else if (action === 'reject') {
        await rejectReview(reviewId)
        message.success('审核已驳回')
      } else {
        await requestReviewRevision(reviewId)
        message.success('已退回改写')
      }
      await fetchReviews()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '审核操作失败')
    } finally {
      setActionLoadingId('')
    }
  }

  return (
    <div className="backstage-page">
      <div className={styles.layout}>
        <Card className="backstage-surface-card" size="small">
          <div className={styles.toolbar}>
            <Space wrap>
              <Select
                aria-label="审核状态筛选"
                value={status}
                options={filterOptions}
                style={{ width: 160 }}
                onChange={handleStatusChange}
              />
              <Statistic title="待处理" value={pendingCount} />
            </Space>
            <Button icon={<ReloadOutlined />} onClick={() => void fetchReviews()} loading={loading}>
              刷新
            </Button>
          </div>
          {reviews.length === 0 && !loading ? (
            <Empty description="暂无待审核内容" />
          ) : (
            <ReviewQueueTable
              reviews={reviews}
              loading={loading}
              actionLoadingId={actionLoadingId}
              onApprove={(reviewId) => void runReviewAction(reviewId, 'approve')}
              onReject={(reviewId) => void runReviewAction(reviewId, 'reject')}
              onRequestRevision={(reviewId) => void runReviewAction(reviewId, 'revision')}
            />
          )}
        </Card>

        <Card className="backstage-surface-card" size="small">
          <div className={styles.riskPanel}>
            <Title level={4}>风险摘要</Title>
            {selectedReview ? (
              <>
                <Paragraph type="secondary">
                  {selectedReview.risk_summary ||
                    selectedPayload.risk_summary ||
                    selectedReview.blocking_reasons?.join('、') ||
                    '当前记录暂无风险摘要。'}
                </Paragraph>
                <RiskIssueList issues={riskIssues} />
              </>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择审核记录后查看风险项" />
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}
