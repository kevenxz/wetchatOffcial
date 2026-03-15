import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Card,
  Steps,
  Typography,
  Tag,
  Space,
  Button,
  Progress,
  Descriptions,
  Result,
  Spin,
  Divider,
  message,
} from 'antd'
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  ClockCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { getTask, retryTask, type TaskResponse } from '@/api'
import styles from './TaskDetail.module.css'

const { Title, Text } = Typography

/** 工作流 Skill 节点元信息 */
const SKILL_STEPS = [
  { key: 'initialize', title: '任务初始化', description: '验证参数、准备执行环境' },
  { key: 'search_web', title: '搜索网页', description: '根据关键词搜索相关链接' },
  { key: 'fetch_and_extract', title: '提取内容', description: '抓取网页并清洗正文' },
  { key: 'generate_article', title: '生成文章', description: '调用 LLM 生成公众号文章' },
  { key: 'generate_images', title: '处理图片', description: '生成或提取封面与插图' },
  { key: 'push_to_draft', title: '推送草稿', description: '推送至微信公众号草稿箱' },
]

interface WsPayload {
  task_id: string
  status: string
  current_skill: string
  progress: number
  message: string
  result: unknown
}

const STATUS_COLOR: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  done: 'success',
  failed: 'error',
}

const STATUS_LABEL: Record<string, string> = {
  pending: '等待中',
  running: '执行中',
  done: '已完成',
  failed: '失败',
}

function getStepStatus(
  skillKey: string,
  currentSkill: string,
  taskStatus: string,
): 'wait' | 'process' | 'finish' | 'error' {
  const currentIdx = SKILL_STEPS.findIndex((s) => s.key === currentSkill)
  const stepIdx = SKILL_STEPS.findIndex((s) => s.key === skillKey)

  if (taskStatus === 'failed' && skillKey === currentSkill) return 'error'
  if (taskStatus === 'done') return 'finish'
  if (stepIdx < currentIdx) return 'finish'
  if (stepIdx === currentIdx) return 'process'
  return 'wait'
}

function getStepIcon(status: 'wait' | 'process' | 'finish' | 'error') {
  switch (status) {
    case 'finish':
      return <CheckCircleOutlined />
    case 'process':
      return <LoadingOutlined />
    case 'error':
      return <CloseCircleOutlined />
    default:
      return <ClockCircleOutlined />
  }
}

export default function TaskDetail() {
  const { id: taskId } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [task, setTask] = useState<TaskResponse | null>(null)
  const [wsStatus, setWsStatus] = useState<string>('pending')
  const [currentSkill, setCurrentSkill] = useState<string>('')
  const [progress, setProgress] = useState<number>(0)
  const [statusMessage, setStatusMessage] = useState<string>('正在连接…')

  const wsRef = useRef<WebSocket | null>(null)
  
  const handleRetry = async () => {
    if (!taskId) return
    try {
      await retryTask(taskId)
      message.success('已触发重传')
      setWsStatus('pending')
      setStatusMessage('尝试恢复重传连接…')
    } catch (e: any) {
      message.error(e.message || '重传请求失败')
    }
  }

  // 初始加载任务信息
  useEffect(() => {
    if (!taskId) return
    getTask(taskId).then((res) => {
      setTask(res)
      setWsStatus(res.status)
      if (res.status === 'done') setStatusMessage('任务执行完成')
      if (res.status === 'failed') setStatusMessage(res.error || '任务执行失败')
    }).catch(() => undefined)
  }, [taskId])

  // 建立 WebSocket 连接
  useEffect(() => {
    if (!taskId) return

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsUrl = `${protocol}://${window.location.host}/ws/tasks/${taskId}`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setStatusMessage('已连接，等待任务执行…')
    }

    ws.onmessage = (event: MessageEvent<string>) => {
      try {
        const data: WsPayload = JSON.parse(event.data)
        setWsStatus(data.status)
        setCurrentSkill(data.current_skill)
        setProgress(data.progress)
        setStatusMessage(data.message)

        // 同步更新 task 状态
        setTask((prev) => {
          if (!prev) return prev
          const nextTask = { ...prev, status: data.status as TaskResponse['status'] }
          if (data.result && typeof data.result === 'object') {
            const res = data.result as any
            if (res.generated_article) nextTask.generated_article = res.generated_article
            if (res.draft_info) nextTask.draft_info = res.draft_info
          }
          return nextTask
        })
      } catch {
        // ignore malformed messages
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

  const progressStatus = wsStatus === 'failed'
    ? 'exception' as const
    : wsStatus === 'done'
      ? 'success' as const
      : 'active' as const

  return (
    <div className={styles.container}>
      {/* 返回按钮 */}
      <Button
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/task')}
        className={styles.backBtn}
      >
        返回
      </Button>

      {isLoading ? (
        <div className={styles.loadingWrap}>
          <Spin size="large" tip="加载任务信息…" />
        </div>
      ) : (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          {/* 基本信息卡片 */}
          <Card variant="borderless">
            <Descriptions
              title={
                <Space>
                  <Title level={4} className={styles.taskTitle}>
                    任务详情
                  </Title>
                  <Tag color={STATUS_COLOR[wsStatus] ?? 'default'}>
                    {STATUS_LABEL[wsStatus] ?? wsStatus}
                  </Tag>
                </Space>
              }
              column={{ xs: 1, sm: 2 }}
            >
              <Descriptions.Item label="任务 ID">
                <Text copyable className={styles.taskIdText}>
                  {task.task_id}
                </Text>
              </Descriptions.Item>
              <Descriptions.Item label="关键词">
                <Text strong>{task.keywords}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {new Date(task.created_at).toLocaleString('zh-CN')}
              </Descriptions.Item>
              <Descriptions.Item label="当前状态">
                {statusMessage}
              </Descriptions.Item>
            </Descriptions>
          </Card>

          {/* 进度条 */}
          <Card variant="borderless">
            <div className={styles.sectionTitle}>执行进度</div>
            <Progress
              percent={progress}
              status={progressStatus}
              strokeColor={{ '0%': '#1677ff', '100%': '#52c41a' }}
              className={styles.progressBar}
            />

            {/* Skill 步骤 */}
            <Steps
              direction="vertical"
              size="small"
              items={SKILL_STEPS.map((step) => {
                const s = getStepStatus(step.key, currentSkill, wsStatus)
                return {
                  title: step.title,
                  description: step.description,
                  status: s,
                  icon: getStepIcon(s),
                }
              })}
            />
          </Card>

          {/* 完成 / 失败结果 */}
          {wsStatus === 'done' && (
            <Card variant="borderless" style={{ marginTop: 24 }}>
              <Result
                status="success"
                title="文章生成完毕并已推送到草稿箱"
                subTitle={task.draft_info?.url ? (
                  <a href={task.draft_info.url} target="_blank" rel="noreferrer">
                    点击查看微信草稿预览链接
                  </a>
                ) : null}
              />
              {task?.generated_article && (
                <div style={{ marginTop: 32, backgroundColor: '#fafafa', padding: 24, borderRadius: 8 }}>
                  <Typography>
                    <Title level={3} style={{ textAlign: 'center' }}>
                      {task.generated_article.title}
                    </Title>
                    <div style={{ textAlign: 'center', marginBottom: 24, color: '#888' }}>
                      备选标题：{task.generated_article.alt_titles?.join(' / ')}
                    </div>
                    <Divider />
                    <div style={{ whiteSpace: 'pre-wrap', fontSize: 16, lineHeight: 2 }}>
                      {task.generated_article.content}
                    </div>
                  </Typography>
                </div>
              )}
            </Card>
          )}

          {wsStatus === 'failed' && (
            <Card variant="borderless">
              <Result
                status="error"
                title="任务执行失败"
                subTitle={statusMessage || task.error || '未知错误'}
                extra={
                  <Space>
                    <Button type="primary" onClick={() => navigate('/task')}>
                      创建一个新任务
                    </Button>
                    <Button 
                      icon={<ReloadOutlined />} 
                      onClick={handleRetry}
                    >
                      从断点重新执行
                    </Button>
                  </Space>
                }
              />
            </Card>
          )}
        </Space>
      )}
    </div>
  )
}
