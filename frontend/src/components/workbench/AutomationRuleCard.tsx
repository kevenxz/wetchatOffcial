import type { ReactNode } from 'react'
import styles from './AutomationRuleCard.module.css'

type AutomationRuleItem = {
  label: string
  value: ReactNode
}

type AutomationRuleCardProps = {
  eyebrow?: string
  title: string
  status?: ReactNode
  tags?: ReactNode
  items: AutomationRuleItem[]
  note?: ReactNode
  actions?: ReactNode
}

export default function AutomationRuleCard({
  eyebrow,
  title,
  status,
  tags,
  items,
  note,
  actions,
}: AutomationRuleCardProps) {
  return (
    <article className={styles.card}>
      <div className={styles.header}>
        <div className={styles.identity}>
          {eyebrow ? <span className={styles.eyebrow}>{eyebrow}</span> : null}
          <h3 className={styles.title}>{title}</h3>
        </div>
        {status ? <div className={styles.status}>{status}</div> : null}
      </div>

      {tags ? <div className={styles.tags}>{tags}</div> : null}

      <dl className={styles.details}>
        {items.map((item) => (
          <div className={styles.detail} key={item.label}>
            <dt className={styles.label}>{item.label}</dt>
            <dd className={styles.value}>{item.value}</dd>
          </div>
        ))}
      </dl>

      {note ? <div className={styles.note}>{note}</div> : null}
      {actions ? <div className={styles.actions}>{actions}</div> : null}
    </article>
  )
}
