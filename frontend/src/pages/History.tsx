import { useEffect, useState } from 'react'
import { Button, Popconfirm, Space, Table, Tag, Tooltip, message } from 'antd'
import { DeleteOutlined, EyeOutlined, ReloadOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import { ARTICLE_STRATEGY_LABELS, deleteTask, listTasks, type TaskResponse } from '@/api'
import { EmptyState, PageHeader, Panel, Stat, StatGrid } from '@/components/layout'
import styles from './History.module.css'

const statusColorMap: Record<TaskResponse['status'], string> = {
  pending: 'default',
  queued: 'cyan',
  running: 'processing',
  done: 'success',
  failed: 'error',
  cancelled: 'warning',
}

const statusTextMap: Record<TaskResponse['status'], string> = {
  pending: '等待中',
  queued: '排队中',
  running: '执行中',
  done: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

export default function History() {
  const [tasks, setTasks] = useState<TaskResponse[]>([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  const fetchTasks = async () => {
    setLoading(true)
    try {
      const data = await listTasks()
      setTasks(data)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '获取任务列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchTasks()
  }, [])

  const handleDelete = async (taskId: string) => {
    try {
      await deleteTask(taskId)
      message.success('删除成功')
      await fetchTasks()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除失败')
    }
  }

  const doneCount = tasks.filter((task) => task.status === 'done').length
  const runningCount = tasks.filter((task) => task.status === 'running' || task.status === 'queued').length
  const failedCount = tasks.filter((task) => task.status === 'failed').length

  const columns = [
    {
      title: '任务 ID',
      dataIndex: 'task_id',
      key: 'task_id',
      width: 150,
      render: (taskId: string) => (
        <Tooltip title={taskId}>
          <span className={styles.taskId}>{taskId.slice(0, 8)}...</span>
        </Tooltip>
      ),
    },
    {
      title: '关键词',
      dataIndex: 'keywords',
      key: 'keywords',
      ellipsis: true,
    },
    {
      title: '角色 / 策略',
      key: 'generation_config',
      width: 240,
      render: (_: unknown, record: TaskResponse) => (
        <div className={styles.roles}>
          {record.generation_config?.audience_roles?.map((role) => (
            <Tag key={role}>{role}</Tag>
          ))}
          <Tag>
            {ARTICLE_STRATEGY_LABELS[record.generation_config?.article_strategy || 'auto']}
          </Tag>
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: TaskResponse['status']) => (
        <Tag color={statusColorMap[status]}>{statusTextMap[status] || status}</Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (date: string) => dayjs(date).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_: unknown, record: TaskResponse) => (
        <Space size="middle">
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/task/${record.task_id}`)}
          >
            详情
          </Button>
          <Popconfirm
            title="确认删除"
            description="确定要删除这条任务记录吗？"
            onConfirm={() => handleDelete(record.task_id)}
            okText="删除"
            cancelText="取消"
          >
            <Button type="link" danger size="small" icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className={styles.page}>
      <PageHeader
        eyebrow="Asset Archive"
        title="内容资产"
        description="统一回看历史任务、文章策略和执行状态，让可复用的内容沉淀成可浏览资产。"
        actions={
          <Button icon={<ReloadOutlined />} onClick={() => void fetchTasks()}>
            刷新
          </Button>
        }
      />

      <StatGrid>
        <Stat label="任务总数" value={tasks.length} />
        <Stat label="已完成" value={doneCount} tone={doneCount > 0 ? 'positive' : 'neutral'} />
        <Stat label="排队与执行中" value={runningCount} />
        <Stat label="失败" value={failedCount} tone={failedCount > 0 ? 'negative' : 'neutral'} />
      </StatGrid>

      <Panel title="历史任务" aside={`共 ${tasks.length} 条记录`} flush>
        {tasks.length === 0 && !loading ? (
          <div className={styles.emptyPad}>
            <EmptyState
              title="还没有历史内容资产"
              description="在「新建任务」里启动一次创作流程后，任务会出现在这里。"
            />
          </div>
        ) : (
          <Table
            columns={columns}
            dataSource={tasks}
            rowKey="task_id"
            loading={loading}
            pagination={{ pageSize: 10 }}
            size="middle"
          />
        )}
      </Panel>
    </div>
  )
}
