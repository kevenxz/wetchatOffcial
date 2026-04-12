import { beforeEach, expect, test } from 'vitest'
import WorkbenchShell from '@/components/workbench/WorkbenchShell'
import { renderWithRouter } from '@/test/renderWithRouter'

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
})

test('renders a fixed 216px sidebar shell with compact main spacing', () => {
  const { container } = renderWithRouter(<WorkbenchShell />, { route: '/task', theme: 'light' })

  const shell = container.querySelector('[class*="shell"]') as HTMLElement | null
  const sidebar = container.querySelector('[class*="sidebar"]') as HTMLElement | null
  const main = container.querySelector('[class*="main"]') as HTMLElement | null
  const frame = container.querySelector('[class*="frame"]') as HTMLElement | null

  expect(shell).toBeInTheDocument()
  expect(sidebar).toBeInTheDocument()
  expect(main).toBeInTheDocument()
  expect(frame).toBeInTheDocument()
  expect(getComputedStyle(shell as HTMLElement).gridTemplateColumns).toContain('216px')
  expect(getComputedStyle(main as HTMLElement).padding).toBe('20px 24px')
  expect(getComputedStyle(frame as HTMLElement).gap).toBe('16px')
})
