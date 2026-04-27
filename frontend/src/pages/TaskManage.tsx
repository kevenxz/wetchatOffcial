import { useEffect, useMemo, useState } from 'react'
import { Button, Empty, Input, Popconfirm, Space, Table, Tag, Tooltip, message } from 'antd'
import {
  CheckCircleOutlined,
  DeleteOutlined,
  EyeOutlined,
  PlusOutlined,
  ReloadOutlined,
  RetweetOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import { deleteTask, listTasks, retryTask, type TaskResponse } from '@/api'
import styles from './TaskManage.module.css'

type TaskFilter = 'all' | 'done' | 'review' | 'pending' | 'failed'

const filterOptions: Array<{ label: string; value: TaskFilter }> = [
  { label: '全部', value: 'all' },
  { label: '已完成', value: 'done' },
  { label: '审核中', value: 'review' },
  { label: '等待中', value: 'pending' },
  { label: '失败', value: 'failed' },
]

const categoryPalette: Record<string, string> = {
  AI: 'purple',
  ai: 'purple',
  科技: 'blue',
  tech: 'blue',
  财经: 'green',
  finance: 'green',
  汽车: 'orange',
  国际: 'cyan',
  军事: 'red',
}

function taskDisplayId(task: TaskResponse, index: number) {
  const raw = task.task_id.replace(/-/g, '').slice(0, 4).toUpperCase()
  return `T-${raw || String(2042 - index)}`
}

function getRecordValue(source: Record<string, any> | null | undefined, key: string) {
  const value = source?.[key]
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

function getTaskCategory(task: TaskResponse) {
  const selectedTopic = task.selected_topic ?? {}
  const config = task.config_snapshot ?? {}
  const category =
    getRecordValue(selectedTopic, 'category') ||
    task.selected_hotspot?.category ||
    getRecordValue(selectedTopic.metadata as Record<string, any> | undefined, 'category') ||
    config.hotspot?.categories?.[0] ||
    task.generation_config.account_profile?.fit_tags?.[0] ||
    '科技'
  return String(category)
}

function getTaskMode(task: TaskResponse) {
  return task.mode === 'auto_hotspot' || task.hotspot_capture_config?.enabled ? '热点自动' : '手动任务'
}

function getTaskStatus(task: TaskResponse): { label: string; color: string; filter: TaskFilter } {
  if (task.status === 'failed') return { label: '失败', color: 'error', filter: 'failed' }
  if (task.human_review_required) return { label: '审核中', color: 'warning', filter: 'review' }
  if (task.status === 'done') return { label: '已完成', color: 'success', filter: 'done' }
  return { label: '等待中', color: 'processing', filter: 'pending' }
}

function formatDuration(task: TaskResponse) {
  if (!task.updated_at || !task.created_at || task.status === 'pending') return '-'
  const seconds = Math.max(0, dayjs(task.updated_at).diff(dayjs(task.created_at), 'second'))
  if (!seconds) return '-'
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return minutes ? `${minutes}分${String(rest).padStart(2, '0')}秒` : `${rest}秒`
}

function getArticleCount(task: TaskResponse) {
  if (Array.isArray(task.final_article)) return task.final_article.length
  if (Array.isArray(task.generated_article)) return task.generated_article.length
  return task.final_article || task.generated_article ? 1 : 0
}

export default function TaskManage() {
  const [tasks, setTasks] = useState<TaskResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [keyword, setKeyword] = useState('')
  const [filter, setFilter] = useState<TaskFilter>('all')
  const navigate = useNavigate()

  const fetchTasks = async () => {
    setLoading(true)
    try {
      setTasks(await listTasks())
    } catch (error) {
      message.error(error instanceof Error ? error.message : '获取任务列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchTasks()
  }, [])

  const filteredTasks = useMemo(() => {
    return tasks.filter((task) => {
      const status = getTaskStatus(task)
      const matchesStatus = filter === 'all' || status.filter === filter
      const text = `${task.task_id} ${task.keywords} ${getTaskCategory(task)} ${getTaskMode(task)}`.toLowerCase()
      const matchesKeyword = !keyword || text.includes(keyword.toLowerCase())
      return matchesStatus && matchesKeyword
    })
  }, [filter, keyword, tasks])

  const summary = useMemo(() => {
    const done = tasks.filter((task) => getTaskStatus(task).filter === 'done').length
    const review = tasks.filter((task) => getTaskStatus(task).filter === 'review').length
    const failed = tasks.filter((task) => getTaskStatus(task).filter === 'failed').length
    return { total: tasks.length, done, review, failed }
  }, [tasks])

  const handleDelete = async (taskId: string) => {
    try {
      await deleteTask(taskId)
      message.success('删除成功')
      await fetchTasks()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除失败')
    }
  }

  const handleRetry = async (taskId: string) => {
    try {
      await retryTask(taskId)
      message.success('已重新提交任务')
      await fetchTasks()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '重试失败')
    }
  }

  const columns: ColumnsType<TaskResponse> = [
    {
      title: '任务ID',
      key: 'display_id',
      width: 140,
      render: (_value, record, index) => (
        <Tooltip title={record.task_id}>
          <span className={styles.taskId}>{taskDisplayId(record, index)}</span>
        </Tooltip>
      ),
    },
    {
      title: '主题',
      dataIndex: 'keywords',
      key: 'keywords',
      ellipsis: true,
      render: (keywords: string, record) => (
        <div className={styles.taskTitle}>
          <strong>{keywords}</strong>
          <span>生成 {Math.max(getArticleCount(record), 1)} 篇文章</span>
        </div>
      ),
    },
    {
      title: '分类',
      key: 'category',
      width: 120,
      render: (_value, record) => {
        const category = getTaskCategory(record)
        return (
          <Tag className={styles.categoryTag} color={categoryPalette[category] ?? 'blue'}>
            {category}
          </Tag>
        )
      },
    },
    {
      title: '模式',
      key: 'mode',
      width: 140,
      render: (_value, record) => {
        const mode = getTaskMode(record)
        const hot = mode === '热点自动'
        return (
          <span className={`${styles.mode} ${hot ? styles.modeHot : ''}`.trim()}>
            {hot ? <ThunderboltOutlined /> : <UserOutlined />}
            {mode}
          </span>
        )
      },
    },
    {
      title: '状态',
      key: 'status',
      width: 130,
      render: (_value, record) => {
        const status = getTaskStatus(record)
        return (
          <Tag
            className={styles.statusTag}
            color={status.color}
            icon={status.filter === 'done' ? <CheckCircleOutlined /> : undefined}
          >
            {status.label}
          </Tag>
        )
      },
    },
    {
      title: '耗时',
      key: 'duration',
      width: 120,
      render: (_value, record) => formatDuration(record),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (date: string) => dayjs(date).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_value, record) => (
        <Space size={8}>
          <Button
            type="text"
            size="small"
            className={styles.iconAction}
            icon={<EyeOutlined />}
            aria-label="查看任务"
            onClick={() => navigate(`/task/${record.task_id}`)}
          />
          {record.status === 'failed' ? (
            <Button
              type="text"
              size="small"
              className={styles.iconAction}
              icon={<RetweetOutlined />}
              aria-label="重试任务"
              onClick={() => void handleRetry(record.task_id)}
            />
          ) : null}
          <Popconfirm
            title="确认删除"
            description="确定要删除这条任务记录吗？"
            onConfirm={() => handleDelete(record.task_id)}
            okText="删除"
            cancelText="取消"
          >
            <Button
              type="text"
              size="small"
              className={styles.iconAction}
              icon={<DeleteOutlined />}
              aria-label="删除任务"
            />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className={styles.page}>
      <div className={styles.toolbar}>
        <Input.Search
          size="large"
          placeholder="搜索任务..."
          allowClear
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
        />
        <div className={styles.filters}>
          {filterOptions.map((item) => (
            <Button
              key={item.value}
              className={`${styles.filterButton} ${filter === item.value ? styles.filterButtonActive : ''}`.trim()}
              onClick={() => setFilter(item.value)}
            >
              {item.label}
            </Button>
          ))}
        </div>
        <div className={styles.actions}>
          <Button size="large" icon={<ReloadOutlined />} onClick={() => void fetchTasks()} loading={loading}>
            刷新
          </Button>
          <Button size="large" type="primary" icon={<PlusOutlined />} onClick={() => navigate('/task/new')}>
            新建任务
          </Button>
        </div>
      </div>

      <div className={styles.summaryGrid}>
        <div className={styles.summaryCard}>
          <div className={styles.summaryLabel}>总任务</div>
          <div className={styles.summaryValue}>{summary.total}</div>
        </div>
        <div className={styles.summaryCard}>
          <div className={styles.summaryLabel}>已完成</div>
          <div className={styles.summaryValue} style={{ color: '#059669' }}>
            {summary.done}
          </div>
        </div>
        <div className={styles.summaryCard}>
          <div className={styles.summaryLabel}>审核中</div>
          <div className={styles.summaryValue} style={{ color: '#d97706' }}>
            {summary.review}
          </div>
        </div>
        <div className={styles.summaryCard}>
          <div className={styles.summaryLabel}>失败</div>
          <div className={styles.summaryValue} style={{ color: '#e11d48' }}>
            {summary.failed}
          </div>
        </div>
      </div>

      <div className={styles.tableCard}>
        {filteredTasks.length === 0 && !loading ? (
          <Empty description="暂无任务" style={{ padding: 48 }} />
        ) : (
          <Table
            columns={columns}
            dataSource={filteredTasks}
            rowKey="task_id"
            loading={loading}
            pagination={false}
            size="middle"
          />
        )}
      </div>
    </div>
  )
}
