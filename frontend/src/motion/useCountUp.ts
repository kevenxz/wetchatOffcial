import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from './useReducedMotion'

type UseCountUpOptions = {
  durationMs?: number
  /** Skip straight to the final value without waiting to be scrolled into view. */
  immediate?: boolean
}

function easeOutCubic(t: number): number {
  return 1 - (1 - t) ** 3
}

/**
 * Animate a number up to its value when it scrolls into view.
 *
 * With reduced motion (or without `IntersectionObserver`/`requestAnimationFrame`,
 * as in jsdom) the value is shown immediately — a counter must never be the reason
 * a figure is missing.
 */
export function useCountUp(target: number, { durationMs = 1200, immediate = false }: UseCountUpOptions = {}) {
  const ref = useRef<HTMLSpanElement>(null)
  const reduced = useReducedMotion()
  const [value, setValue] = useState(() => (immediate ? target : 0))

  useEffect(() => {
    const canAnimate =
      !reduced &&
      !immediate &&
      typeof window !== 'undefined' &&
      typeof IntersectionObserver !== 'undefined' &&
      typeof window.requestAnimationFrame === 'function'

    if (!canAnimate) {
      setValue(target)
      return
    }

    const node = ref.current
    if (!node) {
      setValue(target)
      return
    }

    let frame = 0
    let startedAt = 0

    const step = (timestamp: number) => {
      if (startedAt === 0) {
        startedAt = timestamp
      }
      const elapsed = timestamp - startedAt
      const progress = Math.min(1, elapsed / durationMs)
      setValue(Math.round(target * easeOutCubic(progress)))

      if (progress < 1) {
        frame = window.requestAnimationFrame(step)
      }
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            observer.disconnect()
            frame = window.requestAnimationFrame(step)
            return
          }
        }
      },
      { threshold: 0.4 },
    )

    observer.observe(node)
    return () => {
      observer.disconnect()
      if (frame !== 0) {
        window.cancelAnimationFrame(frame)
      }
    }
  }, [target, durationMs, immediate, reduced])

  return { ref, value }
}

export default useCountUp
