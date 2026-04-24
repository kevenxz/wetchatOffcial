import { useEffect, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import type { ReactNode } from 'react'
import {
  Button,
  Card,
  Col,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Radio,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons'
import type { TableProps } from 'antd'
import {
  ARTICLE_STRATEGY_LABELS,
  DEFAULT_GENERATION_CONFIG,
  GENERATION_ROLE_PRESETS,
  createSchedule,
  deleteSchedule,
  getCustomThemes,
  getPresetThemes,
  listAccounts,
  listSchedules,
  previewHotspots,
  runScheduleNow,
  startSchedule,
  stopSchedule,
  updateSchedule,
  type AccountConfig,
  type ArticleStrategy,
  type HotspotCaptureConfig,
  type HotspotPlatformConfig,
  type ScheduleConfig,
  type ScheduleMode,
} from '@/api'
import { HeroPanel, SectionBlock } from '@/components/workbench'

const { Text } = Typography
const CURRENT_THEME_KEY = '__current__'
const HOTSPOT_CATEGORY_PRESETS = [
  { label: 'AI', value: 'ai' },
  { label: '科技', value: 'tech' },
  { label: '财经', value: 'finance' },
  { label: '社会', value: 'news' },
  { label: '消费', value: 'consumer' },
  { label: '行业', value: 'industry' },
]
const PAGE_STACK_STYLE = {
  display: 'grid',
  gap: 24,
} as const
const FORM_STACK_STYLE = {
  display: 'grid',
  gap: 16,
} as const

interface FormValues {
  name: string
  mode: ScheduleMode
  run_at?: Dayjs
  interval_minutes?: number
  theme_name: string
  account_ids: string[]
  hotspot_capture: HotspotCaptureConfig
  audience_roles: string[]
  article_strategy: ArticleStrategy
  style_hint?: string
  enabled: boolean
}

const buildDefaultHotspotCapture = (): HotspotCaptureConfig => ({
  enabled: false,
  source: 'tophub',
  categories: [],
  platforms: [],
  filters: {
    top_n_per_platform: 10,
    min_selection_score: 60,
    exclude_keywords: [],
    prefer_keywords: [],
  },
  fallback_topics: [],
})

const normalizeUniqueTags = (items?: string[]): string[] => {
  const normalized: string[] = []
  ;(items || []).forEach((item) => {
    const cleaned = item.trim()
    if (cleaned && !normalized.includes(cleaned)) {
      normalized.push(cleaned)
    }
  })
  return normalized
}

const normalizePlatformList = (platforms?: HotspotPlatformConfig[]): HotspotPlatformConfig[] => {
  const seenPaths = new Set<string>()
  const normalized: HotspotPlatformConfig[] = []
  ;(platforms || []).forEach((platform) => {
    const name = platform?.name?.trim() || ''
    const path = platform?.path?.trim() || ''
    if (!name || !path) {
      return
    }
    if (seenPaths.has(path)) {
      return
    }
    seenPaths.add(path)
    normalized.push({
      name,
      path,
      weight: Number(platform.weight || 1),
      enabled: platform.enabled !== false,
    })
  })
  return normalized
}

const normalizeHotspotCapture = (value?: HotspotCaptureConfig): HotspotCaptureConfig => {
  return {
    enabled: Boolean(value?.enabled),
    source: 'tophub',
    categories: normalizeUniqueTags(value?.categories),
    platforms: normalizePlatformList(value?.platforms),
    filters: {
      top_n_per_platform: Math.min(50, Math.max(1, Number(value?.filters?.top_n_per_platform || 10))),
      min_selection_score: Math.min(100, Math.max(0, Number(value?.filters?.min_selection_score || 60))),
      exclude_keywords: normalizeUniqueTags(value?.filters?.exclude_keywords),
      prefer_keywords: normalizeUniqueTags(value?.filters?.prefer_keywords),
    },
    fallback_topics: normalizeUniqueTags(value?.fallback_topics),
  }
}

const resolveFormHotspotCapture = (record?: ScheduleConfig | null): HotspotCaptureConfig => {
  if (!record) {
    return buildDefaultHotspotCapture()
  }
  if (record.hotspot_capture) {
    return normalizeHotspotCapture(record.hotspot_capture)
  }
  return normalizeHotspotCapture({
    ...buildDefaultHotspotCapture(),
    fallback_topics: record.hot_topics || [],
  })
}

const formatDateTime = (value?: string | null): string => {
  if (!value) {
    return '等待触发'
  }
  return dayjs(value).format('YYYY-MM-DD HH:mm:ss')
}

const formatThemeName = (name?: string | null): string => (name === CURRENT_THEME_KEY ? '当前配置' : name || '未配置')

const summarizeHotspotCapture = (record: ScheduleConfig): ReactNode => {
  const capture = record.hotspot_capture || buildDefaultHotspotCapture()
  const enabledPlatformCount = (capture.platforms || []).filter((platform) => platform.enabled !== false).length

  if (!capture.enabled) {
    if (capture.fallback_topics?.length) {
      return `未启用热点抓取，回退主题：${capture.fallback_topics.slice(0, 3).join('、')}`
    }
    return '未启用热点抓取，按任务主题直接生成'
  }

  const parts = [
    `Top ${capture.filters.top_n_per_platform}`,
    `阈值 ${capture.filters.min_selection_score}`,
    enabledPlatformCount ? `已配置 ${enabledPlatformCount} 个平台节点` : '按分类自动发现平台',
  ]

  if (capture.categories?.length) {
    parts.push(`分类 ${capture.categories.slice(0, 2).join('、')}`)
  }

  if (capture.fallback_topics?.length) {
    parts.push(`回退 ${capture.fallback_topics.slice(0, 2).join('、')}`)
  }

  return parts.join(' · ')
}

export default function ScheduleManage() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [schedules, setSchedules] = useState<ScheduleConfig[]>([])
  const [accounts, setAccounts] = useState<AccountConfig[]>([])
  const [themeNames, setThemeNames] = useState<string[]>([CURRENT_THEME_KEY])
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<ScheduleConfig | null>(null)
  const [form] = Form.useForm<FormValues>()

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
    setEditing(null)
    form.setFieldsValue({
      name: '',
      mode: 'interval',
      interval_minutes: 60,
      theme_name: CURRENT_THEME_KEY,
      account_ids: [],
      hotspot_capture: buildDefaultHotspotCapture(),
      audience_roles: DEFAULT_GENERATION_CONFIG.audience_roles,
      article_strategy: DEFAULT_GENERATION_CONFIG.article_strategy,
      style_hint: DEFAULT_GENERATION_CONFIG.style_hint,
      enabled: true,
    })
    setModalOpen(true)
  }

  const openEdit = (record: ScheduleConfig) => {
    setEditing(record)
    form.setFieldsValue({
      name: record.name,
      mode: record.mode,
      run_at: record.run_at ? dayjs(record.run_at) : undefined,
      interval_minutes: record.interval_minutes ?? undefined,
      theme_name: record.theme_name || CURRENT_THEME_KEY,
      account_ids: record.account_ids,
      hotspot_capture: resolveFormHotspotCapture(record),
      audience_roles: record.generation_config?.audience_roles || DEFAULT_GENERATION_CONFIG.audience_roles,
      article_strategy: record.generation_config?.article_strategy || DEFAULT_GENERATION_CONFIG.article_strategy,
      style_hint: record.generation_config?.style_hint || DEFAULT_GENERATION_CONFIG.style_hint,
      enabled: record.enabled,
    })
    setModalOpen(true)
  }

  const submit = async () => {
    const values = await form.validateFields()
    const hotspotCapture = normalizeHotspotCapture(values.hotspot_capture)
    const payload = {
      name: values.name,
      mode: values.mode,
      run_at: values.mode === 'once' && values.run_at ? values.run_at.toISOString() : null,
      interval_minutes: values.mode === 'interval' ? values.interval_minutes ?? 60 : null,
      theme_name: values.theme_name || CURRENT_THEME_KEY,
      account_ids: values.account_ids || [],
      hot_topics: hotspotCapture.fallback_topics,
      hotspot_capture: hotspotCapture,
      generation_config: {
        audience_roles: values.audience_roles?.length
          ? values.audience_roles
          : DEFAULT_GENERATION_CONFIG.audience_roles,
        article_strategy: values.article_strategy || DEFAULT_GENERATION_CONFIG.article_strategy,
        style_hint: values.style_hint?.trim() || DEFAULT_GENERATION_CONFIG.style_hint,
      },
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
    await startSchedule(scheduleId)
    message.success('已启动')
    await fetchData()
  }

  const handleStop = async (scheduleId: string) => {
    await stopSchedule(scheduleId)
    message.success('已停止')
    await fetchData()
  }

  const handleRunNow = async (scheduleId: string) => {
    const result = await runScheduleNow(scheduleId)
    message.success(result.task_id ? `已执行，任务ID: ${result.task_id}` : '已执行')
    await fetchData()
  }

  const handleDelete = async (scheduleId: string) => {
    await deleteSchedule(scheduleId)
    message.success('已删除')
    await fetchData()
  }

  const handlePreviewHotspots = async () => {
    const values = form.getFieldsValue()
    const hotspotCapture = normalizeHotspotCapture(values.hotspot_capture)
    if (!hotspotCapture.enabled) {
      message.info('请先启用热点捕获')
      return
    }
    setPreviewing(true)
    try {
      const result = await previewHotspots({
        keywords: values.name || '热点预览',
        hotspot_capture: hotspotCapture,
      })
      if (result.selected_hotspot?.title) {
        message.success(`预览命中：${result.selected_hotspot.title}`)
      } else {
        message.warning(result.hotspot_capture_error || '未命中可用热点')
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '热点预览失败')
    } finally {
      setPreviewing(false)
    }
  }

  const columns: TableProps<ScheduleConfig>['columns'] = [
    {
      title: '自动化规则',
      dataIndex: 'name',
      key: 'name',
      width: 180,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.name}</Text>
          <Text type="secondary">主题：{formatThemeName(record.theme_name)}</Text>
        </Space>
      ),
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
      title: '内容策略',
      key: 'generation_config',
      width: 260,
      render: (_, record) => (
        <Space size={[4, 8]} wrap>
          {(record.generation_config?.audience_roles || []).map((role) => (
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
      title: '热点规则',
      key: 'hotspot_capture',
      render: (_, record) => <Text>{summarizeHotspotCapture(record)}</Text>,
    },
    {
      title: '推送目标',
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
      render: (value: string | null) => formatDateTime(value),
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
    <div style={PAGE_STACK_STYLE}>
      <HeroPanel
        eyebrow="Automation Workbench"
        title="自动化编排台"
        description="在同一块工作台内整理执行节奏、热点输入与推送目标。现有的新建、编辑、启动、停止、立即执行和删除能力保持不变，只重构规则可读性和配置分组。"
      >
        <div role="toolbar" aria-label="Schedule actions" style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button type="primary" size="large" onClick={openCreate}>
            新建自动化规则
          </Button>
        </div>
      </HeroPanel>

      <SectionBlock
        title="规则明细"
        aside={<Text type="secondary">保留原有明细表，便于巡检时间、状态和批量查看。</Text>}
      >
        <Table rowKey="schedule_id" loading={loading} columns={columns} dataSource={schedules} />
      </SectionBlock>

      <Modal
        title={editing ? '编辑自动化规则' : '新建自动化规则'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={submit}
        confirmLoading={saving}
        width={920}
      >
        <Form layout="vertical" form={form}>
          <div style={FORM_STACK_STYLE}>
            <Card size="small" title="规则编排">
              <Row gutter={16}>
                <Col xs={24} md={12}>
                  <Form.Item label="任务名称" name="name" rules={[{ required: true, message: '请输入任务名称' }]}>
                    <Input placeholder="例如：早报自动发布" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label="执行方式" name="mode" rules={[{ required: true }]}>
                    <Radio.Group
                      options={[
                        { label: '指定时间执行', value: 'once' },
                        { label: '按时间间隔执行', value: 'interval' },
                      ]}
                    />
                  </Form.Item>
                </Col>
              </Row>

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
            </Card>

            <Card size="small" title="推送目标">
              <Row gutter={16}>
                <Col xs={24} md={12}>
                  <Form.Item label="文章主题样式" name="theme_name" rules={[{ required: true }]}>
                    <Select options={themeOptions} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="推送账号（可多选）"
                    name="account_ids"
                    rules={[{ required: true, message: '请选择至少一个账号' }]}
                  >
                    <Select mode="multiple" options={accountOptions} />
                  </Form.Item>
                </Col>
              </Row>
            </Card>

            <Card size="small" title="热点与回退">
              <Form.Item label="启用热点捕获" name={['hotspot_capture', 'enabled']} rules={[{ required: true }]}>
                <Radio.Group
                  options={[
                    { label: '是', value: true },
                    { label: '否', value: false },
                  ]}
                />
              </Form.Item>

              <Form.Item label="回退主题（可多项）" name={['hotspot_capture', 'fallback_topics']}>
                <Select
                  mode="tags"
                  tokenSeparators={[',', '，', ';', '；']}
                  placeholder="抓取失败或未命中时使用，例如：人工智能、A股、宏观经济"
                />
              </Form.Item>

              <Form.Item shouldUpdate noStyle>
                {({ getFieldValue }) => {
                  const enabled = getFieldValue(['hotspot_capture', 'enabled'])
                  if (!enabled) {
                    return <Text type="secondary">未启用时将直接使用“回退主题”或任务名称继续生成。</Text>
                  }
                  return (
                    <Space direction="vertical" size={16} style={{ width: '100%' }}>
                      <Row gutter={16}>
                        <Col xs={24} md={12}>
                          <Form.Item label="来源" name={['hotspot_capture', 'source']}>
                            <Select options={[{ label: 'TopHub', value: 'tophub' }]} />
                          </Form.Item>
                        </Col>
                        <Col xs={24} md={12}>
                          <Form.Item label="题材分类" name={['hotspot_capture', 'categories']}>
                            <Select
                              mode="tags"
                              tokenSeparators={[',', '，', ';', '；']}
                              options={HOTSPOT_CATEGORY_PRESETS}
                              placeholder="例如：AI、财经、科技"
                            />
                          </Form.Item>
                        </Col>
                      </Row>

                      <Form.List name={['hotspot_capture', 'platforms']}>
                        {(fields, { add, remove }) => (
                          <div>
                            <Space style={{ marginBottom: 8 }}>
                              <Text strong>平台节点</Text>
                              <Button
                                type="dashed"
                                icon={<PlusOutlined />}
                                onClick={() => add({ name: '', path: '', weight: 1, enabled: true })}
                              >
                                添加平台
                              </Button>
                            </Space>
                            {fields.length === 0 && <Text type="secondary">未配置平台时，会尝试从分类页自动发现。</Text>}
                            {fields.map((field) => (
                              <Card key={field.key} size="small" style={{ marginTop: 8 }}>
                                <Row gutter={16}>
                                  <Col xs={24} md={8}>
                                    <Form.Item
                                      {...field}
                                      label="平台名称"
                                      name={[field.name, 'name']}
                                      rules={[{ required: true, message: '请输入平台名称' }]}
                                    >
                                      <Input placeholder="例如：知乎热榜" />
                                    </Form.Item>
                                  </Col>
                                  <Col xs={24} md={8}>
                                    <Form.Item
                                      {...field}
                                      label="节点路径"
                                      name={[field.name, 'path']}
                                      rules={[{ required: true, message: '请输入节点路径' }]}
                                    >
                                      <Input placeholder="例如：/n/mproPpoq6O" />
                                    </Form.Item>
                                  </Col>
                                  <Col xs={24} md={4}>
                                    <Form.Item
                                      {...field}
                                      label="权重"
                                      name={[field.name, 'weight']}
                                      rules={[{ required: true, message: '请输入权重' }]}
                                    >
                                      <InputNumber min={0.1} max={10} step={0.1} style={{ width: '100%' }} />
                                    </Form.Item>
                                  </Col>
                                  <Col xs={24} md={4}>
                                    <Form.Item {...field} label="启用" name={[field.name, 'enabled']} initialValue>
                                      <Radio.Group
                                        options={[
                                          { label: '是', value: true },
                                          { label: '否', value: false },
                                        ]}
                                      />
                                    </Form.Item>
                                  </Col>
                                </Row>
                                <Button danger icon={<MinusCircleOutlined />} onClick={() => remove(field.name)}>
                                  删除平台
                                </Button>
                              </Card>
                            ))}
                          </div>
                        )}
                      </Form.List>

                      <Card size="small" title="筛选条件">
                        <Row gutter={16}>
                          <Col xs={24} md={12}>
                            <Form.Item
                              label="每个平台抓取数量"
                              name={['hotspot_capture', 'filters', 'top_n_per_platform']}
                              rules={[{ required: true, message: '请输入数量' }]}
                            >
                              <InputNumber min={1} max={50} style={{ width: '100%' }} />
                            </Form.Item>
                          </Col>
                          <Col xs={24} md={12}>
                            <Form.Item
                              label="最低命中分"
                              name={['hotspot_capture', 'filters', 'min_selection_score']}
                              rules={[{ required: true, message: '请输入分数阈值' }]}
                            >
                              <InputNumber min={0} max={100} style={{ width: '100%' }} />
                            </Form.Item>
                          </Col>
                        </Row>

                        <Form.Item label="排除关键词" name={['hotspot_capture', 'filters', 'exclude_keywords']}>
                          <Select
                            mode="tags"
                            tokenSeparators={[',', '，', ';', '；']}
                            placeholder="命中这些词的标题会被过滤"
                          />
                        </Form.Item>

                        <Form.Item label="偏好关键词" name={['hotspot_capture', 'filters', 'prefer_keywords']}>
                          <Select
                            mode="tags"
                            tokenSeparators={[',', '，', ';', '；']}
                            placeholder="命中这些词会额外加分"
                          />
                        </Form.Item>
                      </Card>

                      <Button loading={previewing} onClick={handlePreviewHotspots}>
                        预览热点命中
                      </Button>
                    </Space>
                  )
                }}
              </Form.Item>
            </Card>

            <Card size="small" title="内容策略">
              <Form.Item
                label="目标角色"
                name="audience_roles"
                rules={[{ required: true, message: '请至少选择一个目标角色' }]}
                extra="支持多角色视角，排在最前面的角色会被视为主视角。"
              >
                <Select
                  mode="tags"
                  options={GENERATION_ROLE_PRESETS.map((role) => ({ label: role, value: role }))}
                  tokenSeparators={[',', '，', ';', '；']}
                  placeholder="例如：投资者、开发者"
                />
              </Form.Item>

              <Form.Item
                label="文章策略"
                name="article_strategy"
                rules={[{ required: true, message: '请选择文章策略' }]}
              >
                <Select
                  options={Object.entries(ARTICLE_STRATEGY_LABELS).map(([value, label]) => ({
                    label,
                    value,
                  }))}
                />
              </Form.Item>

              <Form.Item
                label="风格补充（可选）"
                name="style_hint"
                extra="不填时系统会自动推断风格，填写后会作为定时任务的长期风格偏好。"
              >
                <Input.TextArea
                  rows={3}
                  maxLength={500}
                  showCount
                  placeholder="例如：偏理性分析，适合公众号阅读，参考财经或科技深度号的克制表达"
                  style={{ resize: 'none' }}
                />
              </Form.Item>
            </Card>

            <Card size="small" title="启用状态">
              <Form.Item label="创建后立即启动" name="enabled" rules={[{ required: true }]}>
                <Radio.Group
                  options={[
                    { label: '是', value: true },
                    { label: '否', value: false },
                  ]}
                />
              </Form.Item>
            </Card>
          </div>
        </Form>
      </Modal>
    </div>
  )
}
