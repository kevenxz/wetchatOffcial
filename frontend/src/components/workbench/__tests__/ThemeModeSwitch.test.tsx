import { act, fireEvent, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import WorkbenchShell from '../WorkbenchShell'
import { useThemeStore } from '@/store/themeStore'
import { renderWithRouter } from '@/test/renderWithRouter'
import '../../../styles/global.css'

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

    expect(document.documentElement.dataset.theme).toBe('light')
    expect(getComputedStyle(document.documentElement).getPropertyValue('--app-bg').trim()).toBe(
      '#f3f6fb',
    )
    expect(getComputedStyle(document.documentElement).getPropertyValue('--bg-workbench').trim()).toBe(
      'var(--app-bg)',
    )
  })
})
