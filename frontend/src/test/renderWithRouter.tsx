import type { ReactElement, ReactNode } from 'react'
import { render, type RenderOptions } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

type RenderWithRouterOptions = Omit<RenderOptions, 'wrapper'> & {
  route?: string
  entries?: string[]
}

export function renderWithRouter(
  ui: ReactElement,
  { route = '/', entries = [route], ...renderOptions }: RenderWithRouterOptions = {},
) {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={entries}>{children}</MemoryRouter>
  )

  return render(ui, { wrapper: Wrapper, ...renderOptions })
}
