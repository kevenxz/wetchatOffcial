import type { ReactNode } from 'react'
import styles from './layout.module.css'

type PageHeaderProps = {
  /** Small mono label above the title — the editorial layer of the type hierarchy. */
  eyebrow?: string
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
}

/**
 * Page title block.
 *
 * Exists because the shell previously hid its own `contextEyebrow` /
 * `contextDescription` (`display: none`), throwing away the editorial hierarchy the
 * navigation metadata already provided.
 */
export default function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  return (
    <header className={styles.pageHeader}>
      <div className={styles.pageHeaderRow}>
        <div className={styles.pageHeaderMain}>
          {eyebrow ? <span className={styles.eyebrow}>{eyebrow}</span> : null}
          <h1 className={styles.title}>{title}</h1>
          {description ? <p className={styles.description}>{description}</p> : null}
        </div>
        {actions ? <div className={styles.actions}>{actions}</div> : null}
      </div>
    </header>
  )
}
