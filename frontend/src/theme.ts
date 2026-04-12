import { theme as antdTheme, type ThemeConfig } from 'antd'
import type { ResolvedTheme } from './store/themeStore'

const sharedToken = {
  colorPrimary: '#7dd3fc',
  colorSuccess: '#34d399',
  colorWarning: '#fbbf24',
  colorError: '#f87171',
  colorInfo: '#7dd3fc',
  fontFamily:
    "'Inter', 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', sans-serif",
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
    colorBgLayout: '#f3f6fb',
    colorBgContainer: '#ffffff',
    colorBgElevated: '#ffffff',
    colorBorder: '#d8e1ee',
    colorBorderSecondary: '#e5ebf5',
    colorSplit: '#e5ebf5',
    colorText: '#0f172a',
    colorTextSecondary: '#516074',
    colorTextTertiary: '#738196',
    colorTextQuaternary: '#94a3b8',
    colorFillSecondary: 'rgba(15, 23, 42, 0.05)',
    colorFillQuaternary: 'rgba(15, 23, 42, 0.03)',
    colorPrimaryBg: 'rgba(125, 211, 252, 0.16)',
    colorPrimaryBgHover: 'rgba(125, 211, 252, 0.24)',
    colorPrimaryBorder: 'rgba(56, 189, 248, 0.28)',
    colorPrimaryBorderHover: 'rgba(56, 189, 248, 0.4)',
    colorLink: '#0284c7',
    colorLinkHover: '#0369a1',
    boxShadow:
      '0 18px 40px -24px rgba(15, 23, 42, 0.18), 0 10px 24px -18px rgba(15, 23, 42, 0.16)',
    boxShadowSecondary:
      '0 12px 28px -20px rgba(15, 23, 42, 0.12), 0 6px 16px -10px rgba(15, 23, 42, 0.1)',
  },
  components: {
    Layout: {
      siderBg: '#ffffff',
      triggerBg: '#eff5fb',
    },
    Menu: {
      itemBg: 'transparent',
      itemSelectedBg: 'rgba(125, 211, 252, 0.14)',
      itemSelectedColor: '#0f172a',
    },
  },
}

const darkTheme: ThemeConfig = {
  algorithm: antdTheme.darkAlgorithm,
  token: {
    ...sharedToken,
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
    colorFillSecondary: 'rgba(125, 211, 252, 0.08)',
    colorFillQuaternary: 'rgba(255, 255, 255, 0.04)',
    colorPrimaryBg: 'rgba(125, 211, 252, 0.12)',
    colorPrimaryBgHover: 'rgba(125, 211, 252, 0.18)',
    colorPrimaryBorder: 'rgba(125, 211, 252, 0.32)',
    colorPrimaryBorderHover: 'rgba(125, 211, 252, 0.5)',
    colorLink: '#7dd3fc',
    colorLinkHover: '#a5f3fc',
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
      darkItemSelectedBg: 'rgba(125, 211, 252, 0.18)',
    },
  },
}

export function getAntdTheme(resolvedTheme: ResolvedTheme): ThemeConfig {
  return resolvedTheme === 'light' ? lightTheme : darkTheme
}

