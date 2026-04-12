import { CheckOutlined, DesktopOutlined, MoonOutlined, SunOutlined } from '@ant-design/icons'
import { Button } from 'antd'
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react'
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

type OpenDirection = 'first' | 'last' | 'selected' | null

export default function ThemeModeSwitch() {
  const mode = useThemeStore((state) => state.mode)
  const setMode = useThemeStore((state) => state.setMode)
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const [openDirection, setOpenDirection] = useState<OpenDirection>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const triggerRef = useRef<HTMLButtonElement | null>(null)
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([])

  const closeMenu = () => {
    setOpen(false)
    setOpenDirection(null)
    triggerRef.current?.focus()
  }

  useEffect(() => {
    if (!open) {
      return
    }

    const handlePointerDown = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        closeMenu()
      }
    }

    document.addEventListener('pointerdown', handlePointerDown, true)

    return () => {
      document.removeEventListener('pointerdown', handlePointerDown, true)
    }
  }, [open])

  useEffect(() => {
    if (!open) {
      return
    }

    if (openDirection === 'first') {
      setActiveIndex(0)
      return
    }

    if (openDirection === 'last') {
      setActiveIndex(themeModes.length - 1)
      return
    }

    const selectedIndex = themeModes.indexOf(mode)
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : 0)
  }, [mode, open, openDirection])

  useLayoutEffect(() => {
    if (!open) {
      return
    }

    itemRefs.current[activeIndex]?.focus()
  }, [activeIndex, open])

  const handleSelect = (nextMode: ThemeMode) => {
    const prefersDark =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches

    setMode(nextMode, prefersDark)
    closeMenu()
  }

  const moveFocus = (nextIndex: number) => {
    const normalizedIndex = (nextIndex + themeModes.length) % themeModes.length
    setActiveIndex(normalizedIndex)
    itemRefs.current[normalizedIndex]?.focus()
  }

  const handleItemKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
      event.preventDefault()
      moveFocus(index + 1)
      return
    }

    if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
      event.preventDefault()
      moveFocus(index - 1)
      return
    }

    if (event.key === 'Home') {
      event.preventDefault()
      moveFocus(0)
      return
    }

    if (event.key === 'End') {
      event.preventDefault()
      moveFocus(themeModes.length - 1)
      return
    }

    if (event.key === 'Escape') {
      event.preventDefault()
      closeMenu()
    }
  }

  const handleTriggerKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      setOpenDirection(event.key === 'ArrowDown' ? 'first' : 'last')
      setOpen(true)
    }
  }

  return (
    <div ref={containerRef} className={styles.root}>
      <Button
        ref={triggerRef}
        type="text"
        className={styles.trigger}
        aria-label="主题模式"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => {
          setOpenDirection('selected')
          setOpen((current) => !current)
        }}
        onKeyDown={handleTriggerKeyDown}
      >
        <span className={styles.triggerIcon} aria-hidden="true">
          {modeIconMap[mode]}
        </span>
        <span className={styles.triggerLabel}>主题模式</span>
        <span className={styles.triggerValue}>{modeLabelMap[mode]}</span>
      </Button>

      {open ? (
        <div className={styles.menu} role="menu" aria-label="主题模式">
          {themeModes.map((itemMode, index) => {
            const selected = itemMode === mode

            return (
              <button
                key={itemMode}
                ref={(element) => {
                  itemRefs.current[index] = element
                }}
                type="button"
                role="menuitemradio"
                aria-checked={selected}
                tabIndex={index === activeIndex ? 0 : -1}
                className={`${styles.menuItem} ${selected ? styles.menuItemSelected : ''}`.trim()}
                onClick={() => handleSelect(itemMode)}
                onKeyDown={(event) => handleItemKeyDown(event, index)}
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
