import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeBootstrap } from '../themeBootstrap'
import { useThemeStore } from '../store/themeStore'

let renderSpy: ReturnType<typeof vi.fn>
let createRootSpy: ReturnType<typeof vi.fn>

describe('main entrypoint', () => {
  beforeEach(() => {
    localStorage.clear()
    document.body.innerHTML = '<div id="root"></div>'
    document.documentElement.removeAttribute('data-theme')
    document.documentElement.style.colorScheme = ''
    useThemeStore.setState({
      mode: 'system',
      resolvedTheme: 'light',
      initialized: false,
    })
    renderSpy = vi.fn((element: React.ReactNode) => {
      expect(useThemeStore.getState().initialized).toBe(true)
      expect(useThemeStore.getState().resolvedTheme).toBe('dark')
      return element
    })
    createRootSpy = vi.fn(() => ({
      render: renderSpy,
    }))

    const matchMedia = vi.fn(() => ({
      matches: true,
      media: '(prefers-color-scheme: dark)',
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }))

    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: matchMedia,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('bootstraps theme state before mounting the themed app', async () => {
    vi.doMock('react-dom/client', () => ({
      __esModule: true,
      default: {
        createRoot: createRootSpy,
      },
      createRoot: createRootSpy,
    }))

    await import('../main')

    expect(window.matchMedia).toHaveBeenCalledWith('(prefers-color-scheme: dark)')
    expect(createRootSpy).toHaveBeenCalledWith(document.getElementById('root'))
    expect(renderSpy).toHaveBeenCalledTimes(1)
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(useThemeStore.getState().resolvedTheme).toBe('dark')

    const renderedTree = renderSpy.mock.calls[0][0] as React.ReactElement

    expect(renderedTree.type).toBe(React.StrictMode)
    expect(renderedTree.props.children.type).toBe(ThemeBootstrap)
  })
})
