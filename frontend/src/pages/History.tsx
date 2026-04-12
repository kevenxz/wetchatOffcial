import { useEffect, useState } from 'react'
import { Button, Card, Empty, Popconfirm, Space, Table, Tag, Tooltip, message } from 'antd'
import { DeleteOutlined, EyeOutlined, ReloadOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import { ARTICLE_STRATEGY_LABELS, deleteTask, listTasks, type TaskResponse } from '@/api'
import { HeroPanel } from '@/components/workbench'

const statusColorMap: Record<TaskResponse['status'], string> = {
  pending: 'default',
  running: 'processing',
  done: 'success',
  failed: 'error',
}

const statusTextMap: Record<TaskResponse['status'], string> = {
  pending: '排队中',
  running: '执行中',
  done: '已完成',
  failed: '失败',
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

  const columns = [
    {
      title: '任务 ID',
      dataIndex: 'task_id',
      key: 'task_id',
      width: 150,
      render: (taskId: string) => (
        <Tooltip title={taskId}>
          <span style={{ fontFamily: 'monospace', color: '#94a3b8' }}>{taskId.slice(0, 8)}...</span>
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
        <Space size={[4, 8]} wrap>
          {record.generation_config?.audience_roles?.map((role) => (
            <Tag color="blue" key={role}>
              {role}
            </Tag>
          ))}
          <Tag color="purple">
            {ARTICLE_STRATEGY_LABELS[record.generation_config?.article_strategy || 'auto']}
          </Tag>
        </Space>
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
    <div className="backstage-page">
      <HeroPanel
        eyebrow="Asset Archive"
        title="内容资产"
        description="统一回看历史任务、文章策略和执行状态，让可复用的内容沉淀成可浏览资产。"
      >
        <Space wrap style={{ marginTop: 12, justifyContent: 'space-between', width: '100%' }}>
          <Space wrap>
            <Tag bordered={false} color="cyan">
              共 {tasks.length} 条
            </Tag>
            <Tag bordered={false} color="success">
              已完成 {tasks.filter((task) => task.status === 'done').length} 条
            </Tag>
          </Space>
          <Button icon={<ReloadOutlined />} onClick={() => void fetchTasks()}>
            刷新
          </Button>
        </Space>
      </HeroPanel>

      <Card className="backstage-surface-card">
        {tasks.length === 0 && !loading ? (
          <Empty description="还没有历史内容资产" />
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
      </Card>
    </div>
  )
}
