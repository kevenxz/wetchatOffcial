import { useEffect, useState } from 'react'
import { Button, Card, Empty, Select, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import {
  convertTopicToTask,
  ignoreTopic,
  listTopics,
  type TopicCandidate,
  type TopicStatus,
} from '@/api'
import { TopicCandidateTable, TopicScoreCard, getTopicMetrics } from '@/components/topics'
import styles from './TopicCenter.module.css'

type TopicFilter = TopicStatus | 'all'

const filterOptions: Array<{ label: string; value: TopicFilter }> = [
  { label: '全部状态', value: 'all' },
  { label: '候选', value: 'pending' },
  { label: '已忽略', value: 'ignored' },
  { label: '已转任务', value: 'converted' },
]

export default function TopicCenter() {
  const [topics, setTopics] = useState<TopicCandidate[]>([])
  const [status, setStatus] = useState<TopicFilter>('pending')
  const [loading, setLoading] = useState(false)
  const [actionLoadingId, setActionLoadingId] = useState('')

  const fetchTopics = async (nextStatus = status) => {
    setLoading(true)
    try {
      const data = await listTopics({ status: nextStatus, limit: 50 })
      setTopics(Array.isArray(data) ? data : [])
    } catch (error) {
      setTopics([])
      message.error(error instanceof Error ? error.message : '获取候选选题失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchTopics()
  }, [])

  const handleStatusChange = (nextStatus: TopicFilter) => {
    setStatus(nextStatus)
    void fetchTopics(nextStatus)
  }

  const runTopicAction = async (topicId: string, action: 'ignore' | 'convert') => {
    setActionLoadingId(`${topicId}:${action}`)
    try {
      if (action === 'ignore') {
        await ignoreTopic(topicId)
        message.success('已忽略选题')
      } else {
        await convertTopicToTask(topicId)
        message.success('已转为创作任务')
      }
      await fetchTopics()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '选题操作失败')
    } finally {
      setActionLoadingId('')
    }
  }

  const metrics = getTopicMetrics(topics)

  return (
    <div className="backstage-page">
      <div className={styles.summaryGrid}>
        <TopicScoreCard label="当前列表" value={metrics.total} />
        <TopicScoreCard label="候选待处理" value={metrics.pending} tone="warning" />
        <TopicScoreCard label="已转任务" value={metrics.converted} tone="success" />
      </div>

      <Card className="backstage-surface-card">
        <div className={styles.toolbar}>
          <Select
            aria-label="选题状态筛选"
            value={status}
            options={filterOptions}
            style={{ width: 160 }}
            onChange={handleStatusChange}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void fetchTopics()} loading={loading}>
            刷新
          </Button>
        </div>
      </Card>

      <Card className="backstage-surface-card">
        {topics.length === 0 && !loading ? (
          <Empty description="暂无候选选题" />
        ) : (
          <TopicCandidateTable
            topics={topics}
            loading={loading}
            actionLoadingId={actionLoadingId}
            onIgnore={(topicId) => void runTopicAction(topicId, 'ignore')}
            onConvert={(topicId) => void runTopicAction(topicId, 'convert')}
          />
        )}
      </Card>
    </div>
  )
}
