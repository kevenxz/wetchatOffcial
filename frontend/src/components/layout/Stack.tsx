import type { ReactNode } from 'react'
import styles from './layout.module.css'

type StackProps = {
  children: ReactNode
  /** `tight` halves the rhythm for related controls inside one panel. */
  gap?: 'base' | 'tight'
  className?: string
}

/** Vertical rhythm container. Pages compose panels with this, never with margins. */
export function Stack({ children, gap = 'base', className }: StackProps) {
  const gapClass = gap === 'tight' ? styles.stackTight : styles.stack
  return <div className={[gapClass, className].filter(Boolean).join(' ')}>{children}</div>
}

type SplitProps = {
  children: ReactNode
  className?: string
}

/** Main + aside two-column layout. Collapses to one column under 1080px. */
export function Split({ children, className }: SplitProps) {
  return <div className={[styles.split, className].filter(Boolean).join(' ')}>{children}</div>
}

type GridProps = {
  children: ReactNode
  className?: string
}

/** Auto-fitting card grid. */
export function Grid({ children, className }: GridProps) {
  return <div className={[styles.grid, className].filter(Boolean).join(' ')}>{children}</div>
}

export default Stack
