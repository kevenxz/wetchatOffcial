import type { CSSProperties } from 'react'
import { Button, Form, Input, Select, Tag, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import {
  ARTICLE_STRATEGY_LABELS,
  DEFAULT_GENERATION_CONFIG,
  GENERATION_ROLE_PRESETS,
  type ArticleStrategy,
} from '@/api'
import { HeroPanel, SectionBlock } from '@/components/workbench'
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
  gap: 20,
}

const guidanceListStyle: CSSProperties = {
  display: 'grid',
  gap: 8,
  margin: 0,
  paddingInlineStart: 18,
  color: 'var(--text-secondary)',
  fontSize: 13,
  lineHeight: 1.6,
}

const topicCloudStyle: CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 10,
}

const helperTextStyle: CSSProperties = {
  fontSize: 13,
  color: 'var(--text-secondary)',
}

const formGroupsStyle: CSSProperties = {
  display: 'grid',
  gap: 20,
}

const formGroupStyle: CSSProperties = {
  display: 'grid',
  gap: 12,
}

const groupTitleStyle: CSSProperties = {
  margin: 0,
  fontSize: 15,
  fontWeight: 600,
  color: 'var(--text-primary)',
}

const twoColumnStyle: CSSProperties = {
  display: 'grid',
  gap: 16,
  gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
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
    <div style={pageLayoutStyle} data-testid="task-create-grid">
      <HeroPanel
        eyebrow="Studio Launch"
        title="启动一次完整创作流程"
        description="从热点捕捉、受众视角到文章风格，一次配置就能进入完整的公众号创作链路。"
      >
        <ul style={guidanceListStyle} aria-label="创作提示">
          <li>先点灵感标签补齐关键词，再继续填写表单。</li>
          <li>受众角色和文章策略直接沿用系统预设，保持投递兼容。</li>
          <li>风格补充只写差异信息，默认值会自动兜底。</li>
        </ul>
      </HeroPanel>

      <SectionBlock
        title="热点灵感"
        aside={<span style={helperTextStyle}>点选标签即可把词条补进关键词输入框。</span>}
      >
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

      <SectionBlock
        title="创作表单"
        aside={<span style={helperTextStyle}>保留原有创建任务逻辑，仅调整为更紧凑的分组呈现。</span>}
      >
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
          <div style={formGroupsStyle}>
            <section style={formGroupStyle}>
              <h3 style={groupTitleStyle}>基础输入</h3>
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
            </section>

            <section style={formGroupStyle}>
              <h3 style={groupTitleStyle}>受众与策略</h3>
              <div style={twoColumnStyle}>
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
              </div>
            </section>

            <section style={formGroupStyle}>
              <h3 style={groupTitleStyle}>风格补充</h3>
              <Form.Item
                name="style_hint"
                label="风格补充（可选）"
                extra="不填写时系统会自动判断；填写后会作为语气、结构和叙事重点的补充提示。"
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
            </section>
          </div>
        </Form>
      </SectionBlock>
    </div>
  )
}
