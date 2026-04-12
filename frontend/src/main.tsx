import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import { getAntdTheme } from './theme'
import { useThemeStore } from './store/themeStore'
import './styles/global.css'

function ThemeBootstrap() {
  const resolvedTheme = useThemeStore((state) => state.resolvedTheme)

  return (
    <ConfigProvider theme={getAntdTheme(resolvedTheme)} locale={zhCN}>
      <App />
    </ConfigProvider>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeBootstrap />
  </React.StrictMode>,
)
