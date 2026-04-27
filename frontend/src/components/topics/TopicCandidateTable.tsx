import { Button, Progress, Space, Table, Tag, Tooltip } from 'antd'
import { EyeInvisibleOutlined, SendOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import type { TopicCandidate, TopicStatus } from '@/api'

const statusText: Record<TopicStatus, string> = {
  pending: '候选',
  ignored: '已忽略',
  converted: '已转任务',
}

const statusColor: Record<TopicStatus, string> = {
  pending: 'processing',
  ignored: 'default',
  converted: 'success',
}

type TopicCandidateTableProps = {
  topics: TopicCandidate[]
  loading?: boolean
  actionLoadingId?: string
  onIgnore: (topicId: string) => void
  onConvert: (topicId: string) => void
}

function scorePercent(value: number | null | undefined) {
  return Math.max(0, Math.min(100, Math.round(Number(value || 0))))
}

function topicMeta(record: TopicCandidate) {
  return record.metadata ?? {}
}

export default function TopicCandidateTable({
  topics,
  loading = false,
  actionLoadingId,
  onIgnore,
  onConvert,
}: TopicCandidateTableProps) {
  const columns: ColumnsType<TopicCandidate> = [
    {
      title: '候选选题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (title: string, record) => (
        <Space direction="vertical" size={4}>
          <Tooltip title={title}>
            <strong>{title}</strong>
          </Tooltip>
          <Space size={[4, 4]} wrap>
            {(record.category || topicMeta(record).category) ? <Tag>{record.category || topicMeta(record).category}</Tag> : null}
            {record.source ? <Tag color="blue">{record.source}</Tag> : null}
            <Tag color={statusColor[record.status]}>{statusText[record.status]}</Tag>
          </Space>
        </Space>
      ),
    },
    {
      title: '角度',
      dataIndex: 'angle',
      key: 'angle',
      ellipsis: true,
      responsive: ['md'],
      render: (_value: string | undefined, record) => record.angle || topicMeta(record).angle || record.summary || '-',
    },
    {
      title: '热度',
      dataIndex: 'hot_score',
      key: 'hot_score',
      width: 120,
      render: (value: number | undefined, record) => (
        <Progress percent={scorePercent(value ?? record.score ?? topicMeta(record).hot_score)} size="small" />
      ),
    },
    {
      title: '匹配',
      dataIndex: 'account_fit_score',
      key: 'account_fit_score',
      width: 120,
      responsive: ['lg'],
      render: (value: number | undefined, record) => (
        <Progress percent={scorePercent(value ?? topicMeta(record).account_fit_score)} size="small" status="active" />
      ),
    },
    {
      title: '风险',
      dataIndex: 'risk_score',
      key: 'risk_score',
      width: 100,
      render: (value: number | undefined, record) => {
        const risk = scorePercent(value ?? topicMeta(record).risk_score)
        return <Tag color={risk >= 70 ? 'error' : risk >= 40 ? 'warning' : 'success'}>{risk}</Tag>
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      render: (_, record) => (
        <Space size={4}>
          <Button
            size="small"
            icon={<EyeInvisibleOutlined />}
            disabled={record.status !== 'pending'}
            loading={actionLoadingId === `${record.topic_id}:ignore`}
            onClick={() => onIgnore(record.topic_id)}
          >
            忽略
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<SendOutlined />}
            disabled={record.status !== 'pending'}
            loading={actionLoadingId === `${record.topic_id}:convert`}
            onClick={() => onConvert(record.topic_id)}
          >
            转任务
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <Table
      columns={columns}
      dataSource={topics}
      rowKey="topic_id"
      loading={loading}
      pagination={{ pageSize: 8 }}
      size="small"
    />
  )
}
