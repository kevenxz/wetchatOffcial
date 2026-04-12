import userEvent from '@testing-library/user-event'
import { render, screen } from '@testing-library/react'
import { beforeEach, expect, test } from 'vitest'
import App from '@/App'

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
  window.history.replaceState({}, '', '/task')
})

test('renders the studio landing page for task creation', () => {
  render(<App />)

  expect(screen.getByText('启动一次完整创作流程')).toBeInTheDocument()
  expect(screen.getByText('热点灵感')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '启动创作流程' })).toBeInTheDocument()
  expect(screen.getByTestId('task-create-grid')).toHaveClass('task-create-grid')
})

test('clicking a hot-topic chip fills the keywords field', async () => {
  const user = userEvent.setup()

  render(<App />)

  await user.click(screen.getByText('人工智能'))

  expect(screen.getByLabelText('关键词')).toHaveValue('人工智能')
})
