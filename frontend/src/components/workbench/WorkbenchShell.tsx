import { useEffect, useMemo, useRef, useState } from 'react'
import { BellOutlined, SearchOutlined, UserOutlined } from '@ant-design/icons'
import { Badge, Dropdown, Empty, Input, Menu, Tooltip } from 'antd'
import type { InputRef } from 'antd'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { listTasks, searchAll, type SearchResponse } from '@/api'
import BrandMark from '@/components/brand/BrandMark'
import { navigationItems, resolveRouteMeta } from '@/config/navigation'
import useAuthStore from '@/store/authStore'
import ThemeModeSwitch from './ThemeModeSwitch'
import styles from './WorkbenchShell.module.css'

const SEARCH_DEBOUNCE_MS = 300
const REVIEW_REFRESH_MS = 60_000

const EMPTY_RESULTS: SearchResponse = { tasks: [], articles: [], topics: [] }

export default function WorkbenchShell() {
  const location = useLocation()
  const routeMeta = resolveRouteMeta(location.pathname)
  const user = useAuthStore((state) => state.user)
  const navigate = useNavigate()
  const searchInputRef = useRef<InputRef>(null)

  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResponse>(EMPTY_RESULTS)
  const [searchLoading, setSearchLoading] = useState(false)
  const [reviewCount, setReviewCount] = useState(0)

  // ⌘K / Ctrl+K focuses the global search: one keyboard entry point for the console.
  const shortcutLabel = useMemo(() => {
    const agent = typeof navigator === 'undefined' ? '' : navigator.userAgent
    return /Mac|iPhone|iPad|iPod/.test(agent) ? '⌘ K' : 'Ctrl K'
  }, [])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        searchInputRef.current?.focus()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  useEffect(() => {
    const trimmed = query.trim()
    if (!trimmed) {
      setResults(EMPTY_RESULTS)
      setSearchLoading(false)
      return
    }

    let cancelled = false
    setSearchLoading(true)
    const timer = window.setTimeout(() => {
      searchAll(trimmed)
        .then((response) => {
          if (cancelled) return
          setResults({
            tasks: response.tasks ?? [],
            articles: response.articles ?? [],
            topics: response.topics ?? [],
          })
        })
        .catch(() => {
          if (cancelled) return
          setResults(EMPTY_RESULTS)
        })
        .finally(() => {
          if (!cancelled) setSearchLoading(false)
        })
    }, SEARCH_DEBOUNCE_MS)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [query])

  useEffect(() => {
    let active = true

    const loadReviewCount = () => {
      listTasks()
        .then((tasks) => {
          if (!active) return
          setReviewCount(
            tasks.filter((task) => task.human_review_required || task.status === 'failed').length,
          )
        })
        .catch(() => {
          if (active) setReviewCount(0)
        })
    }

    loadReviewCount()
    const timer = window.setInterval(loadReviewCount, REVIEW_REFRESH_MS)

    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [])

  const totalResults = results.tasks.length + results.articles.length + results.topics.length

  const menuItems = useMemo(
    () => [
      {
        type: 'group' as const,
        key: 'group-tasks',
        label: `任务（${results.tasks.length}）`,
        children: results.tasks.length
          ? results.tasks.map((task) => ({
              key: `task:${task.task_id}`,
              label: task.keywords || task.task_id,
            }))
          : [{ key: 'task-empty', label: '暂无匹配任务', disabled: true }],
      },
      {
        type: 'group' as const,
        key: 'group-articles',
        label: `文章（${results.articles.length}）`,
        children: results.articles.length
          ? results.articles.map((article) => ({
              key: `article:${article.task_id}`,
              label: article.keywords || article.task_id,
            }))
          : [{ key: 'article-empty', label: '暂无匹配文章', disabled: true }],
      },
      {
        type: 'group' as const,
        key: 'group-topics',
        label: `热点（${results.topics.length}）`,
        children: results.topics.length
          ? results.topics.map((topic) => ({
              key: `topic:${topic.topic_id}`,
              label: topic.title || topic.topic_id,
            }))
          : [{ key: 'topic-empty', label: '暂无匹配热点', disabled: true }],
      },
    ],
    [results],
  )

  const handleResultClick = (key: string) => {
    if (key.startsWith('task:') || key.startsWith('article:')) {
      const taskId = key.slice(key.indexOf(':') + 1)
      navigate(`/task/${taskId}`)
    } else if (key.startsWith('topic:')) {
      navigate('/topics')
    }
    searchInputRef.current?.blur()
  }

  const searchOpen = Boolean(query.trim()) && (searchLoading || totalResults > 0)

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <BrandMark size={34} />
          <div>
            <strong className={styles.brandTitle}>AI 内容工厂</strong>
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
          <Dropdown
            open={searchOpen}
            trigger={['click']}
            placement="bottomLeft"
            dropdownRender={() => (
              <div className={styles.searchPanel}>
                {totalResults === 0 ? (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={searchLoading ? '搜索中...' : '未找到匹配结果'}
                  />
                ) : (
                  <Menu
                    items={menuItems}
                    selectable={false}
                    onClick={({ key }) => handleResultClick(String(key))}
                  />
                )}
              </div>
            )}
          >
            <Input
              ref={searchInputRef}
              className={styles.globalSearch}
              size="large"
              prefix={<SearchOutlined />}
              suffix={
                <span className={styles.commandHint} aria-hidden="true">
                  {shortcutLabel}
                </span>
              }
              placeholder="搜索文章、任务、热点..."
              allowClear
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </Dropdown>
          <div />
          <div className={styles.toolbar}>
            <ThemeModeSwitch />
            <Tooltip title="待处理审核与失败任务">
              <button
                type="button"
                className={styles.bellButton}
                aria-label="通知"
                onClick={() => navigate('/reviews')}
              >
                <Badge count={reviewCount} size="small" offset={[2, -2]}>
                  <BellOutlined className={styles.bell} />
                </Badge>
              </button>
            </Tooltip>
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
