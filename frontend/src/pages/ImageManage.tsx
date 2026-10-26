import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Segmented, Tag, Tooltip, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { Link } from 'react-router-dom'
import dayjs from 'dayjs'
import { listImages, type ImageAssetItem } from '@/api'
import { EmptyState, PageHeader, Panel, Stat, StatGrid, Toolbar } from '@/components/layout'
import styles from './ImageManage.module.css'

type Filter = 'all' | 'degraded'

const SPEC_FIELDS: Array<{ key: keyof ImageAssetItem['visual_spec']; label: string }> = [
  { key: 'subject', label: '主体' },
  { key: 'setting', label: '环境' },
  { key: 'composition', label: '构图' },
  { key: 'section_link', label: '对应论点' },
]

function formatTime(value: string): string {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '—'
}

export default function ImageManage() {
  const [items, setItems] = useState<ImageAssetItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<Filter>('all')

  const fetchImages = useCallback(async () => {
    setLoading(true)
    try {
      const response = await listImages({ limit: 200, degraded_only: filter === 'degraded' })
      setItems(response.items)
      setTotal(response.total)
    } catch {
      message.error('加载图片资产失败')
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    void fetchImages()
  }, [fetchImages])

  const summary = useMemo(() => {
    const degraded = items.filter((item) => item.degraded).length
    return {
      total: items.length,
      degraded,
      healthy: items.length - degraded,
    }
  }, [items])

  return (
    <div className={styles.page}>
      <PageHeader
        eyebrow="Console / Visual Assets"
        title="图片管理"
        description="查看每张生成图片的实拍提示词与视觉描述，用于人工确认画面是否与文章一致、是否夹带文字。"
        actions={
          <Button icon={<ReloadOutlined />} size="large" loading={loading} onClick={() => void fetchImages()}>
            刷新
          </Button>
        }
      />

      <StatGrid>
        <Stat label="当前列表" value={summary.total} />
        <Stat label="生成成功" value={summary.healthy} tone="positive" />
        <Stat label="缺失或降级" value={summary.degraded} tone="negative" />
      </StatGrid>

      <Toolbar actions={<span className={styles.meta}>共 {total} 条记录</span>}>
        <Segmented<Filter>
          value={filter}
          onChange={setFilter}
          options={[
            { label: '全部', value: 'all' },
            { label: '仅看失败', value: 'degraded' },
          ]}
        />
      </Toolbar>

      <div className={styles.notice}>
        本系统<strong>没有视觉模型</strong>，无法自动判断画面内容是否与文章一致、是否包含文字。
        此处展示的是生成时使用的提示词与视觉描述，最终判断需要人工完成。
      </div>

      {items.length === 0 && !loading ? (
        <Panel>
          <EmptyState
            title={filter === 'degraded' ? '没有失败或缺失的图片' : '暂无图片资产'}
            description={
              filter === 'degraded'
                ? '当前所有配图都成功生成。'
                : '运行一条开启配图的任务后，生成结果会出现在这里。'
            }
          />
        </Panel>
      ) : (
        <div className={styles.grid}>
          {items.map((item) => (
            <article
              key={`${item.task_id}-${item.role}-${item.created_at}`}
              className={`${styles.card} ${item.degraded ? styles.cardDegraded : ''}`.trim()}
            >
              <div className={styles.cardHead}>
                <span className={styles.role}>{item.role || 'visual'}</span>
                <Tag color={item.degraded ? 'error' : 'success'}>{item.degraded ? '缺失/降级' : '已生成'}</Tag>
              </div>

              {item.ref ? (
                <a href={item.ref} target="_blank" rel="noreferrer">
                  <img className={styles.thumb} src={item.ref} alt={item.visual_spec.subject || item.role} />
                </a>
              ) : (
                <div className={styles.thumbMissing}>生成失败，无图片文件</div>
              )}

              <h2 className={styles.cardTitle}>{item.article_title || '未命名文章'}</h2>

              {item.visual_spec.subject ? (
                <div className={styles.specList}>
                  {SPEC_FIELDS.map((field) => {
                    const value = item.visual_spec[field.key]
                    if (!value) {
                      return null
                    }
                    return (
                      <div key={field.key} className={styles.specRow}>
                        <span className={styles.specTerm}>{field.label}</span>
                        <span className={styles.specValue}>{String(value)}</span>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className={styles.specValue}>
                  这条记录生成于改造之前：当时没有视觉描述阶段，提示词由角色标识符与抓取正文拼接而成。
                </p>
              )}

              <Tooltip title="这张图实际发给图像模型的提示词">
                <pre className={styles.prompt}>{item.prompt || '(空提示词)'}</pre>
              </Tooltip>

              <div className={styles.meta}>
                <span>{formatTime(item.created_at)}</span>
                {item.style_id ? <span>风格：{item.style_id}</span> : null}
                <Link className={styles.metaLink} to={`/task/${item.task_id}`}>
                  查看任务
                </Link>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
