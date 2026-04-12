import { afterEach, describe, expect, it, vi } from 'vitest'
import indexHtml from '../../index.html?raw'

const inlineBootstrapScript = indexHtml.match(/<script>([\s\S]*?)<\/script>/)?.[1]

const installMatchMedia = (prefersDark: boolean) => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn(() => ({
      matches: prefersDark,
      media: '(prefers-color-scheme: dark)',
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    })),
  })
}

describe('index theme bootstrap script', () => {
  afterEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    document.documentElement.style.colorScheme = ''
    vi.restoreAllMocks()
  })

  it('exists and applies a persisted dark selection before the bundle mounts', () => {
    expect(inlineBootstrapScript).toBeTruthy()

    localStorage.setItem('app-theme-mode', 'dark')
    installMatchMedia(false)

    window.eval(inlineBootstrapScript!)

    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')
  })

  it('falls back to the dark system preference when no theme is stored', () => {
    expect(inlineBootstrapScript).toBeTruthy()

    installMatchMedia(true)

    window.eval(inlineBootstrapScript!)

    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')
  })
})
