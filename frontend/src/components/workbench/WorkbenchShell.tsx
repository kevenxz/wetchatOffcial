import { BellOutlined, SearchOutlined, UserOutlined, WechatOutlined } from '@ant-design/icons'
import { Badge, Input } from 'antd'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { navigationItems, resolveRouteMeta } from '@/config/navigation'
import useAuthStore from '@/store/authStore'
import ThemeModeSwitch from './ThemeModeSwitch'
import styles from './WorkbenchShell.module.css'

export default function WorkbenchShell() {
  const location = useLocation()
  const routeMeta = resolveRouteMeta(location.pathname)
  const user = useAuthStore((state) => state.user)

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true">
            <WechatOutlined />
          </span>
          <div>
            <strong className={styles.brandTitle}>AI内容工厂</strong>
            <span className={styles.brandCopy}>智能公众号生产系统</span>
          </div>
        </div>

        <div className={styles.systemStatus}>
          <span className={styles.statusDot} />
          <span>系统运行正常</span>
          <span className={styles.online}>在线</span>
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

        <div className={styles.sidebarFooter}>
          <span className={styles.avatar}>
            <UserOutlined />
          </span>
          <div>
            <div className={styles.adminName}>{user?.display_name ?? user?.username ?? '管理员'}</div>
            <div className={styles.adminMail}>{user?.username ? `${user.username}@ai-content.com` : 'admin@ai-content.com'}</div>
          </div>
        </div>
      </aside>

      <main className={styles.main}>
        <header className={styles.topbar}>
          <div className={styles.routeContext}>
            <span className={styles.eyebrow}>{routeMeta.contextEyebrow}</span>
            <h1>{routeMeta.contextTitle}</h1>
            <p>{routeMeta.contextDescription}</p>
          </div>
          <Input
            className={styles.globalSearch}
            size="large"
            prefix={<SearchOutlined />}
            placeholder="搜索文章、任务..."
          />
          <div />
          <div className={styles.toolbar}>
            <ThemeModeSwitch />
            <Badge dot offset={[-2, 2]}>
              <BellOutlined className={styles.bell} />
            </Badge>
            <span className={styles.topAvatar}>
              <UserOutlined />
            </span>
          </div>
        </header>

        <div className={styles.canvas}>
          <Outlet />
        </div>
      </main>
    </div>
  )
}
