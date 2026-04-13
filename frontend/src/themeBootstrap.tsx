import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import { getAntdTheme } from './theme'
import { bootstrapThemeStore, useThemeStore } from './store/themeStore'

export function bootstrapThemeFromWindow() {
  const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  return bootstrapThemeStore(systemPrefersDark)
}

export function ThemeBootstrap() {
  const resolvedTheme = useThemeStore((state) => state.resolvedTheme)

  return (
    <ConfigProvider theme={getAntdTheme(resolvedTheme)} locale={zhCN}>
      <App />
    </ConfigProvider>
  )
}
