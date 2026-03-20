import { useEffect, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import {
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Radio,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { TableProps } from 'antd'
import {
  createSchedule,
  deleteSchedule,
  getCustomThemes,
  getPresetThemes,
  listAccounts,
  listSchedules,
  runScheduleNow,
  startSchedule,
  stopSchedule,
  updateSchedule,
  type AccountConfig,
  type ScheduleConfig,
  type ScheduleMode,
} from '@/api'

const { Text } = Typography
const CURRENT_THEME_KEY = '__current__'

interface FormValues {
  name: string
  mode: ScheduleMode
  run_at?: Dayjs
  interval_minutes?: number
  theme_name: string
  account_ids: string[]
  hot_topics: string[]
  enabled: boolean
}

export default function ScheduleManage() {
  // Page-level states: list loading, modal saving, and edit context.
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [schedules, setSchedules] = useState<ScheduleConfig[]>([])
  const [accounts, setAccounts] = useState<AccountConfig[]>([])
  const [themeNames, setThemeNames] = useState<string[]>([CURRENT_THEME_KEY])
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<ScheduleConfig | null>(null)
  const [form] = Form.useForm<FormValues>()

  // Schedules only support enabled WeChat public accounts.
  const wechatAccounts = accounts.filter((item) => item.platform === 'wechat_mp' && item.enabled)

  const accountOptions = wechatAccounts.map((item) => ({
    label: item.name,
    value: item.account_id,
  }))
  const themeOptions = themeNames.map((name) => ({
    label: name === CURRENT_THEME_KEY ? '当前配置' : name,
    value: name,
  }))

  const fetchData = async () => {
    // Load schedules + account options + theme options in one request batch.
    setLoading(true)
    try {
      const [scheduleList, accountList, presetThemes, customThemes] = await Promise.all([
        listSchedules(),
        listAccounts(),
        getPresetThemes(),
        getCustomThemes(),
      ])
      const names = [CURRENT_THEME_KEY, ...Object.keys(presetThemes), ...Object.keys(customThemes)]
      setSchedules(scheduleList)
      setAccounts(accountList)
      setThemeNames(Array.from(new Set(names)))
    } catch (error) {
      message.error(error instanceof Error ? error.message : '获取定时任务失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  const openCreate = () => {
    // Reset form to default template when creating a new schedule.
    setEditing(null)
    form.setFieldsValue({
      name: '',
      mode: 'interval',
      interval_minutes: 60,
      theme_name: CURRENT_THEME_KEY,
      account_ids: [],
      hot_topics: [],
      enabled: true,
    })
    setModalOpen(true)
  }

  const openEdit = (record: ScheduleConfig) => {
    // Rehydrate form fields from persisted schedule for editing.
    setEditing(record)
    form.setFieldsValue({
      name: record.name,
      mode: record.mode,
      run_at: record.run_at ? dayjs(record.run_at) : undefined,
      interval_minutes: record.interval_minutes ?? undefined,
      theme_name: record.theme_name || CURRENT_THEME_KEY,
      account_ids: record.account_ids,
      hot_topics: record.hot_topics,
      enabled: record.enabled,
    })
    setModalOpen(true)
  }

  const submit = async () => {
    // Submit handler supports both create and update.
    const values = await form.validateFields()
    const payload = {
      name: values.name,
      mode: values.mode,
      run_at: values.mode === 'once' && values.run_at ? values.run_at.toISOString() : null,
      interval_minutes: values.mode === 'interval' ? values.interval_minutes ?? 60 : null,
      theme_name: values.theme_name || CURRENT_THEME_KEY,
      account_ids: values.account_ids || [],
      hot_topics: values.hot_topics || [],
      enabled: values.enabled ?? true,
    }

    setSaving(true)
    try {
      if (editing) {
        await updateSchedule(editing.schedule_id, payload)
        message.success('定时任务已更新')
      } else {
        await createSchedule(payload)
        message.success('定时任务已创建')
      }
      setModalOpen(false)
      await fetchData()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleStart = async (scheduleId: string) => {
    // Start a stopped schedule.
    await startSchedule(scheduleId)
    message.success('已启动')
    await fetchData()
  }

  const handleStop = async (scheduleId: string) => {
    // Stop a running schedule.
    await stopSchedule(scheduleId)
    message.success('已停止')
    await fetchData()
  }

  const handleRunNow = async (scheduleId: string) => {
    // Manual trigger without changing schedule definition.
    const result = await runScheduleNow(scheduleId)
    message.success(result.task_id ? `已执行，任务ID: ${result.task_id}` : '已执行')
    await fetchData()
  }

  const handleDelete = async (scheduleId: string) => {
    // Hard-delete schedule config from storage.
    await deleteSchedule(scheduleId)
    message.success('已删除')
    await fetchData()
  }

  const columns: TableProps<ScheduleConfig>['columns'] = [
    {
      title: '任务名称',
      dataIndex: 'name',
      key: 'name',
      width: 160,
    },
    {
      title: '执行规则',
      key: 'rule',
      width: 240,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text>{record.mode === 'once' ? '指定时间' : `每 ${record.interval_minutes} 分钟`}</Text>
          {record.mode === 'once' && record.run_at && (
            <Text type="secondary">{dayjs(record.run_at).format('YYYY-MM-DD HH:mm:ss')}</Text>
          )}
        </Space>
      ),
    },
    {
      title: '热门话题',
      dataIndex: 'hot_topics',
      key: 'hot_topics',
      render: (topics: string[]) => (
        <Space size={[4, 8]} wrap>
          {topics.length === 0 && <Text type="secondary">未配置</Text>}
          {topics.map((topic) => (
            <Tag key={topic}>{topic}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '主题',
      dataIndex: 'theme_name',
      key: 'theme_name',
      width: 140,
      render: (name: string) => (name === CURRENT_THEME_KEY ? '当前配置' : name),
    },
    {
      title: '推送账号',
      dataIndex: 'account_ids',
      key: 'account_ids',
      render: (ids: string[]) => {
        if (!ids?.length) return <Text type="secondary">未配置</Text>
        return (
          <Space size={[4, 8]} wrap>
            {ids.map((id) => {
              const account = wechatAccounts.find((item) => item.account_id === id)
              return <Tag key={id}>{account?.name || id}</Tag>
            })}
          </Space>
        )
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={status === 'running' ? 'processing' : 'default'}>
          {status === 'running' ? '运行中' : '已停止'}
        </Tag>
      ),
    },
    {
      title: '下次执行',
      dataIndex: 'next_run_at',
      key: 'next_run_at',
      width: 180,
      render: (value: string | null) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: '操作',
      key: 'action',
      width: 260,
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => openEdit(record)}>
            编辑
          </Button>
          {record.status === 'running' ? (
            <Button size="small" onClick={() => handleStop(record.schedule_id)}>
              停止
            </Button>
          ) : (
            <Button size="small" type="primary" onClick={() => handleStart(record.schedule_id)}>
              启动
            </Button>
          )}
          <Button size="small" onClick={() => handleRunNow(record.schedule_id)}>
            立即执行
          </Button>
          <Popconfirm title="确认删除该定时任务？" onConfirm={() => handleDelete(record.schedule_id)}>
            <Button size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ maxWidth: 1320, margin: '32px auto', padding: '0 24px' }}>
      <Card
        title={<span style={{ fontSize: 18, fontWeight: 600 }}>定时任务配置</span>}
        extra={
          <Button type="primary" onClick={openCreate}>
            新建定时任务
          </Button>
        }
      >
        <Table rowKey="schedule_id" loading={loading} columns={columns} dataSource={schedules} />
      </Card>

      <Modal
        title={editing ? '编辑定时任务' : '新建定时任务'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={submit}
        confirmLoading={saving}
        width={760}
      >
        <Form layout="vertical" form={form}>
          <Form.Item label="任务名称" name="name" rules={[{ required: true, message: '请输入任务名称' }]}>
            <Input placeholder="例如：早报自动发布" />
          </Form.Item>

          <Form.Item label="执行方式" name="mode" rules={[{ required: true }]}>
            <Radio.Group
              options={[
                { label: '指定时间执行', value: 'once' },
                { label: '按时间间隔执行', value: 'interval' },
              ]}
            />
          </Form.Item>

          <Form.Item shouldUpdate noStyle>
            {({ getFieldValue }) =>
              getFieldValue('mode') === 'once' ? (
                <Form.Item
                  label="执行时间"
                  name="run_at"
                  rules={[{ required: true, message: '请选择执行时间' }]}
                >
                  <DatePicker showTime style={{ width: '100%' }} />
                </Form.Item>
              ) : (
                <Form.Item
                  label="执行间隔（分钟）"
                  name="interval_minutes"
                  rules={[{ required: true, message: '请输入执行间隔' }]}
                >
                  <InputNumber min={1} max={10080} style={{ width: '100%' }} />
                </Form.Item>
              )
            }
          </Form.Item>

          <Form.Item label="文章主题样式" name="theme_name" rules={[{ required: true }]}>
            <Select options={themeOptions} />
          </Form.Item>

          <Form.Item label="推送账号（可多选）" name="account_ids" rules={[{ required: true, message: '请选择至少一个账号' }]}>
            <Select mode="multiple" options={accountOptions} />
          </Form.Item>

          <Form.Item label="热门话题（可多项，执行时随机取一个）" name="hot_topics">
            <Select
              mode="tags"
              tokenSeparators={[',', '，', ';', '；']}
              placeholder="输入热门话题并回车，例如：AI Agent、A股、新能源"
            />
          </Form.Item>

          <Form.Item label="创建后立即启动" name="enabled" valuePropName="checked">
            <Radio.Group
              options={[
                { label: '是', value: true },
                { label: '否', value: false },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
