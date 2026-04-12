import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  STORAGE_KEY,
  applyResolvedTheme,
  createSystemThemeListener,
  getStoredThemeMode,
  resolveThemeMode,
} from '../themeStore'

describe('themeStore helpers', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    document.documentElement.style.colorScheme = ''
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('defaults to system mode when storage is empty', () => {
    expect(getStoredThemeMode()).toBe('system')
  })

  it('returns stored mode when it is valid', () => {
    localStorage.setItem(STORAGE_KEY, 'dark')
    expect(getStoredThemeMode()).toBe('dark')
  })

  it('falls back to system mode when storage value is invalid', () => {
    localStorage.setItem(STORAGE_KEY, 'sepia')
    expect(getStoredThemeMode()).toBe('system')
  })

  it('resolves system mode using the media query result', () => {
    expect(resolveThemeMode('system', true)).toBe('dark')
    expect(resolveThemeMode('system', false)).toBe('light')
  })

  it('keeps explicit theme modes unchanged', () => {
    expect(resolveThemeMode('light', true)).toBe('light')
    expect(resolveThemeMode('dark', false)).toBe('dark')
  })

  it('applies the resolved theme to the document root', () => {
    applyResolvedTheme('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')
  })

  it('subscribes to system theme changes', () => {
    const addEventListener = vi.fn()
    const removeEventListener = vi.fn()
    const mediaQuery = {
      matches: true,
      addEventListener,
      removeEventListener,
    } as unknown as MediaQueryList

    const callback = vi.fn()
    const unsubscribe = createSystemThemeListener(mediaQuery, callback)

    expect(addEventListener).toHaveBeenCalledWith('change', callback)

    unsubscribe()

    expect(removeEventListener).toHaveBeenCalledWith('change', callback)
  })
})
