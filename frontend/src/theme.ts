import type { ThemeConfig } from 'antd'

const theme: ThemeConfig = {
  token: {
    colorPrimary: '#7dd3fc',
    colorSuccess: '#34d399',
    colorWarning: '#fbbf24',
    colorError: '#f87171',
    colorInfo: '#7dd3fc',
    colorBgLayout: '#0b1020',
    colorBgContainer: '#121a2b',
    colorBgElevated: '#182235',
    colorBorder: '#273449',
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
    colorBorderSecondary: '#1f2a3d',
    colorSplit: '#1f2a3d',
    colorLink: '#7dd3fc',
    colorLinkHover: '#a5f3fc',
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
    boxShadow:
      '0 18px 40px -24px rgba(2, 8, 23, 0.85), 0 10px 24px -18px rgba(2, 8, 23, 0.7)',
    boxShadowSecondary:
      '0 12px 28px -20px rgba(2, 8, 23, 0.72), 0 6px 16px -10px rgba(2, 8, 23, 0.56)',
    motionDurationFast: '0.1s',
    motionDurationMid: '0.2s',
    motionDurationSlow: '0.3s',
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

export default theme
