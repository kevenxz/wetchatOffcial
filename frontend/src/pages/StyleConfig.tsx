import { useEffect, useState, useMemo } from 'react'
import { Card, Form, Input, Button, message, Row, Col, Typography, Spin } from 'antd'
import { SaveOutlined, ReloadOutlined } from '@ant-design/icons'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { getStyleConfig, updateStyleConfig, type StyleConfig } from '@/api'

const { Title, Text } = Typography
const { TextArea } = Input

// 示例 Markdown 文本用于实时预览
const PREVIEW_MARKDOWN = `
# 微信公众号排版演示（一级标题）

这是一段普通的正文文本 (Paragraph)。微信公众号的图文排版非常看重行距与字体的搭配。合理的行距和字号能够极大地提升用户的阅读体验。

## 核心论点展示（二级标题）

我们往往会在文章中需要强调某些**非常重要的关键词** (Strong)。通过给标粗文本加上独特的主题色，可以吸引视线。

### 三级标题举例

下面是一些常见的列表形态：

* 第一点：坚持原创高质量内容
* 第二点：注重排版与视觉体验
* 第三点：保持稳定的更新频率

> 这里是一段引用文字 (Blockquote)。通常用来引用名人名言，或者展示关键性的金句总结。合理的边距和底色能让它脱颖而出。

欢迎点击 [了解更多详情](https://mp.weixin.qq.com)。
`

export default function StyleConfigPage() {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [currentConfig, setCurrentConfig] = useState<StyleConfig>({})

  // 加载配置
  const fetchConfig = async () => {
    setLoading(true)
    try {
      const data = await getStyleConfig()
      setCurrentConfig(data)
      form.setFieldsValue(data)
    } catch (err: any) {
      message.error(err.message || '加载样式配置失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchConfig()
  }, [])

  // 监听表单数据变化，以便实时更新预览
  const formValues = Form.useWatch([], form)
  
  useEffect(() => {
    if (formValues) {
      setCurrentConfig((prev) => ({ ...prev, ...formValues }))
    }
  }, [formValues])

  const handleSave = async (values: typeof currentConfig) => {
    setSaving(true)
    try {
      await updateStyleConfig(values)
      message.success('保存样式配置成功')
    } catch (err: any) {
      message.error(err.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  // 动态生成内联样式应用后的 HTML 内容
  const previewHtml = useMemo(() => {
    // 1. Markdown 转普通 HTML
    const rawHtml = marked.parse(PREVIEW_MARKDOWN, { breaks: true }) as string
    
    // 2. DOMPurify 过滤防 XSS（虽然仅作本地预览，好习惯）
    const cleanHtml = DOMPurify.sanitize(rawHtml)
    
    // 3. 将 currentConfig 中的 CSS 直接正则替换进 HTML（简易版预览器注入）
    // 注意：这里的正则注入比较粗糙，仅用于前端即时预览展示，后端使用的是稳定的 BeautifulSoup
    let styledHtml = cleanHtml
    
    Object.entries(currentConfig).forEach(([tag, styleStr]) => {
      if (!styleStr) return
      // 为诸如 <h2 id="..."> 或者 <p> 替换添加 style='...'，这需要匹配开口标签
      const regObj = new RegExp(`<${tag}(\\s+[^>]*?)?>`, 'gi')
      styledHtml = styledHtml.replace(regObj, (match, p1) => {
        // 如果原本就有 style（比如某些框架本身带的），我们要追加
        if (p1 && p1.includes('style=')) {
           return match.replace(/style=["'](.*?)["']/, `style="$1 ${styleStr}"`)
        }
        const attributes = p1 || ''
        return `<${tag}${attributes} style="${styleStr}">`
      })
    })

    return styledHtml
  }, [currentConfig])

  // 配置项定义
  const STYLE_FIELDS = [
    { name: 'h1', label: '一级标题 (h1)', tooltip: '用于文章主标题' },
    { name: 'h2', label: '二级标题 (h2)', tooltip: '用于段落小标题' },
    { name: 'h3', label: '三级标题 (h3)', tooltip: '用于次级段落小结' },
    { name: 'p', label: '正文段落 (p)', tooltip: '用于普通正文' },
    { name: 'strong', label: '加粗文本 (strong)', tooltip: '用于 **加粗** 的文字' },
    { name: 'blockquote', label: '引用块 (blockquote)', tooltip: '用于 > 引用内容' },
    { name: 'ul', label: '无序列表 (ul)', tooltip: '<ul> 容器样式' },
    { name: 'li', label: '列表项 (li)', tooltip: '<li> 元素自身样式' },
    { name: 'a', label: '超链接 (a)', tooltip: '用于超链接文字' },
  ]

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" tip="加载样式配置中..." />
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 1200, margin: '24px auto', padding: '0 24px' }}>
      <Row justify="space-between" align="middle" style={{ marginBottom: 24 }}>
        <Col>
          <Title level={2} style={{ margin: 0 }}>公众号排版样式配置</Title>
          <Text type="secondary">配置 Markdown 转换到微信公众号时各元素的内联 CSS (Inline-CSS)。</Text>
        </Col>
        <Col>
          <Button 
            icon={<ReloadOutlined />} 
            onClick={fetchConfig} 
            style={{ marginRight: 16 }}
          >
            重置更改
          </Button>
          <Button 
            type="primary" 
            icon={<SaveOutlined />} 
            onClick={() => form.submit()} 
            loading={saving}
          >
            保存配置
          </Button>
        </Col>
      </Row>

      <Row gutter={24}>
        {/* 左侧配置编辑区 */}
        <Col xs={24} md={12} lg={14}>
          <Card title="CSS 属性配置" variant="borderless">
            <Form
              form={form}
              layout="vertical"
              onFinish={handleSave}
            >
              <Row gutter={16}>
                {STYLE_FIELDS.map((field) => (
                  <Col span={24} key={field.name}>
                    <Form.Item
                      name={field.name}
                      label={field.label}
                      tooltip={field.tooltip}
                    >
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

        {/* 右侧实时预览区 */}
        <Col xs={24} md={12} lg={10}>
          <div style={{ position: 'sticky', top: 24 }}>
            <Card 
              title="实时预览 (模拟手机端)" 
              variant="borderless"
            >
              <div 
                style={{ 
                  width: '100%', 
                  maxWidth: 400, 
                  margin: '0 auto', 
                  border: '1px solid #e8e8e8', 
                  borderRadius: 24, 
                  padding: '40px 20px', 
                  backgroundColor: '#fff',
                  boxShadow: '0 12px 24px rgba(0,0,0,0.05)'
                }}
              >
                {/* 模拟顶栏 */}
                <div style={{ textAlign: 'center', marginBottom: 20, paddingBottom: 10, borderBottom: '1px solid #f0f0f0' }}>
                  <Text strong>公众号文章预览</Text>
                </div>
                
                {/* 预览正文装载区 */}
                <div 
                  className="wx-article-preview" 
                  dangerouslySetInnerHTML={{ __html: previewHtml }}
                  style={{ wordWrap: 'break-word', overflowWrap: 'break-word' }}
                />
              </div>
            </Card>
          </div>
        </Col>
      </Row>
    </div>
  )
}
