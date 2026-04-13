import { WechatOutlined } from '@ant-design/icons'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { navigationItems, resolveRouteMeta } from '@/config/navigation'
import HeroPanel from './HeroPanel'
import ThemeModeSwitch from './ThemeModeSwitch'
import SectionBlock from './SectionBlock'
import styles from './WorkbenchShell.module.css'

export default function WorkbenchShell() {
  const location = useLocation()
  const routeMeta = resolveRouteMeta(location.pathname)

  return (
    <div className={styles.shell}>
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
