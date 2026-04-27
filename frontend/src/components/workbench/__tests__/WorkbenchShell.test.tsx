import { screen } from '@testing-library/react'
import { beforeEach, expect, test } from 'vitest'
import WorkbenchShell from '@/components/workbench/WorkbenchShell'
import useAuthStore from '@/store/authStore'
import { renderWithRouter } from '@/test/renderWithRouter'

beforeEach(() => {
  useAuthStore.setState({
    token: 'test-token',
    user: {
      user_id: 'u-1',
      username: 'admin',
      display_name: '管理员',
      role: 'admin',
      enabled: true,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: null,
      last_login_at: null,
    },
    initialized: true,
  })
})

test('renders the AI content factory shell for task management', () => {
  renderWithRouter(<WorkbenchShell />, { route: '/task' })

  expect(screen.getByText('AI内容工厂')).toBeInTheDocument()
  expect(screen.getByText('智能公众号生产系统')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '任务管理' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '任务管理' })).toBeInTheDocument()
})

test('keeps system accounts as a standalone navigation entry', () => {
  renderWithRouter(<WorkbenchShell />, { route: '/task' })

  const systemAccountLink = screen.getByRole('link', { name: '系统账号' })

  expect(systemAccountLink).toHaveAttribute('href', '/users')
  expect(screen.queryByRole('link', { name: '系统管理' })).not.toBeInTheDocument()
})
