import { Button, Progress, Space, Table, Tag, Tooltip, Typography } from 'antd'
import { CheckOutlined, CloseOutlined, RollbackOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import type { ReviewDecision, ReviewStatus } from '@/api'

const { Text } = Typography

const statusText: Record<ReviewStatus, string> = {
  pending: '待审核',
  approved: '已通过',
  rejected: '已驳回',
  revision_requested: '已退回改写',
}

const statusColor: Record<ReviewStatus, string> = {
  pending: 'warning',
  approved: 'success',
  rejected: 'error',
  revision_requested: 'processing',
}

type ReviewQueueTableProps = {
  reviews: ReviewDecision[]
  loading?: boolean
  actionLoadingId?: string
  onApprove: (reviewId: string) => void
  onReject: (reviewId: string) => void
  onRequestRevision: (reviewId: string) => void
}

function score(value: number | null | undefined) {
  return Math.max(0, Math.min(100, Math.round(Number(value || 0))))
}

function reviewPayload(record: ReviewDecision) {
  return record.payload ?? {}
}

export default function ReviewQueueTable({
  reviews,
  loading = false,
  actionLoadingId,
  onApprove,
  onReject,
  onRequestRevision,
}: ReviewQueueTableProps) {
  const columns: ColumnsType<ReviewDecision> = [
    {
      title: '审核对象',
      dataIndex: 'task_id',
      key: 'task_id',
      width: 180,
      render: (taskId: string | undefined, record) => (
        <Space direction="vertical" size={4}>
          <Text code>{taskId || record.target_id || record.review_id}</Text>
          <Text>{record.title || '待审核内容'}</Text>
          <Space size={[4, 4]} wrap>
            <Tag>{record.target_type}</Tag>
            <Tag color={statusColor[record.status]}>{statusText[record.status]}</Tag>
          </Space>
        </Space>
      ),
    },
    {
      title: '风险摘要',
      dataIndex: 'risk_summary',
      key: 'risk_summary',
      ellipsis: true,
      render: (summary: string | null | undefined, record) => (
        <Tooltip title={summary || reviewPayload(record).risk_summary || record.blocking_reasons?.join('、') || '暂无摘要'}>
          <span>{summary || reviewPayload(record).risk_summary || record.blocking_reasons?.join('、') || '暂无摘要'}</span>
        </Tooltip>
      ),
    },
    {
      title: '文章分',
      dataIndex: 'article_score',
      key: 'article_score',
      width: 120,
      responsive: ['md'],
      render: (value: number | undefined, record) => (
        <Progress percent={score(value ?? reviewPayload(record).article_score)} size="small" />
      ),
    },
    {
      title: '视觉分',
      dataIndex: 'visual_score',
      key: 'visual_score',
      width: 120,
      responsive: ['lg'],
      render: (value: number | undefined, record) => (
        <Progress percent={score(value ?? reviewPayload(record).visual_score)} size="small" />
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 260,
      render: (_, record) => (
        <Space size={4} wrap>
          <Button
            size="small"
            type="primary"
            icon={<CheckOutlined />}
            disabled={record.status !== 'pending'}
            loading={actionLoadingId === `${record.review_id}:approve`}
            onClick={() => onApprove(record.review_id)}
          >
            通过
          </Button>
          <Button
            size="small"
            icon={<RollbackOutlined />}
            disabled={record.status !== 'pending'}
            loading={actionLoadingId === `${record.review_id}:revision`}
            onClick={() => onRequestRevision(record.review_id)}
          >
            退回改写
          </Button>
          <Button
            danger
            size="small"
            icon={<CloseOutlined />}
            disabled={record.status !== 'pending'}
            loading={actionLoadingId === `${record.review_id}:reject`}
            onClick={() => onReject(record.review_id)}
          >
            驳回
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <Table
      columns={columns}
      dataSource={reviews}
      rowKey="review_id"
      loading={loading}
      pagination={{ pageSize: 8 }}
      size="small"
    />
  )
}
