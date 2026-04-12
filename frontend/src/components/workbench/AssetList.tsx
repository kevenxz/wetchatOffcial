import type { ReactNode } from 'react'
import styles from './AssetList.module.css'

type AssetView = {
  key: string
  label: string
}

type AssetListProps = {
  eyebrow: string
  title: string
  description: string
  meta?: ReactNode
  actions?: ReactNode
  views?: AssetView[]
  activeView?: string
  onViewChange?: (key: string) => void
  children: ReactNode
}

export default function AssetList({
  eyebrow,
  title,
  description,
  meta,
  actions,
  views = [],
  activeView,
  onViewChange,
  children,
}: AssetListProps) {
  return (
    <section className={styles.assetList}>
      <header className={styles.hero}>
        <div className={styles.heroTop}>
          <div>
            <p className={styles.eyebrow}>{eyebrow}</p>
            <h1 className={styles.title}>{title}</h1>
            <p className={styles.description}>{description}</p>
          </div>
          {actions ? <div className={styles.actions}>{actions}</div> : null}
        </div>

        {(meta || views.length > 0) && (
          <div className={styles.controls}>
            <div className={styles.meta}>{meta}</div>
            {views.length > 0 ? (
              <div className={styles.views} aria-label="资产视图切换">
                {views.map((view) => {
                  const isActive = view.key === activeView
                  const className = `${styles.viewButton} ${isActive ? styles.viewButtonActive : ''}`.trim()

                  if (!onViewChange) {
                    return (
                      <span key={view.key} className={className}>
                        {view.label}
                      </span>
                    )
                  }

                  return (
                    <button
                      key={view.key}
                      type="button"
                      className={className}
                      onClick={() => onViewChange(view.key)}
                    >
                      {view.label}
                    </button>
                  )
                })}
              </div>
            ) : null}
          </div>
        )}
      </header>

      <div className={styles.body}>{children}</div>
    </section>
  )
}
