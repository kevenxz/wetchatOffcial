import { useEffect, useMemo, useState } from 'react'
import { Button, Empty, Progress, Switch, Tag, Tooltip, message } from 'antd'
import {
  CheckCircleOutlined,
  DownOutlined,
  ExportOutlined,
  FireOutlined,
  ReloadOutlined,
  SafetyOutlined,
  StarFilled,
  StarOutlined,
  SyncOutlined,
  UpOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  captureHotspotMonitor,
  convertTopicToTask,
  getHotspotMonitor,
  ignoreTopic,
  type HotspotCaptureConfig,
  type HotspotMonitorItem,
  type HotspotMonitorStats,
  type TopicStatus,
} from '@/api'
import styles from './TopicCenter.module.css'

type TopicFilter = 'all' | '科技' | 'AI' | '财经' | '军事' | '国际' | '社会' | '汽车'
type TopicMeta = Record<string, unknown>

const filterOptions: TopicFilter[] = ['all', '科技', 'AI', '财经', '军事', '国际', '社会', '汽车']

const filterLabels: Record<TopicFilter, string> = {
  all: '全部',
  科技: '科技',
  AI: 'AI',
  财经: '财经',
  军事: '军事',
  国际: '国际',
  社会: '社会',
  汽车: '汽车',
}

const defaultHotspotCapture: HotspotCaptureConfig = {
  enabled: true,
  source: 'tophub',
  categories: ['科技', '财经', '军事', '国际', '社会', '汽车'],
  platforms: [],
  filters: {
    top_n_per_platform: 10,
    min_selection_score: 45,
    exclude_keywords: [],
    prefer_keywords: ['AI', '芯片', '大模型', '利率', '新能源'],
  },
  fallback_topics: ['AI 产业趋势', '半导体供应链', '全球科技政策'],
}

const statusText: Record<TopicStatus, string> = {
  pending: '候选',
  ignored: '已忽略',
  converted: '已转任务',
}

function topicMeta(topic: HotspotMonitorItem): TopicMeta {
  return topic.metadata ?? {}
}

function numberValue(value: unknown, fallback = 0) {
  const number = Number(value)
  if (!Number.isFinite(number)) return fallback
  return Math.max(0, Math.min(100, Math.round(number)))
}

function textValue(value: unknown, fallback = '') {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback
}

function listValue(value: unknown) {
  if (!Array.isArray(value)) return []
  return value.map((item) => String(item).trim()).filter(Boolean)
}

function getCategory(topic: HotspotMonitorItem) {
  const meta = topicMeta(topic)
  return topic.category || textValue(meta.category) || topic.tags?.[0] || '科技'
}

function getHotScore(topic: HotspotMonitorItem) {
  return numberValue(topic.hot_score, 0)
}

function getFitScore(topic: HotspotMonitorItem) {
  return numberValue(topic.account_fit_score, 0)
}

function getRiskScore(topic: HotspotMonitorItem) {
  return numberValue(topic.risk_score, 0)
}

function getSource(topic: HotspotMonitorItem) {
  const meta = topicMeta(topic)
  return topic.source || textValue(meta.platform_name) || textValue(meta.source, '热点源')
}

function getChannelCount(topic: HotspotMonitorItem) {
  return numberValue(topic.channel_count, 1)
}

function getTags(topic: HotspotMonitorItem) {
  const meta = topicMeta(topic)
  const tags = [
    ...(topic.tags ?? []),
    getCategory(topic),
    ...listValue(meta.tags),
    ...listValue(meta.keywords),
  ]
  return Array.from(new Set(tags.map((item) => item.trim()).filter(Boolean))).slice(0, 5)
}

function riskTone(score: number) {
  if (score >= 70) return { label: `高风险 (${score})`, className: styles.riskHigh }
  if (score >= 40) return { label: `中风险 (${score})`, className: styles.riskMedium }
  return { label: `低风险 (${score})`, className: styles.riskLow }
}

function isRecommended(topic: HotspotMonitorItem) {
  return topic.recommended
}

function formatRelativeTime(value?: string | null) {
  if (!value) return '刚刚'
  const minutes = Math.max(0, dayjs().diff(dayjs(value), 'minute'))
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}小时前`
  return `${Math.floor(hours / 24)}天前`
}

export default function TopicCenter() {
  const [topics, setTopics] = useState<HotspotMonitorItem[]>([])
  const [monitorStats, setMonitorStats] = useState<HotspotMonitorStats | null>(null)
  const [category, setCategory] = useState<TopicFilter>('all')
  const [recommendedOnly, setRecommendedOnly] = useState(false)
  const [loading, setLoading] = useState(false)
  const [capturing, setCapturing] = useState(false)
  const [actionLoadingId, setActionLoadingId] = useState('')
  const [expandedId, setExpandedId] = useState('')

  const fetchTopics = async () => {
    setLoading(true)
    try {
      const data = await getHotspotMonitor({ status: 'pending', limit: 80 })
      setTopics(data.items)
      setMonitorStats(data.stats)
    } catch (error) {
      setTopics([])
      setMonitorStats(null)
      message.error(error instanceof Error ? error.message : '获取热点列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchTopics()
  }, [])

  useEffect(() => {
    if (!expandedId && topics.length) {
      setExpandedId(topics[0].topic_id)
    }
  }, [expandedId, topics])

  const filteredTopics = useMemo(() => {
    return topics
      .filter((topic) => category === 'all' || getCategory(topic) === category || topic.tags?.includes(category))
      .filter((topic) => !recommendedOnly || isRecommended(topic))
      .sort((a, b) => getHotScore(b) - getHotScore(a))
  }, [category, recommendedOnly, topics])

  const stats = useMemo(() => {
    if (monitorStats) {
      return {
        total: monitorStats.total,
        recommended: monitorStats.recommended,
        highRisk: monitorStats.high_risk,
        sourceCount: monitorStats.source_count,
        latestText: monitorStats.latest_captured_at ? formatRelativeTime(monitorStats.latest_captured_at) : '尚未抓取',
      }
    }
    const highRisk = topics.filter((topic) => getRiskScore(topic) >= 70).length
    const recommended = topics.filter(isRecommended).length
    const sortedTimes = topics
      .map((topic) => topic.updated_at || topic.captured_at)
      .filter(Boolean)
      .sort()
    const latest = sortedTimes[sortedTimes.length - 1]
    return {
      total: topics.length,
      recommended,
      highRisk,
      sourceCount: new Set(topics.map(getSource)).size,
      latestText: latest ? formatRelativeTime(latest) : '尚未抓取',
    }
  }, [monitorStats, topics])

  const handleCapture = async () => {
    setCapturing(true)
    try {
      const result = await captureHotspotMonitor({
        keywords: '热点监控',
        hotspot_capture: defaultHotspotCapture,
      })
      const count = result.items.length
      message.success(count ? `已抓取 ${count} 条热点` : '抓取完成，暂无命中热点')
      setTopics(result.items)
      setMonitorStats(result.stats)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '热点抓取失败')
    } finally {
      setCapturing(false)
    }
  }

  const runTopicAction = async (topicId: string, action: 'ignore' | 'convert') => {
    setActionLoadingId(`${topicId}:${action}`)
    try {
      if (action === 'ignore') {
        await ignoreTopic(topicId)
        message.success('已忽略热点')
      } else {
        const task = await convertTopicToTask(topicId)
        message.success(`已生成任务：${task.task_id}`)
      }
      await fetchTopics()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '热点操作失败')
    } finally {
      setActionLoadingId('')
    }
  }

  const renderTopic = (topic: HotspotMonitorItem, index: number) => {
    const hotScore = getHotScore(topic)
    const fitScore = getFitScore(topic)
    const riskScore = getRiskScore(topic)
    const risk = riskTone(riskScore)
    const expanded = expandedId === topic.topic_id
    const recommended = isRecommended(topic)
    const source = getSource(topic)
    const createdText = formatRelativeTime(topic.captured_at)
    const channelCount = getChannelCount(topic)
    const summary = topic.summary || textValue(topicMeta(topic).extra_text, '暂无摘要')

    return (
      <article key={topic.topic_id} className={`${styles.topicCard} ${expanded ? styles.topicCardExpanded : ''}`.trim()}>
        <div className={styles.topicMain}>
          <div className={styles.hotScore}>
            <strong>{hotScore || 60 + index}</strong>
            <span>热度</span>
          </div>
          <div className={styles.topicContent}>
            <div className={styles.topicHeader}>
              <h2>{topic.title}</h2>
              <div className={styles.topicActions}>
                {recommended ? (
                  <Tag className={styles.recommendTag} icon={<StarFilled />}>
                    推荐
                  </Tag>
                ) : null}
                {topic.url ? (
                  <Tooltip title="打开来源">
                    <Button
                      type="text"
                      size="small"
                      icon={<ExportOutlined />}
                      href={topic.url}
                      target="_blank"
                      rel="noreferrer"
                    />
                  </Tooltip>
                ) : null}
                <Button
                  type="text"
                  size="small"
                  icon={expanded ? <UpOutlined /> : <DownOutlined />}
                  aria-label={expanded ? '收起热点' : '展开热点'}
                  onClick={() => setExpandedId(expanded ? '' : topic.topic_id)}
                />
              </div>
            </div>
            <div className={styles.metaLine}>
              <span>{createdText}</span>
              <span>来源：{source}</span>
              <span>{channelCount}个渠道</span>
              <span className={risk.className}>{risk.label}</span>
              <span className={styles.fitText}>匹配度 {fitScore}%</span>
              {topic.status !== 'pending' ? <span>{statusText[topic.status]}</span> : null}
            </div>
            <div className={styles.tags}>
              {getTags(topic).map((tag) => (
                <Tag key={tag} className={styles.topicTag}>
                  {tag}
                </Tag>
              ))}
            </div>
          </div>
        </div>

        {expanded ? (
          <div className={styles.topicDetail}>
            <p>{summary}</p>
            <div className={styles.scoreGrid}>
              <div className={styles.scoreBox}>
                <span>热度评分</span>
                <div>
                  <Progress percent={hotScore} showInfo={false} strokeColor="#ff6b00" />
                  <strong>{hotScore}</strong>
                </div>
              </div>
              <div className={styles.scoreBox}>
                <span>账号匹配</span>
                <div>
                  <Progress percent={fitScore} showInfo={false} strokeColor="#6254f3" />
                  <strong>{fitScore}</strong>
                </div>
              </div>
              <div className={styles.scoreBox}>
                <span>风险评分</span>
                <div>
                  <Progress percent={riskScore} showInfo={false} strokeColor="#10b981" />
                  <strong>{riskScore}</strong>
                </div>
              </div>
            </div>
            <div className={styles.detailActions}>
              <Button
                onClick={() => void runTopicAction(topic.topic_id, 'ignore')}
                loading={actionLoadingId === `${topic.topic_id}:ignore`}
              >
                忽略
              </Button>
              <Button
                type="primary"
                icon={<CheckCircleOutlined />}
                onClick={() => void runTopicAction(topic.topic_id, 'convert')}
                loading={actionLoadingId === `${topic.topic_id}:convert`}
              >
                立即生成文章
              </Button>
            </div>
          </div>
        ) : null}
      </article>
    )
  }

  return (
    <div className={styles.page}>
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <span className={`${styles.statIcon} ${styles.statHot}`}>
            <FireOutlined />
          </span>
          <div>
            <span>今日捕获热点</span>
            <strong>{stats.total}</strong>
            <em>来自{stats.sourceCount || 0}个来源</em>
          </div>
        </div>
        <div className={styles.statCard}>
          <span className={`${styles.statIcon} ${styles.statRecommend}`}>
            <StarOutlined />
          </span>
          <div>
            <span>推荐选题</span>
            <strong>{stats.recommended}</strong>
            <em>适合账号定位</em>
          </div>
        </div>
        <div className={styles.statCard}>
          <span className={`${styles.statIcon} ${styles.statRisk}`}>
            <SafetyOutlined />
          </span>
          <div>
            <span>高风险拦截</span>
            <strong>{stats.highRisk}</strong>
            <em>需人工审核</em>
          </div>
        </div>
        <div className={styles.statCard}>
          <span className={`${styles.statIcon} ${styles.statSync}`}>
            <SyncOutlined />
          </span>
          <div>
            <span>上次更新</span>
            <strong>{stats.latestText}</strong>
            <em>自动抓取</em>
          </div>
        </div>
      </div>

      <div className={styles.filterBar}>
        <div className={styles.categoryTabs}>
          {filterOptions.map((item) => (
            <Button
              key={item}
              className={`${styles.categoryButton} ${category === item ? styles.categoryButtonActive : ''}`.trim()}
              onClick={() => setCategory(item)}
            >
              {filterLabels[item]}
            </Button>
          ))}
        </div>
        <div className={styles.filterActions}>
          <Switch checked={recommendedOnly} onChange={setRecommendedOnly} />
          <span>只看推荐</span>
          <Button icon={<ReloadOutlined />} onClick={() => void handleCapture()} loading={capturing}>
            立即抓取
          </Button>
        </div>
      </div>

      <div className={styles.topicList} aria-busy={loading}>
        {filteredTopics.length === 0 && !loading ? (
          <Empty description="暂无热点候选" style={{ padding: 64 }} />
        ) : (
          filteredTopics.map(renderTopic)
        )}
      </div>
    </div>
  )
}
