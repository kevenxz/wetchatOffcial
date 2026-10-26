import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeftOutlined, EditOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { Alert, Button, Collapse, Empty, Popconfirm, Result, Spin, Table, Tag, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import {
  ARTICLE_STRATEGY_LABELS,
  cancelTask,
  getTask,
  listWorkflowRunSteps,
  retryTask,
  type PushRecord,
  type PublishStatus,
  type TaskResponse,
  type WorkflowRunStepRecord,
} from '@/api'
import { TruncatedText } from '@/components/layout'
import { HeroPanel, SectionBlock, StatusRail, ViralityScorecard, type StatusRailStep } from '@/components/workbench'
import styles from './TaskDetail.module.css'

const SKILL_STEPS: StatusRailStep[] = [
  { key: 'capture_hot_topics', title: '热点捕获', description: '抓取、打分并选择热点；关闭时透传主题。' },
  { key: 'intake_task_brief', title: '任务简报', description: '归一化主题、受众、热点和生成配置。' },
  { key: 'planner_agent', title: '流程规划', description: '确定文章类型、研究计划、图片策略和质量阈值。' },
  { key: 'analyze_hotspot_opportunities', title: '选题评估', description: '把热点候选转为可写选题。' },
  { key: 'plan_research', title: '研究规划', description: '拆解检索角度和证据覆盖目标。' },
  { key: 'run_research', title: '资料研究', description: '搜索、抓取并整理可信来源。' },
  { key: 'build_evidence_pack', title: '证据包', description: '提炼事实、数据、案例和风险边界。' },
  { key: 'resolve_article_type', title: '策略路由', description: '根据目标和证据选择文章类型。' },
  { key: 'design_viral_strategy', title: '传播策略', description: '定义读者张力、内容承诺与分享触发点。' },
  { key: 'outline_planner', title: '文章大纲', description: '基于搜索素材提炼标题、子标题、结构和证据映射。' },
  { key: 'merge_outline_strategy', title: '大纲策略融合', description: '把传播策略并入大纲，形成统一的写作骨架。' },
  { key: 'compose_draft', title: '写作成稿', description: '输出标题、摘要和公众号正文。' },
  { key: 'normalize_draft', title: '稿件归一化', description: '统一正文结构、插图占位和排版字段。' },
  { key: 'plan_visual_assets', title: '图片规划', description: '决定封面和文内配图需求。' },
  // 图片生成与图片审核在同一个节点内完成，使两条并发分支深度一致，
  // 质量门禁才能真正等到两侧都结束后再判定。
  { key: 'parallel_review', title: '并行审核', description: '同时执行文章质量审核与传播潜力评审。' },
  { key: 'image_agent', title: '生图与图片审核', description: '生成封面和文内插图，并检查完整性与内容适配度。' },
  { key: 'quality_gate', title: '质量门禁', description: '决定发布、修订或人工处理。' },
  { key: 'push_to_draft', title: '推送草稿', description: '推送至微信公众号草稿箱。' },
]

const PUBLISH_STATUS_LABELS: Record<PublishStatus, string> = {
  draft_only: '仅草稿',
  publishing: '发布中',
  published: '已发布',
  publish_failed: '发布失败',
  failed: '推送失败',
}

const PUBLISH_STATUS_COLORS: Record<PublishStatus, string> = {
  draft_only: 'default',
  publishing: 'processing',
  published: 'success',
  publish_failed: 'error',
  failed: 'error',
}

const CANCELLABLE_STATUSES: ReadonlyArray<TaskResponse['status']> = ['pending', 'queued', 'running']

interface WsPayload {
  task_id: string
  run_id?: string
  run_step_id?: string
  status: string
  current_skill: string
  progress: number
  message: string
  result: unknown
}

const STATUS_COPY: Record<string, string> = {
  pending: '等待执行',
  queued: '排队中',
  running: '执行中',
  done: '结果已交付',
  failed: '需要处理',
  cancelled: '已取消',
}

function formatDate(value: string | null | undefined) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}

function publishStatusOf(record: PushRecord): PublishStatus {
  if (record.publish_status) return record.publish_status
  return record.status === 'success' ? 'draft_only' : 'failed'
}

function draftUrlOf(record: PushRecord): string {
  const url = record.draft_info?.url
  return typeof url === 'string' && url.trim() ? url.trim() : ''
}

function renderValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.length ? value.join(' / ') : '-'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

function normalizeImageSrc(value: string | undefined) {
  if (!value) return ''
  if (/^https?:\/\//i.test(value) || value.startsWith('/')) return value
  const normalized = value.replace(/\\/g, '/')
  const marker = '/artifacts/'
  const index = normalized.indexOf(marker)
  if (index >= 0) return normalized.slice(index)
  if (value.startsWith('generated://')) return ''
  return value
}

function buildArticleHtml(content: string | undefined, illustrations: string[] | undefined) {
  const md = String(content || '').replace(/\[插图(\d+)\]/g, (_, rawIndex: string) => {
    const index = Number(rawIndex) - 1
    const src = normalizeImageSrc(illustrations?.[index])
    if (!src) return `[插图${rawIndex}]`
    return `<figure class="task-article-figure"><img src="${src}" alt="文章插图${rawIndex}" /></figure>`
  })
  return DOMPurify.sanitize(marked.parse(md, { breaks: true }) as string)
}

function normalizeArticleHtml(html: string | undefined) {
  if (!html) return ''
  const cleanHtml = DOMPurify.sanitize(html)
  const parser = new DOMParser()
  const doc = parser.parseFromString(cleanHtml, 'text/html')
  doc.querySelectorAll('img').forEach((image) => {
    const src = normalizeImageSrc(image.getAttribute('src') || '')
    if (src) {
      image.setAttribute('src', src)
    }
  })
  return doc.body.innerHTML
}

/**
 * Provenance for a photograph harvested from a reference article.
 *
 * Using a third-party photo forces human review, so the reviewer must be able to see where each
 * one came from — and be warned when a cover crop was aggressive, since nothing in this system
 * can tell whether the crop removed the subject.
 */
export interface ImageProvenance {
  label: string
  url: string
  warning?: string
}

function readProvenance(asset: Record<string, any>): ImageProvenance | undefined {
  if (String(asset.provider || '') !== 'source') return undefined
  const attribution = (asset.attribution || {}) as Record<string, any>
  const label = String(attribution.source_title || attribution.source_domain || '').trim()
  const url = String(attribution.source_url || '').trim()
  const notes = Array.isArray(asset.notes) ? asset.notes.filter(Boolean).join('；') : ''
  if (!label && !notes) return undefined
  return { label, url, warning: notes || undefined }
}

export function collectImageRefs(article: Record<string, any> | undefined) {
  if (!article) return []
  const refs: Array<{
    role: string
    src: string
    prompt?: string
    purpose?: string
    provenance?: ImageProvenance
  }> = []
  const seen = new Set<string>()
  const pushRef = (
    role: string,
    rawSrc: string | undefined,
    prompt?: string,
    purpose?: string,
    provenance?: ImageProvenance,
  ) => {
    const src = normalizeImageSrc(rawSrc)
    if (!src || seen.has(src)) return
    seen.add(src)
    refs.push({ role, src, prompt, purpose, provenance })
  }
  pushRef('cover', article.cover_image)
  ;(article.illustrations || []).forEach((item: string, index: number) => pushRef(`插图${index + 1}`, item))
  ;[...(article.images || []), ...(article.visual_assets || [])].forEach((asset: string | Record<string, any>, index: number) => {
    if (typeof asset === 'string') {
      pushRef(`图片${index + 1}`, asset)
      return
    }
    pushRef(
      String(asset.role || `图片${index + 1}`),
      String(asset.url || asset.path || asset.src || asset.ref || ''),
      String(asset.prompt || ''),
      String(asset.purpose || asset.section || ''),
      readProvenance(asset),
    )
  })
  return refs
}

export default function TaskDetail() {
  const { id: taskId } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [task, setTask] = useState<TaskResponse | null>(null)
  const [wsStatus, setWsStatus] = useState<string>('pending')
  const [currentSkill, setCurrentSkill] = useState<string>('')
  const [progress, setProgress] = useState<number>(0)
  const [statusMessage, setStatusMessage] = useState<string>('正在连接...')
  const [workflowSteps, setWorkflowSteps] = useState<WorkflowRunStepRecord[]>([])

  const wsRef = useRef<WebSocket | null>(null)

  const refreshWorkflowSteps = async () => {
    if (!taskId) return
    try {
      const steps = await listWorkflowRunSteps({ task_id: taskId })
      setWorkflowSteps(
        [...steps].sort((left, right) => {
          const leftTime = new Date(left.started_at || left.created_at).getTime()
          const rightTime = new Date(right.started_at || right.created_at).getTime()
          return leftTime - rightTime
        }),
      )
    } catch {
      // Step tracing is diagnostic; the task detail should still render if it fails.
    }
  }

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

  const handleCancel = async () => {
    if (!taskId) return
    try {
      const result = await cancelTask(taskId)
      setTask((prev) => (prev ? { ...prev, status: result.status } : result))
      setWsStatus(result.status)
      setStatusMessage('任务已取消')
      message.success('任务已取消')
    } catch (error: any) {
      message.error(error.message || '取消任务失败')
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
    refreshWorkflowSteps()
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
        if (data.run_step_id || data.status === 'done' || data.status === 'failed') {
          refreshWorkflowSteps()
        }

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
            if (result.viral_state) nextTask.viral_state = result.viral_state
            if (result.quality_state) nextTask.quality_state = result.quality_state
            if (result.quality_report) nextTask.quality_report = result.quality_report
            if ('human_review_required' in result) nextTask.human_review_required = Boolean(result.human_review_required)
            if (result.user_intent) nextTask.user_intent = result.user_intent
            if (result.style_profile) nextTask.style_profile = result.style_profile
            if (result.article_blueprint) nextTask.article_blueprint = result.article_blueprint
            if (result.article_plan) nextTask.article_plan = result.article_plan
            if (result.outline_result) nextTask.outline_result = result.outline_result
            if (result.generated_article) nextTask.generated_article = result.generated_article
            if (result.final_article) nextTask.final_article = result.final_article
            if (result.config_snapshot) nextTask.config_snapshot = result.config_snapshot
            if (result.selected_topic) nextTask.selected_topic = result.selected_topic
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
    | {
        title?: string
        alt_titles?: string[]
        content?: string
        summary?: string
        cover_image?: string
        illustrations?: string[]
        html_content?: string
        images?: Record<string, any>[]
        image_plan?: Record<string, any>
        outline_result?: Record<string, any>
      }
    | undefined
  const imageRefs = collectImageRefs(finalArticle)
  const htmlHasImages = /<img\s/i.test(String(finalArticle?.html_content || ''))
  const articleHtml = finalArticle?.html_content && (htmlHasImages || !finalArticle?.illustrations?.length)
    ? normalizeArticleHtml(finalArticle.html_content)
    : buildArticleHtml(finalArticle?.content, finalArticle?.illustrations)
  const coverImage = normalizeImageSrc(finalArticle?.cover_image)
  const outlineResult = task?.outline_result || task?.planning_state?.outline_result || finalArticle?.outline_result
  const qualityReport = task?.quality_report || task?.quality_state?.quality_report
  const viralStrategy = task?.viral_state?.strategy
  const viralReview = task?.viral_state?.review || task?.writing_state?.viral_review
  const hotspotCandidates = task?.hotspot_candidates || []
  const searchContract = task?.planning_state?.search_contract || task?.research_state?.search_contract
  const searchEvaluation = task?.research_state?.search_evaluation || task?.research_state?.evidence_pack?.search_evaluation
  const searchRuns = task?.research_state?.search_runs || []
  const citations = task?.research_state?.evidence_pack?.citations || []
  const sourceFiltering = task?.research_state?.source_filtering
  const hotspotSourceStatus = task?.research_state?.hotspot_source_status
  const blueprintSource = task?.planning_state?.blueprint_source
  const draftGenerationMode = task?.writing_state?.draft_generation_mode
  // A degraded run silently produces a template article; surface it prominently
  // instead of burying it in the diagnostics panel.
  const degradationNotices: string[] = []
  if (blueprintSource === 'fallback') {
    degradationNotices.push(
      `文章结构由本地模板生成（原因：${task?.planning_state?.blueprint_degraded_reason || '模型未返回可用结构'}）。
       请检查「模型配置」中的结构化模型是否为非推理模型。`,
    )
  }
  if (typeof draftGenerationMode === 'string' && draftGenerationMode.startsWith('fallback')) {
    degradationNotices.push(
      `正文由本地模板生成（原因：${task?.writing_state?.draft_degraded_reason || '模型调用失败'}）。`,
    )
  }
  if (sourceFiltering?.insufficient) {
    degradationNotices.push('过滤后可用来源不足，本文已标记为需要人工复核。')
  }
  if (hotspotSourceStatus && hotspotSourceStatus !== 'resolved') {
    degradationNotices.push(`未读取到热点原文（状态：${hotspotSourceStatus}），结构将主要依据搜索结果。`)
  }
  const stepByName = workflowSteps.reduce<Record<string, WorkflowRunStepRecord[]>>((acc, step) => {
    acc[step.step_name] = [...(acc[step.step_name] || []), step]
    return acc
  }, {})
  const orderedWorkflowSteps = [
    ...SKILL_STEPS.flatMap((step) => stepByName[step.key] || []),
    ...workflowSteps.filter((step) => !SKILL_STEPS.some((known) => known.key === step.step_name)),
  ]
  const pushRecords = task?.push_records ?? []
  const pushColumns: ColumnsType<PushRecord> = [
    {
      title: '账号',
      dataIndex: 'account_name',
      key: 'account_name',
      render: (_value, record) => record.account_name || record.account_id || '-',
    },
    {
      title: '推送状态',
      key: 'status',
      render: (_value, record) => (
        <Tag color={record.status === 'success' ? 'success' : 'error'}>
          {record.status === 'success' ? '推送成功' : '推送失败'}
        </Tag>
      ),
    },
    {
      title: '发布状态',
      key: 'publish_status',
      render: (_value, record) => {
        const status = publishStatusOf(record)
        return <Tag color={PUBLISH_STATUS_COLORS[status]}>{PUBLISH_STATUS_LABELS[status]}</Tag>
      },
    },
    {
      title: '发布 ID',
      dataIndex: 'publish_id',
      key: 'publish_id',
      render: (value: string | null | undefined) => value || '-',
    },
    {
      title: '主题',
      dataIndex: 'theme_name',
      key: 'theme_name',
      render: (value: string | null | undefined) => value || '-',
    },
    {
      title: '尝试次数',
      dataIndex: 'attempt',
      key: 'attempt',
      render: (value: number | undefined) => (value === undefined ? '-' : String(value)),
    },
    {
      title: '时间',
      dataIndex: 'pushed_at',
      key: 'pushed_at',
      render: (value: string) => formatDate(value),
    },
    {
      title: '操作',
      key: 'action',
      render: (_value, record) =>
        draftUrlOf(record) ? (
          <a href={draftUrlOf(record)} target="_blank" rel="noreferrer">
            查看草稿
          </a>
        ) : (
          '-'
        ),
    },
  ]
  const pushErrorRecords = pushRecords.filter((record) => Boolean(record.error))
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
          <Tag
            color={
              wsStatus === 'done'
                ? 'success'
                : wsStatus === 'failed'
                  ? 'error'
                  : wsStatus === 'cancelled'
                    ? 'warning'
                    : 'processing'
            }
          >
            {STATUS_COPY[wsStatus] ?? wsStatus}
          </Tag>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/task')}>
            返回创作台
          </Button>
          {CANCELLABLE_STATUSES.includes(wsStatus as TaskResponse['status']) ? (
            <Popconfirm
              title="确认取消任务"
              description="取消后本次任务将停止执行，已产生的中间结果会保留。"
              okText="取消任务"
              cancelText="再想想"
              onConfirm={() => void handleCancel()}
            >
              <Button danger icon={<StopOutlined />}>
                取消任务
              </Button>
            </Popconfirm>
          ) : null}
          {wsStatus === 'failed' ? (
            <Button type="primary" icon={<ReloadOutlined />} onClick={handleRetry}>
              从断点重试
            </Button>
          ) : null}
          <Button icon={<EditOutlined />} onClick={() => navigate('/articles')}>
            编辑文章
          </Button>
        </div>
      </HeroPanel>

      {isLoading ? (
        <div className={styles.loadingWrap}>
          <Spin size="large" />
          <p>加载任务信息...</p>
        </div>
      ) : (
        <div className={styles.workspaceLayout}>
          <ViralityScorecard strategy={viralStrategy} review={viralReview} />
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
                        {coverImage ? (
                          <figure className={styles.coverFrame}>
                            <img src={coverImage} alt={finalArticle?.title || '文章封面'} />
                          </figure>
                        ) : null}
                        <header className={styles.articleHeader}>
                          <p className={styles.kicker}>Generated Article</p>
                          <TruncatedText as="h3" lines={2}>
                            {finalArticle?.title || '未返回标题'}
                          </TruncatedText>
                          {finalArticle?.alt_titles?.length ? (
                            <p className={styles.altTitles}>
                              备选标题：{finalArticle.alt_titles.join(' / ')}
                            </p>
                          ) : null}
                        </header>
                        <div
                          className={styles.articleContent}
                          dangerouslySetInnerHTML={{ __html: articleHtml || '<p>暂无正文内容。</p>' }}
                        />
                        {imageRefs.length ? (
                          <div className={styles.imageGallery}>
                            {imageRefs.map((image) => (
                              <figure key={`${image.role}-${image.src}`} className={styles.imageCard}>
                                <img src={image.src} alt={image.role} />
                                <figcaption>
                                  <strong>{image.role}</strong>
                                  {image.purpose ? <span>{image.purpose}</span> : null}
                                  {image.provenance ? (
                                    <span className={styles.imageSource}>
                                      来源：
                                      {image.provenance.url ? (
                                        <a href={image.provenance.url} target="_blank" rel="noreferrer">
                                          {image.provenance.label || image.provenance.url}
                                        </a>
                                      ) : (
                                        image.provenance.label
                                      )}
                                    </span>
                                  ) : null}
                                  {image.provenance?.warning ? (
                                    <span className={styles.imageWarning}>{image.provenance.warning}</span>
                                  ) : null}
                                </figcaption>
                              </figure>
                            ))}
                          </div>
                        ) : null}
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
                ) : wsStatus === 'cancelled' ? (
                  <Result
                    status="warning"
                    title="任务已取消"
                    subTitle="本次任务已停止执行，已生成的中间结果仍保留在下方开发者诊断中。"
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
            {degradationNotices.length ? (
              <Alert
                type="warning"
                showIcon
                message="本次生成已降级，结果可能不达标"
                description={
                  <ul className={styles.noticeList}>
                    {degradationNotices.map((notice) => (
                      <li key={notice}>{notice}</li>
                    ))}
                  </ul>
                }
              />
            ) : null}

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

            <SectionBlock title="发布状态">
              {pushRecords.length ? (
                <div className={styles.signalStack}>
                  <Table
                    columns={pushColumns}
                    dataSource={pushRecords}
                    rowKey={(record) => record.push_id || record.account_id}
                    pagination={false}
                    size="small"
                    scroll={{ x: 'max-content' }}
                  />
                  {pushErrorRecords.length ? (
                    <ul className={styles.publishErrors} aria-label="推送错误">
                      {pushErrorRecords.map((record) => (
                        <li key={`${record.push_id || record.account_id}-error`}>
                          <strong>{record.account_name || record.account_id}</strong>
                          <span>{record.error}</span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {task?.draft_info?.url ? (
                    <a href={String(task.draft_info.url)} target="_blank" rel="noreferrer">
                      查看微信草稿预览链接
                    </a>
                  ) : null}
                </div>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未产生推送记录。" />
              )}
            </SectionBlock>

            <SectionBlock title="开发者诊断">
              <Collapse
                defaultActiveKey={[]}
                items={[
                  {
                    key: 'signals',
                    label: '结构信号（步骤输入输出与原始 JSON）',
                    children: (
              <div className={styles.signalStack}>
                <div className={styles.signalCard}>
                  <span>步骤输入输出</span>
                  {orderedWorkflowSteps.length ? (
                    <div className={styles.stepTraceList}>
                      {orderedWorkflowSteps.map((step, index) => (
                        <details key={step.run_step_id} className={styles.stepTraceItem}>
                          <summary>
                            <strong>{`${index + 1}. ${step.step_name}`}</strong>
                            <Tag color={step.status === 'failed' ? 'error' : step.status === 'succeeded' ? 'success' : 'processing'}>
                              {step.status}
                            </Tag>
                            <small>
                              {formatDate(step.started_at || step.created_at)}
                              {step.payload?.duration_ms ? ` · ${step.payload.duration_ms}ms` : ''}
                            </small>
                          </summary>
                          {step.error ? <p className={styles.stepError}>{step.error}</p> : null}
                          <div className={styles.stepTraceGrid}>
                            <section>
                              <h4>Input</h4>
                              <pre>{renderValue(step.payload?.input_state)}</pre>
                            </section>
                            <section>
                              <h4>Output</h4>
                              <pre>{renderValue(step.payload?.output)}</pre>
                            </section>
                            <section>
                              <h4>State After</h4>
                              <pre>{renderValue(step.payload?.state_after)}</pre>
                            </section>
                          </div>
                        </details>
                      ))}
                    </div>
                  ) : (
                    <pre>暂无步骤记录。新任务运行后会自动记录每一步输入和输出。</pre>
                  )}
                </div>
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
                  <span>传播策略</span>
                  <pre>{renderValue(viralStrategy)}</pre>
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
                  <span>文章大纲</span>
                  <pre>{renderValue(outlineResult)}</pre>
                </div>
                <div className={styles.signalCard}>
                  <span>图片计划</span>
                  <pre>{renderValue(task?.visual_state?.image_briefs || finalArticle?.image_plan)}</pre>
                </div>
                <div className={styles.signalCard}>
                  <span>图片资产</span>
                  <pre>{renderValue(task?.visual_state?.assets || finalArticle?.images)}</pre>
                </div>
                <div className={styles.signalCard}>
                  <span>Research Plan</span>
                  <pre>{renderValue(task?.planning_state?.research_plan)}</pre>
                </div>
                <div className={styles.signalCard}>
                  <span>Search Contract</span>
                  <pre>{renderValue(searchContract)}</pre>
                </div>
                <div className={styles.signalCard}>
                  <span>Search Evaluation</span>
                  <pre>{renderValue(searchEvaluation)}</pre>
                </div>
                <div className={styles.signalCard}>
                  <span>Search Rounds</span>
                  <pre>{renderValue(searchRuns)}</pre>
                </div>
                <div className={styles.signalCard}>
                  <span>Citations</span>
                  {citations.length ? (
                    <div className={styles.citationList}>
                      {citations.slice(0, 12).map((item: Record<string, any>, index: number) => (
                        <a
                          key={`${item.url || item.title || index}`}
                          href={String(item.url || '#')}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <strong>{item.title || item.domain || item.url}</strong>
                          <small>
                            {item.source_type || 'unknown'} · {item.confidence || 'unknown'}
                          </small>
                        </a>
                      ))}
                    </div>
                  ) : (
                    <pre>{renderValue(citations)}</pre>
                  )}
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
                    ),
                  },
                ]}
              />
            </SectionBlock>
          </div>
        </div>
      )}
    </div>
  )
}

