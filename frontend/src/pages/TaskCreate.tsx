import type { CSSProperties } from 'react'
import {
  BulbOutlined,
  FireOutlined,
  FormOutlined,
  RadarChartOutlined,
  RocketOutlined,
} from '@ant-design/icons'
import { Button, Card, Form, Input, Select, Tag, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import {
  ARTICLE_STRATEGY_LABELS,
  DEFAULT_GENERATION_CONFIG,
  GENERATION_ROLE_PRESETS,
  type ArticleStrategy,
} from '@/api'
import { HeroPanel, MetricCard, SectionBlock, SignalCard } from '@/components/workbench'
import useTaskStore from '@/store/taskStore'

const HOT_TOPICS = ['人工智能', '大模型', '新能源', '量子计算', '元宇宙', '碳中和']

interface TaskCreateFormValues {
  keywords: string
  audience_roles: string[]
  article_strategy: ArticleStrategy
  style_hint?: string
}

const pageLayoutStyle: CSSProperties = {
  display: 'grid',
  gap: 24,
}

const insightGridStyle: CSSProperties = {
  display: 'grid',
  gap: 16,
  gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
}

const signalGridStyle: CSSProperties = {
  display: 'grid',
  gap: 12,
}

const topicCloudStyle: CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 10,
}

const formCardStyle: CSSProperties = {
  borderRadius: 24,
  border: '1px solid rgba(148, 163, 184, 0.18)',
  background: 'rgba(15, 23, 42, 0.78)',
  boxShadow: '0 24px 80px rgba(15, 23, 42, 0.16)',
}

const formBodyStyle: CSSProperties = {
  padding: 28,
}

const helperTextStyle: CSSProperties = {
  fontSize: 13,
  color: 'var(--text-secondary)',
}

export default function TaskCreate() {
  const [form] = Form.useForm<TaskCreateFormValues>()
  const navigate = useNavigate()
  const { isCreating, createTask } = useTaskStore()

  const handleSubmit = async (values: TaskCreateFormValues) => {
    try {
      const taskId = await createTask({
        keywords: values.keywords.trim(),
        generation_config: {
          audience_roles: values.audience_roles?.length
            ? values.audience_roles
            : DEFAULT_GENERATION_CONFIG.audience_roles,
          article_strategy: values.article_strategy || DEFAULT_GENERATION_CONFIG.article_strategy,
          style_hint: values.style_hint?.trim() || DEFAULT_GENERATION_CONFIG.style_hint,
        },
      })
      navigate(`/task/${taskId}`)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '创建任务失败')
    }
  }

  const fillKeyword = (topic: string) => {
    const current = form.getFieldValue('keywords') as string | undefined
    const next = current?.trim() ? `${current.trim()} ${topic}` : topic
    form.setFieldValue('keywords', next)
    form.validateFields(['keywords']).catch(() => undefined)
  }

  return (
    <div style={pageLayoutStyle}>
      <HeroPanel
        eyebrow="Studio Launch"
        title="启动一次完整创作流程"
        description="从热点捕捉、受众视角到文章风格，一次配置就能进入完整的公众号创作链路。"
      >
        <div style={insightGridStyle}>
          <MetricCard label="创作节奏" value="15m" hint="从选题到任务启动保持同一操作面板" />
          <MetricCard label="受众视角" value="5类" hint="沿用系统角色预设，保证投递配置兼容现有流程" />
          <MetricCard label="热点输入" value="6组" hint="点击灵感标签即可快速补充关键词" />
        </div>
      </HeroPanel>

      <div className="task-create-grid" data-testid="task-create-grid">
        <div style={signalGridStyle}>
          <SectionBlock title="热点灵感">
            <div style={topicCloudStyle}>
              {HOT_TOPICS.map((topic) => (
                <Tag
                  key={topic}
                  color="cyan"
                  style={{ cursor: 'pointer', userSelect: 'none', paddingInline: 12, paddingBlock: 6 }}
                  onClick={() => fillKeyword(topic)}
                >
                  {topic}
                </Tag>
              ))}
            </div>
          </SectionBlock>

          <SectionBlock title="启动信号">
            <SignalCard
              icon={<FireOutlined />}
              title="热点进入选题池"
              description="先收集关键词，再把最值得写的方向送入本次创作任务。"
            />
            <SignalCard
              icon={<RadarChartOutlined />}
              title="受众视角稳定输出"
              description="目标角色直接复用系统预设，避免新页面提交出兼容性错误的受众值。"
            />
            <SignalCard
              icon={<BulbOutlined />}
              title="风格补充按需介入"
              description="你可以保持系统自动判断，也可以补充期望语气、结构和参考范式。"
            />
          </SectionBlock>
        </div>

        <SectionBlock
          title="创作发射台"
          aside={<span style={helperTextStyle}>保留原有创建任务逻辑，仅更新页面呈现。</span>}
        >
          <Card title="启动创作流程" variant="borderless" style={formCardStyle} styles={{ body: formBodyStyle }}>
            <Form
              form={form}
              layout="vertical"
              onFinish={handleSubmit}
              requiredMark="optional"
              initialValues={{
                audience_roles: DEFAULT_GENERATION_CONFIG.audience_roles,
                article_strategy: DEFAULT_GENERATION_CONFIG.article_strategy,
                style_hint: DEFAULT_GENERATION_CONFIG.style_hint,
              }}
            >
              <Form.Item
                name="keywords"
                label="关键词"
                rules={[
                  { required: true, message: '请输入关键词' },
                  {
                    validator: (_, value: string) =>
                      value?.trim()
                        ? Promise.resolve()
                        : Promise.reject(new Error('关键词不能为空白内容')),
                  },
                ]}
                extra="多个关键词可用空格分隔，用于锁定本次主题与检索方向。"
              >
                <Input.TextArea
                  rows={4}
                  maxLength={200}
                  showCount
                  placeholder={'输入关键词，多个关键词用空格分隔\n例如：人工智能 最新进展'}
                  style={{ resize: 'none' }}
                />
              </Form.Item>

              <Form.Item
                name="audience_roles"
                label="目标角色"
                rules={[{ required: true, message: '请至少选择一个目标角色' }]}
                extra="可多选，排序会影响系统理解的主视角。"
              >
                <Select
                  mode="tags"
                  options={GENERATION_ROLE_PRESETS.map((role) => ({ label: role, value: role }))}
                  tokenSeparators={[',', '，', ';', '；']}
                  placeholder="例如：投资者、开发者"
                />
              </Form.Item>

              <Form.Item
                name="article_strategy"
                label="文章策略"
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
                name="style_hint"
                label="风格补充（可选）"
                extra="不填写时系统自动判断；填写后会作为语气、结构和叙事重点的补充提示。"
              >
                <Input.TextArea
                  rows={3}
                  maxLength={500}
                  showCount
                  placeholder="例如：面向投资者，语言理性克制，结构偏市场观察与机会判断。"
                  style={{ resize: 'none' }}
                />
              </Form.Item>

              <Form.Item style={{ marginBottom: 0 }}>
                <Button type="primary" htmlType="submit" size="large" block loading={isCreating}>
                  启动创作流程
                </Button>
              </Form.Item>
            </Form>
          </Card>

          <div style={{ ...signalGridStyle, gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
            <SignalCard
              icon={<FormOutlined />}
              title="表单逻辑保留"
              description="仍然提交关键词、角色、文章策略和风格补充，并跳转到任务详情。"
            />
            <SignalCard
              icon={<RocketOutlined />}
              title="进入任务详情"
              description="创建成功后沿用原有导航行为，直接进入对应任务页面。"
            />
          </div>
        </SectionBlock>
      </div>
    </div>
  )
}
