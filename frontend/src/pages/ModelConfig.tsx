import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Form,
  Input,
  Row,
  Space,
  Spin,
  Switch,
  Typography,
  message,
} from 'antd'
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons'

import {
  getModelConfig,
  updateModelConfig,
  type ModelConfig,
} from '@/api'

const { Title, Paragraph, Text } = Typography

const EMPTY_CONFIG: ModelConfig = {
  text: {
    api_key: '',
    base_url: '',
    model: 'gpt-4o',
  },
  image: {
    enabled: false,
    api_key: '',
    base_url: '',
    model: 'dall-e-3',
  },
}

export default function ModelConfigPage() {
  const [form] = Form.useForm<ModelConfig>()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const imageEnabled = Form.useWatch(['image', 'enabled'], form) ?? false

  const loadConfig = async () => {
    setLoading(true)
    try {
      const config = await getModelConfig()
      form.setFieldsValue({
        text: {
          api_key: config.text.api_key || '',
          base_url: config.text.base_url || '',
          model: config.text.model || 'gpt-4o',
        },
        image: {
          enabled: Boolean(config.image.enabled),
          api_key: config.image.api_key || '',
          base_url: config.image.base_url || '',
          model: config.image.model || 'dall-e-3',
        },
      })
    } catch (err: any) {
      message.error(err.message || '加载模型配置失败')
      form.setFieldsValue(EMPTY_CONFIG)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadConfig()
  }, [])

  const handleSave = async (values: ModelConfig) => {
    setSaving(true)
    try {
      const payload: ModelConfig = {
        text: {
          api_key: values.text.api_key?.trim() || '',
          base_url: values.text.base_url?.trim() || null,
          model: values.text.model?.trim() || 'gpt-4o',
        },
        image: {
          enabled: Boolean(values.image.enabled),
          api_key: values.image.api_key?.trim() || '',
          base_url: values.image.base_url?.trim() || null,
          model: values.image.model?.trim() || 'dall-e-3',
        },
      }
      const updated = await updateModelConfig(payload)
      form.setFieldsValue({
        text: {
          api_key: updated.text.api_key || '',
          base_url: updated.text.base_url || '',
          model: updated.text.model || 'gpt-4o',
        },
        image: {
          enabled: Boolean(updated.image.enabled),
          api_key: updated.image.api_key || '',
          base_url: updated.image.base_url || '',
          model: updated.image.model || 'dall-e-3',
        },
      })
      message.success('模型配置已保存')
    } catch (err: any) {
      message.error(err.message || '保存模型配置失败')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" tip="加载模型配置中..." />
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 1400, margin: '24px auto', padding: '0 24px' }}>
      <Row justify="space-between" align="middle" style={{ marginBottom: 20 }}>
        <Col>
          <Title level={2} style={{ margin: 0 }}>模型配置</Title>
          <Paragraph type="secondary" style={{ margin: '8px 0 0' }}>
            分别配置文本生成和图像生成的模型、网关地址与 API Key。保存后，文章生成与图片生成节点会直接读取这里的配置。
          </Paragraph>
        </Col>
        <Col>
          <Space size={12}>
            <Button icon={<ReloadOutlined />} onClick={loadConfig}>重新加载</Button>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => form.submit()}>
              保存配置
            </Button>
          </Space>
        </Col>
      </Row>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 20 }}
        message="配置说明"
        description="文本模型用于策略规划和文章生成。图像模型用于封面图和正文插图生成；关闭图像生成后，系统会继续回退到网页抓取图片。"
      />

      <Form<ModelConfig>
        form={form}
        layout="vertical"
        initialValues={EMPTY_CONFIG}
        onFinish={handleSave}
      >
        <Row gutter={24}>
          <Col xs={24} xl={12}>
            <Card
              title="文本模型"
              extra={<Text type="secondary">用于文章规划与正文生成</Text>}
            >
              <Form.Item
                label="API Key"
                name={['text', 'api_key']}
                rules={[{ required: true, message: '请输入文本模型 API Key' }]}
              >
                <Input.Password placeholder="输入文本模型 API Key" />
              </Form.Item>

              <Form.Item
                label="Base URL"
                name={['text', 'base_url']}
                tooltip="兼容 OpenAI 接口的网关地址，可留空使用默认地址"
              >
                <Input placeholder="例如：https://api.example.com/v1" />
              </Form.Item>

              <Form.Item
                label="模型名称"
                name={['text', 'model']}
                rules={[{ required: true, message: '请输入文本模型名称' }]}
              >
                <Input placeholder="例如：gpt-4o / qwen-max / deepseek-chat" />
              </Form.Item>
            </Card>
          </Col>

          <Col xs={24} xl={12}>
            <Card
              title="图像模型"
              extra={<Text type="secondary">用于封面图与插图生成</Text>}
            >
              <Form.Item label="启用图像生成" name={['image', 'enabled']} valuePropName="checked">
                <Switch checkedChildren="已启用" unCheckedChildren="已关闭" />
              </Form.Item>

              <Form.Item
                label="API Key"
                name={['image', 'api_key']}
                rules={imageEnabled ? [{ required: true, message: '启用图像生成时必须填写 API Key' }] : []}
              >
                <Input.Password placeholder="输入图像模型 API Key" disabled={!imageEnabled} />
              </Form.Item>

              <Form.Item
                label="Base URL"
                name={['image', 'base_url']}
                tooltip="兼容 OpenAI Images 接口的网关地址"
              >
                <Input placeholder="例如：https://images.example.com/v1" disabled={!imageEnabled} />
              </Form.Item>

              <Form.Item
                label="模型名称"
                name={['image', 'model']}
                rules={imageEnabled ? [{ required: true, message: '请输入图像模型名称' }] : []}
              >
                <Input placeholder="例如：dall-e-3 / flux / seedream" disabled={!imageEnabled} />
              </Form.Item>
            </Card>
          </Col>
        </Row>
      </Form>
    </div>
  )
}
