import type { ReactNode } from 'react'
import styles from './SectionBlock.module.css'

type SectionBlockProps = {
  title?: string
  aside?: ReactNode
  children: ReactNode
}

export default function SectionBlock({ title, aside, children }: SectionBlockProps) {
  return (
    <section className={styles.section}>
      {(title || aside) && (
        <div className={styles.header}>
          {title ? <h2 className={styles.title}>{title}</h2> : <span />}
          {aside}
        </div>
      )}
      <div className={styles.content}>{children}</div>
    </section>
  )
}
