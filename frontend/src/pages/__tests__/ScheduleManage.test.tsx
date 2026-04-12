import { screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import type { AccountConfig, ScheduleConfig } from '@/api'
import ScheduleManage from '@/pages/ScheduleManage'
import { renderWithRouter } from '@/test/renderWithRouter'

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
})

test('renders schedule management as a compact toolbar and table layout', async () => {
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
        audience_roles: ['Developer'],
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
      name: 'Brand Account A',
      platform: 'wechat_mp',
      app_id: 'app-id',
      app_secret: 'secret',
      enabled: true,
      created_at: '2026-04-12T00:00:00Z',
      updated_at: '2026-04-12T00:00:00Z',
    },
  ])

  renderWithRouter(<ScheduleManage />, { route: '/schedules' })

  expect(await screen.findByRole('toolbar', { name: 'Schedule actions' })).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: '新建自动化规则' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '规则明细' })).toBeInTheDocument()
  expect(screen.getByRole('table')).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: '执行规则' })).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: '推送目标' })).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: '公众号账号池' })).not.toBeInTheDocument()
})
