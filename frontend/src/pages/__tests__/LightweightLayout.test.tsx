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
import variablesSource from '@/styles/variables.css?inline'
import { renderWithRouter } from '@/test/renderWithRouter'

const {
  getStyleConfigMock,
  getPresetThemesMock,
  getCustomThemesMock,
  getModelConfigMock,
  listAccountsMock,
} = vi.hoisted(() => ({
  getStyleConfigMock: vi.fn(),
  getPresetThemesMock: vi.fn(),
  getCustomThemesMock: vi.fn(),
  getModelConfigMock: vi.fn(),
  listAccountsMock: vi.fn(),
}))

vi.mock('@/api', () => ({
  getStyleConfig: getStyleConfigMock,
  getPresetThemes: getPresetThemesMock,
  getCustomThemes: getCustomThemesMock,
  getModelConfig: getModelConfigMock,
  listAccounts: listAccountsMock,
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
  const { container } = renderWithRouter(<WorkbenchShell />, { route: '/task' })

  const shell = container.firstElementChild as HTMLElement | null
  const sidebar = shell?.querySelector('aside') as HTMLElement | null
  const canvas = container.querySelector(`.${styles.canvas}`) as HTMLElement | null

  expect(shell).toBeInTheDocument()
  expect(sidebar).toBeInTheDocument()
  expect(canvas).toBeInTheDocument()

  const rootRuleBody = getRuleBody(variablesSource, ":root[data-theme='light']")
  expect(getDeclarationValue(rootRuleBody, '--app-surface-muted')).toBe('#f8fbff')
  expect(getDeclarationValue(rootRuleBody, '--app-toolbar-bg')).toBe('#f8fbff')
  expect(getDeclarationValue(rootRuleBody, '--app-list-row-hover')).toBe('#f3f7fd')

  const toolbarRuleBody = getRuleBody(globalStylesSource, '.backstage-toolbar')
  expect(getDeclarationValue(toolbarRuleBody, 'background')).toBe('var(--app-toolbar-bg)')

  const cardRuleBody = getRuleBody(globalStylesSource, '.backstage-surface-card')
  expect(getDeclarationValue(cardRuleBody, 'background')).toBe('var(--app-surface)')

  const previewRuleBody = getRuleBody(globalStylesSource, '.backstage-preview-frame')
  expect(getDeclarationValue(previewRuleBody, 'background')).toBe('var(--app-surface-muted)')

  const hoverRuleBody = getRuleBody(globalStylesSource, '.ant-table-wrapper .ant-table-tbody > tr:hover > td')
  expect(getDeclarationValue(hoverRuleBody, 'background')).toBe('var(--app-list-row-hover)')
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
