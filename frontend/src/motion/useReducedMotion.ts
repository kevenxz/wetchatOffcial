import { useEffect, useState } from 'react'

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

/**
 * Read the OS motion preference.
 *
 * Defensive on purpose: `window.matchMedia` does not exist in jsdom, so every
 * motion primitive must degrade to "no animation" rather than throw. That also
 * means server-rendered/pre-hydration frames assume motion is allowed, which is
 * the safe default because the CSS guard in `global.css` still suppresses it.
 */
function readPreference(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false
  }
  return window.matchMedia(REDUCED_MOTION_QUERY).matches
}

export function prefersReducedMotion(): boolean {
  return readPreference()
}

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(readPreference)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return
    }

    const mediaQuery = window.matchMedia(REDUCED_MOTION_QUERY)
    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches)

    mediaQuery.addEventListener('change', onChange)
    return () => mediaQuery.removeEventListener('change', onChange)
  }, [])

  return reduced
}

export default useReducedMotion
