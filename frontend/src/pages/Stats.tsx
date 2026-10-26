import { useEffect, useMemo, useState } from 'react'
import { Button, Form, InputNumber, Modal, Segmented, Table, Tag, message } from 'antd'
import { ReloadOutlined, SyncOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import {
  getArticleStats,
  getStatsArticles,
  getStatsOverview,
  syncArticleStats,
  updateArticleStats,
  type StatsOverview,
  type StatsRangeDays,
  type StatsTopArticle,
  type StatsTrendPoint,
} from '@/api'
import { EmptyState, PageHeader, Panel, Stat, StatGrid } from '@/components/layout'
import styles from './Stats.module.css'

const RANGE_OPTIONS: Array<{ label: string; value: string }> = [
  { label: '近 7 天', value: '7' },
  { label: '近 30 天', value: '30' },
]

const EMPTY_OVERVIEW: StatsOverview = {
  total_articles: 0,
  total_published: 0,
  total_drafts: 0,
  total_reads: 0,
  total_shares: 0,
  total_collects: 0,
  total_likes: 0,
}

const CHART_WIDTH = 720
const CHART_HEIGHT = 260
const CHART_PADDING = { top: 20, right: 20, bottom: 34, left: 52 }

interface StatsEntryValues {
  read_num: number
  like_num: number
  share_num: number
  collect_num: number
  fav_num: number
}

type ChartSeries = {
  key: 'published' | 'reads'
  color: string
  points: string
}

function buildChart(trend: StatsTrendPoint[]): {
  series: ChartSeries[]
  gridLines: number[]
  ticks: Array<{ x: number; label: string }>
  maxLabel: number
} {
  const plotWidth = CHART_WIDTH - CHART_PADDING.left - CHART_PADDING.right
  const plotHeight = CHART_HEIGHT - CHART_PADDING.top - CHART_PADDING.bottom
  const maxValue = Math.max(1, ...trend.map((point) => Math.max(point.published, point.reads)))

  const xOf = (index: number) =>
    trend.length <= 1
      ? CHART_PADDING.left + plotWidth / 2
      : CHART_PADDING.left + (plotWidth * index) / (trend.length - 1)
  const yOf = (value: number) => CHART_PADDING.top + plotHeight - (plotHeight * value) / maxValue

  const toPoints = (pick: (point: StatsTrendPoint) => number) =>
    trend.map((point, index) => `${xOf(index).toFixed(1)},${yOf(pick(point)).toFixed(1)}`).join(' ')

  const tickStep = Math.max(1, Math.ceil(trend.length / 8))

  return {
    series: [
      { key: 'published', color: 'var(--accent)', points: toPoints((point) => point.published) },
      { key: 'reads', color: 'var(--status-warning-text)', points: toPoints((point) => point.reads) },
    ],
    gridLines: [0, 0.25, 0.5, 0.75, 1].map((ratio) => CHART_PADDING.top + plotHeight * ratio),
    ticks: trend
      .map((point, index) => ({ index, point }))
      .filter((item) => item.index % tickStep === 0)
      .map((item) => ({
        x: xOf(item.index),
        label: item.point.date?.slice(5) ?? '',
      })),
    maxLabel: maxValue,
  }
}

export default function Stats() {
  const [overview, setOverview] = useState<StatsOverview>(EMPTY_OVERVIEW)
  const [rangeDays, setRangeDays] = useState<StatsRangeDays>(7)
  const [trend, setTrend] = useState<StatsTrendPoint[]>([])
  const [topArticles, setTopArticles] = useState<StatsTopArticle[]>([])
  const [loadingOverview, setLoadingOverview] = useState(false)
  const [loadingArticles, setLoadingArticles] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [entryArticle, setEntryArticle] = useState<StatsTopArticle | null>(null)
  const [entryLoading, setEntryLoading] = useState(false)
  const [savingEntry, setSavingEntry] = useState(false)
  const [entryForm] = Form.useForm<StatsEntryValues>()

  const loadOverview = async () => {
    setLoadingOverview(true)
    try {
      setOverview(await getStatsOverview())
    } catch (error) {
      message.error(error instanceof Error ? error.message : '获取统计数据概览失败')
    } finally {
      setLoadingOverview(false)
    }
  }

  const loadArticles = async (nextRange: StatsRangeDays = rangeDays) => {
    setLoadingArticles(true)
    try {
      const data = await getStatsArticles(nextRange)
      setTrend(Array.isArray(data.trend) ? data.trend : [])
      setTopArticles(Array.isArray(data.top_articles) ? data.top_articles : [])
    } catch (error) {
      setTrend([])
      setTopArticles([])
      message.error(error instanceof Error ? error.message : '获取文章统计数据失败')
    } finally {
      setLoadingArticles(false)
    }
  }

  useEffect(() => {
    void loadOverview()
  }, [])

  useEffect(() => {
    void loadArticles(rangeDays)
  }, [rangeDays])

  const chart = useMemo(() => buildChart(trend), [trend])

  const handleSync = async () => {
    setSyncing(true)
    try {
      const result = await syncArticleStats()
      message.success(result.message || `同步完成：成功 ${result.synced}，失败 ${result.failed}`)
      await Promise.all([loadOverview(), loadArticles()])
    } catch (error) {
      message.error(error instanceof Error ? error.message : '同步微信数据失败')
    } finally {
      setSyncing(false)
    }
  }

  const openEntryModal = async (article: StatsTopArticle) => {
    setEntryArticle(article)
    entryForm.setFieldsValue({
      read_num: article.reads,
      like_num: article.likes,
      share_num: article.shares,
      collect_num: article.collects,
      fav_num: 0,
    })
    setEntryLoading(true)
    try {
      const detail = await getArticleStats(article.task_id)
      entryForm.setFieldsValue({
        read_num: detail.read_num,
        like_num: detail.like_num,
        share_num: detail.share_num,
        collect_num: detail.collect_num,
        fav_num: detail.fav_num,
      })
    } catch {
      // Fall back to the values already listed in the ranking table.
    } finally {
      setEntryLoading(false)
    }
  }

  const closeEntryModal = () => {
    setEntryArticle(null)
    entryForm.resetFields()
  }

  const submitEntry = async () => {
    if (!entryArticle) return
    let values: StatsEntryValues
    try {
      values = await entryForm.validateFields()
    } catch {
      return
    }

    setSavingEntry(true)
    try {
      await updateArticleStats(entryArticle.task_id, {
        read_num: values.read_num,
        like_num: values.like_num,
        share_num: values.share_num,
        collect_num: values.collect_num,
        fav_num: values.fav_num,
      })
      message.success('阅读数据已更新')
      closeEntryModal()
      await Promise.all([loadOverview(), loadArticles()])
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存阅读数据失败')
    } finally {
      setSavingEntry(false)
    }
  }

  const columns: ColumnsType<StatsTopArticle> = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (title: string, record) => (
        <div className={styles.articleTitle}>
          <strong>{title || '未命名文章'}</strong>
          <span>{record.task_id}</span>
        </div>
      ),
    },
    {
      title: '阅读',
      dataIndex: 'reads',
      key: 'reads',
      width: 100,
      sorter: (left, right) => left.reads - right.reads,
      defaultSortOrder: 'descend',
    },
    { title: '分享', dataIndex: 'shares', key: 'shares', width: 90 },
    { title: '收藏', dataIndex: 'collects', key: 'collects', width: 90 },
    { title: '点赞', dataIndex: 'likes', key: 'likes', width: 90 },
    {
      title: '发布时间',
      dataIndex: 'published_at',
      key: 'published_at',
      width: 180,
      render: (value: string | null) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'),
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_value, record) => (
        <Button size="small" onClick={() => void openEntryModal(record)}>
          手动录入
        </Button>
      ),
    },
  ]

  const refreshAll = () => {
    void loadOverview()
    void loadArticles()
  }

  return (
    <div className={styles.page}>
      <PageHeader
        eyebrow="Analytics"
        title="数据看板"
        description="查看文章产出、发布量与阅读互动数据的趋势和排行。"
        actions={
          <>
            <Segmented
              aria-label="统计区间"
              value={String(rangeDays)}
              options={RANGE_OPTIONS}
              onChange={(value) => setRangeDays(Number(value) === 30 ? 30 : 7)}
            />
            <Button icon={<SyncOutlined />} loading={syncing} onClick={() => void handleSync()}>
              同步微信数据
            </Button>
            <Button icon={<ReloadOutlined />} onClick={refreshAll}>
              刷新
            </Button>
          </>
        }
      />

      <StatGrid>
        <Stat label="累计文章" value={overview.total_articles} hint={loadingOverview ? '加载中' : undefined} />
        <Stat label="累计发布" value={overview.total_published} hint={loadingOverview ? '加载中' : undefined} />
        <Stat label="累计草稿" value={overview.total_drafts} hint={loadingOverview ? '加载中' : undefined} />
        <Stat label="总阅读" value={overview.total_reads} hint={loadingOverview ? '加载中' : undefined} />
        <Stat label="总分享" value={overview.total_shares} hint={loadingOverview ? '加载中' : undefined} />
        <Stat label="总收藏" value={overview.total_collects} hint={loadingOverview ? '加载中' : undefined} />
        <Stat label="总点赞" value={overview.total_likes} hint={loadingOverview ? '加载中' : undefined} />
      </StatGrid>

      <Panel title="创作与阅读趋势" aside="按发布日期聚合的发布量与阅读量走势。">
        {trend.length === 0 ? (
          <div className={styles.chartEmpty}>
            <EmptyState
              title={loadingArticles ? '正在加载趋势数据' : '所选区间暂无趋势数据'}
              description="发布或同步文章后，这里会显示发布量与阅读量的走势。"
            />
          </div>
        ) : (
          <div className={styles.chartStack}>
            <div className={styles.chartScroll}>
              <svg
                className={styles.chart}
                viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
                role="img"
                aria-label="发布量与阅读量趋势图"
                preserveAspectRatio="none"
              >
                {chart.gridLines.map((y) => (
                  <line
                    key={y}
                    x1={CHART_PADDING.left}
                    x2={CHART_WIDTH - CHART_PADDING.right}
                    y1={y}
                    y2={y}
                    stroke="var(--border-hairline)"
                    strokeDasharray="4 6"
                  />
                ))}
                {chart.ticks.map((tick) => (
                  <text
                    key={tick.x}
                    x={tick.x}
                    y={CHART_HEIGHT - 12}
                    textAnchor="middle"
                    fill="var(--text-tertiary)"
                    fontSize="11"
                  >
                    {tick.label}
                  </text>
                ))}
                <text
                  x={CHART_PADDING.left - 10}
                  y={CHART_PADDING.top + 4}
                  textAnchor="end"
                  fill="var(--text-tertiary)"
                  fontSize="11"
                >
                  {chart.maxLabel}
                </text>
                <text
                  x={CHART_PADDING.left - 10}
                  y={CHART_HEIGHT - CHART_PADDING.bottom}
                  textAnchor="end"
                  fill="var(--text-tertiary)"
                  fontSize="11"
                >
                  0
                </text>
                {chart.series.map((item) => (
                  <polyline
                    key={item.key}
                    points={item.points}
                    fill="none"
                    stroke={item.color}
                    strokeWidth={2.5}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                ))}
              </svg>
            </div>
            <div className={styles.chartLegend}>
              <span className={styles.chartLegendItem}>
                <span className={`${styles.chartLegendSwatch} ${styles.chartLegendSwatchPublished}`} />
                发布量
              </span>
              <span className={styles.chartLegendItem}>
                <span className={`${styles.chartLegendSwatch} ${styles.chartLegendSwatchReads}`} />
                阅读量
              </span>
            </div>
          </div>
        )}
      </Panel>

      <Panel
        title="文章阅读排行"
        aside="按阅读量倒序展示所选区间内的文章表现。"
        actions={<Tag>{rangeDays === 30 ? '近 30 天' : '近 7 天'}</Tag>}
        flush
      >
        {topArticles.length === 0 && !loadingArticles ? (
          <div className={styles.tableEmpty}>
            <EmptyState
              title="暂无文章统计数据"
              description="同步微信数据或手动录入阅读数后，排行会显示在这里。"
            />
          </div>
        ) : (
          <Table
            columns={columns}
            dataSource={topArticles}
            rowKey="task_id"
            loading={loadingArticles}
            size="middle"
            pagination={{ pageSize: 8, hideOnSinglePage: true }}
          />
        )}
      </Panel>

      <Modal
        open={Boolean(entryArticle)}
        title="手动录入阅读数据"
        okText="保存"
        cancelText="取消"
        confirmLoading={savingEntry}
        onOk={() => void submitEntry()}
        onCancel={closeEntryModal}
        destroyOnHidden
      >
        <p className={styles.entryHint}>
          {entryArticle ? `${entryArticle.title || entryArticle.task_id}（${entryArticle.task_id}）` : ''}
        </p>
        <Form form={entryForm} layout="vertical" disabled={entryLoading} preserve={false}>
          <div className={styles.entryGrid}>
            <Form.Item name="read_num" label="阅读数">
              <InputNumber min={0} className={styles.fullWidthField} />
            </Form.Item>
            <Form.Item name="like_num" label="点赞数">
              <InputNumber min={0} className={styles.fullWidthField} />
            </Form.Item>
            <Form.Item name="share_num" label="分享数">
              <InputNumber min={0} className={styles.fullWidthField} />
            </Form.Item>
            <Form.Item name="collect_num" label="收藏数">
              <InputNumber min={0} className={styles.fullWidthField} />
            </Form.Item>
            <Form.Item name="fav_num" label="推荐数">
              <InputNumber min={0} className={styles.fullWidthField} />
            </Form.Item>
          </div>
        </Form>
      </Modal>
    </div>
  )
}
