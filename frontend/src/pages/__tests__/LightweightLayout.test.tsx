import userEvent from '@testing-library/user-event'
import { render, screen } from '@testing-library/react'
import { beforeEach, afterEach, expect, test, vi } from 'vitest'
import HeroPanel from '@/components/workbench/HeroPanel'
import WorkbenchShell from '@/components/workbench/WorkbenchShell'
import styles from '@/components/workbench/WorkbenchShell.module.css'
import AccountConfigPage from '@/pages/AccountConfig'
import ModelConfigPage from '@/pages/ModelConfig'
import StyleConfigPage from '@/pages/StyleConfig'
import globalStylesSource from '@/styles/global.css?inline'
import tokensSource from '@/styles/tokens.css?inline'
import { primitiveTokens } from '@/styles/tokens'
import variablesSource from '@/styles/variables.css?inline'
import { renderWithRouter } from '@/test/renderWithRouter'

/** WCAG relative luminance, used to prove "light mode" is genuinely light. */
function relativeLuminance(hex: string) {
  const normalized = hex.replace('#', '')
  const channels = [0, 2, 4].map((offset) => {
    const value = Number.parseInt(normalized.slice(offset, offset + 2), 16) / 255
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
}

const {
  getStyleConfigMock,
  getPresetThemesMock,
  getCustomThemesMock,
  getModelConfigMock,
  listAccountsMock,
  listTasksMock,
  searchAllMock,
} = vi.hoisted(() => ({
  getStyleConfigMock: vi.fn(),
  getPresetThemesMock: vi.fn(),
  getCustomThemesMock: vi.fn(),
  getModelConfigMock: vi.fn(),
  listAccountsMock: vi.fn(),
  listTasksMock: vi.fn(),
  searchAllMock: vi.fn(),
}))

vi.mock('@/api', () => ({
  getStyleConfig: getStyleConfigMock,
  getPresetThemes: getPresetThemesMock,
  getCustomThemes: getCustomThemesMock,
  getModelConfig: getModelConfigMock,
  listAccounts: listAccountsMock,
  listTasks: listTasksMock,
  searchAll: searchAllMock,
}))

let previousTheme: string | undefined

beforeEach(() => {
  previousTheme = document.documentElement.dataset.theme
  document.documentElement.dataset.theme = 'light'
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
  getStyleConfigMock.mockResolvedValue({})
  getPresetThemesMock.mockResolvedValue({})
  getCustomThemesMock.mockResolvedValue({})
  getModelConfigMock.mockResolvedValue({
    text: { api_key: '', base_url: '', model: 'gpt-4o' },
    image: { enabled: false, api_key: '', base_url: '', model: 'dall-e-3' },
  })
  listAccountsMock.mockResolvedValue([])
  listTasksMock.mockResolvedValue([])
  searchAllMock.mockResolvedValue({ tasks: [], articles: [], topics: [] })
})

afterEach(() => {
  if (previousTheme === undefined) {
    delete document.documentElement.dataset.theme
  } else {
    document.documentElement.dataset.theme = previousTheme
  }
})

function getRuleBody(source: string, selector: string) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = source.match(new RegExp(`${escapedSelector}\\s*\\{([\\s\\S]*?)\\}`))
  return match?.[1] ?? ''
}

function getDeclarationValue(ruleBody: string, property: string) {
  const escapedProperty = property.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = ruleBody.match(new RegExp(`${escapedProperty}\\s*:\\s*([^;]+);`))
  return match?.[1]?.replace(/\s*!important\s*$/i, '').trim() ?? ''
}

test('renders a sidebar shell with a top context bar', () => {
  const { container } = renderWithRouter(<WorkbenchShell />, { route: '/task', theme: 'light' })

  const shell = container.firstElementChild as HTMLElement | null
  const sidebar = shell?.querySelector('aside') as HTMLElement | null
  const main = shell?.querySelector('main') as HTMLElement | null
  const topbar = main?.firstElementChild as HTMLElement | null

  expect(shell).toBeInTheDocument()
  expect(sidebar).toBeInTheDocument()
  expect(main).toBeInTheDocument()
  expect(topbar).toBeInTheDocument()

  const shellStyle = getComputedStyle(shell as HTMLElement)
  const topbarStyle = getComputedStyle(topbar as HTMLElement)

  // jsdom does not resolve custom properties, so assert the token reference rather
  // than a resolved pixel value.
  expect(shellStyle.getPropertyValue('grid-template-columns')).toContain('var(--layout-sidebar)')
  expect(shellStyle.getPropertyValue('background-image')).toBe('')
  expect(topbarStyle.getPropertyValue('padding')).toContain('var(--space-6)')
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

  expect(panelStyle.paddingTop).toBe('2px')
  expect(panelStyle.paddingRight).toBe('0px')
  expect(panelStyle.paddingBottom).toBe('0px')
  expect(panelStyle.paddingLeft).toBe('0px')
  expect(contentStyle.gap).toBe('4px')
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
        (rule) => rule instanceof CSSMediaRule && rule.conditionText.includes('max-width: 1180px'),
      )
    } catch {
      return false
    }
  })

  expect(sheet).toBeDefined()

  const mediaRule = Array.from((sheet as CSSStyleSheet).cssRules).find(
    (rule) => rule instanceof CSSMediaRule && rule.conditionText.includes('max-width: 1180px'),
  ) as CSSMediaRule | undefined

  expect(mediaRule).toBeDefined()

  const shellRule = Array.from(mediaRule!.cssRules).find(
    (rule) => rule instanceof CSSStyleRule && rule.selectorText === `.${styles.shell}`,
  ) as CSSStyleRule | undefined

  expect(shellRule).toBeDefined()
  expect(shellRule!.style.getPropertyValue('grid-template-columns')).toBe('minmax(0, 1fr)')
})

test('keeps shared surfaces light in light mode', () => {
  const { container } = renderWithRouter(<WorkbenchShell />, { route: '/task' })

  const shell = container.firstElementChild as HTMLElement | null
  const sidebar = shell?.querySelector('aside') as HTMLElement | null
  const canvas = container.querySelector(`.${styles.canvas}`) as HTMLElement | null

  expect(shell).toBeInTheDocument()
  expect(sidebar).toBeInTheDocument()
  expect(canvas).toBeInTheDocument()

  // Light is the default theme now, so the values live in the token layer and the
  // legacy names are aliases onto the semantic tokens. Look these up across the
  // whole sheet: `?inline` inlines the `@import`, so matching a single `:root`
  // block would find the token layer's block instead of the alias block.
  expect(getDeclarationValue(variablesSource, '--app-surface-muted')).toBe('var(--surface-sunken)')
  expect(getDeclarationValue(variablesSource, '--app-toolbar-bg')).toBe('var(--surface-raised)')
  expect(getDeclarationValue(variablesSource, '--app-list-row-hover')).toBe('var(--surface-hover)')

  expect(getDeclarationValue(tokensSource, '--surface-sunken')).toBe('var(--paper-100)')
  expect(getDeclarationValue(tokensSource, '--surface-raised')).toBe('var(--paper-0)')
  expect(getDeclarationValue(tokensSource, '--surface-hover')).toBe('var(--paper-100)')

  // "Light mode" must actually be light: assert the resolved primitives rather than
  // restating hex codes, so a palette change does not silently make this lie.
  for (const name of ['--paper-0', '--paper-50', '--paper-100'] as const) {
    expect(relativeLuminance(primitiveTokens[name])).toBeGreaterThan(0.9)
  }

  const toolbarRuleBody = getRuleBody(globalStylesSource, '.backstage-toolbar')
  expect(getDeclarationValue(toolbarRuleBody, 'background')).toBe('var(--app-toolbar-bg)')

  const cardRuleBody = getRuleBody(globalStylesSource, '.backstage-surface-card')
  expect(getDeclarationValue(cardRuleBody, 'background')).toBe('var(--app-surface)')

  const previewRuleBody = getRuleBody(globalStylesSource, '.backstage-preview-frame')
  expect(getDeclarationValue(previewRuleBody, 'background')).toBe('var(--app-surface-muted)')

  const hoverRuleBody = getRuleBody(globalStylesSource, '.ant-table-wrapper .ant-table-tbody > tr:hover > td')
  expect(getDeclarationValue(hoverRuleBody, 'background')).toBe('var(--surface-hover)')
  expect(hoverRuleBody).toContain('!important')
})

test('renders compact grouped config pages without metric-card emphasis', async () => {
  const user = userEvent.setup()
  const styleConfig = renderWithRouter(<StyleConfigPage />, { route: '/settings' })
  const modelConfig = renderWithRouter(<ModelConfigPage />, { route: '/models' })
  const accountConfig = renderWithRouter(<AccountConfigPage />, { route: '/accounts' })

  expect(await screen.findByText('品牌样式管理台')).toBeInTheDocument()
  expect(await screen.findByText('模型接入配置')).toBeInTheDocument()
  expect(await screen.findByText('账户接入配置')).toBeInTheDocument()

  expect(styleConfig.container.querySelector('.backstage-page')).toBeInTheDocument()
  expect(modelConfig.container.querySelector('.backstage-page')).toBeInTheDocument()
  expect(accountConfig.container.querySelector('.backstage-page')).toBeInTheDocument()

  expect(styleConfig.container.querySelector('.backstage-metric-grid')).not.toBeInTheDocument()
  expect(modelConfig.container.querySelector('.backstage-metric-grid')).not.toBeInTheDocument()
  expect(accountConfig.container.querySelector('.backstage-metric-grid')).not.toBeInTheDocument()

  expect(screen.getByRole('list', { name: '样式提示' })).toBeInTheDocument()
  expect(screen.getByRole('list', { name: '模型配置提示' })).toBeInTheDocument()
  expect(screen.getByRole('list', { name: '账户配置提示' })).toBeInTheDocument()

  expect(screen.getByRole('button', { name: /主题中心/ })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /主题中心/ }))
  expect(await screen.findByRole('button', { name: /导出当前主题/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /保存配置/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /新增账户/ })).toBeInTheDocument()
})
