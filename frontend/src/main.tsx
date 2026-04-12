import React from 'react'
import ReactDOM from 'react-dom/client'
import { ThemeBootstrap, bootstrapThemeFromWindow } from './themeBootstrap'
import './styles/global.css'

bootstrapThemeFromWindow()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeBootstrap />
  </React.StrictMode>,
)
