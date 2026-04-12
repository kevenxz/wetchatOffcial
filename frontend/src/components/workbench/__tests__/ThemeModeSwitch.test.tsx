import { act, fireEvent, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import WorkbenchShell from '../WorkbenchShell'
import { useThemeStore } from '@/store/themeStore'
import { renderWithRouter } from '@/test/renderWithRouter'
import '../../../styles/global.css'

const resolveCssValue = (value: string): string => {
  const trimmed = value.trim()
  const match = trimmed.match(/^var\((--[\w-]+)\)$/)

  if (!match) {
    return trimmed
  }

  const resolved = getComputedStyle(document.documentElement).getPropertyValue(match[1]).trim()

  return resolved === trimmed ? resolved : resolveCssValue(resolved)
}

const resetThemeState = () => {
  act(() => {
    useThemeStore.setState({
      mode: 'system',
      resolvedTheme: 'light',
      initialized: false,
    })
  })

  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.style.colorScheme = ''
}

afterEach(() => {
  resetThemeState()
})

describe('ThemeModeSwitch', () => {
  it('exposes all three theme modes from the shared workbench shell', async () => {
    const user = userEvent.setup()

    act(() => {
      useThemeStore.setState({
        mode: 'system',
        resolvedTheme: 'light',
        initialized: true,
      })
    })

    renderWithRouter(<WorkbenchShell />, { route: '/task' })

    await user.click(screen.getByRole('button', { name: /主题模式/i }))

    expect(screen.getByRole('menuitemradio', { name: /跟随系统/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitemradio', { name: /浅色模式/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitemradio', { name: /深色模式/i })).toBeInTheDocument()
  })

  it('opens on ArrowDown and focuses the first menu item', async () => {
    const user = userEvent.setup()

    act(() => {
      useThemeStore.setState({
        mode: 'light',
        resolvedTheme: 'light',
        initialized: true,
      })
    })

    renderWithRouter(<WorkbenchShell />, { route: '/task' })

    const trigger = screen.getByRole('button', { name: /主题模式/i })
    trigger.focus()
    await user.keyboard('{ArrowDown}')

    const systemItem = screen.getByRole('menuitemradio', { name: /跟随系统/i })
    expect(systemItem).toHaveFocus()
    expect(screen.getByRole('menuitemradio', { name: /浅色模式/i })).toHaveAttribute('aria-checked', 'true')
  })

  it('opens on ArrowUp and focuses the last menu item', async () => {
    const user = userEvent.setup()

    act(() => {
      useThemeStore.setState({
        mode: 'light',
        resolvedTheme: 'light',
        initialized: true,
      })
    })

    renderWithRouter(<WorkbenchShell />, { route: '/task' })

    const trigger = screen.getByRole('button', { name: /主题模式/i })
    trigger.focus()
    await user.keyboard('{ArrowUp}')

    const darkItem = screen.getByRole('menuitemradio', { name: /深色模式/i })
    expect(darkItem).toHaveFocus()
    expect(screen.getByRole('menuitemradio', { name: /浅色模式/i })).toHaveAttribute('aria-checked', 'true')
  })

  it('moves focus into the popup and restores it to the trigger when closed with Escape', async () => {
    const user = userEvent.setup()

    act(() => {
      useThemeStore.setState({
        mode: 'light',
        resolvedTheme: 'light',
        initialized: true,
      })
    })

    renderWithRouter(<WorkbenchShell />, { route: '/task' })

    const trigger = screen.getByRole('button', { name: /主题模式/i })
    trigger.focus()
    await user.keyboard('{ArrowDown}')

    const systemItem = screen.getByRole('menuitemradio', { name: /跟随系统/i })
    expect(systemItem).toHaveFocus()

    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitemradio', { name: /浅色模式/i })).toHaveFocus()

    await user.keyboard('{Escape}')

    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('closes when the user taps outside the popup and restores trigger focus', async () => {
    const user = userEvent.setup()

    act(() => {
      useThemeStore.setState({
        mode: 'system',
        resolvedTheme: 'light',
        initialized: true,
      })
    })

    renderWithRouter(<WorkbenchShell />, { route: '/task' })

    const trigger = screen.getByRole('button', { name: /主题模式/i })
    await user.click(trigger)
    expect(screen.getByRole('menu')).toBeInTheDocument()

    fireEvent.pointerDown(document.body)

    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('updates the theme store when dark mode is selected', async () => {
    const user = userEvent.setup()

    act(() => {
      useThemeStore.setState({
        mode: 'system',
        resolvedTheme: 'light',
        initialized: true,
      })
    })

    renderWithRouter(<WorkbenchShell />, { route: '/task' })

    await user.click(screen.getByRole('button', { name: /主题模式/i }))
    await user.click(screen.getByRole('menuitemradio', { name: /深色模式/i }))

    expect(useThemeStore.getState().mode).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('applies light theme variables to the document root', () => {
    act(() => {
      useThemeStore.getState().setMode('light', false)
    })

    renderWithRouter(<WorkbenchShell />, { route: '/task' })

    const bridgeProbe = document.createElement('div')
    bridgeProbe.style.backgroundColor = 'var(--bg-workbench)'
    document.body.appendChild(bridgeProbe)

    expect(document.documentElement.dataset.theme).toBe('light')
    expect(getComputedStyle(document.documentElement).getPropertyValue('--app-bg').trim()).toBe(
      '#f3f6fb',
    )
    expect(resolveCssValue(getComputedStyle(bridgeProbe).backgroundColor)).toBe('#f3f6fb')

    document.documentElement.removeAttribute('data-theme')

    expect(resolveCssValue(getComputedStyle(bridgeProbe).backgroundColor)).toBe('#f3f6fb')

    bridgeProbe.remove()
  })

  it('renders theme-aware shell surfaces for light and dark themes', () => {
    const getCssRuleForClass = (className: string) => {
      for (const sheet of Array.from(document.styleSheets)) {
        let rules: CSSRuleList

        try {
          rules = sheet.cssRules
        } catch {
          continue
        }

        const matchingRule = Array.from(rules).find(
          (rule) => 'cssText' in rule && rule.cssText.includes(className),
        )

        if (matchingRule && 'cssText' in matchingRule) {
          return matchingRule.cssText
        }
      }

      throw new Error(`Unable to find CSS rule for ${className}`)
    }

    const getCssModuleClass = (element: Element, token?: string) => {
      if (!token) {
        return element.className
      }

      return (
        element.className
          .split(/\s+/)
          .find((className) => className.includes(token)) ?? element.className
      )
    }

    const getSurfaceNodes = (container: HTMLElement) => ({
      shell: container.querySelector('[class*="shell"]'),
      sidebar: container.querySelector('[class*="sidebar"]'),
      brand: container.querySelector('[class*="brand"]'),
      activeNav: container.querySelector('[class*="navLinkActive"]'),
      footer: container.querySelector('[class*="sidebarFooter"]'),
      canvas: container.querySelector('[class*="canvas"]'),
    })

    act(() => {
      useThemeStore.getState().setMode('light', false)
    })

    const lightRender = renderWithRouter(<WorkbenchShell />, { route: '/task' })
    const lightSurfaces = getSurfaceNodes(lightRender.container)

    expect(lightSurfaces.shell).toBeInTheDocument()
    expect(lightSurfaces.sidebar).toBeInTheDocument()
    expect(lightSurfaces.brand).toBeInTheDocument()
    expect(lightSurfaces.activeNav).toBeInTheDocument()
    expect(lightSurfaces.footer).toBeInTheDocument()
    expect(lightSurfaces.canvas).toBeInTheDocument()

    const shellRule = getCssRuleForClass(getCssModuleClass(lightSurfaces.shell!))
    const sidebarRule = getCssRuleForClass(getCssModuleClass(lightSurfaces.sidebar!))
    const brandRule = getCssRuleForClass(getCssModuleClass(lightSurfaces.brand!))
    const activeNavRule = getCssRuleForClass(getCssModuleClass(lightSurfaces.activeNav!, 'navLinkActive'))
    const footerRule = getCssRuleForClass(getCssModuleClass(lightSurfaces.footer!))
    const canvasRule = getCssRuleForClass(getCssModuleClass(lightSurfaces.canvas!))

    expect(shellRule).toContain('var(--app-bg)')
    expect(shellRule).toContain('var(--app-bg-gradient)')
    expect(sidebarRule).toContain('var(--app-surface)')
    expect(sidebarRule).toContain('var(--app-border)')
    expect(brandRule).toContain('var(--app-surface-strong)')
    expect(brandRule).toContain('var(--app-border)')
    expect(activeNavRule).toContain('var(--app-primary-bg)')
    expect(activeNavRule).toContain('var(--app-surface-strong)')
    expect(footerRule).toContain('var(--text-tertiary)')
    expect(canvasRule).toContain('var(--app-surface)')
    expect(canvasRule).toContain('var(--app-border)')

    act(() => {
      useThemeStore.getState().setMode('dark', true)
    })

    const darkRender = renderWithRouter(<WorkbenchShell />, { route: '/task' })
    const darkSurfaces = getSurfaceNodes(darkRender.container)

    expect(darkSurfaces.sidebar).toBeInTheDocument()
    expect(darkSurfaces.brand).toBeInTheDocument()
    expect(darkSurfaces.activeNav).toBeInTheDocument()
    expect(darkSurfaces.footer).toBeInTheDocument()
    expect(darkSurfaces.canvas).toBeInTheDocument()
  })
})
