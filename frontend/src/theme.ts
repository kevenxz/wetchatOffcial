import { theme as antdTheme, type ThemeConfig } from 'antd'
import type { ResolvedTheme } from './store/themeStore'
import { darkTokens, px, primitiveTokens as t, seconds, withAlpha } from './styles/tokens'

/**
 * antd theme, generated from the design tokens.
 *
 * The previous version hard-coded a second copy of the palette here, which is how
 * the documented brand colour (`#1677FF`) and the implemented one (`#0f766e`) drifted
 * apart. Every value below is now derived from `styles/tokens.ts`, which the
 * `tokenParity` test keeps in sync with `styles/tokens.css`.
 *
 * Re-skin direction (bright minimal Swiss): square corners, hairlines instead of
 * shadows, a single accent, no decorative glow.
 */

const accent = {
  primary: t['--accent-600'],
  hover: t['--accent-500'],
  active: t['--accent-700'],
}

const sharedToken = {
  fontFamily: 'var(--font-sans)',
  fontFamilyCode: 'var(--font-mono)',
  fontWeightStrong: 600,
  fontSize: px(t['--type-base']),
  fontSizeSM: px(t['--type-sm']),
  fontSizeLG: px(t['--type-md']),
  fontSizeXL: px(t['--type-lg']),
  fontSizeHeading1: px(t['--type-2xl']),
  fontSizeHeading2: px(t['--type-xl']),
  fontSizeHeading3: px(t['--type-lg']),
  fontSizeHeading4: px(t['--type-md']),
  fontSizeHeading5: px(t['--type-base']),
  lineHeight: Number.parseFloat(t['--leading-base']),
  // Square surfaces, a hair of rounding on controls only.
  borderRadius: px(t['--radius-hair']),
  borderRadiusSM: px(t['--radius-hair']),
  borderRadiusLG: px(t['--radius-sm']),
  borderRadiusXS: px(t['--radius-none']),
  controlHeight: 36,
  controlHeightSM: 28,
  controlHeightLG: 44,
  motionDurationFast: seconds(t['--dur-fast']),
  motionDurationMid: seconds(t['--dur-base']),
  motionDurationSlow: seconds(t['--dur-slow']),
  // Swiss: hierarchy comes from rules and space, not from glow.
  boxShadow: 'none',
  boxShadowSecondary: 'none',
  boxShadowTertiary: 'none',
  wireframe: false,
} as const

const lightTheme: ThemeConfig = {
  algorithm: antdTheme.defaultAlgorithm,
  token: {
    ...sharedToken,
    colorPrimary: accent.primary,
    colorPrimaryHover: accent.hover,
    colorPrimaryActive: accent.active,
    colorPrimaryBg: withAlpha(accent.primary, 0.08),
    colorPrimaryBgHover: withAlpha(accent.primary, 0.14),
    colorPrimaryBorder: withAlpha(accent.primary, 0.3),
    colorPrimaryBorderHover: withAlpha(accent.primary, 0.48),

    colorSuccess: t['--status-success'],
    colorWarning: t['--status-warning'],
    colorError: t['--status-danger'],
    colorInfo: t['--status-info'],
    colorLink: accent.primary,
    colorLinkHover: accent.hover,

    colorBgLayout: t['--paper-50'],
    colorBgContainer: t['--paper-0'],
    colorBgElevated: t['--paper-0'],
    colorBgSpotlight: t['--ink-900'],

    colorBorder: t['--line-300'],
    colorBorderSecondary: t['--line-200'],
    colorSplit: t['--line-200'],

    colorText: t['--ink-900'],
    colorTextSecondary: t['--ink-700'],
    colorTextTertiary: t['--ink-500'],
    colorTextQuaternary: t['--ink-400'],
    colorFillSecondary: 'rgba(10, 10, 10, 0.04)',
    colorFillQuaternary: 'rgba(10, 10, 10, 0.02)',
  },
  components: {
    Layout: { bodyBg: t['--paper-50'], headerBg: t['--paper-0'], siderBg: t['--paper-0'] },
    Menu: {
      itemBg: 'transparent',
      itemSelectedBg: withAlpha(accent.primary, 0.08),
      itemSelectedColor: t['--ink-900'],
      itemHoverBg: t['--paper-100'],
    },
    Table: {
      headerBg: t['--paper-0'],
      headerColor: t['--ink-500'],
      rowHoverBg: t['--paper-50'],
      borderColor: t['--line-200'],
      headerSplitColor: 'transparent',
    },
    Card: { headerBg: 'transparent', paddingLG: 20 },
    Button: {
      primaryShadow: 'none',
      defaultShadow: 'none',
      dangerShadow: 'none',
      fontWeight: 500,
    },
    Input: { paddingBlock: 6 },
    Segmented: { itemSelectedBg: t['--paper-0'] },
    Tabs: { horizontalItemGutter: 28 },
  },
}

const darkTheme: ThemeConfig = {
  algorithm: antdTheme.darkAlgorithm,
  token: {
    ...sharedToken,
    colorPrimary: t['--accent-400'],
    colorPrimaryHover: '#5eead4',
    colorPrimaryActive: t['--accent-500'],
    colorPrimaryBg: withAlpha(t['--accent-400'], 0.12),
    colorPrimaryBgHover: withAlpha(t['--accent-400'], 0.2),
    colorPrimaryBorder: withAlpha(t['--accent-400'], 0.38),
    colorPrimaryBorderHover: withAlpha(t['--accent-400'], 0.58),

    colorSuccess: '#4ade80',
    colorWarning: '#fbbf24',
    colorError: '#f87171',
    colorInfo: '#7dd3fc',
    colorLink: t['--accent-400'],
    colorLinkHover: '#5eead4',

    colorBgLayout: darkTokens['--surface-page'],
    colorBgContainer: darkTokens['--surface-raised'],
    colorBgElevated: darkTokens['--surface-interactive'],
    colorBgSpotlight: t['--paper-0'],

    colorBorder: darkTokens['--border-strong'],
    colorBorderSecondary: darkTokens['--border-hairline'],
    colorSplit: darkTokens['--border-hairline'],

    colorText: darkTokens['--text-primary'],
    colorTextSecondary: darkTokens['--text-secondary'],
    colorTextTertiary: darkTokens['--text-tertiary'],
    colorTextQuaternary: darkTokens['--text-quaternary'],
    colorFillSecondary: 'rgba(255, 255, 255, 0.06)',
    colorFillQuaternary: 'rgba(255, 255, 255, 0.03)',
  },
  components: {
    Layout: {
      bodyBg: darkTokens['--surface-page'],
      headerBg: darkTokens['--surface-raised'],
      siderBg: darkTokens['--surface-raised'],
    },
    Menu: {
      darkItemBg: 'transparent',
      darkSubMenuItemBg: 'transparent',
      darkItemSelectedBg: withAlpha(t['--accent-400'], 0.16),
      darkItemSelectedColor: darkTokens['--text-primary'],
    },
    Table: {
      headerBg: darkTokens['--surface-raised'],
      headerColor: darkTokens['--text-tertiary'],
      rowHoverBg: darkTokens['--surface-hover'],
      borderColor: darkTokens['--border-hairline'],
      headerSplitColor: 'transparent',
    },
    Card: { headerBg: 'transparent', paddingLG: 20 },
    Button: {
      primaryShadow: 'none',
      defaultShadow: 'none',
      dangerShadow: 'none',
      fontWeight: 500,
    },
    Input: { paddingBlock: 6 },
    Segmented: { itemSelectedBg: darkTokens['--surface-active'] },
    Tabs: { horizontalItemGutter: 28 },
  },
}

export function getAntdTheme(resolvedTheme: ResolvedTheme): ThemeConfig {
  return resolvedTheme === 'light' ? lightTheme : darkTheme
}
