import { useEffect } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { WorkbenchShell } from '@/components/workbench'
import { createSystemThemeListener } from '@/store/themeStore'
import { useThemeStore } from '@/store/themeStore'
import AccountConfigPage from '@/pages/AccountConfig'
import ArticleManage from '@/pages/ArticleManage'
import History from '@/pages/History'
import ImageManage from '@/pages/ImageManage'
import LandingPage from '@/pages/Landing'
import LoginPage from '@/pages/Login'
import ModelConfigPage from '@/pages/ModelConfig'
import ReviewCenter from '@/pages/ReviewCenter'
import ScheduleManage from '@/pages/ScheduleManage'
import Stats from '@/pages/Stats'
import StyleConfigPage from '@/pages/StyleConfig'
import TaskCreate from '@/pages/TaskCreate'
import TaskDetail from '@/pages/TaskDetail'
import TaskManage from '@/pages/TaskManage'
import TopicCenter from '@/pages/TopicCenter'
import UserManage from '@/pages/UserManage'
import useAuthStore from '@/store/authStore'

function RequireAuth() {
  const token = useAuthStore((state) => state.token)
  const initialized = useAuthStore((state) => state.initialized)
  const bootstrap = useAuthStore((state) => state.bootstrap)

  useEffect(() => {
    if (!initialized) {
      bootstrap()
    }
  }, [bootstrap, initialized])

  if (!initialized) return null
  if (!token) return <Navigate to="/login" replace />
  return <Outlet />
}

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
        {/* Public surfaces. The landing page is the only front door a jury (or a
            prospective operator) sees, and it must not sit behind auth. */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<WorkbenchShell />}>
            <Route path="/topics" element={<TopicCenter />} />
            <Route path="/task" element={<TaskManage />} />
            <Route path="/task/new" element={<TaskCreate />} />
            <Route path="/task/:id" element={<TaskDetail />} />
            <Route path="/reviews" element={<ReviewCenter />} />
            <Route path="/history" element={<History />} />
            <Route path="/stats" element={<Stats />} />
            <Route path="/articles" element={<ArticleManage />} />
            <Route path="/images" element={<ImageManage />} />
            <Route path="/schedules" element={<ScheduleManage />} />
            <Route path="/settings" element={<StyleConfigPage />} />
            <Route path="/models" element={<ModelConfigPage />} />
            <Route path="/accounts" element={<AccountConfigPage />} />
            <Route path="/users" element={<UserManage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
