import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { Button, Card, Collapse, Form, Input, InputNumber, Select, Steps, Switch, Tag, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import {
  ARTICLE_STRATEGY_LABELS,
  DEFAULT_GENERATION_CONFIG,
  GENERATION_ROLE_PRESETS,
  getHotspotPlatforms,
  getImageStyles,
  listAccounts,
  type AccountConfig,
  type ArticleStrategy,
  type HotspotCaptureConfig,
  type HotspotPlatformCatalogItem,
  type HotspotPlatformConfig,
  type HotspotSource,
  type ImageStylePreset,
} from '@/api'
import { HeroPanel, SectionBlock } from '@/components/workbench'
import useTaskStore from '@/store/taskStore'
import styles from './TaskCreate.module.css'

const HOT_TOPICS = ['人工智能', '大模型', '新能源', '量子计算', '消费趋势', '机器人']
const HOTSPOT_CATEGORY_PRESETS = [
  { label: 'AI', value: 'ai' },
  { label: '科技', value: 'tech' },
  { label: '财经', value: 'finance' },
  { label: '社会', value: 'news' },
  { label: '消费', value: 'consumer' },
  { label: '行业', value: 'industry' },
]

const STEP_FIELDS: ReadonlyArray<ReadonlyArray<string>> = [
  ['keywords'],
  ['audience_roles', 'article_strategy'],
  [],
]

const WIZARD_STEPS = [
  {
    title: '主题与热点',
    description: '确定写作主题，并决定是否先抓取热点再做选题。',
  },
  {
    title: '受众与策略',
    description: '配置目标角色、文章策略、账号定位和内容模板。',
  },
  {
    title: '发布与审核',
    description: '设置研究深度、审核要求、图片策略和发布方式。',
  },
]

interface TaskCreateFormValues {
  keywords: string
  audience_roles: string[]
  article_strategy: ArticleStrategy
  /** Empty means "let the planning agent decide the article type". */
  requested_article_type?: string
  style_hint?: string
  hotspot_enabled?: boolean
  hotspot_categories?: string[]
  hotspot_platforms?: HotspotPlatformConfig[]
  /** Paths chosen in the platform picker; resolved against the catalogue on submit. */
  hotspot_platform_paths?: string[]
  hotspot_top_n_per_platform?: number
  hotspot_min_selection_score?: number
  hotspot_prefer_keywords?: string[]
  hotspot_exclude_keywords?: string[]
  account_positioning?: string
  account_fit_tags?: string[]
  template_id?: string
  article_length?: 'short' | 'medium' | 'long'
  review_strictness?: 'lenient' | 'standard' | 'strict'
  search_mode?: 'quick' | 'standard' | 'deep' | 'strict'
  auto_deepen_for_sensitive_categories?: boolean
  min_sources?: number
  min_official_sources?: number
  min_cross_sources?: number
  require_opposing_view?: boolean
  freshness_window_days?: number
  require_human_review?: boolean
  image_enabled?: boolean
  image_style?: string
  image_style_preset?: string
  image_allow_text?: boolean
  inline_count?: number
  auto_publish_to_draft?: boolean
  auto_publish?: boolean
  account_ids?: string[]
}

/**
 * The 16 structured newsnow platforms from the backend catalogue.
 *
 * These are the defaults because they are served from the background snapshot — a task using
 * them makes **no** upstream calls at creation time. The TopHub entries in the same catalogue
 * are live-scraped instead, which is the path that produced 429 retries and 176
 * `hotspot_source_unavailable` events in production.
 */
const newsnowPlatformPaths = (catalog: HotspotPlatformCatalogItem[]): string[] =>
  catalog.filter((item) => item.source === 'newsnow').map((item) => item.path)

const buildHotspotConfig = (
  values: TaskCreateFormValues,
  catalog: HotspotPlatformCatalogItem[],
): HotspotCaptureConfig | null => {
  if (!values.hotspot_enabled) return null

  // The picker stores `path` values; resolve them back to full platform entries from the
  // catalogue so `source`/`provider_id` always come from the backend rather than from a
  // hand-written literal in the UI. `provider_id` is the upstream id newsnow needs, and a
  // missing `source` used to let a newsnow platform be silently downgraded to a TopHub scrape.
  const byPath = new Map(catalog.map((item) => [item.path, item]))
  const selectedPaths = values.hotspot_platform_paths?.length
    ? values.hotspot_platform_paths
    : newsnowPlatformPaths(catalog)

  const platforms = selectedPaths
    .map((path) => byPath.get(path))
    .filter((item): item is HotspotPlatformCatalogItem => Boolean(item))
    .map((platform) => ({
      name: platform.name?.trim() || '',
      path: platform.path?.trim() || '',
      source: platform.source,
      provider_id: platform.provider_id?.trim() || undefined,
      category: platform.category?.trim() || undefined,
      weight: Number(platform.weight || 1),
      enabled: platform.enabled !== false,
    }))
    .filter((platform) => platform.name && platform.path)

  // The per-platform `source` is what the backend dispatches on; this top-level value is
  // descriptive only, so report whichever provider actually dominates the selection.
  const sourceCounts = new Map<string, number>()
  for (const platform of platforms) {
    const key = platform.source || 'tophub'
    sourceCounts.set(key, (sourceCounts.get(key) || 0) + 1)
  }
  const dominantSource = [...sourceCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0]

  return {
    enabled: true,
    source: (dominantSource || 'tophub') as HotspotSource,
    categories: values.hotspot_categories || [],
    platforms,
    filters: {
      top_n_per_platform: Number(values.hotspot_top_n_per_platform || 10),
      min_selection_score: Number(values.hotspot_min_selection_score || 60),
      exclude_keywords: values.hotspot_exclude_keywords || [],
      prefer_keywords: values.hotspot_prefer_keywords || [],
    },
    fallback_topics: [String(values.keywords ?? '').trim()].filter(Boolean),
  }
}

/** 隐藏非当前步骤：保留挂载以维持 Form 字段注册，同时不占布局空间。 */
const hiddenStepStyle: CSSProperties = { display: 'none' }

/**
 * Suggestions only — there is deliberately no fixed enum. The planning agent decides the
 * article type from the source material and names it itself; these are here so an
 * operator who wants to override that has something to click.
 */
const ARTICLE_TYPE_SUGGESTIONS = [
  '事件复盘',
  '热点解读',
  '政策解读',
  '案例分析',
  '趋势展望',
  '观点评论',
  '工具评测',
  '人物故事',
]

/**
 * 后端 `/api/images/styles` 是风格预设的唯一真源；这里只是它在接口返回前的兜底，
 * 保证下拉框永不为空。
 */
const FALLBACK_IMAGE_STYLES: ImageStylePreset[] = [
  { style_id: 'editorial_photo', name: '编辑部摄影感', description: '真实场景与物件、自然布光、浅景深', default_palette: [] },
  { style_id: 'concept_illustration', name: '概念插画', description: '扁平矢量、隐喻表达', default_palette: [] },
  { style_id: 'minimal_geometric', name: '极简几何', description: '抽象几何、大留白', default_palette: [] },
]

export default function TaskCreate() {
  const [form] = Form.useForm<TaskCreateFormValues>()
  const navigate = useNavigate()
  const { isCreating, createTask } = useTaskStore()

  const [currentStep, setCurrentStep] = useState(0)
  const [accounts, setAccounts] = useState<AccountConfig[]>([])
  const [imageStyles, setImageStyles] = useState<ImageStylePreset[]>(FALLBACK_IMAGE_STYLES)
  const [platformCatalog, setPlatformCatalog] = useState<HotspotPlatformCatalogItem[]>([])

  // Load the hotspot catalogue and default the picker to the newsnow platforms. Setting the
  // field here (rather than in `initialValues`) is required because the catalogue arrives
  // asynchronously; the guard keeps a value the user already changed.
  useEffect(() => {
    getHotspotPlatforms()
      .then((result) => {
        const items = result.items ?? []
        setPlatformCatalog(items)
        if (form.getFieldValue('hotspot_platform_paths') === undefined) {
          form.setFieldValue('hotspot_platform_paths', newsnowPlatformPaths(items))
        }
      })
      .catch(() => setPlatformCatalog([]))
  }, [form])

  const platformOptions = useMemo(
    () =>
      platformCatalog.map((item) => ({
        value: item.path,
        label: item.source === 'newsnow' ? `${item.name}（热点快照）` : `${item.name}（${item.source}）`,
        title: item.category ? `分类：${item.category}` : undefined,
      })),
    [platformCatalog],
  )

  useEffect(() => {
    getImageStyles()
      .then((result) => setImageStyles(result.items?.length ? result.items : FALLBACK_IMAGE_STYLES))
      .catch(() => setImageStyles(FALLBACK_IMAGE_STYLES))
  }, [])

  const imageStyleOptions = useMemo(
    () =>
      imageStyles.map((preset) => ({
        value: preset.style_id,
        label: preset.name,
        title: preset.description,
      })),
    [imageStyles],
  )

  useEffect(() => {
    listAccounts()
      .then((result) => setAccounts(Array.isArray(result) ? result : []))
      .catch(() => setAccounts([]))
  }, [])

  const accountOptions = useMemo(
    () =>
      accounts
        .filter((account) => account.enabled)
        .map((account) => ({
          label: `${account.name}（${account.platform === 'wechat_mp' ? '微信公众号' : '头条号'}）`,
          value: account.account_id,
        })),
    [accounts],
  )

  const handleSubmit = async (values: TaskCreateFormValues) => {
    // Defensive: a field can legitimately be absent from `values` if it was
    // unmounted, so never call .trim() on it directly.
    const keywords = String(values.keywords ?? '').trim()
    if (!keywords) {
      message.error('请返回第一步填写关键词')
      setCurrentStep(0)
      return
    }

    try {
      const taskId = await createTask({
        keywords,
        account_ids: values.account_ids?.length ? values.account_ids : undefined,
        generation_config: {
          audience_roles: values.audience_roles?.length
            ? values.audience_roles
            : DEFAULT_GENERATION_CONFIG.audience_roles,
          article_strategy: values.article_strategy || DEFAULT_GENERATION_CONFIG.article_strategy,
          // Left empty, the planning agent decides the type from the source material.
          requested_article_type: values.requested_article_type?.trim() || '',
          style_hint: values.style_hint?.trim() || DEFAULT_GENERATION_CONFIG.style_hint,
          account_profile: {
            positioning: values.account_positioning?.trim() || '',
            target_readers: values.audience_roles || [],
            fit_tags: values.account_fit_tags || [],
            avoid_topics: [],
          },
          content_template: {
            template_id: values.template_id || 'auto',
            name: values.template_id === 'hotspot_analysis_v1' ? '热点解读模板' : '自动选择',
            preferred_framework: values.template_id || '',
            article_length: values.article_length || 'medium',
            tone: values.style_hint?.trim() || '',
          },
          review_policy: {
            strictness: values.review_strictness || 'standard',
            auto_rewrite: true,
            require_human_review: Boolean(values.require_human_review),
            block_high_risk: true,
            max_revision_rounds: 1,
            viral_threshold: DEFAULT_GENERATION_CONFIG.review_policy?.viral_threshold || 78,
          },
          research_policy: {
            search_mode: values.search_mode || DEFAULT_GENERATION_CONFIG.research_policy?.search_mode || 'standard',
            auto_deepen_for_sensitive_categories: values.auto_deepen_for_sensitive_categories !== false,
            min_sources: Number(values.min_sources ?? DEFAULT_GENERATION_CONFIG.research_policy?.min_sources ?? 6),
            min_official_sources: Number(
              values.min_official_sources ?? DEFAULT_GENERATION_CONFIG.research_policy?.min_official_sources ?? 1,
            ),
            min_cross_sources: Number(
              values.min_cross_sources ?? DEFAULT_GENERATION_CONFIG.research_policy?.min_cross_sources ?? 3,
            ),
            require_opposing_view: values.require_opposing_view !== false,
            freshness_window_days: Number(
              values.freshness_window_days ?? DEFAULT_GENERATION_CONFIG.research_policy?.freshness_window_days ?? 7,
            ),
          },
          image_policy: {
            enabled: values.image_enabled !== false,
            cover_enabled: values.image_enabled !== false,
            inline_enabled: values.image_enabled !== false,
            inline_count: Number(values.inline_count ?? 1),
            style: values.image_style?.trim() || '',
            brand_colors: [],
            title_safe_area: true,
            style_preset: values.image_style_preset || 'editorial_photo',
            // Words in the picture were the core complaint: image models render Chinese
            // as garbage, so text stays off unless the operator explicitly asks for it.
            allow_text_overlay: Boolean(values.image_allow_text),
            prompt_max_chars: 400,
          },
          publish_policy: {
            auto_publish_to_draft: values.auto_publish_to_draft !== false,
            require_manual_confirmation: Boolean(values.require_human_review),
            auto_publish: Boolean(values.auto_publish),
            publish_retry_limit: DEFAULT_GENERATION_CONFIG.publish_policy?.publish_retry_limit ?? 3,
            publish_poll_interval_seconds:
              DEFAULT_GENERATION_CONFIG.publish_policy?.publish_poll_interval_seconds ?? 5,
            publish_poll_max_attempts:
              DEFAULT_GENERATION_CONFIG.publish_policy?.publish_poll_max_attempts ?? 10,
          },
        },
        hotspot_capture_config: buildHotspotConfig(values, platformCatalog),
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

  const goNext = async () => {
    try {
      await form.validateFields([...STEP_FIELDS[currentStep]])
      setCurrentStep((prev) => Math.min(prev + 1, WIZARD_STEPS.length - 1))
    } catch {
      // Ant Design already highlights the invalid fields for the current step.
    }
  }

  const goPrev = () => setCurrentStep((prev) => Math.max(prev - 1, 0))

  /** 提交时若必填项未通过，跳回它所在的步骤，否则错误信息藏在隐藏步骤里看不见。 */
  const handleFinishFailed = (errorInfo: { errorFields: Array<{ name: (string | number)[] }> }) => {
    const firstField = String(errorInfo.errorFields[0]?.name?.[0] ?? '')
    const failedStep = STEP_FIELDS.findIndex((fields) => fields.includes(firstField))
    if (failedStep >= 0 && failedStep !== currentStep) {
      setCurrentStep(failedStep)
      message.error(`请先完成「${WIZARD_STEPS[failedStep].title}」的必填项`)
    }
  }

  const renderStepOne = () => (
    <section className={styles.stepPanel} aria-label="主题与热点">
      <header className={styles.stepHeader}>
        <h3 className={styles.stepTitle}>主题与热点</h3>
        <p className={styles.stepDescription}>
          关闭热点捕获时，关键词会直接作为写作主题；开启后系统会先抓取热点并完成选题，再把命中结果送入写作链路。
        </p>
      </header>

      <Form.Item
        name="keywords"
        label="关键词"
        rules={[
          { required: true, message: '请输入关键词' },
          {
            validator: (_, value: string) =>
              value?.trim() ? Promise.resolve() : Promise.reject(new Error('关键词不能为空白内容')),
          },
        ]}
        extra="关闭热点捕获时直接作为写作主题；开启热点捕获时作为抓取失败或未命中时的回退主题。"
      >
        <Input.TextArea
          rows={4}
          maxLength={200}
          showCount
          placeholder="例如：人工智能 最新进展"
          className={styles.textAreaFixed}
        />
      </Form.Item>

      <div className={styles.groupStack}>
        <h4 className={styles.groupTitle}>热点灵感</h4>
        <span className={styles.helperText}>点选标签即可追加到关键词输入框。</span>
        <div className={styles.topicCloud}>
          {HOT_TOPICS.map((topic) => (
            <Tag
              key={topic}
              color="cyan"
              className={styles.topicTag}
              onClick={() => fillKeyword(topic)}
            >
              {topic}
            </Tag>
          ))}
        </div>
      </div>

      <Card size="small">
        <Form.Item name="hotspot_enabled" label="本次任务启用热点捕获" valuePropName="checked">
          <Switch checkedChildren="启用" unCheckedChildren="关闭" />
        </Form.Item>

        <Form.Item shouldUpdate noStyle>
          {({ getFieldValue }) =>
            getFieldValue('hotspot_enabled') ? (
              <div className={styles.groupStack}>
                <div className={styles.twoColumn}>
                  <Form.Item name="hotspot_categories" label="题材分类" className={styles.fieldFlush}>
                    <Select mode="multiple" options={HOTSPOT_CATEGORY_PRESETS} />
                  </Form.Item>
                  <Form.Item name="hotspot_min_selection_score" label="最低命中分" className={styles.fieldFlush}>
                    <InputNumber min={0} max={100} className={styles.fieldFull} />
                  </Form.Item>
                </div>

                <div className={styles.twoColumn}>
                  <Form.Item name="hotspot_top_n_per_platform" label="每个平台抓取数量" className={styles.fieldFlush}>
                    <InputNumber min={1} max={50} className={styles.fieldFull} />
                  </Form.Item>
                  <Form.Item name="hotspot_prefer_keywords" label="偏好关键词" className={styles.fieldFlush}>
                    <Select mode="tags" tokenSeparators={[',', '，', ';', '；']} />
                  </Form.Item>
                </div>

                <Form.Item name="hotspot_exclude_keywords" label="排除关键词" className={styles.fieldFlush}>
                  <Select mode="tags" tokenSeparators={[',', '，', ';', '；']} />
                </Form.Item>

                <Form.Item
                  name="hotspot_platform_paths"
                  label="热点平台"
                  className={styles.fieldFlush}
                  extra="默认只选「热点快照」来源的平台：它们由后台定时拉取，建任务时不请求上游。选 TopHub 平台会改为实时抓取。"
                >
                  <Select
                    mode="multiple"
                    allowClear
                    options={platformOptions}
                    placeholder="选择要抓取的热点平台"
                    loading={!platformCatalog.length}
                    maxTagCount="responsive"
                  />
                </Form.Item>
              </div>
            ) : (
              <span className={styles.helperText}>关闭时不抓取热点，直接使用上方关键词进入内容生产链路。</span>
            )
          }
        </Form.Item>
      </Card>
    </section>
  )

  const renderStepTwo = () => (
    <section className={styles.stepPanel} aria-label="受众与策略">
      <header className={styles.stepHeader}>
        <h3 className={styles.stepTitle}>受众与策略</h3>
        <p className={styles.stepDescription}>
          受众角色和文章策略会影响研究重点、写作结构和审核阈值；账号定位与匹配标签用于判断选题适配度。
        </p>
      </header>

      <div className={styles.twoColumn}>
        <Form.Item
          name="audience_roles"
          label="受众角色"
          rules={[{ required: true, message: '请至少选择一个受众角色' }]}
          extra="可多选，排在前面的角色会被视为主视角。"
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
          name="requested_article_type"
          label="文章类型"
          extra="默认由 Agent 读完素材后自己判定类型并决定结构；留空即为自动判断。"
        >
          <Select
            allowClear
            showSearch
            // Free text is allowed: there is deliberately no fixed enum, so these entries
            // are suggestions rather than the whole set.
            options={ARTICLE_TYPE_SUGGESTIONS.map((item) => ({ label: item, value: item }))}
            placeholder="自动判断（推荐）"
          />
        </Form.Item>
      </div>

      <div className={styles.twoColumn}>
        <Form.Item name="account_positioning" label="账号定位" className={styles.fieldFlush}>
          <Input placeholder="例如：面向科技商业读者，偏深度解读" />
        </Form.Item>
        <Form.Item name="account_fit_tags" label="账号匹配标签" className={styles.fieldFlush}>
          <Select mode="tags" tokenSeparators={[',', '，', ';', '；']} />
        </Form.Item>
      </div>

      <Form.Item name="template_id" label="内容模板" className={styles.fieldFlush}>
        <Select
          options={[
            { label: '自动选择', value: 'auto' },
            { label: '热点解读模板', value: 'hotspot_analysis_v1' },
            { label: '趋势分析模板', value: 'trend_analysis_v1' },
          ]}
        />
      </Form.Item>

      <div className={styles.groupStack}>
        <h4 className={styles.groupTitle}>风格补充</h4>
        <Form.Item
          name="style_hint"
          label="风格补充（可选）"
          extra="不填时系统会自动判断；填写后作为语气、结构和叙事重点的补充提示。"
          className={styles.fieldFlush}
        >
          <Input.TextArea
            rows={3}
            maxLength={500}
            showCount
            placeholder="例如：面向投资者，语言理性克制，结构偏市场观察与机会判断。"
            className={styles.textAreaFixed}
          />
        </Form.Item>
      </div>
    </section>
  )

  const renderStepThree = () => (
    <section className={styles.stepPanel} aria-label="发布与审核">
      <header className={styles.stepHeader}>
        <h3 className={styles.stepTitle}>发布与审核</h3>
        <p className={styles.stepDescription}>
          图像、研究和审核参数已归入「高级设置」；直接发布不可撤回，请确认账号具备发布权限后再开启。
        </p>
      </header>

      <Form.Item name="article_length" label="文章长度" className={styles.fieldFlush}>
        <Select
          options={[
            { label: '短篇', value: 'short' },
            { label: '中篇', value: 'medium' },
            { label: '长篇', value: 'long' },
          ]}
        />
      </Form.Item>

      <Collapse
        defaultActiveKey={['advanced']}
        items={[
          {
            key: 'advanced',
            label: '高级设置',
            children: (
              <div className={styles.groupStack}>
                <div className={styles.twoColumn}>
                  <Form.Item
                    name="review_strictness"
                    label="审核严格度"
                    aria-label="审核严格度"
                    className={styles.fieldFlush}
                  >
                    <Select
                      options={[
                        { label: '宽松', value: 'lenient' },
                        { label: '标准', value: 'standard' },
                        { label: '严格', value: 'strict' },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item
                    name="require_human_review"
                    label="必须人工复核"
                    aria-label="必须人工复核"
                    valuePropName="checked"
                    className={styles.fieldFlush}
                  >
                    <Switch checkedChildren="需要" unCheckedChildren="不需要" />
                  </Form.Item>
                </div>

                <div className={styles.twoColumn}>
                  <Form.Item name="search_mode" label="检索深度" aria-label="检索深度" className={styles.fieldFlush}>
                    <Select
                      options={[
                        { label: '快速', value: 'quick' },
                        { label: '标准', value: 'standard' },
                        { label: '深度', value: 'deep' },
                        { label: '严格', value: 'strict' },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item
                    name="freshness_window_days"
                    label="内容时效窗口"
                    aria-label="内容时效窗口"
                    className={styles.fieldFlush}
                  >
                    <InputNumber min={1} max={365} className={styles.fieldFull} />
                  </Form.Item>
                </div>

                <div className={styles.twoColumn}>
                  <Form.Item name="min_sources" label="最少来源数" aria-label="最少来源数" className={styles.fieldFlush}>
                    <InputNumber min={1} max={30} className={styles.fieldFull} />
                  </Form.Item>
                  <Form.Item
                    name="min_official_sources"
                    label="最少官方来源数"
                    aria-label="最少官方来源数"
                    className={styles.fieldFlush}
                  >
                    <InputNumber min={0} max={10} className={styles.fieldFull} />
                  </Form.Item>
                </div>

                <div className={styles.twoColumn}>
                  <Form.Item
                    name="min_cross_sources"
                    label="最少来源域名数"
                    aria-label="最少来源域名数"
                    className={styles.fieldFlush}
                  >
                    <InputNumber min={1} max={20} className={styles.fieldFull} />
                  </Form.Item>
                  <Form.Item
                    name="require_opposing_view"
                    label="要求风险与反向观点"
                    aria-label="要求风险与反向观点"
                    valuePropName="checked"
                    className={styles.fieldFlush}
                  >
                    <Switch checkedChildren="要求" unCheckedChildren="可选" />
                  </Form.Item>
                </div>

                <Form.Item
                  name="auto_deepen_for_sensitive_categories"
                  label="敏感题材自动加深检索"
                  aria-label="敏感题材自动加深检索"
                  valuePropName="checked"
                  className={styles.fieldFlush}
                >
                  <Switch checkedChildren="自动加深" unCheckedChildren="手动控制" />
                </Form.Item>

                <div className={styles.twoColumn}>
                  <Form.Item
                    name="image_enabled"
                    label="自动出图"
                    aria-label="自动出图"
                    valuePropName="checked"
                    className={styles.fieldFlush}
                  >
                    <Switch checkedChildren="启用" unCheckedChildren="关闭" />
                  </Form.Item>
                  <Form.Item name="inline_count" label="文内配图数量" aria-label="文内配图数量" className={styles.fieldFlush}>
                    <InputNumber min={0} max={4} className={styles.fieldFull} />
                  </Form.Item>
                </div>

                <Form.Item
                  name="image_style_preset"
                  label="图片风格"
                  aria-label="图片风格"
                  extra="风格由预设描述控制。此前是自由文本，默认值还会和英文兜底串冲突。"
                  className={styles.fieldFlush}
                >
                  <Select
                    options={imageStyleOptions}
                    placeholder="选择图片风格"
                  />
                </Form.Item>

                <Form.Item
                  name="image_style"
                  label="补充风格说明（可选）"
                  aria-label="补充风格说明"
                  className={styles.fieldFlush}
                >
                  <Input placeholder="例如：留出标题安全区、避免人脸特写" />
                </Form.Item>

                <Form.Item
                  name="image_allow_text"
                  label="允许画面出现文字"
                  aria-label="允许画面出现文字"
                  valuePropName="checked"
                  extra="默认关闭：图像模型渲染中文会变成乱码，这是图片看起来像海报的主要原因。"
                  className={styles.fieldFlush}
                >
                  <Switch checkedChildren="允许" unCheckedChildren="禁止" />
                </Form.Item>
              </div>
            ),
          },
        ]}
      />

      <Form.Item
        name="account_ids"
        label="发布账号（可选）"
        aria-label="发布账号（可选）"
        extra="不选择时使用系统默认的微信公众号凭据。"
        className={styles.fieldFlush}
      >
        <Select
          mode="multiple"
          allowClear
          placeholder="选择用于推送的渠道账号"
          options={accountOptions}
          notFoundContent="暂无可用渠道账号"
        />
      </Form.Item>

      <Form.Item
        name="auto_publish_to_draft"
        label="自动入公众号草稿箱"
        aria-label="自动入公众号草稿箱"
        valuePropName="checked"
        className={styles.fieldFlush}
      >
        <Switch checkedChildren="自动" unCheckedChildren="手动" />
      </Form.Item>

      <Form.Item
        name="auto_publish"
        label="直接发布到公众号"
        aria-label="直接发布到公众号"
        valuePropName="checked"
        extra="开启后会调用微信发布接口，文章将直接对读者可见且无法撤回。需要账号具备发布权限。"
        className={styles.fieldFlush}
      >
        <Switch checkedChildren="直接发布" unCheckedChildren="仅草稿" />
      </Form.Item>
    </section>
  )

  return (
    <div className={styles.page} data-testid="task-create-grid">
      <HeroPanel
        eyebrow="Studio Launch"
        title="启动一次完整创作流程"
        description="手动主题仍是默认入口；需要追热点时，可以临时开启 TopHub 捕获，让系统先选题再进入写作链路。全流程按三个步骤配置。"
      >
        <ul className={styles.guidanceList} aria-label="创作提示">
          <li>先点灵感标签补齐关键词，再继续填写表单。</li>
          <li>受众角色和文章策略会影响研究重点、写作结构和审核阈值。</li>
          <li>未配置热点平台时，系统会尝试按分类自动发现 TopHub 节点。</li>
        </ul>
      </HeroPanel>

      <SectionBlock
        title="创作表单"
        aside={<span className={styles.helperText}>一次配置即可进入热点、研究、写作、审核、出图和草稿箱链路。</span>}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          onFinishFailed={handleFinishFailed}
          requiredMark="optional"
          initialValues={{
            audience_roles: DEFAULT_GENERATION_CONFIG.audience_roles,
            article_strategy: DEFAULT_GENERATION_CONFIG.article_strategy,
            // Empty by default: the agent decides the type unless the operator says otherwise.
            requested_article_type: '',
            style_hint: DEFAULT_GENERATION_CONFIG.style_hint,
            // On by default: hotspots are served from the background snapshot, so enabling
            // them costs no upstream call at creation time and gives the article a real,
            // current subject instead of running on search results alone.
            hotspot_enabled: true,
            hotspot_categories: ['ai', 'tech'],
            hotspot_top_n_per_platform: 10,
            hotspot_min_selection_score: 60,
            hotspot_platforms: [],
            // Filled from the catalogue once it loads (see the fetch effect).
            hotspot_platform_paths: undefined,
            hotspot_prefer_keywords: [],
            hotspot_exclude_keywords: [],
            account_positioning: '',
            account_fit_tags: [],
            template_id: 'auto',
            article_length: 'medium',
            review_strictness: 'standard',
            search_mode: DEFAULT_GENERATION_CONFIG.research_policy?.search_mode || 'standard',
            auto_deepen_for_sensitive_categories: true,
            min_sources: DEFAULT_GENERATION_CONFIG.research_policy?.min_sources || 6,
            min_official_sources: DEFAULT_GENERATION_CONFIG.research_policy?.min_official_sources || 1,
            min_cross_sources: DEFAULT_GENERATION_CONFIG.research_policy?.min_cross_sources || 3,
            require_opposing_view: DEFAULT_GENERATION_CONFIG.research_policy?.require_opposing_view ?? true,
            freshness_window_days: DEFAULT_GENERATION_CONFIG.research_policy?.freshness_window_days || 7,
            require_human_review: false,
            image_enabled: true,
            image_style: '',
            image_style_preset: DEFAULT_GENERATION_CONFIG.image_policy?.style_preset || 'editorial_photo',
            image_allow_text: DEFAULT_GENERATION_CONFIG.image_policy?.allow_text_overlay ?? false,
            inline_count: 1,
            auto_publish_to_draft: true,
            auto_publish: false,
            account_ids: [],
          }}
        >
          <div className={styles.wizardCard}>
            <Steps
              current={currentStep}
              size="small"
              labelPlacement="vertical"
              items={WIZARD_STEPS.map((step) => ({
                title: step.title,
                description: step.description,
              }))}
            />
          </div>

          {/* 三个步骤必须保持挂载，仅切换可见性。
              Ant Design 的 Form 会在 Form.Item 卸载时注销该字段，
              若按步骤卸载，提交时 values 中会缺失前几步的字段
              （例如在第三步提交时取不到第一步的 keywords）。 */}
          <div className={styles.stepStack}>
            <div style={currentStep === 0 ? undefined : hiddenStepStyle}>{renderStepOne()}</div>
            <div style={currentStep === 1 ? undefined : hiddenStepStyle}>{renderStepTwo()}</div>
            <div style={currentStep === 2 ? undefined : hiddenStepStyle}>{renderStepThree()}</div>
          </div>

          <div className={styles.wizardActions}>
            <Button size="large" onClick={goPrev} disabled={currentStep === 0}>
              上一步
            </Button>
            <div className={styles.wizardActionsEnd}>
              {currentStep < WIZARD_STEPS.length - 1 ? (
                <Button size="large" type="primary" onClick={() => void goNext()}>
                  下一步
                </Button>
              ) : (
                <Button type="primary" size="large" htmlType="submit" loading={isCreating}>
                  启动创作流程
                </Button>
              )}
            </div>
          </div>
        </Form>
      </SectionBlock>
    </div>
  )
}
