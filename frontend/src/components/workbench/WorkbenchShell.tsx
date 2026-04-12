import { BulbOutlined, CompassOutlined, WechatOutlined } from '@ant-design/icons'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { navigationItems, resolveRouteMeta } from '@/config/navigation'
import HeroPanel from './HeroPanel'
import MetricCard from './MetricCard'
import ThemeModeSwitch from './ThemeModeSwitch'
import SectionBlock from './SectionBlock'
import SignalCard from './SignalCard'
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
          >
            <div className={styles.metrics}>
              <MetricCard label="Focus" value="01" hint="当前界面统一由路由元数据驱动" />
              <MetricCard label="Shell" value="Live" hint="导航、标题和内容画布已接通" />
              <MetricCard label="Stage" value="Task 2" hint="页面内部重设计留给后续任务" />
            </div>
          </HeroPanel>

          <div className={styles.overview}>
            <SectionBlock title="工作区">
              <div className={styles.canvas}>
                <Outlet />
              </div>
            </SectionBlock>
            <SectionBlock title="工作台信号">
              <SignalCard
                icon={<CompassOutlined />}
                title="Route metadata"
                description="标题、说明和导航状态从共享配置解析，便于后续扩展。"
              />
              <SignalCard
                icon={<BulbOutlined />}
                title="Shared container"
                description="当前只提供统一框架，不改写现有页面内部逻辑。"
              />
            </SectionBlock>
          </div>
        </div>
      </main>
    </div>
  )
}
