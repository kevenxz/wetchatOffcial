import { theme as antdTheme, type ThemeConfig } from 'antd'
import type { ResolvedTheme } from './store/themeStore'

const sharedToken = {
  colorPrimary: '#0f766e',
  colorSuccess: '#34d399',
  colorWarning: '#fbbf24',
  colorError: '#f87171',
  colorInfo: '#0f766e',
  fontFamily:
    "'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif",
  fontFamilyCode: "'JetBrains Mono', 'SFMono-Regular', Consolas, monospace",
  fontWeightStrong: 600,
  fontSize: 14,
  fontSizeSM: 12,
  fontSizeLG: 16,
  fontSizeXL: 20,
  fontSizeHeading1: 32,
  fontSizeHeading2: 26,
  fontSizeHeading3: 22,
  fontSizeHeading4: 18,
  fontSizeHeading5: 16,
  lineHeight: 1.6,
  borderRadius: 10,
  borderRadiusSM: 6,
  borderRadiusLG: 14,
  motionDurationFast: '0.1s',
  motionDurationMid: '0.2s',
  motionDurationSlow: '0.3s',
} as const

const lightTheme: ThemeConfig = {
  algorithm: antdTheme.defaultAlgorithm,
  token: {
    ...sharedToken,
    colorBgLayout: '#f4f0e8',
    colorBgContainer: '#fffdf8',
    colorBgElevated: '#fffdf8',
    colorBorder: '#d3c6b6',
    colorBorderSecondary: '#e3dacd',
    colorSplit: '#e3dacd',
    colorText: '#1c1917',
    colorTextSecondary: '#625b52',
    colorTextTertiary: '#8a8177',
    colorTextQuaternary: '#a8a096',
    colorFillSecondary: 'rgba(68, 44, 30, 0.05)',
    colorFillQuaternary: 'rgba(68, 44, 30, 0.03)',
    colorPrimaryBg: 'rgba(15, 118, 110, 0.09)',
    colorPrimaryBgHover: 'rgba(15, 118, 110, 0.15)',
    colorPrimaryBorder: 'rgba(15, 118, 110, 0.28)',
    colorPrimaryBorderHover: 'rgba(15, 118, 110, 0.46)',
    colorLink: '#0f766e',
    colorLinkHover: '#0d9488',
    boxShadow:
      '0 18px 40px -24px rgba(15, 23, 42, 0.18), 0 10px 24px -18px rgba(15, 23, 42, 0.16)',
    boxShadowSecondary:
      '0 12px 28px -20px rgba(15, 23, 42, 0.12), 0 6px 16px -10px rgba(15, 23, 42, 0.1)',
  },
  components: {
    Layout: {
      siderBg: '#fffdf8',
      triggerBg: '#eee6d9',
    },
    Menu: {
      itemBg: 'transparent',
      itemSelectedBg: 'rgba(15, 118, 110, 0.11)',
      itemSelectedColor: '#1c1917',
    },
  },
}

const darkTheme: ThemeConfig = {
  algorithm: antdTheme.darkAlgorithm,
  token: {
    ...sharedToken,
    colorPrimary: '#2dd4bf',
    colorBgLayout: '#0b1020',
    colorBgContainer: '#121a2b',
    colorBgElevated: '#182235',
    colorBorder: '#273449',
    colorBorderSecondary: '#1f2a3d',
    colorSplit: '#1f2a3d',
    colorText: '#e5edf9',
    colorTextSecondary: '#a6b4c9',
    colorTextTertiary: '#71829e',
    colorTextQuaternary: '#4b5b75',
    colorFillSecondary: 'rgba(45, 212, 191, 0.1)',
    colorFillQuaternary: 'rgba(255, 255, 255, 0.04)',
    colorPrimaryBg: 'rgba(45, 212, 191, 0.14)',
    colorPrimaryBgHover: 'rgba(45, 212, 191, 0.22)',
    colorPrimaryBorder: 'rgba(94, 234, 212, 0.38)',
    colorPrimaryBorderHover: 'rgba(94, 234, 212, 0.58)',
    colorLink: '#2dd4bf',
    colorLinkHover: '#5eead4',
    boxShadow:
      '0 18px 40px -24px rgba(2, 8, 23, 0.85), 0 10px 24px -18px rgba(2, 8, 23, 0.7)',
    boxShadowSecondary:
      '0 12px 28px -20px rgba(2, 8, 23, 0.72), 0 6px 16px -10px rgba(2, 8, 23, 0.56)',
  },
  components: {
    Layout: {
      siderBg: '#0e1627',
      triggerBg: '#162033',
    },
    Menu: {
      darkItemBg: '#0e1627',
      darkSubMenuItemBg: '#0b1020',
      darkItemSelectedBg: 'rgba(45, 212, 191, 0.2)',
    },
  },
}

export function getAntdTheme(resolvedTheme: ResolvedTheme): ThemeConfig {
  return resolvedTheme === 'light' ? lightTheme : darkTheme
}

