import { LogoutOutlined, WechatOutlined } from '@ant-design/icons'
import { Button } from 'antd'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { navigationItems, resolveRouteMeta } from '@/config/navigation'
import useAuthStore from '@/store/authStore'
import ThemeModeSwitch from './ThemeModeSwitch'
import styles from './WorkbenchShell.module.css'

export default function WorkbenchShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const routeMeta = resolveRouteMeta(location.pathname)
  const user = useAuthStore((state) => state.user)
  const clearSession = useAuthStore((state) => state.clearSession)

  const handleLogout = () => {
    clearSession()
    navigate('/login', { replace: true })
  }

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true">
            <WechatOutlined />
          </span>
          <div>
            <strong className={styles.brandTitle}>Brand Studio</strong>
            <span className={styles.brandCopy}>内容生产后台</span>
          </div>
        </div>

        <nav className={styles.nav} aria-label="Primary">
          {navigationItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`.trim()
              }
            >
              <span className={styles.navIcon} aria-hidden="true">
                {item.icon}
              </span>
              <span>{item.navLabel}</span>
            </NavLink>
          ))}
        </nav>

        <p className={styles.sidebarFooter}>Workflow / Agents / Review</p>
      </aside>

      <main className={styles.main}>
        <header className={styles.topbar}>
          <div className={styles.routeContext}>
            <span className={styles.eyebrow}>{routeMeta.contextEyebrow}</span>
            <h1>{routeMeta.contextTitle}</h1>
            <p>{routeMeta.contextDescription}</p>
          </div>
          <div className={styles.toolbar}>
            <ThemeModeSwitch />
            <Button icon={<LogoutOutlined />} size="small" onClick={handleLogout}>
              {user?.display_name ?? user?.username ?? '退出登录'}
            </Button>
          </div>
        </header>

        <div className={styles.canvas}>
          <Outlet />
        </div>
      </main>
    </div>
  )
}
