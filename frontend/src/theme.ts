import type { ThemeConfig } from 'antd'

const theme: ThemeConfig = {
  token: {
    // 主色
    colorPrimary: '#1677FF',
    colorSuccess: '#52c41a',
    colorWarning: '#faad14',
    colorError: '#ff4d4f',
    colorInfo: '#1677FF',

    // 字体
    fontFamily:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, " +
      "'Noto Sans', sans-serif",
    fontSize: 14,
    fontSizeSM: 12,
    fontSizeLG: 16,
    fontSizeXL: 20,
    fontSizeHeading1: 30,
    fontSizeHeading2: 24,
    fontSizeHeading3: 20,
    fontSizeHeading4: 18,
    fontSizeHeading5: 16,

    // 行高
    lineHeight: 1.5714,

    // 圆角
    borderRadius: 6,
    borderRadiusSM: 4,
    borderRadiusLG: 8,

    // 间距
    padding: 16,
    paddingSM: 8,
    paddingLG: 24,
    paddingXL: 32,
    margin: 16,
    marginSM: 8,
    marginLG: 24,
    marginXL: 32,

    // 高度
    controlHeight: 32,
    controlHeightSM: 24,
    controlHeightLG: 40,

    // 阴影
    boxShadow:
      '0 6px 16px 0 rgba(0,0,0,.08), 0 3px 6px -4px rgba(0,0,0,.12), 0 9px 28px 8px rgba(0,0,0,.05)',
    boxShadowSecondary:
      '0 6px 16px 0 rgba(0,0,0,.08), 0 3px 6px -4px rgba(0,0,0,.12), 0 9px 28px 8px rgba(0,0,0,.05)',

    // 过渡
    motionDurationFast: '0.1s',
    motionDurationMid: '0.2s',
    motionDurationSlow: '0.3s',

    // 色板
    colorBgLayout: '#f5f5f5',
    colorBgContainer: '#ffffff',
  },
  components: {
    Layout: {
      siderBg: '#001529',
      triggerBg: '#002140',
    },
    Menu: {
      darkItemBg: '#001529',
      darkSubMenuItemBg: '#000c17',
      darkItemSelectedBg: '#1677ff',
    },
  },
}

export default theme
