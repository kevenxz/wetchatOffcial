import { render, screen } from '@testing-library/react'
import { beforeEach, expect, test } from 'vitest'
import App from '@/App'
import useAuthStore from '@/store/authStore'

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  })
  localStorage.setItem('wechat_project_access_token', 'test-token')
  useAuthStore.setState({
    token: 'test-token',
    user: {
      user_id: 'u-1',
      username: 'admin',
      display_name: 'Admin',
      role: 'admin',
      enabled: true,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: null,
      last_login_at: null,
    },
    initialized: true,
  })
  window.history.replaceState({}, '', '/task')
})

test('renders the brand studio shell for the task creation route', async () => {
  render(<App />)

  expect((await screen.findAllByText('Brand Studio')).length).toBeGreaterThan(0)
  expect(screen.getByRole('link', { name: '创作台' })).toBeInTheDocument()
  expect(screen.getByText('任务创建')).toBeInTheDocument()
})
