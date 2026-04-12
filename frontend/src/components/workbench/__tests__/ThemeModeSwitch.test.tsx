import { act, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import WorkbenchShell from '../WorkbenchShell'
import { useThemeStore } from '@/store/themeStore'
import { renderWithRouter } from '@/test/renderWithRouter'

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
})
