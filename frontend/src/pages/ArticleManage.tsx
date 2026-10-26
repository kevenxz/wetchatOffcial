import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Form, Input, Modal, Popconfirm, Select, Space, Switch, Tag, Tooltip, message } from 'antd'
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  FileTextOutlined,
  PlusOutlined,
  SendOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import {
  deleteTask,
  getCustomThemes,
  getPresetThemes,
  getStyleConfig,
  listAccounts,
  listArticles,
  pushArticle,
  updateArticleContent,
  type AccountConfig,
  type PublishStatus,
  type StyleConfig,
  type TaskResponse,
} from '@/api'
import { EmptyState, TruncatedText } from '@/components/layout'
import styles from './ArticleManage.module.css'

const CURRENT_THEME_KEY = '__current__'

type ArticleFilter = 'all' | 'published' | 'review' | 'draft'

const filterOptions: Array<{ label: string; value: ArticleFilter }> = [
  { label: '全部', value: 'all' },
  { label: '已发布', value: 'published' },
  { label: '审核中', value: 'review' },
  { label: '草稿', value: 'draft' },
]

const PUBLISH_STATUS_LABELS: Record<PublishStatus, string> = {
  draft_only: '仅草稿',
  publishing: '发布中',
  published: '已发布',
  publish_failed: '发布失败',
  failed: '推送失败',
}

const PUBLISH_STATUS_COLORS: Record<PublishStatus, string> = {
  draft_only: 'default',
  publishing: 'processing',
  published: 'success',
  publish_failed: 'error',
  failed: 'error',
}

interface EditingIllustration {
  key: string
  value: string
}

interface EditingArticleState {
  title: string
  summary: string
  content: string
  coverImage: string
  illustrations: EditingIllustration[]
}

const EMPTY_EDITING_ARTICLE: EditingArticleState = {
  title: '',
  summary: '',
  content: '',
  coverImage: '',
  illustrations: [],
}

const illustrationKey = (() => {
  let seed = 0
  return () => {
    seed += 1
    return `illustration-${seed}`
  }
})()

const categoryColors: Record<string, string> = {
  AI: 'purple',
  科技: 'blue',
  财经: 'green',
  汽车: 'orange',
  国际: 'cyan',
  军事: 'red',
}

function mergeStyle(existing: string | null, next: string) {
  if (!existing) return next
  return `${existing}${existing.trim().endsWith(';') ? ' ' : '; '}${next}`
}

function normalizeImageSrc(value: string | undefined) {
  if (!value) return ''
  if (/^https?:\/\//i.test(value) || value.startsWith('/')) return value
  const normalized = value.replace(/\\/g, '/')
  const marker = '/artifacts/'
  const index = normalized.indexOf(marker)
  if (index >= 0) return normalized.slice(index)
  if (value.startsWith('generated://')) return ''
  return value
}

function injectIllustrations(markdownText: string, illustrations: string[] | undefined) {
  return String(markdownText || '').replace(/\[插图(\d+)\]/g, (_, rawIndex: string) => {
    const index = Number(rawIndex) - 1
    const src = normalizeImageSrc(illustrations?.[index])
    if (!src) return `[插图${rawIndex}]`
    return `<figure class="wx-illustration-container"><img src="${src}" alt="文章插图${rawIndex}" /></figure>`
  })
}

function normalizeHtmlImages(html: string) {
  const parser = new DOMParser()
  const doc = parser.parseFromString(html, 'text/html')
  doc.querySelectorAll('img').forEach((image) => {
    const src = normalizeImageSrc(image.getAttribute('src') || '')
    if (src) image.setAttribute('src', src)
  })
  return doc.body.innerHTML
}

function buildPreviewHtml(markdownText: string, config: StyleConfig | undefined, illustrations?: string[], htmlContent?: string) {
  const rawHtml = htmlContent
    ? normalizeHtmlImages(DOMPurify.sanitize(htmlContent))
    : marked.parse(injectIllustrations(markdownText, illustrations), { breaks: true }) as string
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

function collectImageRefs(article: Record<string, any> | undefined) {
  if (!article) return []
  const refs: Array<{ role: string; src: string }> = []
  const seen = new Set<string>()
  const pushRef = (role: string, rawSrc: string | undefined) => {
    const src = normalizeImageSrc(rawSrc)
    if (!src || seen.has(src)) return
    seen.add(src)
    refs.push({ role, src })
  }
  pushRef('封面', article.cover_image)
  ;(article.illustrations || []).forEach((item: string, index: number) => pushRef(`插图${index + 1}`, item))
  ;[...(article.images || []), ...(article.visual_assets || [])].forEach((asset: string | Record<string, any>, index: number) => {
    if (typeof asset === 'string') {
      pushRef(`图片${index + 1}`, asset)
      return
    }
    pushRef(String(asset.role || `图片${index + 1}`), String(asset.url || asset.path || asset.src || asset.ref || ''))
  })
  return refs
}

function articleBody(task: TaskResponse) {
  return (task.final_article || task.generated_article || {}) as Record<string, any>
}

function textValue(value: unknown, fallback = '') {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback
}

function getArticleTitle(task: TaskResponse) {
  return textValue(articleBody(task).title, task.keywords || '未命名文章')
}

function getArticleSummary(task: TaskResponse) {
  const article = articleBody(task)
  const summary = textValue(article.summary) || textValue(article.description)
  if (summary) return summary
  return String(article.content || '').replace(/[#>*_`[\]()]/g, '').replace(/\s+/g, ' ').trim().slice(0, 72)
}

function getArticleCategory(task: TaskResponse) {
  const topic = task.selected_topic ?? {}
  const category =
    textValue(topic.category) ||
    textValue(topic.metadata?.category) ||
    textValue(task.selected_hotspot?.category) ||
    task.generation_config.account_profile?.fit_tags?.[0] ||
    '科技'
  return category
}

function getTemplateName(task: TaskResponse) {
  const template = task.generation_config.content_template?.name
  if (template && template !== '自动选择') return template
  const strategy = task.generation_config.article_strategy
  if (strategy === 'tech_breakdown') return '热点解读型'
  if (strategy === 'application_review') return '产品评测型'
  if (strategy === 'trend_outlook') return '趋势分析型'
  return '热点解读型'
}

function getArticleStatus(task: TaskResponse): ArticleFilter {
  if ((task.push_records ?? []).some((record) => record.status === 'success')) return 'published'
  if (task.human_review_required || task.status === 'running') return 'review'
  return 'draft'
}

function statusLabel(status: ArticleFilter) {
  if (status === 'published') return { label: '已发布', color: 'success' }
  if (status === 'review') return { label: '审核中', color: 'warning' }
  return { label: '草稿', color: 'processing' }
}

/**
 * The latest push record wins: it reflects the current state of the article on
 * the publishing channel. Records without a `publish_status` fall back to the
 * legacy `status` field.
 */
function latestPublishStatus(task: TaskResponse): PublishStatus | null {
  const records = task.push_records ?? []
  if (!records.length) return null
  const latest = [...records].sort(
    (left, right) => new Date(right.pushed_at).getTime() - new Date(left.pushed_at).getTime(),
  )[0]
  if (latest.publish_status) return latest.publish_status
  return latest.status === 'success' ? 'draft_only' : 'failed'
}

function reviewText(task: TaskResponse) {
  if (task.status === 'failed') return { label: '审核：被拒', className: styles.reviewRejected }
  if (task.human_review_required || task.status === 'running') return { label: '审核：待审核', className: styles.reviewPending }
  return { label: '审核：已通过', className: styles.reviewPassed }
}

function countWords(task: TaskResponse) {
  const content = String(articleBody(task).content || '')
  const compact = content.replace(/\s+/g, '')
  return compact.length || Number(articleBody(task).word_count || 0)
}

function displayId(index: number) {
  return `A-${String(1024 - index)}`
}

export default function ArticleManage() {
  const [articles, setArticles] = useState<TaskResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [filter, setFilter] = useState<ArticleFilter>('all')
  const [publishFilter, setPublishFilter] = useState<PublishStatus | 'all'>('all')
  const [category, setCategory] = useState('all')
  const [currentTheme, setCurrentTheme] = useState<StyleConfig>({})
  const [presetThemes, setPresetThemes] = useState<Record<string, StyleConfig>>({})
  const [customThemes, setCustomThemes] = useState<Record<string, StyleConfig>>({})
  const [previewArticle, setPreviewArticle] = useState<TaskResponse | null>(null)
  const [accounts, setAccounts] = useState<AccountConfig[]>([])
  const [pushArticleTask, setPushArticleTask] = useState<TaskResponse | null>(null)
  const [pushAccountIds, setPushAccountIds] = useState<string[]>([])
  const [pushAutoPublish, setPushAutoPublish] = useState(false)
  const [pushing, setPushing] = useState(false)
  const [editingArticle, setEditingArticle] = useState<TaskResponse | null>(null)
  const [editingValues, setEditingValues] = useState<EditingArticleState>(EMPTY_EDITING_ARTICLE)
  const [savingContent, setSavingContent] = useState(false)
  const [editForm] = Form.useForm<{ title: string; summary: string; content: string; coverImage: string }>()

  const themeConfigMap: Record<string, StyleConfig> = {
    [CURRENT_THEME_KEY]: currentTheme,
    ...presetThemes,
    ...customThemes,
  }

  const fetchData = async () => {
    setLoading(true)
    try {
      const [articleList, currentConfig, preset, custom, accountList] = await Promise.all([
        listArticles(),
        getStyleConfig(),
        getPresetThemes(),
        getCustomThemes(),
        listAccounts(),
      ])

      setArticles(articleList)
      setAccounts(accountList)
      setCurrentTheme(currentConfig)
      setPresetThemes(preset)
      setCustomThemes(custom)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '获取文章列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchData()
  }, [])

  const categories = useMemo(() => {
    return Array.from(new Set(articles.map(getArticleCategory))).map((item) => ({ label: item, value: item }))
  }, [articles])

  const filteredArticles = useMemo(() => {
    const lowerKeyword = keyword.toLowerCase()
    return articles.filter((item) => {
      const status = getArticleStatus(item)
      const articleCategory = getArticleCategory(item)
      const publishStatus = latestPublishStatus(item)
      const text = `${getArticleTitle(item)} ${getArticleSummary(item)} ${item.keywords} ${articleCategory}`.toLowerCase()
      return (
        (filter === 'all' || status === filter) &&
        (publishFilter === 'all' || publishStatus === publishFilter) &&
        (category === 'all' || articleCategory === category) &&
        (!keyword || text.includes(lowerKeyword))
      )
    })
  }, [articles, category, filter, keyword, publishFilter])

  const handleDelete = async (taskId: string) => {
    try {
      await deleteTask(taskId)
      message.success('已删除文章')
      await fetchData()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除文章失败')
    }
  }

  const wechatAccountOptions = accounts
    .filter((item) => item.platform === 'wechat_mp' && item.enabled)
    .map((item) => ({ label: item.name, value: item.account_id }))

  const openPushModal = (article: TaskResponse) => {
    setPushArticleTask(article)
    setPushAccountIds(wechatAccountOptions.length === 1 ? [wechatAccountOptions[0].value] : [])
    // Publishing is irreversible, so the switch always starts in the safe state.
    setPushAutoPublish(false)
  }

  const closePushModal = () => {
    setPushArticleTask(null)
    setPushAccountIds([])
    setPushAutoPublish(false)
  }

  const submitPush = async () => {
    if (!pushArticleTask) return

    if (pushAccountIds.length === 0) {
      message.warning('请先选择微信公众号')
      return
    }

    setPushing(true)
    try {
      const result = await pushArticle(
        pushArticleTask.task_id,
        pushAccountIds,
        pushArticleTask.article_theme || CURRENT_THEME_KEY,
        pushAutoPublish,
      )
      message.success(
        pushAutoPublish
          ? `已提交发布：成功 ${result.success}，失败 ${result.failed}`
          : `已推送到草稿箱：成功 ${result.success}，失败 ${result.failed}`,
      )
      closePushModal()
      await fetchData()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '推送到微信公众号草稿箱失败')
    } finally {
      setPushing(false)
    }
  }

  const openEditModal = (article: TaskResponse) => {
    const body = articleBody(article)
    const illustrations = Array.isArray(body.illustrations) ? (body.illustrations as unknown[]) : []
    setEditingArticle(article)
    setEditingValues({
      title: textValue(body.title),
      summary: textValue(body.summary) || textValue(body.description),
      content: String(body.content || ''),
      coverImage: String(body.cover_image || ''),
      illustrations: illustrations.map((item) => ({
        key: illustrationKey(),
        value: typeof item === 'string' ? item : String((item as Record<string, unknown>)?.url || ''),
      })),
    })
  }

  const closeEditModal = () => {
    setEditingArticle(null)
    setEditingValues(EMPTY_EDITING_ARTICLE)
    editForm.resetFields()
  }

  const updateIllustration = (key: string, value: string) => {
    setEditingValues((prev) => ({
      ...prev,
      illustrations: prev.illustrations.map((item) => (item.key === key ? { ...item, value } : item)),
    }))
  }

  const removeIllustration = (key: string) => {
    setEditingValues((prev) => ({
      ...prev,
      illustrations: prev.illustrations.filter((item) => item.key !== key),
    }))
  }

  const moveIllustration = (index: number, offset: number) => {
    setEditingValues((prev) => {
      const target = index + offset
      if (target < 0 || target >= prev.illustrations.length) return prev
      const next = [...prev.illustrations]
      const [moved] = next.splice(index, 1)
      next.splice(target, 0, moved)
      return { ...prev, illustrations: next }
    })
  }

  const addIllustration = () => {
    setEditingValues((prev) => ({
      ...prev,
      illustrations: [...prev.illustrations, { key: illustrationKey(), value: '' }],
    }))
  }

  const submitEdit = async () => {
    if (!editingArticle) return
    let values: { title: string; summary: string; content: string; coverImage: string }
    try {
      values = await editForm.validateFields()
    } catch {
      return
    }

    setSavingContent(true)
    try {
      // 表单字段可能是 undefined（未填写 / 未注册），统一强制转字符串再 trim。
      await updateArticleContent(editingArticle.task_id, {
        title: String(values.title ?? '').trim(),
        summary: String(values.summary ?? '').trim(),
        content: String(values.content ?? ''),
        cover_image: String(values.coverImage ?? '').trim(),
        illustrations: editingValues.illustrations
          .map((item) => String(item.value ?? '').trim())
          .filter((item) => item.length > 0),
      })
      message.success('文章内容已保存')
      closeEditModal()
      await fetchData()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存文章内容失败')
    } finally {
      setSavingContent(false)
    }
  }

  const previewGeneratedArticle = previewArticle ? articleBody(previewArticle) : undefined
  const previewTitle = previewArticle ? getArticleTitle(previewArticle) : '文章预览'
  const previewContent = previewArticle ? String(previewGeneratedArticle?.content || '') : ''
  const previewCoverImage = normalizeImageSrc(String(previewGeneratedArticle?.cover_image || ''))
  const previewImageRefs = collectImageRefs(previewGeneratedArticle)
  const previewHtmlContent = String(previewGeneratedArticle?.html_content || '')
  const previewHtmlHasImages = /<img\s/i.test(previewHtmlContent)
  const previewHtml = previewArticle
    ? buildPreviewHtml(
        previewContent,
        themeConfigMap[previewArticle.article_theme || CURRENT_THEME_KEY],
        previewGeneratedArticle?.illustrations as string[] | undefined,
        previewHtmlHasImages ? previewHtmlContent : '',
      )
    : ''

  return (
    <div className={styles.page}>
      <div className={styles.toolbar}>
        <Input
          size="large"
          prefix={<SearchOutlined />}
          placeholder="搜索文章..."
          allowClear
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
        />
        <div className={styles.filters}>
          {filterOptions.map((item) => (
            <Button
              key={item.value}
              className={`${styles.filterButton} ${filter === item.value ? styles.filterButtonActive : ''}`.trim()}
              onClick={() => setFilter(item.value)}
            >
              {item.label}
            </Button>
          ))}
          <Select
            size="large"
            value={category}
            className={styles.categorySelect}
            options={[{ label: '全部分类', value: 'all' }, ...categories]}
            onChange={setCategory}
          />
          <Select
            size="large"
            aria-label="发布状态筛选"
            value={publishFilter}
            className={styles.publishSelect}
            options={[
              { label: '全部发布状态', value: 'all' },
              ...(Object.keys(PUBLISH_STATUS_LABELS) as PublishStatus[]).map((status) => ({
                label: PUBLISH_STATUS_LABELS[status],
                value: status,
              })),
            ]}
            onChange={setPublishFilter}
          />
        </div>
      </div>

      <div className={styles.articleList} aria-busy={loading}>
        {filteredArticles.length === 0 && !loading ? (
          <div className={styles.emptyPad}>
            <EmptyState title="暂无文章" description="生成并完成审核后，文章会出现在这里。" />
          </div>
        ) : (
          filteredArticles.map((article, index) => {
            const categoryName = getArticleCategory(article)
            const status = statusLabel(getArticleStatus(article))
            const publishStatus = latestPublishStatus(article)
            const review = reviewText(article)
            const imageCount = collectImageRefs(articleBody(article)).length

            return (
              <article className={styles.articleCard} key={article.task_id}>
                <div className={styles.articleInfo}>
                  <div className={styles.metaTop}>
                    <span>{displayId(index)}</span>
                    <Tag color={categoryColors[categoryName] ?? 'blue'}>{categoryName}</Tag>
                    <span>{getTemplateName(article)}</span>
                    {publishStatus ? (
                      <Tag color={PUBLISH_STATUS_COLORS[publishStatus]}>
                        {PUBLISH_STATUS_LABELS[publishStatus]}
                      </Tag>
                    ) : null}
                  </div>
                  <TruncatedText as="h2" lines={1}>{getArticleTitle(article)}</TruncatedText>
                  <TruncatedText as="p" lines={2}>{getArticleSummary(article)}</TruncatedText>
                  <div className={styles.metaBottom}>
                    <span>{countWords(article)} 字</span>
                    <span>{imageCount || 0} 张图</span>
                    <span>{dayjs(article.created_at).format('YYYY-MM-DD HH:mm')}</span>
                    <span className={review.className}>{review.label}</span>
                  </div>
                </div>
                <div className={styles.articleActions}>
                  <Tag className={styles.statusTag} color={status.color} icon={<FileTextOutlined />}>
                    {status.label}
                  </Tag>
                  <div>
                    <Tooltip title="预览">
                      <Button
                        type="text"
                        icon={<EyeOutlined />}
                        aria-label="预览文章"
                        onClick={() => setPreviewArticle(article)}
                      />
                    </Tooltip>
                    <Tooltip title="编辑内容">
                      <Button
                        type="text"
                        icon={<EditOutlined />}
                        aria-label="编辑文章"
                        onClick={() => openEditModal(article)}
                      />
                    </Tooltip>
                    <Tooltip title="推送到公众号草稿箱">
                      <Button
                        type="text"
                        icon={<SendOutlined />}
                        aria-label="推送到公众号草稿箱"
                        onClick={() => openPushModal(article)}
                      />
                    </Tooltip>
                    <Popconfirm
                      title="确认删除"
                      description="确定要删除这篇文章吗？"
                      okText="删除"
                      cancelText="取消"
                      onConfirm={() => handleDelete(article.task_id)}
                    >
                      <Button type="text" icon={<DeleteOutlined />} aria-label="删除文章" />
                    </Popconfirm>
                  </div>
                </div>
              </article>
            )
          })
        )}
      </div>

      <Modal
        open={Boolean(previewArticle)}
        title={previewTitle}
        width={920}
        footer={null}
        onCancel={() => setPreviewArticle(null)}
        destroyOnHidden
      >
        <div className={styles.previewFrame}>
          {previewCoverImage ? <img src={previewCoverImage} alt={previewTitle} className={styles.coverImage} /> : null}
          <div dangerouslySetInnerHTML={{ __html: previewHtml }} />
          {previewImageRefs.length ? (
            <div className={styles.imageGrid}>
              {previewImageRefs.map((image) => (
                <figure key={`${image.role}-${image.src}`}>
                  <img src={image.src} alt={image.role} />
                  <figcaption>{image.role}</figcaption>
                </figure>
              ))}
            </div>
          ) : null}
        </div>
      </Modal>

      <Modal
        open={Boolean(editingArticle)}
        title="编辑文章内容"
        width={860}
        okText="保存"
        cancelText="取消"
        confirmLoading={savingContent}
        onOk={() => void submitEdit()}
        onCancel={closeEditModal}
        destroyOnHidden
      >
        <Form
          form={editForm}
          layout="vertical"
          key={editingArticle?.task_id ?? 'empty'}
          initialValues={{
            title: editingValues.title,
            summary: editingValues.summary,
            content: editingValues.content,
            coverImage: editingValues.coverImage,
          }}
        >
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入文章标题' }]}>
            <Input placeholder="文章标题" />
          </Form.Item>
          <Form.Item name="summary" label="摘要">
            <Input.TextArea rows={2} maxLength={200} showCount placeholder="文章摘要" className={styles.textAreaFixed} />
          </Form.Item>
          <Form.Item name="content" label="正文（Markdown）">
            <Input.TextArea rows={14} placeholder="支持 Markdown，插图占位可使用 [插图1] 形式。" />
          </Form.Item>
          <Form.Item name="coverImage" label="封面图 URL">
            <Input placeholder="https://..." allowClear />
          </Form.Item>
          <div className={styles.illustrationEditor}>
            <div className={styles.illustrationHeader}>
              <span>插图列表</span>
              <Button size="small" icon={<PlusOutlined />} aria-label="添加插图" onClick={addIllustration}>
                添加插图
              </Button>
            </div>
            {editingValues.illustrations.length === 0 ? (
              <p className={styles.illustrationEmpty}>暂无插图，可点击「添加插图」补充图片地址。</p>
            ) : (
              editingValues.illustrations.map((item, index) => (
                <Space key={item.key} className={styles.illustrationRow} align="center">
                  <Input
                    value={item.value}
                    placeholder={`插图 ${index + 1} 的图片地址`}
                    aria-label={`插图 ${index + 1}`}
                    onChange={(event) => updateIllustration(item.key, event.target.value)}
                  />
                  <Button
                    type="text"
                    icon={<ArrowUpOutlined />}
                    aria-label={`上移插图 ${index + 1}`}
                    disabled={index === 0}
                    onClick={() => moveIllustration(index, -1)}
                  />
                  <Button
                    type="text"
                    icon={<ArrowDownOutlined />}
                    aria-label={`下移插图 ${index + 1}`}
                    disabled={index === editingValues.illustrations.length - 1}
                    onClick={() => moveIllustration(index, 1)}
                  />
                  <Button
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    aria-label={`删除插图 ${index + 1}`}
                    onClick={() => removeIllustration(item.key)}
                  />
                </Space>
              ))
            )}
          </div>
        </Form>
      </Modal>

      <Modal
        open={Boolean(pushArticleTask)}
        title="指定推送到微信公众号草稿箱"
        okText={pushAutoPublish ? '直接发布到公众号' : '推送到草稿箱'}
        cancelText="取消"
        confirmLoading={pushing}
        onOk={submitPush}
        onCancel={closePushModal}
        destroyOnHidden
      >
        <div className={styles.pushModalBody}>
          <div>
            <span>文章</span>
            <strong>{pushArticleTask ? getArticleTitle(pushArticleTask) : ''}</strong>
          </div>
          <Select
            mode="multiple"
            allowClear
            placeholder="选择微信公众号"
            value={pushAccountIds}
            options={wechatAccountOptions}
            onChange={setPushAccountIds}
            notFoundContent="暂无可用微信公众号"
          />
          <div className={styles.pushSwitchRow}>
            <Switch
              checked={pushAutoPublish}
              onChange={setPushAutoPublish}
              checkedChildren="直接发布"
              unCheckedChildren="仅草稿"
            />
            <span>直接发布到公众号</span>
          </div>
          {pushAutoPublish ? (
            <Alert
              type="warning"
              showIcon
              message="该操作不可撤回"
              description="开启后文章会调用微信发布接口直接对读者可见，无法撤回为草稿。请确认内容与账号均无问题。"
            />
          ) : (
            <p>确认后会将当前文章渲染为微信样式 HTML，并写入所选公众号的草稿箱。</p>
          )}
        </div>
      </Modal>
    </div>
  )
}
