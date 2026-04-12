import { CheckOutlined, DesktopOutlined, MoonOutlined, SunOutlined } from '@ant-design/icons'
import { Button, Dropdown } from 'antd'
import type { MenuProps } from 'antd'
import { useThemeStore, type ThemeMode } from '@/store/themeStore'
import styles from './ThemeModeSwitch.module.css'

const modeLabelMap: Record<ThemeMode, string> = {
  system: '跟随系统',
  light: '浅色模式',
  dark: '深色模式',
}

const modeIconMap: Record<ThemeMode, JSX.Element> = {
  system: <DesktopOutlined />,
  light: <SunOutlined />,
  dark: <MoonOutlined />,
}

const createMenuItems = (selectedMode: ThemeMode): MenuProps['items'] =>
  (['system', 'light', 'dark'] as ThemeMode[]).map((mode) => ({
    key: mode,
    icon: modeIconMap[mode],
    label: modeLabelMap[mode],
    extra: mode === selectedMode ? <CheckOutlined aria-hidden="true" className={styles.menuCheck} /> : undefined,
  }))

export default function ThemeModeSwitch() {
  const mode = useThemeStore((state) => state.mode)
  const setMode = useThemeStore((state) => state.setMode)

  const handleClick: MenuProps['onClick'] = ({ key }) => {
    const prefersDark =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches
    setMode(key as ThemeMode, prefersDark)
  }

  return (
    <Dropdown
      trigger={['click']}
      placement="bottomRight"
      menu={{
        items: createMenuItems(mode),
        selectable: true,
        selectedKeys: [mode],
        onClick: handleClick,
      }}
    >
      <Button type="text" className={styles.trigger} aria-label="主题模式">
        <span className={styles.triggerIcon} aria-hidden="true">
          {modeIconMap[mode]}
        </span>
        <span className={styles.triggerLabel}>主题模式</span>
        <span className={styles.triggerValue}>{modeLabelMap[mode]}</span>
      </Button>
    </Dropdown>
  )
}
