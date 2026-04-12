import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons'
import { Button, Empty, Result, Spin, Tag, message } from 'antd'
import {
  ARTICLE_STRATEGY_LABELS,
  getTask,
  retryTask,
  type TaskResponse,
} from '@/api'
import { HeroPanel, SectionBlock, StatusRail, type StatusRailStep } from '@/components/workbench'
import styles from './TaskDetail.module.css'

const SKILL_STEPS: StatusRailStep[] = [
  { key: 'initialize', title: '任务初始化', description: '验证参数并准备执行环境。' },
  { key: 'capture_hot_topics', title: '热点捕获', description: '抓取并筛选高分热点候选。' },
  { key: 'interpret_user_intent', title: '解析意图', description: '识别主题、读者和文章目标。' },
  { key: 'infer_style_profile', title: '推断风格', description: '自动生成公众号风格画像。' },
  { key: 'build_article_blueprint', title: '生成蓝图', description: '先产出结构化文章蓝图。' },
  { key: 'plan_search_queries', title: '规划搜索', description: '根据蓝图规划搜索词和信息需求。' },
  { key: 'search_web', title: '搜索网页', description: '优先搜索官网和高可信来源。' },
  { key: 'rank_sources', title: '排序来源', description: '按可信度和相关度筛选结果。' },
  { key: 'fetch_and_extract', title: '提取内容', description: '抓取网页并清洗正文。' },
  { key: 'generate_article', title: '生成文章', description: '调用模型按蓝图输出公众号文章。' },
  { key: 'generate_images', title: '处理图片', description: '生成或提取封面与插图。' },
  { key: 'push_to_draft', title: '推送草稿', description: '推送至微信公众号草稿箱。' },
]

interface WsPayload {
  task_id: string
  status: string
  current_skill: string
  progress: number
  message: string
  result: unknown
}

const STATUS_COPY: Record<string, string> = {
  pending: '等待执行',
  running: '执行中',
  done: '结果已交付',
  failed: '需要处理',
}

function formatDate(value: string | null | undefined) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}

function renderValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.length ? value.join(' / ') : '-'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

export default function TaskDetail() {
  const { id: taskId } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [task, setTask] = useState<TaskResponse | null>(null)
  const [wsStatus, setWsStatus] = useState<string>('pending')
  const [currentSkill, setCurrentSkill] = useState<string>('')
  const [progress, setProgress] = useState<number>(0)
  const [statusMessage, setStatusMessage] = useState<string>('正在连接...')

  const wsRef = useRef<WebSocket | null>(null)

  const handleRetry = async () => {
    if (!taskId) return
    try {
      await retryTask(taskId)
      message.success('已触发重试')
      setWsStatus('pending')
      setStatusMessage('尝试恢复连接...')
    } catch (error: any) {
      message.error(error.message || '重试请求失败')
    }
  }

  useEffect(() => {
    if (!taskId) return
    getTask(taskId)
      .then((result) => {
        setTask(result)
        setWsStatus(result.status)

        if (result.status === 'done') {
          setProgress(100)
          setStatusMessage('任务执行完成')
        } else if (result.status === 'failed') {
          setStatusMessage(result.error || '任务执行失败')
        } else {
          setStatusMessage('任务已载入，等待实时状态...')
        }
      })
      .catch(() => undefined)
  }, [taskId])

  useEffect(() => {
    if (!taskId) return

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsUrl = `${protocol}://${window.location.host}/ws/tasks/${taskId}`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setStatusMessage('已连接，等待任务执行...')
    }

    ws.onmessage = (event: MessageEvent<string>) => {
      try {
        const data: WsPayload = JSON.parse(event.data)
        setWsStatus(data.status)
        setCurrentSkill(data.current_skill)
        setProgress(data.progress)
        setStatusMessage(data.message)

        setTask((prev) => {
          if (!prev) return prev
          const nextTask = { ...prev, status: data.status as TaskResponse['status'] }
          if (data.result && typeof data.result === 'object') {
            const result = data.result as Record<string, any>
            if (result.generation_config) nextTask.generation_config = result.generation_config
            if (result.user_intent) nextTask.user_intent = result.user_intent
            if (result.style_profile) nextTask.style_profile = result.style_profile
            if (result.article_blueprint) nextTask.article_blueprint = result.article_blueprint
            if (result.article_plan) nextTask.article_plan = result.article_plan
            if (result.generated_article) nextTask.generated_article = result.generated_article
            if (result.draft_info) nextTask.draft_info = result.draft_info
          }
          return nextTask
        })
      } catch {
        // Ignore malformed messages from the socket.
      }
    }

    ws.onclose = () => {
      setStatusMessage((prev) =>
        prev.includes('完成') || prev.includes('失败') ? prev : '连接已断开',
      )
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [taskId])

  if (!taskId) return null

  const isLoading = !task
  const generatedArticle = task?.generated_article as
    | { title?: string; alt_titles?: string[]; content?: string }
    | undefined
  const metaItems = task
    ? [
        { label: '任务 ID', value: task.task_id },
        { label: '关键词', value: task.keywords },
        { label: '原始主题', value: task.original_keywords || '-' },
        {
          label: '热点命中',
          value: task.selected_hotspot?.title
            ? `${task.selected_hotspot.title} / ${task.selected_hotspot.platform_name || '未知平台'}`
            : '未命中 / 未启用',
        },
        { label: '创建时间', value: formatDate(task.created_at) },
        {
          label: '请求策略',
          value: ARTICLE_STRATEGY_LABELS[task.generation_config?.article_strategy || 'auto'],
        },
        {
          label: '实际策略',
          value: task.article_plan?.resolved_strategy_label || task.article_plan?.resolved_strategy || '待规划',
        },
      ]
    : []

  return (
    <div className={styles.page}>
      <HeroPanel
        eyebrow="Task Workspace"
        title={task?.keywords || '任务详情'}
        description="聚焦当前任务的执行轨迹、结构化结果和草稿交付状态。"
      >
        <div className={styles.heroActions} role="toolbar" aria-label="任务操作">
          <Tag color={wsStatus === 'done' ? 'success' : wsStatus === 'failed' ? 'error' : 'processing'}>
            {STATUS_COPY[wsStatus] ?? wsStatus}
          </Tag>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/task')}>
            返回创作台
          </Button>
          {wsStatus === 'failed' ? (
            <Button type="primary" icon={<ReloadOutlined />} onClick={handleRetry}>
              从断点重试
            </Button>
          ) : null}
        </div>
      </HeroPanel>

      {isLoading ? (
        <div className={styles.loadingWrap}>
          <Spin size="large" />
          <p>加载任务信息...</p>
        </div>
      ) : (
        <div className={styles.workspaceLayout}>
          <SectionBlock
            title="执行轨迹"
            aside={<span className={styles.sectionStatus}>{statusMessage}</span>}
          >
            <div className={styles.executionLayout}>
              <StatusRail
                taskStatus={wsStatus}
                currentSkill={currentSkill}
                progress={progress}
                statusMessage={statusMessage}
                steps={SKILL_STEPS}
              />

              <SectionBlock title="结果预览">
                {wsStatus === 'done' ? (
                  <div className={styles.successStack}>
                    <Result
                      status="success"
                      title="文章生成完毕并已推送到草稿箱"
                      subTitle={
                        task?.draft_info?.url ? (
                          <a href={String(task.draft_info.url)} target="_blank" rel="noreferrer">
                            查看微信草稿预览链接
                          </a>
                        ) : (
                          '草稿链接可在任务完成后查看。'
                        )
                      }
                    />

                    {generatedArticle?.title || generatedArticle?.content ? (
                      <article className={styles.articleCard}>
                        <header className={styles.articleHeader}>
                          <p className={styles.kicker}>Generated Article</p>
                          <h3>{generatedArticle?.title || '未返回标题'}</h3>
                          {generatedArticle?.alt_titles?.length ? (
                            <p className={styles.altTitles}>
                              备选标题：{generatedArticle.alt_titles.join(' / ')}
                            </p>
                          ) : null}
                        </header>
                        <div className={styles.articleContent}>
                          {generatedArticle?.content || '暂无正文内容。'}
                        </div>
                      </article>
                    ) : (
                      <Empty description="任务完成，但尚未返回正文内容。" />
                    )}
                  </div>
                ) : wsStatus === 'failed' ? (
                  <Result
                    status="error"
                    title="任务执行失败"
                    subTitle={statusMessage || task?.error || '未知错误'}
                    extra={[
                      <Button key="new" type="primary" onClick={() => navigate('/task')}>
                        创建新任务
                      </Button>,
                      <Button key="retry" icon={<ReloadOutlined />} onClick={handleRetry}>
                        从断点重新执行
                      </Button>,
                    ]}
                  />
                ) : (
                  <div className={styles.pendingState}>
                    <p className={styles.pendingLead}>任务仍在执行，结果区会持续接收实时更新。</p>
                    <p className={styles.pendingBody}>
                      当蓝图、文章正文或草稿链接返回后，这里会优先展示最新可交付结果。
                    </p>
                  </div>
                )}
              </SectionBlock>
            </div>
          </SectionBlock>

          <div className={styles.detailLayout}>
            <SectionBlock title="任务信息">
              <dl className={styles.metaGrid}>
                {metaItems.map((item) => (
                  <div key={item.label} className={styles.metaItem}>
                    <dt>{item.label}</dt>
                    <dd>{item.value}</dd>
                  </div>
                ))}
              </dl>
            </SectionBlock>

            <SectionBlock title="结构信号">
              <div className={styles.signalStack}>
                <div className={styles.signalCard}>
                  <span>读者角色</span>
                  <strong>{renderValue(task?.generation_config?.audience_roles)}</strong>
                </div>
                <div className={styles.signalCard}>
                  <span>意图摘要</span>
                  <pre>{renderValue(task?.user_intent)}</pre>
                </div>
                <div className={styles.signalCard}>
                  <span>风格画像</span>
                  <pre>{renderValue(task?.style_profile)}</pre>
                </div>
                <div className={styles.signalCard}>
                  <span>文章蓝图</span>
                  <pre>{renderValue(task?.article_blueprint)}</pre>
                </div>
              </div>
            </SectionBlock>
          </div>
        </div>
      )}
    </div>
  )
}

