import type { ReactNode } from 'react'
import styles from './layout.module.css'

type StatGridProps = {
  children: ReactNode
  className?: string
  /** Accessible name for the figure block; also lets tests scope their queries. */
  label?: string
}

/**
 * Hairline-divided statistic grid.
 *
 * Uses a 1px grid gap over a border-coloured background so the dividers are real
 * rules rather than per-cell borders — the Swiss way to build a figure block with
 * no cards and no shadows.
 */
export function StatGrid({ children, className, label = '关键指标' }: StatGridProps) {
  return (
    <div
      role="group"
      aria-label={label}
      className={[styles.statGrid, className].filter(Boolean).join(' ')}
    >
      {children}
    </div>
  )
}

type StatProps = {
  label: string
  value: ReactNode
  hint?: ReactNode
  /** Maps to the status palette: success / warning / danger. */
  tone?: 'neutral' | 'positive' | 'warning' | 'negative'
}

/**
 * Numbers are grouped by thousands here so every figure in the app reads the same
 * way. antd's `Statistic` did this before, and dropping it silently lost the
 * separators on read counts.
 */
function formatValue(value: ReactNode): ReactNode {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value.toLocaleString('zh-CN')
  }
  return value
}

const TONE_CLASS: Record<NonNullable<StatProps['tone']>, string> = {
  neutral: '',
  positive: styles.statTonePositive,
  warning: styles.statToneWarning,
  negative: styles.statToneNegative,
}

export function Stat({ label, value, hint, tone = 'neutral' }: StatProps) {
  const toneClass = TONE_CLASS[tone]

  return (
    <div className={[styles.stat, toneClass].filter(Boolean).join(' ')}>
      <span className={styles.statLabel}>{label}</span>
      <span className={styles.statValue}>{formatValue(value)}</span>
      {hint ? <span className={styles.statHint}>{hint}</span> : null}
    </div>
  )
}

export default StatGrid
