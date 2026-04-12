import React from 'react'
import { render, screen } from '@testing-library/react'
import { act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'
import { getAntdTheme } from '../../theme'
import {
  bootstrapThemeStore,
  STORAGE_KEY,
  applyResolvedTheme,
  createSystemThemeListener,
  getStoredThemeMode,
  resolveThemeMode,
  useThemeStore,
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

  it('falls back to system mode when storage access throws', () => {
    const getItemSpy = vi
      .spyOn(window.localStorage, 'getItem')
      .mockImplementation(() => {
        throw new Error('storage unavailable')
      })

    expect(getStoredThemeMode()).toBe('system')

    getItemSpy.mockRestore()
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

  it('uses the legacy MediaQueryList listener APIs when modern ones are unavailable', () => {
    const addListener = vi.fn()
    const removeListener = vi.fn()
    const mediaQuery = {
      matches: true,
      addEventListener: undefined,
      removeEventListener: undefined,
      addListener,
      removeListener,
    } as unknown as MediaQueryList

    const callback = vi.fn()
    const unsubscribe = createSystemThemeListener(mediaQuery, callback)

    expect(addListener).toHaveBeenCalledWith(callback)

    unsubscribe()

    expect(removeListener).toHaveBeenCalledWith(callback)
  })

  it('initializes from system preference when storage is empty', () => {
    act(() => {
      useThemeStore.setState({
        mode: 'system',
        resolvedTheme: 'light',
        initialized: false,
      })
      useThemeStore.getState().initialize(true)
    })

    expect(useThemeStore.getState().mode).toBe('system')
    expect(useThemeStore.getState().resolvedTheme).toBe('dark')
    expect(useThemeStore.getState().initialized).toBe(true)
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('persists explicit theme selections', () => {
    act(() => {
      useThemeStore.setState({
        mode: 'system',
        resolvedTheme: 'light',
        initialized: false,
      })
      useThemeStore.getState().setMode('dark', false)
    })

    expect(useThemeStore.getState().mode).toBe('dark')
    expect(useThemeStore.getState().resolvedTheme).toBe('dark')
    expect(useThemeStore.getState().initialized).toBe(true)
    expect(localStorage.getItem(STORAGE_KEY)).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('updates the resolved theme when system mode receives a new preference', () => {
    act(() => {
      useThemeStore.setState({
        mode: 'system',
        resolvedTheme: 'light',
        initialized: false,
      })
      useThemeStore.getState().initialize(false)
      useThemeStore.getState().syncSystemTheme(true)
    })

    expect(useThemeStore.getState().mode).toBe('system')
    expect(useThemeStore.getState().resolvedTheme).toBe('dark')
  })

  it('ignores system updates when mode is explicitly selected', () => {
    act(() => {
      useThemeStore.setState({
        mode: 'system',
        resolvedTheme: 'light',
        initialized: false,
      })
      useThemeStore.getState().setMode('light', false)
      useThemeStore.getState().syncSystemTheme(true)
    })

    expect(useThemeStore.getState().mode).toBe('light')
    expect(useThemeStore.getState().resolvedTheme).toBe('light')
  })

  it('returns distinct Ant Design tokens for light and dark themes', () => {
    const lightTheme = getAntdTheme('light')
    const darkTheme = getAntdTheme('dark')

    expect(lightTheme.token?.colorBgLayout).toBe('#f3f6fb')
    expect(darkTheme.token?.colorBgLayout).toBe('#0b1020')
    expect(lightTheme.components?.Layout?.siderBg).toBe('#ffffff')
    expect(darkTheme.components?.Layout?.siderBg).toBe('#0e1627')
  })

  it('boots the stored theme before the app shell renders', () => {
    localStorage.setItem(STORAGE_KEY, 'dark')

    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: () => ({
        matches: false,
        media: '(prefers-color-scheme: dark)',
        onchange: null,
        addListener: () => undefined,
        removeListener: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      }),
    })

    expect(bootstrapThemeStore(false)).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(useThemeStore.getState().resolvedTheme).toBe('dark')

    render(React.createElement(App))

    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(screen.getByText('Brand Studio', { selector: 'strong' })).toBeInTheDocument()
  })
})
