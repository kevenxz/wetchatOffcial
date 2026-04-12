import { useEffect, useState } from 'react'
import type { Key } from 'react'
import { Button, Card, Empty, Modal, Select, Space, Table, Tag, Typography, message } from 'antd'
import type { TableProps } from 'antd'
import dayjs from 'dayjs'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import {
  batchPushArticles,
  getCustomThemes,
  getPresetThemes,
  getStyleConfig,
  listAccounts,
  listArticles,
  pushArticle,
  updateArticleTheme,
  type AccountConfig,
  type PushRecord,
  type StyleConfig,
  type TaskResponse,
} from '@/api'
import { HeroPanel } from '@/components/workbench'

const { Paragraph, Text, Title } = Typography
const CURRENT_THEME_KEY = '__current__'
const ARTICLE_LAYOUT_BREAKPOINT = 1100

function mergeStyle(existing: string | null, next: string) {
  if (!existing) return next
  return `${existing}${existing.trim().endsWith(';') ? ' ' : '; '}${next}`
}

function buildPreviewHtml(markdownText: string, config: StyleConfig | undefined) {
  const rawHtml = marked.parse(markdownText || '', { breaks: true }) as string
  const cleanHtml = DOMPurify.sanitize(rawHtml)
  const parser = new DOMParser()
  const doc = parser.parseFromString(`<div class="wx-article-container">${cleanHtml}</div>`, 'text/html')
  const container = doc.body.firstElementChild as HTMLElement | null

  if (!container || !config) return cleanHtml

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

function getPushedAccountNames(pushRecords: PushRecord[] | undefined): string[] {
  const records = pushRecords ?? []
  const names = records
    .filter((item) => item.status === 'success')
    .map((item) => item.account_name)
  return Array.from(new Set(names))
}

export default function ArticleManage() {
  const [articles, setArticles] = useState<TaskResponse[]>([])
  const [accounts, setAccounts] = useState<AccountConfig[]>([])
  const [loading, setLoading] = useState(false)
  const [pushing, setPushing] = useState(false)
  const [selectedArticleKeys, setSelectedArticleKeys] = useState<Key[]>([])
  const [defaultAccountIds, setDefaultAccountIds] = useState<string[]>([])

  const [currentTheme, setCurrentTheme] = useState<StyleConfig>({})
  const [presetThemes, setPresetThemes] = useState<Record<string, StyleConfig>>({})
  const [customThemes, setCustomThemes] = useState<Record<string, StyleConfig>>({})
  const [articleThemes, setArticleThemes] = useState<Record<string, string>>({})

  const [previewArticle, setPreviewArticle] = useState<TaskResponse | null>(null)
  const [pushTargetTaskId, setPushTargetTaskId] = useState<string | null>(null)
  const [pushAccountIds, setPushAccountIds] = useState<string[]>([])
  const [singlePushThemeName, setSinglePushThemeName] = useState<string>(CURRENT_THEME_KEY)
  const [isNarrowLayout, setIsNarrowLayout] = useState(false)

  const wechatAccounts = accounts.filter((item) => item.platform === 'wechat_mp' && item.enabled)

  const accountOptions = wechatAccounts.map((item) => ({
    label: item.name,
    value: item.account_id,
  }))

  const themeOptions = [
    { label: '当前配置', value: CURRENT_THEME_KEY },
    ...Object.keys(presetThemes).map((name) => ({ label: `内置 · ${name}`, value: name })),
    ...Object.keys(customThemes).map((name) => ({ label: `自定义 · ${name}`, value: name })),
  ]

  const themeConfigMap: Record<string, StyleConfig> = {
    [CURRENT_THEME_KEY]: currentTheme,
    ...presetThemes,
    ...customThemes,
  }

  const fetchData = async () => {
    setLoading(true)
    try {
      const [articleList, accountList, currentConfig, preset, custom] = await Promise.all([
        listArticles(),
        listAccounts(),
        getStyleConfig(),
        getPresetThemes(),
        getCustomThemes(),
      ])

      setArticles(articleList)
      setAccounts(accountList)
      setCurrentTheme(currentConfig)
      setPresetThemes(preset)
      setCustomThemes(custom)

      const nextThemes: Record<string, string> = {}
      articleList.forEach((item) => {
        nextThemes[item.task_id] = item.article_theme || CURRENT_THEME_KEY
      })
      setArticleThemes(nextThemes)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '获取文章列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchData()
  }, [])

  useEffect(() => {
    const updateLayoutMode = () => {
      setIsNarrowLayout(window.innerWidth < ARTICLE_LAYOUT_BREAKPOINT)
    }

    updateLayoutMode()
    window.addEventListener('resize', updateLayoutMode)

    return () => {
      window.removeEventListener('resize', updateLayoutMode)
    }
  }, [])

  const openSinglePushModal = (taskId: string) => {
    setPushTargetTaskId(taskId)
    setPushAccountIds(defaultAccountIds)
    setSinglePushThemeName(articleThemes[taskId] || CURRENT_THEME_KEY)
  }

  const handleThemeChange = async (taskId: string, themeName: string) => {
    setArticleThemes((prev) => ({ ...prev, [taskId]: themeName }))
    try {
      const updated = await updateArticleTheme(taskId, themeName)
      setArticles((prev) =>
        prev.map((item) =>
          item.task_id === updated.task_id ? { ...item, article_theme: updated.article_theme } : item,
        ),
      )
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存主题失败')
      setArticleThemes((prev) => ({ ...prev, [taskId]: CURRENT_THEME_KEY }))
    }
  }

  const submitSinglePush = async () => {
    if (!pushTargetTaskId) return

    if (pushAccountIds.length === 0) {
      message.warning('请先选择至少一个公众号')
      return
    }

    setPushing(true)
    try {
      const result = await pushArticle(pushTargetTaskId, pushAccountIds, singlePushThemeName)
      message.success(`推送完成：成功 ${result.success}，失败 ${result.failed}`)
      setPushTargetTaskId(null)
      await fetchData()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '推送失败')
    } finally {
      setPushing(false)
    }
  }

  const submitBatchPush = async () => {
    const taskIds = selectedArticleKeys.map((key) => String(key))

    if (taskIds.length === 0) {
      message.warning('请先勾选要批量推送的文章')
      return
    }

    if (defaultAccountIds.length === 0) {
      message.warning('请先选择目标公众号')
      return
    }

    const taskThemes: Record<string, string> = {}
    taskIds.forEach((taskId) => {
      taskThemes[taskId] = articleThemes[taskId] || CURRENT_THEME_KEY
    })

    setPushing(true)
    try {
      const result = await batchPushArticles(taskIds, defaultAccountIds, taskThemes)
      message.success(`批量推送完成：成功 ${result.success}，失败 ${result.failed}`)
      await fetchData()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '批量推送失败')
    } finally {
      setPushing(false)
    }
  }

  const previewThemeName = previewArticle
    ? articleThemes[previewArticle.task_id] || CURRENT_THEME_KEY
    : CURRENT_THEME_KEY

  const columns: TableProps<TaskResponse>['columns'] = [
    {
      title: '文章标题',
      dataIndex: 'generated_article',
      key: 'title',
      render: (article: TaskResponse['generated_article']) => article?.title ?? '未命名文章',
    },
    {
      title: '关键词',
      dataIndex: 'keywords',
      key: 'keywords',
      width: 220,
      ellipsis: true,
    },
    {
      title: '主题',
      key: 'theme',
      width: 220,
      render: (_, record) => (
        <Select
          style={{ width: '100%' }}
          value={articleThemes[record.task_id] || CURRENT_THEME_KEY}
          options={themeOptions}
          onChange={(value) => handleThemeChange(record.task_id, value)}
        />
      ),
    },
    {
      title: '已推送公众号',
      dataIndex: 'push_records',
      key: 'push_records',
      render: (records: PushRecord[] | undefined) => {
        const names = getPushedAccountNames(records)

        if (names.length === 0) {
          return <Text type="secondary">暂无</Text>
        }

        return (
          <Space size={[4, 8]} wrap>
            {names.map((name) => (
              <Tag color="success" key={name}>
                {name}
              </Tag>
            ))}
          </Space>
        )
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '操作',
      key: 'action',
      width: 190,
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => setPreviewArticle(record)}>
            查看
          </Button>
          <Button size="small" type="primary" onClick={() => openSinglePushModal(record.task_id)}>
            指定推送
          </Button>
        </Space>
      ),
    },
  ]

  const previewTitle = previewArticle?.generated_article?.title ?? '请选择一篇文章查看预览'
  const previewContent = previewArticle ? String(previewArticle.generated_article?.content || '') : ''
  const previewHtml = previewArticle
    ? buildPreviewHtml(previewContent, themeConfigMap[previewThemeName])
    : ''

  return (
    <div className="backstage-page">
      <HeroPanel
        eyebrow="Publishing Assets"
        title="文章库"
        description="在统一资产视图里完成文章筛选、主题配置、预览校对和批量推送。"
      >
        <Space wrap style={{ marginTop: 12, justifyContent: 'space-between', width: '100%' }}>
          <Space wrap>
            <Tag bordered={false} color="blue">
              文章 {articles.length}
            </Tag>
            <Tag bordered={false} color="gold">
              已选 {selectedArticleKeys.length}
            </Tag>
            <Tag bordered={false} color="green">
              公众号 {wechatAccounts.length}
            </Tag>
          </Space>
          <Space wrap>
            <Select
              mode="multiple"
              allowClear
              style={{ width: 360, maxWidth: '100%' }}
              placeholder="选择批量推送目标公众号"
              value={defaultAccountIds}
              onChange={setDefaultAccountIds}
              options={accountOptions}
            />
            <Button type="primary" loading={pushing} onClick={submitBatchPush}>
              批量推送
            </Button>
          </Space>
        </Space>
      </HeroPanel>

      <div
        data-testid="article-manage-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: isNarrowLayout ? 'minmax(0, 1fr)' : 'minmax(0, 1.4fr) minmax(320px, 0.9fr)',
          gap: 16,
          alignItems: 'start',
        }}
      >
        <Card className="backstage-surface-card">
          <Table
            rowKey="task_id"
            loading={loading}
            columns={columns}
            dataSource={articles}
            rowSelection={{
              selectedRowKeys: selectedArticleKeys,
              onChange: setSelectedArticleKeys,
            }}
            pagination={{ pageSize: 10 }}
            size="middle"
          />
        </Card>

        <Card className="backstage-surface-card">
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <div>
              <Title level={3} style={{ marginBottom: 8 }}>
                文章预览
              </Title>
              {previewArticle ? (
                <Space wrap>
                  <Tag color="blue">主题</Tag>
                  <Text>{themeOptions.find((item) => item.value === previewThemeName)?.label || '当前配置'}</Text>
                </Space>
              ) : (
                <Text type="secondary">选择一篇文章查看预览</Text>
              )}
            </div>

            {previewArticle?.generated_article ? (
              <div
                style={{
                  maxHeight: 720,
                  padding: '20px 18px',
                  overflow: 'auto',
                  background: '#fff',
                  border: '1px solid #e5e7eb',
                  boxShadow: '0 12px 30px rgba(15, 23, 42, 0.08)',
                }}
              >
                <Title level={4} style={{ marginTop: 0 }}>
                  {previewTitle}
                </Title>
                <div dangerouslySetInnerHTML={{ __html: previewHtml }} />
              </div>
            ) : (
              <Empty description="选择一篇文章查看预览" />
            )}
          </Space>
        </Card>
      </div>

      <Modal
        open={Boolean(pushTargetTaskId)}
        onCancel={() => setPushTargetTaskId(null)}
        title="指定公众号推送"
        onOk={submitSinglePush}
        confirmLoading={pushing}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Select
            mode="multiple"
            allowClear
            style={{ width: '100%' }}
            placeholder="选择目标公众号"
            value={pushAccountIds}
            onChange={setPushAccountIds}
            options={accountOptions}
          />
          <Select
            style={{ width: '100%' }}
            value={singlePushThemeName}
            onChange={setSinglePushThemeName}
            options={themeOptions}
            placeholder="选择推送主题"
          />
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            推送时将使用所选主题把 Markdown 渲染成微信样式 HTML。
          </Paragraph>
        </Space>
      </Modal>
    </div>
  )
}
