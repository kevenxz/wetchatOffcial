import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { WorkbenchShell } from '@/components/workbench'
import { createSystemThemeListener } from '@/store/themeStore'
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
  const syncSystemTheme = useThemeStore((state) => state.syncSystemTheme)

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

    return createSystemThemeListener(mediaQuery, (event) => {
      syncSystemTheme(event.matches)
    })
  }, [syncSystemTheme])

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
