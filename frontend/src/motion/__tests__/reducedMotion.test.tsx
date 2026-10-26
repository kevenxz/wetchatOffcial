/**
 * Motion primitives must never be the reason content is missing.
 *
 * Every hook has to resolve to its final state when motion is reduced, and also when
 * the browser APIs are unavailable (jsdom has no `IntersectionObserver`, and the
 * tests only stub `matchMedia` when they need it).
 */
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { prefersReducedMotion, useCountUp, useReducedMotion, useReveal } from '@/motion'

const originalMatchMedia = window.matchMedia

function stubMatchMedia(reduced: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: query.includes('prefers-reduced-motion') ? reduced : false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  })
}

function RevealProbe() {
  const { ref, revealed } = useReveal<HTMLDivElement>()
  return <div ref={ref}>{revealed ? 'revealed' : 'hidden'}</div>
}

function ReducedProbe() {
  return <span>{useReducedMotion() ? 'reduced' : 'full'}</span>
}

function CountUpProbe({ target }: { target: number }) {
  const { ref, value } = useCountUp(target)
  return <span ref={ref}>{value}</span>
}

beforeEach(() => {
  stubMatchMedia(false)
})

afterEach(() => {
  if (originalMatchMedia) {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      configurable: true,
      value: originalMatchMedia,
    })
  } else {
    Reflect.deleteProperty(window, 'matchMedia')
  }
})

describe('useReducedMotion', () => {
  it('reports the OS preference', () => {
    stubMatchMedia(true)
    render(<ReducedProbe />)
    expect(screen.getByText('reduced')).toBeInTheDocument()
  })

  it('degrades to "full motion" when matchMedia is unavailable', () => {
    Reflect.deleteProperty(window, 'matchMedia')
    expect(prefersReducedMotion()).toBe(false)
  })
})

describe('useReveal', () => {
  it('reveals content immediately when motion is reduced', () => {
    stubMatchMedia(true)
    render(<RevealProbe />)
    expect(screen.getByText('revealed')).toBeInTheDocument()
  })

  it('reveals content when IntersectionObserver is unavailable', () => {
    stubMatchMedia(false)
    render(<RevealProbe />)
    // jsdom has no IntersectionObserver, so the hook must not leave content hidden.
    expect(screen.getByText('revealed')).toBeInTheDocument()
  })
})

describe('useCountUp', () => {
  it('shows the final value immediately when motion is reduced', () => {
    stubMatchMedia(true)
    render(<CountUpProbe target={23} />)
    expect(screen.getByText('23')).toBeInTheDocument()
  })

  it('shows the final value when it cannot animate', () => {
    stubMatchMedia(false)
    render(<CountUpProbe target={42} />)
    expect(screen.getByText('42')).toBeInTheDocument()
  })
})
