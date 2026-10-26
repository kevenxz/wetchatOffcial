import type { ReactNode } from 'react'
import styles from './layout.module.css'

type EmptyStateProps = {
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
}

/** One empty state for the whole app, so "no data" never looks like a bug. */
export default function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className={styles.emptyState}>
      <p className={styles.emptyTitle}>{title}</p>
      {description ? <p className={styles.emptyDescription}>{description}</p> : null}
      {action ? <div className={styles.emptyAction}>{action}</div> : null}
    </div>
  )
}
