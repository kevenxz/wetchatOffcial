import styles from './BrandMark.module.css'

type BrandMarkProps = {
  /** Rendered size in pixels; the mark is square. */
  size?: number
  className?: string
}

/**
 * The single brand mark.
 *
 * Replaces the previous ad-hoc glyph/icon in the shell and the missing favicon
 * (`index.html` pointed at a `/vite.svg` that did not exist in `public/`). Monochrome
 * so it stays legible at 16px, and it inverts with the theme via tokens.
 */
export default function BrandMark({ size = 32, className }: BrandMarkProps) {
  return (
    <svg
      className={[styles.mark, className].filter(Boolean).join(' ')}
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="img"
      aria-label="微信公众号文章自动发布系统"
      focusable="false"
    >
      <rect className={styles.plate} width="64" height="64" />
      <rect className={styles.rule} x="14" y="12" width="4" height="40" />
      <rect className={styles.bar} x="22" y="12" width="28" height="4" />
      <rect className={styles.barMuted} x="22" y="24" width="20" height="4" />
      <rect className={styles.barMuted} x="22" y="36" width="28" height="4" />
      <rect className={styles.accent} x="22" y="48" width="14" height="4" />
    </svg>
  )
}
