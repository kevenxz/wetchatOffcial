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
  { key: 'capture_hot_topics', title: '热点捕获', description: '抓取、打分并选择热点；关闭时透传主题。' },
  { key: 'intake_task_brief', title: '任务简报', description: '归一化主题、受众、热点和生成配置。' },
  { key: 'planner_agent', title: '流程规划', description: '确定文章类型、研究计划、图片策略和质量阈值。' },
  { key: 'analyze_hotspot_opportunities', title: '选题评估', description: '把热点候选转为可写选题。' },
  { key: 'plan_research', title: '研究规划', description: '拆解检索角度和证据覆盖目标。' },
  { key: 'run_research', title: '资料研究', description: '搜索、抓取并整理可信来源。' },
  { key: 'build_evidence_pack', title: '证据包', description: '提炼事实、数据、案例和风险边界。' },
  { key: 'plan_article_angle', title: '文章角度', description: '生成论点、结构和段落目标。' },
  { key: 'compose_draft', title: '写作成稿', description: '输出标题、摘要和公众号正文。' },
  { key: 'review_article_draft', title: '文章审核', description: '检查结构、事实支撑和表达风险。' },
  { key: 'plan_visual_assets', title: '图片规划', description: '决定封面和文内配图需求。' },
  { key: 'generate_visual_assets', title: '图片生成', description: '生成图片资产并合入文章。' },
  { key: 'review_visual_assets', title: '图片审核', description: '检查图片完整性和内容适配度。' },
  { key: 'quality_gate', title: '质量门禁', description: '决定发布、修订或人工处理。' },
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
            if (result.keywords) nextTask.keywords = result.keywords
            if (result.original_keywords) nextTask.original_keywords = result.original_keywords
            if (result.hotspot_capture_config) nextTask.hotspot_capture_config = result.hotspot_capture_config
            if (Array.isArray(result.hotspot_candidates)) nextTask.hotspot_candidates = result.hotspot_candidates
            if ('selected_hotspot' in result) nextTask.selected_hotspot = result.selected_hotspot
            if ('hotspot_capture_error' in result) nextTask.hotspot_capture_error = result.hotspot_capture_error
            if (result.task_brief) nextTask.task_brief = result.task_brief
            if (result.planning_state) nextTask.planning_state = result.planning_state
            if (result.research_state) nextTask.research_state = result.research_state
            if (result.writing_state) nextTask.writing_state = result.writing_state
            if (result.visual_state) nextTask.visual_state = result.visual_state
            if (result.quality_state) nextTask.quality_state = result.quality_state
            if (result.quality_report) nextTask.quality_report = result.quality_report
            if ('human_review_required' in result) nextTask.human_review_required = Boolean(result.human_review_required)
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
  const finalArticle = (task?.final_article || task?.generated_article) as
    | { title?: string; alt_titles?: string[]; content?: string; summary?: string; cover_image?: string }
    | undefined
  const qualityReport = task?.quality_report || task?.quality_state?.quality_report
  const hotspotCandidates = task?.hotspot_candidates || []
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
        {
          label: '复核状态',
          value: task.human_review_required ? '需要人工复核' : '未要求人工复核',
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
                      status={task?.human_review_required ? 'warning' : 'success'}
                      title={task?.human_review_required ? '文章已生成，但需要人工复核' : '文章生成完毕'}
                      subTitle={
                        task?.draft_info?.url ? (
                          <a href={String(task.draft_info.url)} target="_blank" rel="noreferrer">
                            查看微信草稿预览链接
                          </a>
                        ) : (
                          '如为定时任务，草稿推送结果会记录在文章管理页和推送记录中。'
                        )
                      }
                    />

                    {finalArticle?.title || finalArticle?.content ? (
                      <article className={styles.articleCard}>
                        <header className={styles.articleHeader}>
                          <p className={styles.kicker}>Generated Article</p>
                          <h3>{finalArticle?.title || '未返回标题'}</h3>
                          {finalArticle?.alt_titles?.length ? (
                            <p className={styles.altTitles}>
                              备选标题：{finalArticle.alt_titles.join(' / ')}
                            </p>
                          ) : null}
                        </header>
                        <div className={styles.articleContent}>
                          {finalArticle?.content || '暂无正文内容。'}
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
                  <span>热点候选</span>
                  <pre>
                    {hotspotCandidates.length
                      ? renderValue(
                          hotspotCandidates.slice(0, 5).map((item) => ({
                            title: item.title,
                            platform: item.platform_name,
                            score: item.selection_score,
                          })),
                        )
                      : task?.hotspot_capture_error || '未启用热点捕获或暂无候选。'}
                  </pre>
                </div>
                <div className={styles.signalCard}>
                  <span>质量报告</span>
                  <pre>{renderValue(qualityReport)}</pre>
                </div>
                <div className={styles.signalCard}>
                  <span>读者角色</span>
                  <strong>{renderValue(task?.generation_config?.audience_roles)}</strong>
                </div>
                <div className={styles.signalCard}>
                  <span>任务简报</span>
                  <pre>{renderValue(task?.task_brief)}</pre>
                </div>
                <div className={styles.signalCard}>
                  <span>配置快照</span>
                  <pre>{renderValue(task?.config_snapshot)}</pre>
                </div>
                <div className={styles.signalCard}>
                  <span>选题决策</span>
                  <pre>{renderValue(task?.selected_topic)}</pre>
                </div>
                <div className={styles.signalCard}>
                  <span>研究状态</span>
                  <pre>{renderValue(task?.research_state)}</pre>
                </div>
                <div className={styles.signalCard}>
                  <span>写作审核</span>
                  <pre>{renderValue(task?.writing_state?.article_review || task?.writing_state)}</pre>
                </div>
              </div>
            </SectionBlock>
          </div>
        </div>
      )}
    </div>
  )
}

