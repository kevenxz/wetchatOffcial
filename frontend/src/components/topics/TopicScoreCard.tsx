import { Card, Statistic } from 'antd'
import type { TopicCandidate } from '@/api'
import styles from './TopicScoreCard.module.css'

type TopicScoreCardProps = {
  label: string
  value: number
  tone?: 'default' | 'success' | 'warning'
}

export function TopicScoreCard({ label, value, tone = 'default' }: TopicScoreCardProps) {
  return (
    <Card className={styles.card}>
      <Statistic
        title={label}
        value={value}
        valueStyle={{ color: tone === 'success' ? '#16a34a' : tone === 'warning' ? '#d97706' : undefined }}
      />
    </Card>
  )
}

export function getTopicMetrics(topics: TopicCandidate[]) {
  return {
    total: topics.length,
    pending: topics.filter((item) => item.status === 'pending').length,
    converted: topics.filter((item) => item.status === 'converted').length,
  }
}
