import type { ElementType, ReactNode } from 'react'
import styles from './layout.module.css'

type TruncatedTextProps = {
  children: ReactNode
  /**
   * Maximum lines before the text is clipped with an ellipsis. `1` gives the usual
   * single-line truncation. Clamped to 1–4 because longer clamps stop being readable and
   * the class set is deliberately finite.
   */
  lines?: 1 | 2 | 3 | 4
  /** Element to render. Defaults to a `span` so it can sit inside any layout. */
  as?: ElementType
  /** Extra class for type/spacing; the clamp itself always comes from this component. */
  className?: string
  /** Override the hover tooltip. Defaults to the full text when it is a plain string. */
  title?: string
}

const CLAMP_CLASS: Record<number, string> = {
  1: styles.clamp1,
  2: styles.clamp2,
  3: styles.clamp3,
  4: styles.clamp4,
}

/**
 * Text that never breaks the layout.
 *
 * Cards and table cells were rendering full titles and 200-character summaries, which made
 * a card's height depend on its content — a long summary visibly distorted the surrounding
 * grid. Clamping here means layout height is bounded regardless of what the API returns.
 *
 * Also sets `min-width: 0`, the usual missing piece when truncation "doesn't work": a flex or
 * grid child defaults to `min-width: auto` and refuses to shrink below its content, so the
 * ellipsis never appears even when `text-overflow` is set.
 *
 * The full value stays reachable through the native `title` attribute rather than a
 * tooltip component, so there is no extra DOM node per row and no layout side effects.
 */
export default function TruncatedText({
  children,
  lines = 1,
  as: Tag = 'span',
  className,
  title,
}: TruncatedTextProps) {
  const clampClass = CLAMP_CLASS[lines] ?? styles.clamp1
  const tooltip = title ?? (typeof children === 'string' ? children : undefined)

  return (
    <Tag className={[styles.truncated, clampClass, className].filter(Boolean).join(' ')} title={tooltip}>
      {children}
    </Tag>
  )
}
