import { useEffect, useState } from 'react'
import {
  ApiOutlined,
  PictureOutlined,
  ReloadOutlined,
  RobotOutlined,
  SaveOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { Button, Form, Input, Space, Spin, Switch, Typography, message } from 'antd'
import { getModelConfig, updateModelConfig, type ModelConfig } from '@/api'
import { HeroPanel, SectionBlock, SignalCard } from '@/components/workbench'

const { Text } = Typography

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

const guidanceListStyle = {
  display: 'grid',
  gap: 8,
  margin: 0,
  paddingInlineStart: 20,
  listStyleType: 'disc',
  listStylePosition: 'outside',
  color: 'var(--text-secondary)',
  fontSize: 13,
  lineHeight: 1.6,
}

const panelStyle = {
  display: 'grid',
  gap: 16,
  padding: 20,
  borderRadius: 16,
  border: '1px solid var(--app-border)',
  background: 'var(--app-surface)',
}

const panelTitleStyle = {
  margin: 0,
  fontSize: 15,
  fontWeight: 600,
  color: 'var(--app-text)',
}

export default function ModelConfigPage() {
  const [form] = Form.useForm<ModelConfig>()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const imageEnabled = Form.useWatch(['image', 'enabled'], form) ?? false
  const textModel = Form.useWatch(['text', 'model'], form) ?? EMPTY_CONFIG.text.model
  const imageModel = Form.useWatch(['image', 'model'], form) ?? EMPTY_CONFIG.image.model
  const textApiKey = Form.useWatch(['text', 'api_key'], form) ?? ''
  const imageApiKey = Form.useWatch(['image', 'api_key'], form) ?? ''
  const configuredKeyCount = (textApiKey ? 1 : 0) + (imageEnabled && imageApiKey ? 1 : 0)

  const loadConfig = async () => {
    setLoading(true)
    try {
      const config = await getModelConfig()
      form.setFieldsValue({
        text: {
          api_key: config.text.api_key || '',
          base_url: config.text.base_url || '',
          model: config.text.model || EMPTY_CONFIG.text.model,
        },
        image: {
          enabled: Boolean(config.image.enabled),
          api_key: config.image.api_key || '',
          base_url: config.image.base_url || '',
          model: config.image.model || EMPTY_CONFIG.image.model,
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
    void loadConfig()
  }, [])

  const handleSave = async (values: ModelConfig) => {
    setSaving(true)
    try {
      const payload: ModelConfig = {
        text: {
          api_key: values.text.api_key?.trim() || '',
          base_url: values.text.base_url?.trim() || null,
          model: values.text.model?.trim() || EMPTY_CONFIG.text.model,
        },
        image: {
          enabled: Boolean(values.image.enabled),
          api_key: values.image.api_key?.trim() || '',
          base_url: values.image.base_url?.trim() || null,
          model: values.image.model?.trim() || EMPTY_CONFIG.image.model,
        },
      }
      const updated = await updateModelConfig(payload)
      form.setFieldsValue({
        text: {
          api_key: updated.text.api_key || '',
          base_url: updated.text.base_url || '',
          model: updated.text.model || EMPTY_CONFIG.text.model,
        },
        image: {
          enabled: Boolean(updated.image.enabled),
          api_key: updated.image.api_key || '',
          base_url: updated.image.base_url || '',
          model: updated.image.model || EMPTY_CONFIG.image.model,
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
      <div className="backstage-loading">
        <Space direction="vertical" size={12} align="center">
          <Spin size="large" />
          <Text type="secondary">正在同步模型配置...</Text>
        </Space>
      </div>
    )
  }

  return (
    <div className="backstage-page">
      <HeroPanel
        eyebrow="System Backstage"
        title="模型接入配置"
        description="统一管理文本与图片模型的密钥、网关和默认型号。"
      >
        <ul style={guidanceListStyle} aria-label="模型配置提示">
          <li>文本模型负责常规生成，图片模型按需开启即可。</li>
          <li>Base URL 留空时会回落到默认地址，不影响保存流程。</li>
          <li>修改后直接保存，页面会同步回写最新配置。</li>
        </ul>
      </HeroPanel>

      <SectionBlock
        title="配置操作"
        aside={
          <Space wrap>
            <Button icon={<ReloadOutlined />} onClick={() => void loadConfig()}>
              重新加载
            </Button>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => form.submit()}>
              保存配置
            </Button>
          </Space>
        }
      >
        <Form<ModelConfig> form={form} layout="vertical" initialValues={EMPTY_CONFIG} onFinish={handleSave}>
          <div className="backstage-grid backstage-grid--double">
            <section style={panelStyle}>
              <h3 style={panelTitleStyle}>文本模型</h3>
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
            </section>

            <section style={panelStyle}>
              <h3 style={panelTitleStyle}>图片模型</h3>
              <Form.Item label="启用图片生成" name={['image', 'enabled']} valuePropName="checked">
                <Switch checkedChildren="已启用" unCheckedChildren="已关闭" />
              </Form.Item>

              <Form.Item
                label="API Key"
                name={['image', 'api_key']}
                rules={
                  imageEnabled ? [{ required: true, message: '启用图片生成时必须填写 API Key' }] : []
                }
              >
                <Input.Password placeholder="输入图片模型 API Key" disabled={!imageEnabled} />
              </Form.Item>

              <Form.Item
                label="Base URL"
                name={['image', 'base_url']}
                tooltip="兼容图片模型或 Chat Completions 的网关地址"
              >
                <Input placeholder="例如：https://images.example.com/v1" disabled={!imageEnabled} />
              </Form.Item>

              <Form.Item
                label="模型名称"
                name={['image', 'model']}
                rules={imageEnabled ? [{ required: true, message: '请输入图片模型名称' }] : []}
              >
                <Input
                  placeholder="例如：dall-e-3 / flux / seedream / gemini-3.1-flash-image-preview"
                  disabled={!imageEnabled}
                />
              </Form.Item>
            </section>
          </div>
        </Form>
      </SectionBlock>

      <div className="backstage-grid backstage-grid--double">
        <SectionBlock title="接入提醒" aside={<Text type="secondary">保留原有校验和保存逻辑，只压缩页面呈现。</Text>}>
          <div className="backstage-note-list">
            <SignalCard
              icon={<RobotOutlined />}
              title="文本模型"
              description="负责选题拆解、正文生成和结构规划，是后台工作流的核心输入。"
            />
            <SignalCard
              icon={<PictureOutlined />}
              title="图片模型"
              description="关闭后仍可继续运行文字流程，不会阻断内容生产。"
            />
            <SignalCard
              icon={<ApiOutlined />}
              title="网关地址"
              description="仅在需要接入兼容 OpenAI 规范的中转层时填写，留空则走默认地址。"
            />
            <SignalCard
              icon={<WarningOutlined />}
              title="密钥管理"
              description="建议按环境拆分不同密钥，避免测试和生产流量混用。"
            />
          </div>
        </SectionBlock>

        <SectionBlock title="当前概览">
          <div style={panelStyle}>
            <Space size={[8, 8]} wrap>
              <Text strong>当前文本模型：</Text>
              <Text>{textModel || EMPTY_CONFIG.text.model}</Text>
            </Space>
            <Space size={[8, 8]} wrap>
              <Text strong>当前图片模型：</Text>
              <Text>{imageEnabled ? imageModel || EMPTY_CONFIG.image.model : '已关闭'}</Text>
            </Space>
            <Space size={[8, 8]} wrap>
              <Text strong>已配置密钥：</Text>
              <Text>{configuredKeyCount}</Text>
            </Space>
          </div>
        </SectionBlock>
      </div>
    </div>
  )
}
