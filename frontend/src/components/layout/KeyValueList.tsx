import { Fragment } from 'react'
import type { ReactNode } from 'react'
import styles from './layout.module.css'

export type KeyValueItem = {
  label: string
  value: ReactNode
}

type KeyValueListProps = {
  items: KeyValueItem[]
  className?: string
}

/**
 * Aligned label/value pairs — replaces the per-page definition grids.
 *
 * The `dt`/`dd` elements must stay direct children of the grid container, so they
 * are wrapped in a keyed fragment rather than a `div`.
 */
export default function KeyValueList({ items, className }: KeyValueListProps) {
  return (
    <dl className={[styles.keyValueList, className].filter(Boolean).join(' ')}>
      {items.map((item) => (
        <Fragment key={item.label}>
          <dt className={styles.keyValueTerm}>{item.label}</dt>
          <dd className={styles.keyValueValue}>{item.value}</dd>
        </Fragment>
      ))}
    </dl>
  )
}
