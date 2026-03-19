import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Button,
  Card,
  Col,
  Divider,
  Input,
  Menu,
  Modal,
  Popconfirm,
  Row,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd'
import {
  BgColorsOutlined,
  DeleteOutlined,
  EditOutlined,
  ImportOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

import {
  createCustomTheme,
  deleteCustomTheme,
  getCustomThemes,
  getPresetThemes,
  getStyleConfig,
  importCustomThemes,
  updateCustomTheme,
  updateStyleConfig,
  type CustomThemes,
  type PresetThemes,
  type StyleConfig,
} from '@/api'

const { Title, Text } = Typography
const { TextArea } = Input

const CURRENT_THEME_KEY = '__current__'
const EMPTY_THEME_NAME = '未命名主题'

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
  'container',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'p',
  'strong',
  'em',
  'del',
  'blockquote',
  'ul',
  'ol',
  'li',
  'a',
  'hr',
  'img',
  'figure',
  'figcaption',
  'code',
  'pre',
  'pre code',
  'table',
  'th',
  'td',
] as const

type ThemeSource = 'current' | 'preset' | 'custom'
type EditorMode = 'browse' | 'create' | 'edit'

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

function toCssText(config: StyleConfig) {
  return STYLE_FIELDS.map((name) => {
    const body = (config[name] || '')
      .split(';')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => `  ${line};`)
      .join('\n')
    return `${name === 'container' ? '.wx-article-container' : name} {\n${body}\n}`
  }).join('\n\n')
}

function fromCssText(cssText: string, fallback: StyleConfig) {
  const nextConfig = { ...fallback }
  const blocks = cssText.match(/([^{}]+)\{([^{}]*)\}/g) || []

  STYLE_FIELDS.forEach((field) => {
    if (!(field in nextConfig)) {
      nextConfig[field] = ''
    }
  })

  blocks.forEach((block) => {
    const matched = block.match(/([^{}]+)\{([^{}]*)\}/)
    if (!matched) return

    const rawSelector = matched[1].trim()
    const selector = rawSelector === '.wx-article-container' ? 'container' : rawSelector
    if (!STYLE_FIELDS.includes(selector as (typeof STYLE_FIELDS)[number])) return

    nextConfig[selector] = matched[2]
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .join(' ')
      .trim()
  })

  return nextConfig
}

function normalizeThemeConfig(config: StyleConfig) {
  const normalized: StyleConfig = {}
  STYLE_FIELDS.forEach((field) => {
    normalized[field] = config[field] || ''
  })
  return normalized
}

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export default function StyleConfigPage() {
  const importRef = useRef<HTMLInputElement | null>(null)

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [themeSaving, setThemeSaving] = useState(false)
  const [currentConfig, setCurrentConfig] = useState<StyleConfig>({})
  const [presetThemes, setPresetThemes] = useState<PresetThemes>({})
  const [customThemes, setCustomThemes] = useState<CustomThemes>({})
  const [activeThemeName, setActiveThemeName] = useState('当前主题')
  const [previewMarkdown, setPreviewMarkdown] = useState(DEFAULT_PREVIEW_MARKDOWN)
  const [themeManagerOpen, setThemeManagerOpen] = useState(false)
  const [themeCssText, setThemeCssText] = useState('')
  const [editorMode, setEditorMode] = useState<EditorMode>('browse')
  const [draftThemeName, setDraftThemeName] = useState(EMPTY_THEME_NAME)
  const [themeDraftConfig, setThemeDraftConfig] = useState<StyleConfig>({})
  const [selectedThemeKey, setSelectedThemeKey] = useState(CURRENT_THEME_KEY)
  const [selectedThemeSource, setSelectedThemeSource] = useState<ThemeSource>('current')

  const fetchData = async () => {
    setLoading(true)
    try {
      const [configData, presetData, customData] = await Promise.all([
        getStyleConfig(),
        getPresetThemes(),
        getCustomThemes(),
      ])
      const normalized = normalizeThemeConfig(configData)
      setCurrentConfig(normalized)
      setPresetThemes(presetData)
      setCustomThemes(customData)
      setDraftThemeName('当前主题')
      setThemeDraftConfig(normalized)
      setThemeCssText(toCssText(normalized))
      setSelectedThemeKey(CURRENT_THEME_KEY)
      setSelectedThemeSource('current')
      setEditorMode('browse')
    } catch (err: any) {
      message.error(err.message || '加载样式配置失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  const pagePreviewHtml = useMemo(
    () => buildPreviewHtml(previewMarkdown, currentConfig),
    [previewMarkdown, currentConfig],
  )

  const draftPreviewHtml = useMemo(
    () => buildPreviewHtml(previewMarkdown, themeDraftConfig),
    [previewMarkdown, themeDraftConfig],
  )

  const openThemeManager = () => {
    const normalized = normalizeThemeConfig(currentConfig)
    setThemeDraftConfig(normalized)
    setThemeCssText(toCssText(normalized))
    setDraftThemeName(activeThemeName)
    setSelectedThemeKey(CURRENT_THEME_KEY)
    setSelectedThemeSource('current')
    setEditorMode('browse')
    setThemeManagerOpen(true)
  }

  const loadThemeToEditor = (name: string, config: StyleConfig, source: ThemeSource) => {
    const normalized = normalizeThemeConfig(config)
    setDraftThemeName(name)
    setThemeDraftConfig(normalized)
    setThemeCssText(toCssText(normalized))
    setSelectedThemeKey(source === 'current' ? CURRENT_THEME_KEY : name)
    setSelectedThemeSource(source)
    setEditorMode(source === 'custom' ? 'edit' : 'browse')
  }

  const handleThemeSelect = (key: string) => {
    if (key === CURRENT_THEME_KEY) {
      loadThemeToEditor('当前主题', currentConfig, 'current')
      return
    }
    if (customThemes[key]) {
      loadThemeToEditor(key, customThemes[key], 'custom')
      return
    }
    if (presetThemes[key]) {
      loadThemeToEditor(key, presetThemes[key], 'preset')
    }
  }

  const handleCreateTheme = () => {
    const base = normalizeThemeConfig(currentConfig)
    setDraftThemeName('新建主题')
    setThemeDraftConfig(base)
    setThemeCssText(toCssText(base))
    setSelectedThemeKey('__new__')
    setSelectedThemeSource('custom')
    setEditorMode('create')
  }

  const handleCssChange = (value: string) => {
    setThemeCssText(value)
    setThemeDraftConfig(fromCssText(value, themeDraftConfig))
  }

  const handleApplyTheme = () => {
    setCurrentConfig(normalizeThemeConfig(themeDraftConfig))
    setActiveThemeName(draftThemeName || '当前主题')
    setThemeManagerOpen(false)
    message.success('主题已应用到当前预览')
  }

  const handleSaveConfig = async () => {
    setSaving(true)
    try {
      await updateStyleConfig(currentConfig)
      message.success('系统配置已保存')
    } catch (err: any) {
      message.error(err.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleSaveTheme = async () => {
    const name = draftThemeName.trim()
    if (!name) {
      message.warning('请输入主题名称')
      return
    }

    setThemeSaving(true)
    try {
      let themes: CustomThemes
      if (editorMode === 'edit' && selectedThemeSource === 'custom' && customThemes[selectedThemeKey]) {
        themes = await updateCustomTheme(selectedThemeKey, name, themeDraftConfig)
      } else {
        themes = await createCustomTheme(name, themeDraftConfig)
      }
      setCustomThemes(themes)
      setSelectedThemeKey(name)
      setSelectedThemeSource('custom')
      setEditorMode('edit')
      message.success('主题已保存')
    } catch (err: any) {
      message.error(err.message || '保存主题失败')
    } finally {
      setThemeSaving(false)
    }
  }

  const handleDeleteTheme = async () => {
    if (!customThemes[selectedThemeKey]) return
    try {
      const nextThemes = await deleteCustomTheme(selectedThemeKey)
      setCustomThemes(nextThemes)
      loadThemeToEditor('当前主题', currentConfig, 'current')
      message.success('主题已删除')
    } catch (err: any) {
      message.error(err.message || '删除主题失败')
    }
  }

  const handleImportThemes = async (file: File) => {
    try {
      const text = await file.text()
      const payload = JSON.parse(text) as CustomThemes
      const nextThemes = await importCustomThemes(payload)
      setCustomThemes(nextThemes)
      message.success(`已导入 ${Object.keys(payload).length} 个主题`)
    } catch (err: any) {
      message.error(err.message || '导入主题失败，请检查 JSON 格式')
    }
  }

  const selectedThemeTag = selectedThemeSource === 'preset'
    ? '内置主题'
    : selectedThemeSource === 'custom'
      ? '自定义主题'
      : '当前配置'

  const themeMenuItems = [
    {
      key: 'group-current',
      type: 'group' as const,
      label: '当前配置',
      children: [{ key: CURRENT_THEME_KEY, icon: <EditOutlined />, label: '当前主题' }],
    },
    {
      key: 'group-preset',
      type: 'group' as const,
      label: '内置主题',
      children: Object.keys(presetThemes).map((name) => ({
        key: name,
        icon: <BgColorsOutlined />,
        label: name,
      })),
    },
    {
      key: 'group-custom',
      type: 'group' as const,
      label: '自定义主题',
      children: Object.keys(customThemes).map((name) => ({
        key: name,
        icon: <SaveOutlined />,
        label: name,
      })),
    },
  ]

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" tip="加载样式配置中..." />
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 1680, margin: '24px auto', padding: '0 24px' }}>
      <Row justify="space-between" align="middle" style={{ marginBottom: 20 }}>
        <Col>
          <Title level={2} style={{ margin: 0 }}>系统配置</Title>
          <Text type="secondary">默认展示 Markdown 文本和实时效果，样式编辑通过顶部主题管理进入。</Text>
        </Col>
        <Col>
          <Space size={12}>
            <Button icon={<ReloadOutlined />} onClick={fetchData}>重新加载</Button>
            <Button icon={<BgColorsOutlined />} onClick={openThemeManager}>主题管理</Button>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSaveConfig}>保存配置</Button>
          </Space>
        </Col>
      </Row>

      <Row gutter={24}>
        <Col xs={24} lg={14}>
          <Card
            title={(
              <Space size={8}>
                <span style={{ width: 8, height: 8, borderRadius: 999, background: '#22c55e', display: 'inline-block' }} />
                <span>MARKDOWN 编辑器</span>
              </Space>
            )}
            styles={{ body: { padding: 0 } }}
          >
            <div style={{ borderBottom: '1px solid #f0f0f0', padding: '10px 16px', color: '#64748b', fontSize: 13 }}>
              当前主题：{activeThemeName}
            </div>
            <TextArea
              value={previewMarkdown}
              onChange={(e) => setPreviewMarkdown(e.target.value)}
              autoSize={{ minRows: 28, maxRows: 28 }}
              bordered={false}
              style={{ padding: 20, fontFamily: 'Consolas, Monaco, monospace', fontSize: 14, lineHeight: 1.8 }}
            />
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card
            title={(
              <Space size={8}>
                <span>实时预览</span>
                <Text type="secondary">微信公众号效果</Text>
              </Space>
            )}
            styles={{ body: { background: '#f8fafc', minHeight: 780 } }}
          >
            <div
              style={{
                maxWidth: 414,
                minHeight: 720,
                margin: '0 auto',
                padding: '24px 20px',
                background: '#fff',
                border: '1px solid #e5e7eb',
                boxShadow: '0 12px 30px rgba(15, 23, 42, 0.08)',
                overflow: 'auto',
              }}
            >
              <div dangerouslySetInnerHTML={{ __html: pagePreviewHtml }} style={{ wordWrap: 'break-word', overflowWrap: 'break-word' }} />
            </div>
          </Card>
        </Col>
      </Row>

      <input
        ref={importRef}
        type="file"
        accept="application/json"
        style={{ display: 'none' }}
        onChange={async (event) => {
          const file = event.target.files?.[0]
          if (file) {
            await handleImportThemes(file)
          }
          event.target.value = ''
        }}
      />

      <Modal
        title="主题管理"
        open={themeManagerOpen}
        onCancel={() => setThemeManagerOpen(false)}
        width={1440}
        footer={(
          <Space>
            <Button onClick={() => setThemeManagerOpen(false)}>取消</Button>
            <Button onClick={() => downloadJson('themes-export.json', customThemes)}>导出主题</Button>
            <Button type="primary" onClick={handleApplyTheme}>应用主题</Button>
          </Space>
        )}
        styles={{ body: { padding: 0 } }}
      >
        <div style={{ height: '72vh', minHeight: 620, maxHeight: 760, display: 'flex', overflow: 'hidden' }}>
          <div
            style={{
              width: 260,
              flexShrink: 0,
              borderRight: '1px solid #f0f0f0',
              background: '#fafafa',
              padding: 18,
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
              overflow: 'hidden',
            }}
          >
            <Button type="primary" icon={<PlusOutlined />} size="large" block onClick={handleCreateTheme}>
              新建自定义主题
            </Button>
            <Button icon={<ImportOutlined />} size="large" block onClick={() => importRef.current?.click()}>
              导入主题
            </Button>
            <div style={{ minHeight: 0, overflow: 'auto', paddingRight: 4 }}>
              <Menu
                mode="inline"
                selectedKeys={[selectedThemeKey]}
                onSelect={({ key }) => handleThemeSelect(String(key))}
                items={themeMenuItems}
                style={{ borderInlineEnd: 'none', background: 'transparent' }}
              />
            </div>
          </div>

          <div
            style={{
              flex: 1,
              minWidth: 0,
              borderRight: '1px solid #f0f0f0',
              background: '#f8fafc',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <div style={{ padding: '14px 18px', borderBottom: '1px solid #f0f0f0', background: '#fff' }}>
              <Space size={10}>
                <Text strong>实时预览</Text>
                <Tag color={selectedThemeSource === 'preset' ? 'blue' : selectedThemeSource === 'custom' ? 'green' : 'default'}>
                  {selectedThemeTag}
                </Tag>
              </Space>
            </div>
            <div style={{ padding: 24, overflow: 'auto', minHeight: 0 }}>
              <div
                style={{
                  maxWidth: 414,
                  minHeight: 560,
                  margin: '0 auto',
                  padding: '24px 20px',
                  background: '#fff',
                  border: '1px solid #e5e7eb',
                  boxShadow: '0 12px 30px rgba(15, 23, 42, 0.08)',
                }}
              >
                <div dangerouslySetInnerHTML={{ __html: draftPreviewHtml }} style={{ wordWrap: 'break-word', overflowWrap: 'break-word' }} />
              </div>
            </div>
          </div>

          <div
            style={{
              width: 440,
              flexShrink: 0,
              padding: 20,
              display: 'flex',
              flexDirection: 'column',
              minHeight: 0,
              overflow: 'hidden',
            }}
          >
            <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
              <Space size={10}>
                <Text strong style={{ fontSize: 16 }}>主题编辑</Text>
                <Tag>{editorMode === 'create' ? '新建' : editorMode === 'edit' ? '编辑' : '浏览'}</Tag>
              </Space>
              <Space size={8}>
                {selectedThemeSource === 'custom' && editorMode !== 'create' && (
                  <Button size="small" onClick={() => setEditorMode('edit')}>编辑</Button>
                )}
                {selectedThemeSource === 'custom' && (
                  <Popconfirm title="确定删除这个自定义主题吗？" onConfirm={handleDeleteTheme}>
                    <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
                  </Popconfirm>
                )}
              </Space>
            </Space>

            <Divider style={{ margin: '16px 0' }} />

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minHeight: 0, overflow: 'hidden' }}>
              <div>
                <Text strong>主题名称</Text>
                <Input
                  value={draftThemeName}
                  onChange={(e) => setDraftThemeName(e.target.value)}
                  disabled={selectedThemeSource === 'preset' && editorMode === 'browse'}
                  style={{ marginTop: 8 }}
                />
              </div>

              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Button size="small" onClick={() => navigator.clipboard.writeText(themeCssText).then(() => message.success('CSS 已复制'))}>
                  复制 CSS
                </Button>
                <Button size="small" onClick={() => downloadJson(`${draftThemeName || 'theme'}.json`, { [draftThemeName || 'theme']: themeDraftConfig })}>
                  导出当前主题
                </Button>
                {selectedThemeSource !== 'preset' && (
                  <Button size="small" type="primary" loading={themeSaving} onClick={handleSaveTheme}>
                    {editorMode === 'edit' ? '更新主题' : '保存为新主题'}
                  </Button>
                )}
              </div>

              <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
                <Text strong>CSS 样式</Text>
                <TextArea
                  value={themeCssText}
                  onChange={(e) => handleCssChange(e.target.value)}
                  disabled={selectedThemeSource === 'preset' && editorMode === 'browse'}
                  style={{
                    marginTop: 8,
                    height: '100%',
                    minHeight: 420,
                    resize: 'none',
                    fontFamily: 'Consolas, Monaco, monospace',
                    fontSize: 13,
                    lineHeight: 1.7,
                  }}
                />
              </div>

              <div
                style={{
                  padding: '12px 14px',
                  borderRadius: 12,
                  background: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  color: '#475569',
                  fontSize: 13,
                }}
              >
                内置主题默认只读。要修改它，请点击“新建自定义主题”或先应用后另存为自定义主题。
              </div>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  )
}
