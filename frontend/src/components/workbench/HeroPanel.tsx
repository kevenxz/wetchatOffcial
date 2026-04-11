import type { ReactNode } from 'react'
import styles from './HeroPanel.module.css'

type HeroPanelProps = {
  eyebrow: string
  title: string
  description: string
  children?: ReactNode
}

export default function HeroPanel({ eyebrow, title, description, children }: HeroPanelProps) {
  return (
    <section className={styles.panel}>
      <p className={styles.eyebrow}>{eyebrow}</p>
      <div>
        <h1 className={styles.title}>{title}</h1>
        <p className={styles.description}>{description}</p>
      </div>
      {children}
    </section>
  )
}
