import { render, screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import App from '@/App'
import type { AccountConfig, ScheduleConfig } from '@/api'

const {
  listSchedulesMock,
  listAccountsMock,
  getPresetThemesMock,
  getCustomThemesMock,
} = vi.hoisted(() => ({
  listSchedulesMock: vi.fn<() => Promise<ScheduleConfig[]>>(),
  listAccountsMock: vi.fn<() => Promise<AccountConfig[]>>(),
  getPresetThemesMock: vi.fn(),
  getCustomThemesMock: vi.fn(),
}))

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api')
  return {
    ...actual,
    listSchedules: listSchedulesMock,
    listAccounts: listAccountsMock,
    getPresetThemes: getPresetThemesMock,
    getCustomThemes: getCustomThemesMock,
  }
})

beforeEach(() => {
  vi.clearAllMocks()
  listSchedulesMock.mockResolvedValue([])
  listAccountsMock.mockResolvedValue([])
  getPresetThemesMock.mockResolvedValue({})
  getCustomThemesMock.mockResolvedValue({})

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

  const originalGetComputedStyle = window.getComputedStyle.bind(window)
  Object.defineProperty(window, 'getComputedStyle', {
    writable: true,
    value: (element: Element) => originalGetComputedStyle(element),
  })

  window.history.replaceState({}, '', '/schedules')
})

test('renders the automation workbench shell and a loaded rule card for schedules', async () => {
  listSchedulesMock.mockResolvedValue([
    {
      schedule_id: 'schedule-1',
      name: '晨间快报',
      mode: 'interval',
      interval_minutes: 90,
      theme_name: '__current__',
      account_ids: ['account-1'],
      hot_topics: [],
      hotspot_capture: {
        enabled: false,
        source: 'tophub',
        categories: [],
        platforms: [],
        filters: {
          top_n_per_platform: 10,
          min_selection_score: 60,
          exclude_keywords: [],
          prefer_keywords: [],
        },
        fallback_topics: [],
      },
      generation_config: {
        audience_roles: ['开发者'],
        article_strategy: 'auto',
        style_hint: '',
      },
      status: 'running',
      enabled: true,
      last_run_at: '2026-04-12T00:00:00Z',
      next_run_at: '2026-04-12T01:30:00Z',
      created_at: '2026-04-12T00:00:00Z',
      updated_at: '2026-04-12T00:00:00Z',
      last_error: null,
    },
  ])
  listAccountsMock.mockResolvedValue([
    {
      account_id: 'account-1',
      name: '品牌号-A',
      platform: 'wechat_mp',
      app_id: 'app-id',
      app_secret: 'secret',
      enabled: true,
      created_at: '2026-04-12T00:00:00Z',
      updated_at: '2026-04-12T00:00:00Z',
    },
  ])

  render(<App />)

  expect(await screen.findByText('自动化编排台')).toBeInTheDocument()
  expect(screen.getAllByText('执行规则').length).toBeGreaterThan(0)
  expect(screen.getAllByText('推送目标').length).toBeGreaterThan(0)
  expect((await screen.findAllByText('晨间快报')).length).toBeGreaterThan(0)
  expect(screen.getAllByRole('button', { name: /立即执行/ }).length).toBeGreaterThan(0)
})

test('shows loading copy instead of the empty automation CTA while schedules are loading', () => {
  listSchedulesMock.mockImplementation(() => new Promise(() => undefined))
  listAccountsMock.mockImplementation(() => new Promise(() => undefined))
  getPresetThemesMock.mockImplementation(() => new Promise(() => undefined))
  getCustomThemesMock.mockImplementation(() => new Promise(() => undefined))

  render(<App />)

  expect(screen.getByText('自动化编排台')).toBeInTheDocument()
  expect(screen.getByText('正在加载自动化规则...')).toBeInTheDocument()
  expect(screen.queryByText('还没有自动化规则，先配置一条编排规则。')).not.toBeInTheDocument()
  expect(screen.queryByText('暂无可用公众号账号，规则保存前仍需选择至少一个账号。')).not.toBeInTheDocument()
})
