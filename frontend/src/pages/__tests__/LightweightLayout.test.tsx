import { render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeEach, expect, test } from 'vitest'
import HeroPanel from '@/components/workbench/HeroPanel'
import WorkbenchShell from '@/components/workbench/WorkbenchShell'
import styles from '@/components/workbench/WorkbenchShell.module.css'
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

  const shell = container.firstElementChild as HTMLElement | null
  const sidebar = shell?.querySelector('aside') as HTMLElement | null
  const main = shell?.querySelector('main') as HTMLElement | null
  const frame = main?.firstElementChild as HTMLElement | null

  expect(shell).toBeInTheDocument()
  expect(sidebar).toBeInTheDocument()
  expect(main).toBeInTheDocument()
  expect(frame).toBeInTheDocument()

  const shellStyle = getComputedStyle(shell as HTMLElement)
  const mainStyle = getComputedStyle(main as HTMLElement)
  const frameStyle = getComputedStyle(frame as HTMLElement)

  expect(shellStyle.getPropertyValue('grid-template-columns')).toBe('216px minmax(0, 1fr)')
  expect(shellStyle.getPropertyValue('background-image')).toBe('none')
  expect(mainStyle.paddingTop).toBe('20px')
  expect(mainStyle.paddingRight).toBe('24px')
  expect(mainStyle.paddingBottom).toBe('20px')
  expect(mainStyle.paddingLeft).toBe('24px')
  expect(frameStyle.getPropertyValue('gap')).toBe('16px')
})

test('renders a compact HeroPanel with spaced title and description', () => {
  const { container } = render(
    <HeroPanel eyebrow="Task" title="Compact header" description="Description text" />,
  )

  const panel = container.querySelector('section') as HTMLElement | null
  const content = panel?.querySelector('[class*="content"]') as HTMLElement | null
  const title = panel?.querySelector('[class*="title"]') as HTMLElement | null
  const description = screen.getByText('Description text')

  expect(panel).toBeInTheDocument()
  expect(content).toBeInTheDocument()
  expect(title).toBeInTheDocument()
  expect(description).toBeInTheDocument()

  const panelStyle = getComputedStyle(panel as HTMLElement)
  const contentStyle = getComputedStyle(content as HTMLElement)
  const titleStyle = getComputedStyle(title as HTMLElement)

  expect(panelStyle.paddingTop).toBe('16px')
  expect(panelStyle.paddingRight).toBe('20px')
  expect(panelStyle.paddingBottom).toBe('16px')
  expect(panelStyle.paddingLeft).toBe('20px')
  expect(contentStyle.gap).toBe('6px')
  expect(parseFloat(titleStyle.fontSize)).toBeLessThan(32)
})

test('omits the description when it is not provided', () => {
  const { container } = render(<HeroPanel eyebrow="Task" title="Compact header" />)

  const panel = container.querySelector('section') as HTMLElement | null

  expect(panel).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Compact header' })).toBeInTheDocument()
  expect(screen.queryByText('Description text')).not.toBeInTheDocument()
})

test('collapses the shell to a single column at the breakpoint', () => {
  const sheet = Array.from(document.styleSheets).find((candidate) => {
    try {
      return Array.from(candidate.cssRules).some(
        (rule) => rule instanceof CSSMediaRule && rule.conditionText.includes('max-width: 1100px'),
      )
    } catch {
      return false
    }
  })

  expect(sheet).toBeDefined()

  const mediaRule = Array.from((sheet as CSSStyleSheet).cssRules).find(
    (rule) => rule instanceof CSSMediaRule && rule.conditionText.includes('max-width: 1100px'),
  ) as CSSMediaRule | undefined

  expect(mediaRule).toBeDefined()

  const shellRule = Array.from(mediaRule!.cssRules).find(
    (rule) => rule instanceof CSSStyleRule && rule.selectorText === `.${styles.shell}`,
  ) as CSSStyleRule | undefined

  expect(shellRule).toBeDefined()
  expect(shellRule!.style.getPropertyValue('grid-template-columns')).toBe('1fr')
})

test('keeps shared surfaces light in light mode', () => {
  const testDir = dirname(fileURLToPath(import.meta.url))
  const variables = readFileSync(resolve(testDir, '../../styles/variables.css'), 'utf8')
  const globalStyles = readFileSync(resolve(testDir, '../../styles/global.css'), 'utf8')

  expect(variables).toContain('--app-surface-muted: #f8fbff;')
  expect(variables).toContain('--app-toolbar-bg: #f8fbff;')
  expect(variables).toContain('--app-list-row-hover: #f3f7fd;')
  expect(variables).toContain('--app-surface-muted: #182235;')
  expect(globalStyles).toContain('padding: 12px 16px;')
  expect(globalStyles).toContain('background: var(--app-toolbar-bg);')
  expect(globalStyles).toContain('border-radius: 16px;')
  expect(globalStyles).toContain('background: var(--app-surface-muted);')
  expect(globalStyles).toContain('background: var(--app-list-row-hover) !important;')
})
