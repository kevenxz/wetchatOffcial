import { CheckOutlined, DesktopOutlined, MoonOutlined, SunOutlined } from '@ant-design/icons'
import { Button } from 'antd'
import { useEffect, useRef, useState } from 'react'
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

const themeModes: ThemeMode[] = ['system', 'light', 'dark']

export default function ThemeModeSwitch() {
  const mode = useThemeStore((state) => state.mode)
  const setMode = useThemeStore((state) => state.setMode)
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
      }
    }

    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  const handleSelect = (nextMode: ThemeMode) => {
    const prefersDark =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches

    setMode(nextMode, prefersDark)
    setOpen(false)
  }

  return (
    <div ref={containerRef} className={styles.root}>
      <Button
        type="text"
        className={styles.trigger}
        aria-label="主题模式"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <span className={styles.triggerIcon} aria-hidden="true">
          {modeIconMap[mode]}
        </span>
        <span className={styles.triggerLabel}>主题模式</span>
        <span className={styles.triggerValue}>{modeLabelMap[mode]}</span>
      </Button>

      {open ? (
        <div className={styles.menu} role="menu" aria-label="主题模式">
          {themeModes.map((itemMode) => {
            const selected = itemMode === mode

            return (
              <button
                key={itemMode}
                type="button"
                role="menuitemradio"
                aria-checked={selected}
                className={`${styles.menuItem} ${selected ? styles.menuItemSelected : ''}`.trim()}
                onClick={() => handleSelect(itemMode)}
              >
                <span className={styles.menuIcon} aria-hidden="true">
                  {modeIconMap[itemMode]}
                </span>
                <span className={styles.menuLabel}>{modeLabelMap[itemMode]}</span>
                <span className={styles.menuState} aria-hidden="true">
                  {selected ? <CheckOutlined /> : null}
                </span>
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
