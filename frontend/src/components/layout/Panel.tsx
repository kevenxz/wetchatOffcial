import type { ReactNode } from 'react'
import styles from './layout.module.css'

type PanelProps = {
  title?: ReactNode
  aside?: ReactNode
  actions?: ReactNode
  /** Drop body padding when the panel wraps a table or grid. */
  flush?: boolean
  className?: string
  children: ReactNode
}

/**
 * The only surface container in the design system: a hairline border, square
 * corners, no shadow. Depth is expressed with rules, not elevation.
 */
export default function Panel({ title, aside, actions, flush, className, children }: PanelProps) {
  const hasHeader = Boolean(title || aside || actions)

  return (
    <section className={[styles.panel, className].filter(Boolean).join(' ')}>
      {hasHeader ? (
        <div className={styles.panelHeader}>
          <div className={styles.panelHeading}>
            {title ? <h2 className={styles.panelTitle}>{title}</h2> : null}
            {aside ? <span className={styles.panelAside}>{aside}</span> : null}
          </div>
          {actions ? <div className={styles.actions}>{actions}</div> : null}
        </div>
      ) : null}
      <div className={flush ? styles.panelBodyFlush : styles.panelBody}>{children}</div>
    </section>
  )
}
