import { useEffect, useState } from 'react'
import {
  Button,
  Card,
  Empty,
  Pagination,
  Popconfirm,
  Space,
  Table,
  Tag,
  Tooltip,
  message,
} from 'antd'
import { DeleteOutlined, EyeOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import { ARTICLE_STRATEGY_LABELS, deleteTask, listTasks, type TaskResponse } from '@/api'
import { AssetList } from '@/components/workbench'

type HistoryViewMode = 'cards' | 'table'

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

const CARD_PAGE_SIZE = 8

export default function History() {
  const [tasks, setTasks] = useState<TaskResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [viewMode, setViewMode] = useState<HistoryViewMode>('cards')
  const [cardPage, setCardPage] = useState(1)
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

  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(tasks.length / CARD_PAGE_SIZE))
    if (cardPage > maxPage) {
      setCardPage(maxPage)
    }
  }, [cardPage, tasks.length])

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

  const renderCardView = () => {
    if (!loading && tasks.length === 0) {
      return (
        <Card style={{ borderRadius: 24 }}>
          <Empty description="还没有历史内容资产" />
        </Card>
      )
    }

    const paginatedTasks = tasks.slice((cardPage - 1) * CARD_PAGE_SIZE, cardPage * CARD_PAGE_SIZE)
    const skeletonKeys = Array.from({ length: CARD_PAGE_SIZE }, (_, index) => `loading-${index}`)

    return (
      <>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
            gap: 16,
          }}
        >
          {loading
            ? skeletonKeys.map((key) => (
                <Card
                  key={key}
                  loading
                  style={{
                    borderRadius: 24,
                    background: 'rgba(15, 23, 42, 0.76)',
                    borderColor: 'rgba(148, 163, 184, 0.16)',
                  }}
                />
              ))
            : paginatedTasks.map((task) => (
                <Card
                  key={task.task_id}
                  style={{
                    borderRadius: 24,
                    background: 'rgba(15, 23, 42, 0.76)',
                    borderColor: 'rgba(148, 163, 184, 0.16)',
                  }}
                >
                  <Space direction="vertical" size={14} style={{ width: '100%' }}>
                    <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
                      <Tag color={statusColorMap[task.status]}>{statusTextMap[task.status] || task.status}</Tag>
                      <Tooltip title={task.task_id}>
                        <span style={{ color: '#94a3b8', fontFamily: 'monospace', fontSize: 12 }}>
                          {task.task_id.slice(0, 8)}...
                        </span>
                      </Tooltip>
                    </Space>

                    <div>
                      <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>
                        {task.keywords || '未命名任务'}
                      </div>
                      <div style={{ color: '#94a3b8', fontSize: 13 }}>
                        创建于 {dayjs(task.created_at).format('YYYY-MM-DD HH:mm')}
                      </div>
                    </div>

                    <Space size={[4, 8]} wrap>
                      {task.generation_config?.audience_roles?.map((role: string) => (
                        <Tag color="blue" key={role}>
                          {role}
                        </Tag>
                      ))}
                      <Tag color="purple">
                        {ARTICLE_STRATEGY_LABELS[task.generation_config?.article_strategy || 'auto']}
                      </Tag>
                    </Space>

                    <Space>
                      <Button
                        type="primary"
                        ghost
                        icon={<EyeOutlined />}
                        onClick={() => navigate(`/task/${task.task_id}`)}
                      >
                        查看详情
                      </Button>
                      <Popconfirm
                        title="确认删除"
                        description="确定要删除这条任务记录吗？"
                        onConfirm={() => handleDelete(task.task_id)}
                        okText="删除"
                        cancelText="取消"
                      >
                        <Button danger icon={<DeleteOutlined />}>
                          删除
                        </Button>
                      </Popconfirm>
                    </Space>
                  </Space>
                </Card>
              ))}
        </div>
        {!loading && tasks.length > CARD_PAGE_SIZE ? (
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Pagination
              current={cardPage}
              pageSize={CARD_PAGE_SIZE}
              total={tasks.length}
              onChange={setCardPage}
              showSizeChanger={false}
            />
          </div>
        ) : null}
      </>
    )
  }

  return (
    <AssetList
      eyebrow="Asset Archive"
      title="内容资产"
      description="统一回看历史任务、文章策略和执行状态，让可复用的内容沉淀成可浏览资产。"
      meta={
        <Space wrap>
          <Tag bordered={false} color="cyan">
            共 {tasks.length} 条
          </Tag>
          <Tag bordered={false} color="success">
            已完成 {tasks.filter((task) => task.status === 'done').length} 条
          </Tag>
        </Space>
      }
      views={[
        { key: 'cards', label: '卡片视图' },
        { key: 'table', label: '表格视图' },
      ]}
      activeView={viewMode}
      onViewChange={(nextView) => setViewMode(nextView as HistoryViewMode)}
    >
      {viewMode === 'cards' ? (
        renderCardView()
      ) : (
        <Card style={{ borderRadius: 24 }}>
          <Table
            columns={columns}
            dataSource={tasks}
            rowKey="task_id"
            loading={loading}
            pagination={{ pageSize: 10 }}
          />
        </Card>
      )}
    </AssetList>
  )
}
