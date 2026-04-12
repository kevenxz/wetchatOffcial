import { create } from 'zustand'

export type ThemeMode = 'system' | 'light' | 'dark'
export type ResolvedTheme = 'light' | 'dark'

export const STORAGE_KEY = 'app-theme-mode'

const isThemeMode = (value: string | null): value is ThemeMode =>
  value === 'system' || value === 'light' || value === 'dark'

export function getStoredThemeMode(): ThemeMode {
  const value = window.localStorage.getItem(STORAGE_KEY)
  return isThemeMode(value) ? value : 'system'
}

export function resolveThemeMode(mode: ThemeMode, systemPrefersDark: boolean): ResolvedTheme {
  if (mode === 'system') {
    return systemPrefersDark ? 'dark' : 'light'
  }

  return mode
}

export function applyResolvedTheme(theme: ResolvedTheme) {
  document.documentElement.dataset.theme = theme
  document.documentElement.style.colorScheme = theme
}

export function createSystemThemeListener(
  mediaQuery: MediaQueryList,
  listener: (event: MediaQueryListEvent) => void,
) {
  mediaQuery.addEventListener('change', listener)

  return () => {
    mediaQuery.removeEventListener('change', listener)
  }
}

type ThemeState = {
  mode: ThemeMode
  resolvedTheme: ResolvedTheme
  initialized: boolean
  initialize: (systemPrefersDark: boolean) => void
  setMode: (mode: ThemeMode, systemPrefersDark: boolean) => void
  syncSystemTheme: (systemPrefersDark: boolean) => void
}

export const useThemeStore = create<ThemeState>()((set) => ({
  mode: 'system',
  resolvedTheme: 'light',
  initialized: false,
  initialize: (systemPrefersDark) => {
    const mode = getStoredThemeMode()
    const resolvedTheme = resolveThemeMode(mode, systemPrefersDark)

    window.localStorage.setItem(STORAGE_KEY, mode)
    applyResolvedTheme(resolvedTheme)
    set({ mode, resolvedTheme, initialized: true })
  },
  setMode: (mode, systemPrefersDark) => {
    const resolvedTheme = resolveThemeMode(mode, systemPrefersDark)

    window.localStorage.setItem(STORAGE_KEY, mode)
    applyResolvedTheme(resolvedTheme)
    set({ mode, resolvedTheme, initialized: true })
  },
  syncSystemTheme: (systemPrefersDark) =>
    set((state) => {
      if (state.mode !== 'system') {
        return state
      }

      const resolvedTheme = resolveThemeMode('system', systemPrefersDark)
      applyResolvedTheme(resolvedTheme)
      return { ...state, resolvedTheme }
    }),
}))
