import { Button, Card, Form, Input, Tag, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import useTaskStore from '@/store/taskStore'

const HOT_TOPICS = ['人工智能', '大模型', '新能源', '量子计算', '元宇宙', '碳中和']

export default function TaskCreate() {
  const [form] = Form.useForm<{ keywords: string }>()
  const navigate = useNavigate()
  const { isCreating, createTask } = useTaskStore()

  const handleSubmit = async (values: { keywords: string }) => {
    try {
      const taskId = await createTask(values.keywords.trim())
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
