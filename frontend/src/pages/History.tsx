import { useEffect, useState } from 'react'
import { Card, Table, Tag, Button, Popconfirm, message, Space, Tooltip } from 'antd'
import { EyeOutlined, DeleteOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { listTasks, deleteTask, TaskResponse } from '@/api'
import dayjs from 'dayjs'

export default function History() {
  const [tasks, setTasks] = useState<TaskResponse[]>([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  const fetchTasks = async () => {
    setLoading(true)
    try {
      const data = await listTasks()
      setTasks(data)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '获取任务列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTasks()
  }, [])

  const handleDelete = async (taskId: string) => {
    try {
      await deleteTask(taskId)
      message.success('删除成功')
      fetchTasks()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  const columns = [
    {
      title: '任务 ID',
      dataIndex: 'task_id',
      key: 'task_id',
      width: 150,
      render: (id: string) => (
        <Tooltip title={id}>
          <span style={{ fontFamily: 'monospace', color: '#666' }}>
            {id.substring(0, 8)}...
          </span>
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
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: TaskResponse['status']) => {
        const colorMap: Record<string, string> = {
          pending: 'default',
          running: 'processing',
          done: 'success',
          failed: 'error',
        }
        const textMap: Record<string, string> = {
          pending: '排队中',
          running: '执行中',
          done: '已完成',
          failed: '失败',
        }
        return <Tag color={colorMap[status]}>{textMap[status] || status}</Tag>
      },
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
            okText="是"
            cancelText="否"
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
    <div style={{ maxWidth: 1000, margin: '40px auto', padding: '0 24px' }}>
      <Card
        title={<span style={{ fontSize: 18, fontWeight: 600 }}>历史任务</span>}
        variant="borderless"
      >
        <Table
          columns={columns}
          dataSource={tasks}
          rowKey="task_id"
          loading={loading}
          pagination={{ pageSize: 10 }}
        />
      </Card>
    </div>
  )
}
