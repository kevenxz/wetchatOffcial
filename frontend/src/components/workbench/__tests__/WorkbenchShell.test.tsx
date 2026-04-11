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

test('renders the brand studio shell for the task creation route', async () => {
  render(<App />)

  expect((await screen.findAllByText('Brand Studio')).length).toBeGreaterThan(0)
  expect(screen.getByRole('link', { name: '创作台' })).toBeInTheDocument()
  expect(screen.getByText('任务创建')).toBeInTheDocument()
})
