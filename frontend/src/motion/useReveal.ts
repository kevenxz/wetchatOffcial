import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from './useReducedMotion'

type UseRevealOptions = {
  /** Fraction of the element that must be visible before revealing. */
  threshold?: number
  /** Root margin, so reveals can start slightly before the element scrolls in. */
  rootMargin?: string
}

/**
 * Reveal-on-scroll.
 *
 * Returns `revealed = true` immediately when motion is reduced or when
 * `IntersectionObserver` is unavailable (jsdom), so content is never hidden behind
 * an animation that will not run.
 */
export function useReveal<T extends HTMLElement = HTMLDivElement>({
  threshold = 0.15,
  rootMargin = '0px 0px -8% 0px',
}: UseRevealOptions = {}) {
  const ref = useRef<T>(null)
  const reduced = useReducedMotion()
  const [revealed, setRevealed] = useState(false)

  useEffect(() => {
    if (reduced) {
      setRevealed(true)
      return
    }

    const node = ref.current
    if (!node || typeof IntersectionObserver === 'undefined') {
      setRevealed(true)
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setRevealed(true)
            observer.disconnect()
            return
          }
        }
      },
      { threshold, rootMargin },
    )

    observer.observe(node)
    return () => observer.disconnect()
  }, [reduced, threshold, rootMargin])

  return { ref, revealed }
}

export default useReveal
