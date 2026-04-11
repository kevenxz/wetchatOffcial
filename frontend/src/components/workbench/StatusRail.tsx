import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons'
import { Progress, Tag } from 'antd'
import styles from './StatusRail.module.css'

export interface StatusRailStep {
  key: string
  title: string
  description: string
}

type StepStatus = 'wait' | 'process' | 'finish' | 'error'

const STATUS_LABEL: Record<string, string> = {
  pending: '等待中',
  running: '执行中',
  done: '已完成',
  failed: '失败',
}

const STATUS_COLOR: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  done: 'success',
  failed: 'error',
}

function getStepStatus(
  stepKey: string,
  currentSkill: string,
  taskStatus: string,
  steps: StatusRailStep[],
): StepStatus {
  const currentIndex = steps.findIndex((step) => step.key === currentSkill)
  const stepIndex = steps.findIndex((step) => step.key === stepKey)

  if (taskStatus === 'failed' && stepKey === currentSkill) return 'error'
  if (taskStatus === 'done') return 'finish'
  if (stepIndex < currentIndex) return 'finish'
  if (stepIndex === currentIndex) return 'process'
  return 'wait'
}

function getStepIcon(status: StepStatus) {
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

interface StatusRailProps {
  title?: string
  caption?: string
  taskStatus: string
  currentSkill: string
  progress: number
  statusMessage: string
  steps: StatusRailStep[]
}

export default function StatusRail({
  title = '执行轨道',
  caption = '跟踪工作流所处阶段、实时消息与推进节奏。',
  taskStatus,
  currentSkill,
  progress,
  statusMessage,
  steps,
}: StatusRailProps) {
  const progressStatus =
    taskStatus === 'failed'
      ? ('exception' as const)
      : taskStatus === 'done'
        ? ('success' as const)
        : ('active' as const)

  return (
    <aside className={styles.rail} aria-label={title}>
      <div className={styles.header}>
        <p className={styles.kicker}>Task Rail</p>
        <div className={styles.titleRow}>
          <h2 className={styles.title}>{title}</h2>
          <Tag color={STATUS_COLOR[taskStatus] ?? 'default'}>
            {STATUS_LABEL[taskStatus] ?? taskStatus}
          </Tag>
        </div>
        <p className={styles.caption}>{caption}</p>
      </div>

      <div className={styles.progressCard}>
        <div className={styles.progressMeta}>
          <span>当前消息</span>
          <strong>{statusMessage}</strong>
        </div>
        <Progress
          percent={progress}
          status={progressStatus}
          strokeColor={{ '0%': '#38bdf8', '100%': '#34d399' }}
          trailColor="rgba(148, 163, 184, 0.12)"
          showInfo
        />
      </div>

      <ol className={styles.stepList}>
        {steps.map((step, index) => {
          const status = getStepStatus(step.key, currentSkill, taskStatus, steps)

          return (
            <li key={step.key} className={styles.stepItem} data-status={status}>
              <div className={styles.stepMarker}>
                <span className={styles.iconWrap} aria-hidden="true">
                  {getStepIcon(status)}
                </span>
                {index < steps.length - 1 ? (
                  <span className={styles.connector} aria-hidden="true" />
                ) : null}
              </div>

              <div className={styles.stepBody}>
                <div className={styles.stepHeading}>
                  <span className={styles.stepIndex}>{String(index + 1).padStart(2, '0')}</span>
                  <h3>{step.title}</h3>
                </div>
                <p>{step.description}</p>
              </div>
            </li>
          )
        })}
      </ol>
    </aside>
  )
}
