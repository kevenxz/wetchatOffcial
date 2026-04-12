import { beforeEach, expect, test } from 'vitest'
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

test('renders a compact page header instead of a tall hero panel', () => {
  const { container } = renderWithRouter(<WorkbenchShell />, { route: '/task', theme: 'light' })

  const panel = container.querySelector('[class*="panel"]') as HTMLElement | null
  const title = panel?.querySelector('h1') as HTMLElement | null

  expect(panel).toBeInTheDocument()
  expect(title).toBeInTheDocument()

  const panelStyle = getComputedStyle(panel as HTMLElement)
  const titleStyle = getComputedStyle(title as HTMLElement)

  expect(panelStyle.paddingTop).toBe('16px')
  expect(panelStyle.paddingRight).toBe('20px')
  expect(panelStyle.paddingBottom).toBe('16px')
  expect(panelStyle.paddingLeft).toBe('20px')
  expect(titleStyle.marginTop).toBe('0px')
  expect(titleStyle.marginBottom).toBe('0px')
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
