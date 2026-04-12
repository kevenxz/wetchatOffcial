import type { ReactElement, ReactNode } from 'react'
import { ConfigProvider } from 'antd'
import { render, type RenderOptions } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { getAntdTheme } from '@/theme'

type RenderWithRouterOptions = Omit<RenderOptions, 'wrapper'> & {
  route?: string
  entries?: string[]
}

export function renderWithRouter(
  ui: ReactElement,
  { route = '/', entries = [route], ...renderOptions }: RenderWithRouterOptions = {},
) {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <ConfigProvider theme={getAntdTheme('dark')}>
      <MemoryRouter initialEntries={entries}>{children}</MemoryRouter>
    </ConfigProvider>
  )

  return render(ui, { wrapper: Wrapper, ...renderOptions })
}
