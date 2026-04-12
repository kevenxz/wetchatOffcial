# Global Theme And Ant Design Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a global `system | light | dark` theme system for the frontend, unify Ant Design tokens with app-level CSS variables, and add a persistent theme switcher without rewriting existing business shells.

**Architecture:** Add a small theme state layer that resolves `system` into an effective light or dark theme, persist the user preference in local storage, and expose the resolved theme to both Ant Design `ConfigProvider` and the document root `data-theme` attribute. Update the global style variables and the shared workbench shell to consume the resolved theme so the whole app switches consistently while preserving the current custom business layout.

**Tech Stack:** React 18, TypeScript, Vite, Ant Design 5, Zustand, Vitest, Testing Library, CSS Modules, global CSS variables

---

### File Map

**Create:**
- `frontend/src/store/themeStore.ts`
- `frontend/src/components/workbench/ThemeModeSwitch.tsx`
- `frontend/src/components/workbench/ThemeModeSwitch.module.css`
- `frontend/src/store/__tests__/themeStore.test.ts`
- `frontend/src/components/workbench/__tests__/ThemeModeSwitch.test.tsx`

**Modify:**
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/theme.ts`
- `frontend/src/styles/variables.css`
- `frontend/src/styles/global.css`
- `frontend/src/components/workbench/WorkbenchShell.tsx`
- `frontend/src/components/workbench/WorkbenchShell.module.css`
- `frontend/src/components/workbench/index.ts`
- `frontend/src/test/renderWithRouter.tsx`

**Verify With Existing Commands:**
- `npm run test -- ThemeModeSwitch`
- `npm run test -- themeStore`
- `npm run test -- WorkbenchShell`
- `npm run build`

### Task 1: Add Theme State Helpers And Tests

**Files:**
- Create: `frontend/src/store/themeStore.ts`
- Create: `frontend/src/store/__tests__/themeStore.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- themeStore`

Expected: FAIL with a module resolution error for `frontend/src/store/themeStore.ts` or missing exported helpers.

- [ ] **Step 3: Write minimal implementation**

```ts
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
  return () => mediaQuery.removeEventListener('change', listener)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- themeStore`

Expected: PASS with all helper behavior tests green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/themeStore.ts frontend/src/store/__tests__/themeStore.test.ts
git commit -m "新增主题状态基础能力"
```

### Task 2: Add Zustand Theme Store With Initialization

**Files:**
- Modify: `frontend/src/store/themeStore.ts`
- Modify: `frontend/src/store/__tests__/themeStore.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { act } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useThemeStore } from '../themeStore'

describe('useThemeStore', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    document.documentElement.style.colorScheme = ''
    useThemeStore.setState({
      mode: 'system',
      resolvedTheme: 'light',
      initialized: false,
    })
  })

  it('initializes from system preference when storage is empty', () => {
    act(() => {
      useThemeStore.getState().initialize(true)
    })

    expect(useThemeStore.getState().mode).toBe('system')
    expect(useThemeStore.getState().resolvedTheme).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('persists explicit theme selections', () => {
    act(() => {
      useThemeStore.getState().setMode('dark', false)
    })

    expect(useThemeStore.getState().mode).toBe('dark')
    expect(useThemeStore.getState().resolvedTheme).toBe('dark')
    expect(localStorage.getItem('app-theme-mode')).toBe('dark')
  })

  it('updates the resolved theme when system mode receives a new preference', () => {
    act(() => {
      useThemeStore.getState().initialize(false)
      useThemeStore.getState().syncSystemTheme(true)
    })

    expect(useThemeStore.getState().resolvedTheme).toBe('dark')
  })

  it('ignores system updates when mode is explicitly selected', () => {
    act(() => {
      useThemeStore.getState().setMode('light', false)
      useThemeStore.getState().syncSystemTheme(true)
    })

    expect(useThemeStore.getState().resolvedTheme).toBe('light')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- themeStore`

Expected: FAIL because `useThemeStore`, `initialize`, `setMode`, or `syncSystemTheme` do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```ts
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
  return () => mediaQuery.removeEventListener('change', listener)
}

type ThemeState = {
  mode: ThemeMode
  resolvedTheme: ResolvedTheme
  initialized: boolean
  initialize: (systemPrefersDark: boolean) => void
  setMode: (mode: ThemeMode, systemPrefersDark: boolean) => void
  syncSystemTheme: (systemPrefersDark: boolean) => void
}

export const useThemeStore = create<ThemeState>((set) => ({
  mode: 'system',
  resolvedTheme: 'light',
  initialized: false,
  initialize: (systemPrefersDark) => {
    const mode = getStoredThemeMode()
    const resolvedTheme = resolveThemeMode(mode, systemPrefersDark)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- themeStore`

Expected: PASS with helper tests plus store behavior tests green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/themeStore.ts frontend/src/store/__tests__/themeStore.test.ts
git commit -m "接入全局主题状态仓库"
```

### Task 3: Add Dynamic Ant Design Theme Tokens

**Files:**
- Modify: `frontend/src/theme.ts`
- Modify: `frontend/src/store/__tests__/themeStore.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { getAntdTheme } from '../../theme'

it('returns different layout backgrounds for light and dark themes', () => {
  const lightTheme = getAntdTheme('light')
  const darkTheme = getAntdTheme('dark')

  expect(lightTheme.token?.colorBgLayout).toBe('#f3f6fb')
  expect(darkTheme.token?.colorBgLayout).toBe('#0b1020')
  expect(lightTheme.components?.Layout?.siderBg).toBe('#ffffff')
  expect(darkTheme.components?.Layout?.siderBg).toBe('#0e1627')
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- themeStore`

Expected: FAIL because `getAntdTheme` does not exist or still returns a single static theme.

- [ ] **Step 3: Write minimal implementation**

```ts
import { theme as antdTheme, type ThemeConfig } from 'antd'
import type { ResolvedTheme } from './store/themeStore'

const sharedToken = {
  colorPrimary: '#7dd3fc',
  colorSuccess: '#34d399',
  colorWarning: '#fbbf24',
  colorError: '#f87171',
  colorInfo: '#7dd3fc',
  fontFamily:
    "'Inter', 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', sans-serif",
  fontFamilyCode: "'JetBrains Mono', 'SFMono-Regular', Consolas, monospace",
  fontWeightStrong: 600,
  fontSize: 14,
  fontSizeSM: 12,
  fontSizeLG: 16,
  fontSizeXL: 20,
  fontSizeHeading1: 32,
  fontSizeHeading2: 26,
  fontSizeHeading3: 22,
  fontSizeHeading4: 18,
  fontSizeHeading5: 16,
  lineHeight: 1.6,
  borderRadius: 10,
  borderRadiusSM: 6,
  borderRadiusLG: 14,
  motionDurationFast: '0.1s',
  motionDurationMid: '0.2s',
  motionDurationSlow: '0.3s',
} as const

const lightTheme: ThemeConfig = {
  algorithm: antdTheme.defaultAlgorithm,
  token: {
    ...sharedToken,
    colorBgLayout: '#f3f6fb',
    colorBgContainer: '#ffffff',
    colorBgElevated: '#ffffff',
    colorBorder: '#d8e1ee',
    colorBorderSecondary: '#e5ebf5',
    colorSplit: '#e5ebf5',
    colorText: '#0f172a',
    colorTextSecondary: '#516074',
    colorTextTertiary: '#738196',
    colorTextQuaternary: '#94a3b8',
    colorFillSecondary: 'rgba(15, 23, 42, 0.05)',
    colorFillQuaternary: 'rgba(15, 23, 42, 0.03)',
    colorPrimaryBg: 'rgba(125, 211, 252, 0.16)',
    colorPrimaryBgHover: 'rgba(125, 211, 252, 0.24)',
    colorPrimaryBorder: 'rgba(56, 189, 248, 0.28)',
    colorPrimaryBorderHover: 'rgba(56, 189, 248, 0.4)',
    colorLink: '#0284c7',
    colorLinkHover: '#0369a1',
    boxShadow:
      '0 18px 40px -24px rgba(15, 23, 42, 0.18), 0 10px 24px -18px rgba(15, 23, 42, 0.16)',
    boxShadowSecondary:
      '0 12px 28px -20px rgba(15, 23, 42, 0.12), 0 6px 16px -10px rgba(15, 23, 42, 0.1)',
  },
  components: {
    Layout: {
      siderBg: '#ffffff',
      triggerBg: '#eff5fb',
    },
    Menu: {
      itemBg: 'transparent',
      itemSelectedBg: 'rgba(125, 211, 252, 0.14)',
      itemSelectedColor: '#0f172a',
    },
  },
}

const darkTheme: ThemeConfig = {
  algorithm: antdTheme.darkAlgorithm,
  token: {
    ...sharedToken,
    colorBgLayout: '#0b1020',
    colorBgContainer: '#121a2b',
    colorBgElevated: '#182235',
    colorBorder: '#273449',
    colorBorderSecondary: '#1f2a3d',
    colorSplit: '#1f2a3d',
    colorText: '#e5edf9',
    colorTextSecondary: '#a6b4c9',
    colorTextTertiary: '#71829e',
    colorTextQuaternary: '#4b5b75',
    colorFillSecondary: 'rgba(125, 211, 252, 0.08)',
    colorFillQuaternary: 'rgba(255, 255, 255, 0.04)',
    colorPrimaryBg: 'rgba(125, 211, 252, 0.12)',
    colorPrimaryBgHover: 'rgba(125, 211, 252, 0.18)',
    colorPrimaryBorder: 'rgba(125, 211, 252, 0.32)',
    colorPrimaryBorderHover: 'rgba(125, 211, 252, 0.5)',
    colorLink: '#7dd3fc',
    colorLinkHover: '#a5f3fc',
    boxShadow:
      '0 18px 40px -24px rgba(2, 8, 23, 0.85), 0 10px 24px -18px rgba(2, 8, 23, 0.7)',
    boxShadowSecondary:
      '0 12px 28px -20px rgba(2, 8, 23, 0.72), 0 6px 16px -10px rgba(2, 8, 23, 0.56)',
  },
  components: {
    Layout: {
      siderBg: '#0e1627',
      triggerBg: '#162033',
    },
    Menu: {
      darkItemBg: '#0e1627',
      darkSubMenuItemBg: '#0b1020',
      darkItemSelectedBg: 'rgba(125, 211, 252, 0.18)',
    },
  },
}

export function getAntdTheme(resolvedTheme: ResolvedTheme): ThemeConfig {
  return resolvedTheme === 'light' ? lightTheme : darkTheme
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- themeStore`

Expected: PASS with both light and dark token assertions green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/theme.ts frontend/src/store/__tests__/themeStore.test.ts
git commit -m "补充明暗双主题 token"
```

### Task 4: Wire Theme Initialization Into App Bootstrap

**Files:**
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/test/renderWithRouter.tsx`
- Modify: `frontend/src/store/__tests__/themeStore.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { render, screen } from '@testing-library/react'
import App from '../../App'

it('renders the app after applying the stored theme mode', () => {
  localStorage.setItem('app-theme-mode', 'dark')

  render(<App />)

  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(screen.getByText(/brand studio/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- themeStore`

Expected: FAIL because `App` does not initialize the theme store or apply the root theme.

- [ ] **Step 3: Write minimal implementation**

Update `frontend/src/App.tsx`:

```tsx
import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { WorkbenchShell } from '@/components/workbench'
import { useThemeStore } from '@/store/themeStore'
import AccountConfigPage from '@/pages/AccountConfig'
import ArticleManage from '@/pages/ArticleManage'
import History from '@/pages/History'
import ModelConfigPage from '@/pages/ModelConfig'
import ScheduleManage from '@/pages/ScheduleManage'
import StyleConfigPage from '@/pages/StyleConfig'
import TaskCreate from '@/pages/TaskCreate'
import TaskDetail from '@/pages/TaskDetail'

export default function App() {
  const initialize = useThemeStore((state) => state.initialize)
  const syncSystemTheme = useThemeStore((state) => state.syncSystemTheme)

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

    initialize(mediaQuery.matches)

    const handleChange = (event: MediaQueryListEvent) => {
      syncSystemTheme(event.matches)
    }

    mediaQuery.addEventListener('change', handleChange)

    return () => {
      mediaQuery.removeEventListener('change', handleChange)
    }
  }, [initialize, syncSystemTheme])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/task" replace />} />
        <Route element={<WorkbenchShell />}>
          <Route path="/task" element={<TaskCreate />} />
          <Route path="/task/:id" element={<TaskDetail />} />
          <Route path="/history" element={<History />} />
          <Route path="/articles" element={<ArticleManage />} />
          <Route path="/schedules" element={<ScheduleManage />} />
          <Route path="/settings" element={<StyleConfigPage />} />
          <Route path="/models" element={<ModelConfigPage />} />
          <Route path="/accounts" element={<AccountConfigPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
```

Update `frontend/src/main.tsx`:

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import { getAntdTheme } from './theme'
import { useThemeStore } from './store/themeStore'
import './styles/global.css'

function ThemeProviderApp() {
  const resolvedTheme = useThemeStore((state) => state.resolvedTheme)

  return (
    <ConfigProvider theme={getAntdTheme(resolvedTheme)} locale={zhCN}>
      <App />
    </ConfigProvider>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProviderApp />
  </React.StrictMode>,
)
```

Update `frontend/src/test/renderWithRouter.tsx`:

```tsx
import type { ReactElement, ReactNode } from 'react'
import { ConfigProvider } from 'antd'
import { render, type RenderOptions } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { getAntdTheme } from '@/theme'

type RenderWithRouterOptions = Omit<RenderOptions, 'wrapper'> & {
  route?: string
  entries?: string[]
}

export function renderWithRouter(
  ui: ReactElement,
  { route = '/', entries = [route], ...renderOptions }: RenderWithRouterOptions = {},
) {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={entries}>
      <ConfigProvider theme={getAntdTheme('dark')}>{children}</ConfigProvider>
    </MemoryRouter>
  )

  return render(ui, { wrapper: Wrapper, ...renderOptions })
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- themeStore`

Expected: PASS with the app render test confirming theme initialization.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/main.tsx frontend/src/App.tsx frontend/src/test/renderWithRouter.tsx frontend/src/store/__tests__/themeStore.test.ts
git commit -m "打通应用启动主题初始化"
```

### Task 5: Add Theme Switcher UI To The Shared Workbench Shell

**Files:**
- Create: `frontend/src/components/workbench/ThemeModeSwitch.tsx`
- Create: `frontend/src/components/workbench/ThemeModeSwitch.module.css`
- Modify: `frontend/src/components/workbench/WorkbenchShell.tsx`
- Modify: `frontend/src/components/workbench/WorkbenchShell.module.css`
- Modify: `frontend/src/components/workbench/index.ts`
- Create: `frontend/src/components/workbench/__tests__/ThemeModeSwitch.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithRouter } from '@/test/renderWithRouter'
import { useThemeStore } from '@/store/themeStore'
import WorkbenchShell from '../WorkbenchShell'

describe('ThemeModeSwitch', () => {
  it('shows the current mode and lets the user choose dark mode', async () => {
    const user = userEvent.setup()

    useThemeStore.setState({
      mode: 'system',
      resolvedTheme: 'light',
      initialized: true,
    })

    renderWithRouter(<WorkbenchShell />, { route: '/task' })

    await user.click(screen.getByRole('button', { name: /主题模式/i }))
    await user.click(screen.getByRole('menuitemradio', { name: /深色模式/i }))

    expect(useThemeStore.getState().mode).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- ThemeModeSwitch`

Expected: FAIL because there is no theme switch component or no accessible control labeled `主题模式`.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/workbench/ThemeModeSwitch.tsx`:

```tsx
import { CheckOutlined, DesktopOutlined, MoonOutlined, SunOutlined } from '@ant-design/icons'
import { Button, Dropdown, Space, Typography } from 'antd'
import type { MenuProps } from 'antd'
import { useThemeStore, type ThemeMode } from '@/store/themeStore'
import styles from './ThemeModeSwitch.module.css'

const modeLabelMap: Record<ThemeMode, string> = {
  system: '跟随系统',
  light: '浅色模式',
  dark: '深色模式',
}

export default function ThemeModeSwitch() {
  const mode = useThemeStore((state) => state.mode)
  const setMode = useThemeStore((state) => state.setMode)

  const onClick: MenuProps['onClick'] = ({ key }) => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    setMode(key as ThemeMode, mediaQuery.matches)
  }

  const items: MenuProps['items'] = [
    { key: 'system', icon: <DesktopOutlined />, label: '跟随系统' },
    { key: 'light', icon: <SunOutlined />, label: '浅色模式' },
    { key: 'dark', icon: <MoonOutlined />, label: '深色模式' },
  ].map((item) => ({
    ...item,
    extra: item.key === mode ? <CheckOutlined aria-hidden="true" /> : undefined,
  }))

  return (
    <Dropdown
      menu={{
        items,
        selectable: true,
        selectedKeys: [mode],
        onClick,
      }}
      trigger={['click']}
    >
      <Button className={styles.trigger} type="text" aria-label="主题模式">
        <Space size={8}>
          <Typography.Text className={styles.triggerLabel}>主题</Typography.Text>
          <Typography.Text className={styles.triggerValue}>{modeLabelMap[mode]}</Typography.Text>
        </Space>
      </Button>
    </Dropdown>
  )
}
```

Create `frontend/src/components/workbench/ThemeModeSwitch.module.css`:

```css
.trigger {
  height: auto;
  padding: 10px 14px;
  border: 1px solid var(--app-border);
  border-radius: 999px;
  background: var(--app-surface);
  box-shadow: var(--app-shadow-sm);
}

.triggerLabel {
  color: var(--app-text-secondary);
}

.triggerValue {
  color: var(--app-text);
  font-weight: 600;
}
```

Update `frontend/src/components/workbench/WorkbenchShell.tsx`:

```tsx
import ThemeModeSwitch from './ThemeModeSwitch'

<div className={styles.toolbar}>
  <div className={styles.toolbarSpacer} />
  <ThemeModeSwitch />
</div>
```

Update `frontend/src/components/workbench/WorkbenchShell.module.css`:

```css
.toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
}

.toolbarSpacer {
  flex: 1;
}
```

Update `frontend/src/components/workbench/index.ts`:

```ts
export { default as ThemeModeSwitch } from './ThemeModeSwitch'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- ThemeModeSwitch`

Expected: PASS with menu interaction updating the store and root theme.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/workbench/ThemeModeSwitch.tsx frontend/src/components/workbench/ThemeModeSwitch.module.css frontend/src/components/workbench/WorkbenchShell.tsx frontend/src/components/workbench/WorkbenchShell.module.css frontend/src/components/workbench/index.ts frontend/src/components/workbench/__tests__/ThemeModeSwitch.test.tsx
git commit -m "新增全局主题切换入口"
```

### Task 6: Convert CSS Variables And Global Styles To Support Both Themes

**Files:**
- Modify: `frontend/src/styles/variables.css`
- Modify: `frontend/src/styles/global.css`
- Modify: `frontend/src/components/workbench/__tests__/ThemeModeSwitch.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
it('applies light theme variables to the document root', () => {
  useThemeStore.setState({
    mode: 'light',
    resolvedTheme: 'light',
    initialized: true,
  })
  document.documentElement.dataset.theme = 'light'

  renderWithRouter(<WorkbenchShell />, { route: '/task' })

  expect(document.documentElement.dataset.theme).toBe('light')
  expect(getComputedStyle(document.documentElement).getPropertyValue('--app-bg').trim()).toBe('#f3f6fb')
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- ThemeModeSwitch`

Expected: FAIL because `variables.css` does not define `--app-bg` or only exposes dark-only variables.

- [ ] **Step 3: Write minimal implementation**

Update `frontend/src/styles/variables.css` with shared variables plus both `:root[data-theme='light']` and `:root[data-theme='dark']` blocks defining `--app-bg`, `--app-bg-gradient`, `--app-surface`, `--app-surface-strong`, `--app-border`, `--app-border-strong`, `--app-text`, `--app-text-secondary`, `--app-text-tertiary`, and `--app-text-disabled`.

Update `frontend/src/styles/global.css` so:

```css
body {
  color: var(--app-text);
  background: var(--app-bg-gradient);
  background-color: var(--app-bg);
  transition:
    color var(--transition-base),
    background-color var(--transition-base);
}

h1,
h2,
h3,
h4,
h5,
h6 {
  color: var(--app-text);
}

.text-secondary {
  color: var(--app-text-secondary);
}

.text-disabled {
  color: var(--app-text-disabled);
}

.backstage-surface-card {
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  box-shadow: var(--app-shadow-md);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- ThemeModeSwitch`

Expected: PASS with the root CSS variable assertion green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/styles/variables.css frontend/src/styles/global.css frontend/src/components/workbench/__tests__/ThemeModeSwitch.test.tsx
git commit -m "统一全局主题变量与基础样式"
```

### Task 7: Make Workbench Shell Surfaces Theme-Aware

**Files:**
- Modify: `frontend/src/components/workbench/WorkbenchShell.module.css`
- Modify: `frontend/src/components/workbench/__tests__/ThemeModeSwitch.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
it('renders theme-aware shell surfaces', () => {
  useThemeStore.setState({
    mode: 'dark',
    resolvedTheme: 'dark',
    initialized: true,
  })

  const { container } = renderWithRouter(<WorkbenchShell />, { route: '/task' })

  expect(container.querySelector('[class*="sidebar"]')).toBeInTheDocument()
  expect(container.querySelector('[class*="canvas"]')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- ThemeModeSwitch`

Expected: FAIL after you strengthen assertions around theme-aware shell hooks not present yet.

- [ ] **Step 3: Write minimal implementation**

Update `frontend/src/components/workbench/WorkbenchShell.module.css` so `.shell`, `.sidebar`, `.brand`, `.navLink`, `.navLinkActive`, `.navIcon`, `.sidebarFooter`, and `.canvas` all stop using hard-coded dark colors and instead consume `--app-bg-gradient`, `--app-surface`, `--app-surface-strong`, `--app-border`, `--app-border-strong`, `--app-text`, `--app-text-secondary`, `--app-text-tertiary`, and `--app-primary`.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- ThemeModeSwitch`

Expected: PASS with the shell still rendering and the earlier switcher tests still green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/workbench/WorkbenchShell.module.css frontend/src/components/workbench/__tests__/ThemeModeSwitch.test.tsx
git commit -m "让工作台外壳适配双主题"
```

### Task 8: Run Final Verification

**Files:**
- Modify: none

- [ ] **Step 1: Run focused theme tests**

Run: `npm run test -- themeStore`

Expected: PASS with helper, store, and bootstrap tests green.

- [ ] **Step 2: Run switcher and shell tests**

Run: `npm run test -- ThemeModeSwitch`

Expected: PASS with theme switch and shell surface tests green.

- [ ] **Step 3: Run a broader shared-shell regression test**

Run: `npm run test -- WorkbenchShell`

Expected: PASS or `No test files found`, depending on filename matches.

- [ ] **Step 4: Run production build**

Run: `npm run build`

Expected: PASS with Vite production assets compiled successfully.

- [ ] **Step 5: Commit final integrated changes**

```bash
git add frontend/src/main.tsx frontend/src/App.tsx frontend/src/theme.ts frontend/src/styles/variables.css frontend/src/styles/global.css frontend/src/store/themeStore.ts frontend/src/store/__tests__/themeStore.test.ts frontend/src/components/workbench/ThemeModeSwitch.tsx frontend/src/components/workbench/ThemeModeSwitch.module.css frontend/src/components/workbench/WorkbenchShell.tsx frontend/src/components/workbench/WorkbenchShell.module.css frontend/src/components/workbench/index.ts frontend/src/components/workbench/__tests__/ThemeModeSwitch.test.tsx frontend/src/test/renderWithRouter.tsx
git commit -m "实现全站明暗主题切换"
```

### Self-Review

**Spec coverage**
- Global `system | light | dark` mode: Tasks 1, 2, 4, 5
- First load follows system and can be overridden manually: Tasks 2, 4, 5
- Ant Design token unification: Task 3
- CSS variable unification for custom shells: Tasks 6, 7
- Shared global switch entry: Task 5
- Preserve existing business shell structure: Task 7
- Verification and non-regression: Task 8

**Placeholder scan**
- No `TODO`, `TBD`, or “similar to previous step” placeholders remain.
- Every task contains concrete files, commands, and expected outcomes.

**Type consistency**
- Theme mode names are consistently `system | light | dark`.
- Effective theme names are consistently `light | dark`.
- Store method names are consistently `initialize`, `setMode`, and `syncSystemTheme`.
```
