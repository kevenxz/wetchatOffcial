import { useEffect, useMemo, useState } from 'react'
import { Button, Empty, Input, Modal, Popconfirm, Select, Tag, Tooltip, message } from 'antd'
import {
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  FileTextOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { useNavigate } from 'react-router-dom'
import {
  deleteTask,
  getCustomThemes,
  getPresetThemes,
  getStyleConfig,
  listArticles,
  type StyleConfig,
  type TaskResponse,
} from '@/api'
import styles from './ArticleManage.module.css'

const CURRENT_THEME_KEY = '__current__'

type ArticleFilter = 'all' | 'published' | 'review' | 'draft'

const filterOptions: Array<{ label: string; value: ArticleFilter }> = [
  { label: '全部', value: 'all' },
  { label: '已发布', value: 'published' },
  { label: '审核中', value: 'review' },
  { label: '草稿', value: 'draft' },
]

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
  const [category, setCategory] = useState('all')
  const [currentTheme, setCurrentTheme] = useState<StyleConfig>({})
  const [presetThemes, setPresetThemes] = useState<Record<string, StyleConfig>>({})
  const [customThemes, setCustomThemes] = useState<Record<string, StyleConfig>>({})
  const [previewArticle, setPreviewArticle] = useState<TaskResponse | null>(null)
  const navigate = useNavigate()

  const themeConfigMap: Record<string, StyleConfig> = {
    [CURRENT_THEME_KEY]: currentTheme,
    ...presetThemes,
    ...customThemes,
  }

  const fetchData = async () => {
    setLoading(true)
    try {
      const [articleList, currentConfig, preset, custom] = await Promise.all([
        listArticles(),
        getStyleConfig(),
        getPresetThemes(),
        getCustomThemes(),
      ])

      setArticles(articleList)
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
      const text = `${getArticleTitle(item)} ${getArticleSummary(item)} ${item.keywords} ${articleCategory}`.toLowerCase()
      return (
        (filter === 'all' || status === filter) &&
        (category === 'all' || articleCategory === category) &&
        (!keyword || text.includes(lowerKeyword))
      )
    })
  }, [articles, category, filter, keyword])

  const handleDelete = async (taskId: string) => {
    try {
      await deleteTask(taskId)
      message.success('已删除文章')
      await fetchData()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除文章失败')
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
        </div>
      </div>

      <div className={styles.articleList} aria-busy={loading}>
        {filteredArticles.length === 0 && !loading ? (
          <Empty description="暂无文章" style={{ padding: 72 }} />
        ) : (
          filteredArticles.map((article, index) => {
            const categoryName = getArticleCategory(article)
            const status = statusLabel(getArticleStatus(article))
            const review = reviewText(article)
            const imageCount = collectImageRefs(articleBody(article)).length

            return (
              <article className={styles.articleCard} key={article.task_id}>
                <div className={styles.articleInfo}>
                  <div className={styles.metaTop}>
                    <span>{displayId(index)}</span>
                    <Tag color={categoryColors[categoryName] ?? 'blue'}>{categoryName}</Tag>
                    <span>{getTemplateName(article)}</span>
                  </div>
                  <h2>{getArticleTitle(article)}</h2>
                  <p>{getArticleSummary(article)}</p>
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
                    <Tooltip title="编辑">
                      <Button
                        type="text"
                        icon={<EditOutlined />}
                        aria-label="编辑文章"
                        onClick={() => navigate(`/task/${article.task_id}`)}
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
    </div>
  )
}
