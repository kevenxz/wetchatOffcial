import type { ReactNode } from 'react'
import styles from './layout.module.css'

type ToolbarProps = {
  /** Filters and left-aligned controls. */
  children: ReactNode
  /** Right-aligned primary actions. */
  actions?: ReactNode
  className?: string
}

/** Filter / action bar. One per list view, so filtering never drifts per page. */
export default function Toolbar({ children, actions, className }: ToolbarProps) {
  return (
    <div className={[styles.toolbar, className].filter(Boolean).join(' ')} role="toolbar">
      <div className={styles.toolbarGroup}>{children}</div>
      {actions ? <div className={styles.toolbarGroup}>{actions}</div> : null}
    </div>
  )
}
