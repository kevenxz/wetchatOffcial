import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Col, Form, Input, Menu, Modal, Row, Space, Spin, Typography, message } from 'antd'
import { EditOutlined, FormatPainterOutlined, ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

import { getPresetThemes, getStyleConfig, updateStyleConfig, type PresetThemes, type StyleConfig } from '@/api'

const { Title, Text } = Typography
const { TextArea } = Input

const CUSTOM_THEME_NAME = '当前配置（自定义）'

const DEFAULT_PREVIEW_MARKDOWN = `
# 微信公众号主题预览

这是一段正文示例，用于查看默认主题在公众号文章中的阅读效果。这里包含 **强调文本**、*斜体文本*、~~删除线~~ 和 [链接样式](https://mp.weixin.qq.com)。

## 二级标题示例

> 这是引用内容示例，用于观察左侧强调线、背景色和段落间距。

### 三级标题示例

- 列表项一：适合展示摘要信息
- 列表项二：适合展示步骤说明
- 列表项三：适合展示重点结论

1. 有序列表也需要保持清晰层级
2. 适中的行高和留白会更适合移动端阅读

\`行内代码\` 可以用于标注术语或命令。

\`\`\`python
def hello():
    print("wechat")
\`\`\`

---

| 配置项 | 说明 |
| --- | --- |
| 标题 | 使用绿色主题强调层级 |
| 正文 | 保持简洁、易读、适配手机端 |
`

const STYLE_FIELDS = [
  { name: 'container', label: '容器 (container)', tooltip: '文章最外层容器样式' },
  { name: 'h1', label: '一级标题 (h1)', tooltip: '文章主标题' },
  { name: 'h2', label: '二级标题 (h2)', tooltip: '段落标题' },
  { name: 'h3', label: '三级标题 (h3)', tooltip: '次级段落标题' },
  { name: 'h4', label: '四级标题 (h4)', tooltip: '补充标题层级' },
  { name: 'h5', label: '五级标题 (h5)', tooltip: '补充标题层级' },
  { name: 'h6', label: '六级标题 (h6)', tooltip: '补充标题层级' },
  { name: 'p', label: '正文段落 (p)', tooltip: '普通正文文本' },
  { name: 'strong', label: '强调 (strong)', tooltip: '粗体强调文本' },
  { name: 'em', label: '斜体 (em)', tooltip: '斜体文本' },
  { name: 'del', label: '删除线 (del)', tooltip: '删除线文本' },
  { name: 'blockquote', label: '引用 (blockquote)', tooltip: '引用块内容' },
  { name: 'ul', label: '无序列表 (ul)', tooltip: '无序列表容器' },
  { name: 'ol', label: '有序列表 (ol)', tooltip: '有序列表容器' },
  { name: 'li', label: '列表项 (li)', tooltip: '列表项文本' },
  { name: 'a', label: '链接 (a)', tooltip: '超链接文本' },
  { name: 'hr', label: '分隔线 (hr)', tooltip: '分隔线样式' },
  { name: 'img', label: '图片 (img)', tooltip: '图片元素样式' },
  { name: 'figure', label: '图片容器 (figure)', tooltip: '图片和说明容器' },
  { name: 'figcaption', label: '图片说明 (figcaption)', tooltip: '图片说明文字' },
  { name: 'code', label: '行内代码 (code)', tooltip: '行内代码默认样式' },
  { name: 'pre', label: '代码块容器 (pre)', tooltip: '代码块外层容器' },
  { name: 'pre code', label: '代码块内容 (pre code)', tooltip: '代码块内容样式' },
  { name: 'table', label: '表格 (table)', tooltip: '表格整体样式' },
  { name: 'th', label: '表头 (th)', tooltip: '表头单元格' },
  { name: 'td', label: '表格单元格 (td)', tooltip: '表格内容单元格' },
]

function mergeStyle(existing: string | null, next: string) {
  if (!existing) return next
  return `${existing}${existing.trim().endsWith(';') ? ' ' : '; '}${next}`
}

function buildPreviewHtml(markdownText: string, config: StyleConfig) {
  const rawHtml = marked.parse(markdownText, { breaks: true }) as string
  const cleanHtml = DOMPurify.sanitize(rawHtml)
  const parser = new DOMParser()
  const doc = parser.parseFromString(`<div class="wx-article-container">${cleanHtml}</div>`, 'text/html')
  const container = doc.body.firstElementChild as HTMLElement | null

  if (!container) return cleanHtml

  Object.entries(config).forEach(([selector, styleStr]) => {
    if (!styleStr) return
    if (selector === 'container') {
      container.setAttribute('style', mergeStyle(container.getAttribute('style'), styleStr))
      return
    }

    doc.querySelectorAll(selector).forEach((element) => {
      const htmlElement = element as HTMLElement
      htmlElement.setAttribute('style', mergeStyle(htmlElement.getAttribute('style'), styleStr))
    })
  })

  return container.outerHTML
}

export default function StyleConfigPage() {
  const [form] = Form.useForm<StyleConfig>()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [currentConfig, setCurrentConfig] = useState<StyleConfig>({})
  const [themes, setThemes] = useState<PresetThemes>({})
  const [activeTheme, setActiveTheme] = useState<string>(CUSTOM_THEME_NAME)
  const [previewMarkdown, setPreviewMarkdown] = useState(DEFAULT_PREVIEW_MARKDOWN)
  const [isEditingContent, setIsEditingContent] = useState(false)
  const [tempMarkdown, setTempMarkdown] = useState(DEFAULT_PREVIEW_MARKDOWN)

  const fetchData = async () => {
    setLoading(true)
    try {
      const [configData, themesData] = await Promise.all([getStyleConfig(), getPresetThemes()])
      setCurrentConfig(configData)
      form.setFieldsValue(configData)
      setThemes(themesData)
    } catch (err: any) {
      message.error(err.message || '加载样式配置失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  const formValues = Form.useWatch([], form)

  useEffect(() => {
    if (formValues) {
      setCurrentConfig((prev) => ({ ...prev, ...formValues }))
    }
  }, [formValues])

  const handleSave = async (values: StyleConfig) => {
    setSaving(true)
    try {
      await updateStyleConfig(values)
      message.success('样式配置已保存')
      setActiveTheme(CUSTOM_THEME_NAME)
    } catch (err: any) {
      message.error(err.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const applyTheme = (themeName: string) => {
    const themeConfig = themes[themeName]
    if (!themeConfig) return
    setCurrentConfig(themeConfig)
    form.setFieldsValue(themeConfig)
    setActiveTheme(themeName)
    message.info(`已应用主题：${themeName}`)
  }

  const previewHtml = useMemo(() => buildPreviewHtml(previewMarkdown, currentConfig), [currentConfig, previewMarkdown])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" tip="加载样式配置中..." />
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 1600, margin: '24px auto', padding: '0 24px' }}>
      <Row justify="space-between" align="middle" style={{ marginBottom: 24 }}>
        <Col>
          <Title level={2} style={{ margin: 0 }}>系统配置</Title>
          <Text type="secondary">配置微信公众号文章默认主题，并实时预览 Markdown 渲染效果。</Text>
        </Col>
        <Col>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              fetchData()
              setActiveTheme(CUSTOM_THEME_NAME)
            }}
            style={{ marginRight: 16 }}
          >
            重新加载
          </Button>
          <Button type="primary" icon={<SaveOutlined />} onClick={() => form.submit()} loading={saving}>
            保存配置
          </Button>
        </Col>
      </Row>

      <Row gutter={24} style={{ alignItems: 'stretch' }}>
        <Col xs={24} md={5} lg={4}>
          <Card title="预设主题" styles={{ body: { padding: 0 } }} style={{ height: '100%' }}>
            <Menu
              mode="vertical"
              selectedKeys={[activeTheme]}
              onSelect={({ key }) => applyTheme(String(key))}
              items={Object.keys(themes).map((name) => ({
                key: name,
                icon: <FormatPainterOutlined />,
                label: name,
              }))}
            />
          </Card>
        </Col>

        <Col xs={24} md={10} lg={11}>
          <Card
            title={(
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>实时预览</span>
                <Button type="link" size="small" icon={<EditOutlined />} onClick={() => setIsEditingContent(true)}>
                  编辑示例内容
                </Button>
              </div>
            )}
            styles={{ body: { padding: '40px 0', backgroundColor: '#f0f2f5', minHeight: 600 } }}
          >
            <div
              style={{
                width: '100%',
                maxWidth: 414,
                margin: '0 auto',
                border: '1px solid #e8e8e8',
                padding: 20,
                backgroundColor: '#fff',
                boxShadow: '0 4px 12px rgba(0,0,0,0.05)',
                minHeight: 600,
              }}
            >
              <div
                className="wx-article-preview"
                dangerouslySetInnerHTML={{ __html: previewHtml }}
                style={{ wordWrap: 'break-word', overflowWrap: 'break-word' }}
              />
            </div>
          </Card>
        </Col>

        <Col xs={24} md={9} lg={9}>
          <Card
            title={(
              <Space>
                <FormatPainterOutlined />
                <span>样式编辑器</span>
                <Text type="secondary" style={{ fontSize: 13, fontWeight: 'normal' }}>
                  ({activeTheme})
                </Text>
              </Space>
            )}
          >
            <Form form={form} layout="vertical" onFinish={handleSave}>
              <Row gutter={16}>
                {STYLE_FIELDS.map((field) => (
                  <Col span={24} key={field.name}>
                    <Form.Item name={field.name} label={field.label} tooltip={field.tooltip}>
                      <TextArea
                        rows={3}
                        placeholder="例如: font-size: 16px; color: #333; line-height: 1.6;"
                        style={{ fontFamily: 'monospace', fontSize: 13 }}
                      />
                    </Form.Item>
                  </Col>
                ))}
              </Row>
            </Form>
          </Card>
        </Col>
      </Row>

      <Modal
        title="编辑预览内容"
        open={isEditingContent}
        onOk={() => {
          setPreviewMarkdown(tempMarkdown)
          setIsEditingContent(false)
        }}
        onCancel={() => {
          setTempMarkdown(previewMarkdown)
          setIsEditingContent(false)
        }}
        width={800}
      >
        <TextArea
          value={tempMarkdown}
          onChange={(e) => setTempMarkdown(e.target.value)}
          rows={15}
          style={{ fontFamily: 'monospace', marginTop: 16 }}
        />
      </Modal>
    </div>
  )
}
