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

test('renders grouped form sections with list-style guidance', () => {
  render(<App />)

  expect(screen.getByText('启动一次完整创作流程')).toBeInTheDocument()
  expect(screen.getByText('先点灵感标签补齐关键词，再继续填写表单。')).toBeInTheDocument()
  expect(screen.getByText('基础输入')).toBeInTheDocument()
  expect(screen.getByText('受众与策略')).toBeInTheDocument()
  expect(screen.getByText('风格补充')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '启动创作流程' })).toBeInTheDocument()
  expect(screen.queryByText('创作节奏')).not.toBeInTheDocument()
  expect(screen.queryByText('启动信号')).not.toBeInTheDocument()
})

test('clicking a hot-topic chip fills the keywords field', async () => {
  const user = userEvent.setup()

  render(<App />)

  await user.click(screen.getByText('人工智能'))

  expect(screen.getByLabelText('关键词')).toHaveValue('人工智能')
})
