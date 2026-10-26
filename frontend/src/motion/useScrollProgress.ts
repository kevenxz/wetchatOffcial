import { useEffect, useRef } from 'react'
import { useReducedMotion } from './useReducedMotion'

/**
 * Scroll progress of an element, written to a CSS custom property.
 *
 * `--scroll-progress` goes from 0 (element top reaches the viewport top) to 1
 * (element bottom reaches the viewport bottom). Driving animation from a custom
 * property keeps the movement in CSS — the React tree does not re-render per frame,
 * and `transform` stays on the compositor.
 *
 * Writing one custom property is the sanctioned exception to the "no inline styles"
 * rule: it is a live value, not a style description.
 */
export function useScrollProgress<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T>(null)
  const reduced = useReducedMotion()

  useEffect(() => {
    const node = ref.current
    if (!node || reduced || typeof window === 'undefined') {
      return
    }

    let frame = 0

    const update = () => {
      frame = 0
      const rect = node.getBoundingClientRect()
      const travel = rect.height - window.innerHeight
      const progress = travel <= 0 ? 0 : Math.min(1, Math.max(0, -rect.top / travel))
      node.style.setProperty('--scroll-progress', progress.toFixed(4))
    }

    const schedule = () => {
      if (frame === 0) {
        frame = window.requestAnimationFrame(update)
      }
    }

    update()
    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule)

    return () => {
      window.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', schedule)
      if (frame !== 0) {
        window.cancelAnimationFrame(frame)
      }
    }
  }, [reduced])

  return ref
}

export default useScrollProgress
