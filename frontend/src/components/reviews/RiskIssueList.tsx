import { Empty, List, Tag, Typography } from 'antd'
import type { ReviewRiskIssue } from '@/api'
import styles from './RiskIssueList.module.css'

const { Text } = Typography

const severityColor: Record<string, string> = {
  low: 'success',
  medium: 'warning',
  high: 'error',
  critical: 'error',
}

type RiskIssueListProps = {
  issues: ReviewRiskIssue[]
}

export default function RiskIssueList({ issues }: RiskIssueListProps) {
  if (!issues.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无风险项" />
  }

  return (
    <List
      className={styles.list}
      dataSource={issues}
      renderItem={(item) => (
        <List.Item>
          <div className={styles.item}>
            <Tag color={severityColor[String(item.severity || 'medium')] || 'default'}>
              {item.severity || 'medium'}
            </Tag>
            <Text>{item.message}</Text>
          </div>
        </List.Item>
      )}
    />
  )
}
