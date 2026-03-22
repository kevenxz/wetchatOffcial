import { Button, Card, Form, Input, Select, Tag, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import {
  ARTICLE_STRATEGY_LABELS,
  DEFAULT_GENERATION_CONFIG,
  GENERATION_ROLE_PRESETS,
  type ArticleStrategy,
} from '@/api'
import useTaskStore from '@/store/taskStore'

const HOT_TOPICS = ['人工智能', '大模型', '新能源', '量子计算', '元宇宙', '碳中和']

interface TaskCreateFormValues {
  keywords: string
  audience_roles: string[]
  article_strategy: ArticleStrategy
  style_hint?: string
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
    <div style={{ maxWidth: 720, margin: '40px auto' }}>
      <Card
        title={
          <span style={{ fontSize: 18, fontWeight: 600 }}>
            生成微信公众号文章
          </span>
        }
        variant="borderless"
        styles={{ body: { padding: '32px 40px' } }}
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
          <Form.Item
            name="keywords"
            label="请输入关键词"
            rules={[
              { required: true, message: '请输入关键词' },
              {
                validator: (_, value: string) =>
                  value?.trim()
                    ? Promise.resolve()
                    : Promise.reject(new Error('关键词不能为纯空格')),
              },
            ]}
          >
            <Input.TextArea
              rows={4}
              maxLength={200}
              showCount
              placeholder="输入关键词，多个关键词用空格分隔&#10;例如：人工智能 最新进展"
              style={{ resize: 'none' }}
            />
          </Form.Item>

          <Form.Item label="热门话题" style={{ marginBottom: 24 }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {HOT_TOPICS.map((topic) => (
                <Tag
                  key={topic}
                  color="blue"
                  style={{ cursor: 'pointer', userSelect: 'none' }}
                  onClick={() => fillKeyword(topic)}
                >
                  {topic}
                </Tag>
              ))}
            </div>
          </Form.Item>

          <Form.Item
            name="audience_roles"
            label="目标角色"
            rules={[{ required: true, message: '请至少选择一个目标角色' }]}
            extra="可多选。排序有意义，第一个角色会被视为主视角。"
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
            extra="不填时系统会自动推断风格，填写后会作为偏好提示。"
          >
            <Input.TextArea
              rows={3}
              maxLength={500}
              showCount
              placeholder="例如：面向投资者，语气理性克制，参考财经类公众号的写法"
              style={{ resize: 'none' }}
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              size="large"
              block
              loading={isCreating}
            >
              生成文章
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
