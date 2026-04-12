import type { ReactNode } from 'react'
import styles from './SignalCard.module.css'

type SignalCardProps = {
  icon: ReactNode
  title: string
  description: string
}

export default function SignalCard({ icon, title, description }: SignalCardProps) {
  return (
    <div className={styles.card}>
      <span className={styles.icon}>{icon}</span>
      <div className={styles.body}>
        <strong className={styles.title}>{title}</strong>
        <p className={styles.description}>{description}</p>
      </div>
    </div>
  )
}
