import { LogoutOutlined, WechatOutlined } from '@ant-design/icons'
import { Button } from 'antd'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { navigationItems, resolveRouteMeta } from '@/config/navigation'
import useAuthStore from '@/store/authStore'
import HeroPanel from './HeroPanel'
import ThemeModeSwitch from './ThemeModeSwitch'
import SectionBlock from './SectionBlock'
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
    <div className={styles.shell} style={{ backgroundImage: 'none' }}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true">
            <WechatOutlined />
          </span>
          <strong className={styles.brandTitle}>Brand Studio</strong>
          <p className={styles.brandCopy}>面向公众号生产链路的统一创作工作台。</p>
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

        <p className={styles.sidebarFooter}>Brand Studio 工作台骨架已接入新的应用外壳。</p>
      </aside>

      <main className={styles.main}>
        <div className={styles.frame}>
          <div className={styles.toolbar}>
            <ThemeModeSwitch />
            <Button icon={<LogoutOutlined />} size="small" onClick={handleLogout}>
              {user?.display_name ?? user?.username ?? '退出登录'}
            </Button>
          </div>

          <HeroPanel
            eyebrow={routeMeta.contextEyebrow}
            title={routeMeta.contextTitle}
            description={routeMeta.contextDescription}
          />

          <div className={styles.overview}>
            <SectionBlock title="工作区">
              <div className={styles.canvas}>
                <Outlet />
              </div>
            </SectionBlock>
          </div>
        </div>
      </main>
    </div>
  )
}
