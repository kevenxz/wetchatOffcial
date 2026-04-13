import styles from './MetricCard.module.css'

type MetricCardProps = {
  label: string
  value: string
  hint: string
}

export default function MetricCard({ label, value, hint }: MetricCardProps) {
  return (
    <div className={styles.card}>
      <span className={styles.label}>{label}</span>
      <strong className={styles.value}>{value}</strong>
      <span className={styles.hint}>{hint}</span>
    </div>
  )
}
