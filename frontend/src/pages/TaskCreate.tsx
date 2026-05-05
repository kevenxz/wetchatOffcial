import type { CSSProperties } from 'react'
import { Button, Card, Form, Input, InputNumber, Select, Switch, Tag, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import {
  ARTICLE_STRATEGY_LABELS,
  DEFAULT_GENERATION_CONFIG,
  GENERATION_ROLE_PRESETS,
  type ArticleStrategy,
  type HotspotCaptureConfig,
  type HotspotPlatformConfig,
} from '@/api'
import { HeroPanel, SectionBlock } from '@/components/workbench'
import useTaskStore from '@/store/taskStore'

const HOT_TOPICS = ['人工智能', '大模型', '新能源', '量子计算', '消费趋势', '机器人']
const HOTSPOT_CATEGORY_PRESETS = [
  { label: 'AI', value: 'ai' },
  { label: '科技', value: 'tech' },
  { label: '财经', value: 'finance' },
  { label: '社会', value: 'news' },
  { label: '消费', value: 'consumer' },
  { label: '行业', value: 'industry' },
]

interface TaskCreateFormValues {
  keywords: string
  audience_roles: string[]
  article_strategy: ArticleStrategy
  style_hint?: string
  hotspot_enabled?: boolean
  hotspot_categories?: string[]
  hotspot_platforms?: HotspotPlatformConfig[]
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
  inline_count?: number
  auto_publish_to_draft?: boolean
}

const buildHotspotConfig = (values: TaskCreateFormValues): HotspotCaptureConfig | null => {
  if (!values.hotspot_enabled) return null
  const platforms = (values.hotspot_platforms || [])
    .map((platform) => ({
      name: platform.name?.trim() || '',
      path: platform.path?.trim() || '',
      weight: Number(platform.weight || 1),
      enabled: platform.enabled !== false,
    }))
    .filter((platform) => platform.name && platform.path)

  return {
    enabled: true,
    source: 'tophub',
    categories: values.hotspot_categories || [],
    platforms,
    filters: {
      top_n_per_platform: Number(values.hotspot_top_n_per_platform || 10),
      min_selection_score: Number(values.hotspot_min_selection_score || 60),
      exclude_keywords: values.hotspot_exclude_keywords || [],
      prefer_keywords: values.hotspot_prefer_keywords || [],
    },
    fallback_topics: [values.keywords.trim()].filter(Boolean),
  }
}

const pageLayoutStyle: CSSProperties = { display: 'grid', gap: 20 }
const guidanceListStyle: CSSProperties = {
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
const topicCloudStyle: CSSProperties = { display: 'flex', flexWrap: 'wrap', gap: 10 }
const helperTextStyle: CSSProperties = { fontSize: 13, color: 'var(--text-secondary)' }
const formGroupsStyle: CSSProperties = { display: 'grid', gap: 20 }
const formGroupStyle: CSSProperties = { display: 'grid', gap: 12 }
const groupTitleStyle: CSSProperties = { margin: 0, fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }
const twoColumnStyle: CSSProperties = {
  display: 'grid',
  gap: 16,
  gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
}

export default function TaskCreate() {
  const [form] = Form.useForm<TaskCreateFormValues>()
  const navigate = useNavigate()
  const { isCreating, createTask } = useTaskStore()

  const handleSubmit = async (values: TaskCreateFormValues) => {
    try {
      const taskId = await createTask({
        keywords: values.keywords.trim(),
        generation_config: {
          audience_roles: values.audience_roles?.length
            ? values.audience_roles
            : DEFAULT_GENERATION_CONFIG.audience_roles,
          article_strategy: values.article_strategy || DEFAULT_GENERATION_CONFIG.article_strategy,
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
          },
          publish_policy: {
            auto_publish_to_draft: values.auto_publish_to_draft !== false,
            require_manual_confirmation: Boolean(values.require_human_review),
          },
        },
        hotspot_capture_config: buildHotspotConfig(values),
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

  return (
    <div style={pageLayoutStyle} data-testid="task-create-grid">
      <HeroPanel
        eyebrow="Studio Launch"
        title="启动一次完整创作流程"
        description="手动主题仍是默认入口；需要追热点时，可以临时开启 TopHub 捕获，让系统先选题再进入写作链路。"
      >
        <ul style={guidanceListStyle} aria-label="创作提示">
          <li>先点灵感标签补齐关键词，再继续填写表单。</li>
          <li>受众角色和文章策略会影响研究重点、写作结构和审核阈值。</li>
          <li>未配置热点平台时，系统会尝试按分类自动发现 TopHub 节点。</li>
        </ul>
      </HeroPanel>

      <SectionBlock
        title="热点灵感"
        aside={<span style={helperTextStyle}>点选标签即可追加到关键词输入框。</span>}
      >
        <div style={topicCloudStyle}>
          {HOT_TOPICS.map((topic) => (
            <Tag
              key={topic}
              color="cyan"
              style={{ cursor: 'pointer', userSelect: 'none', paddingInline: 12, paddingBlock: 6 }}
              onClick={() => fillKeyword(topic)}
            >
              {topic}
            </Tag>
          ))}
        </div>
      </SectionBlock>

      <SectionBlock
        title="创作表单"
        aside={<span style={helperTextStyle}>一次配置即可进入热点、研究、写作、审核、出图和草稿箱链路。</span>}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          requiredMark="optional"
          initialValues={{
            audience_roles: DEFAULT_GENERATION_CONFIG.audience_roles,
            article_strategy: DEFAULT_GENERATION_CONFIG.article_strategy,
            style_hint: DEFAULT_GENERATION_CONFIG.style_hint,
            hotspot_enabled: false,
            hotspot_categories: ['ai', 'tech'],
            hotspot_top_n_per_platform: 10,
            hotspot_min_selection_score: 60,
            hotspot_platforms: [],
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
            inline_count: 1,
            auto_publish_to_draft: true,
          }}
        >
          <div style={formGroupsStyle}>
            <section style={formGroupStyle}>
              <h3 style={groupTitleStyle}>基础输入</h3>
              <Form.Item
                name="keywords"
                label="关键词"
                rules={[
                  { required: true, message: '请输入关键词' },
                  {
                    validator: (_, value: string) =>
                      value?.trim()
                        ? Promise.resolve()
                        : Promise.reject(new Error('关键词不能为空白内容')),
                  },
                ]}
                extra="关闭热点捕获时直接作为写作主题；开启热点捕获时作为抓取失败或未命中时的回退主题。"
              >
                <Input.TextArea
                  rows={4}
                  maxLength={200}
                  showCount
                  placeholder="例如：人工智能 最新进展"
                  style={{ resize: 'none' }}
                />
              </Form.Item>
            </section>

            <section style={formGroupStyle}>
              <h3 style={groupTitleStyle}>热点捕获</h3>
              <Card size="small">
                <Form.Item
                  name="hotspot_enabled"
                  label="本次任务启用热点捕获"
                  valuePropName="checked"
                >
                  <Switch checkedChildren="启用" unCheckedChildren="关闭" />
                </Form.Item>

                <Form.Item shouldUpdate noStyle>
                  {({ getFieldValue }) =>
                    getFieldValue('hotspot_enabled') ? (
                      <div style={formGroupsStyle}>
                        <div style={twoColumnStyle}>
                          <Form.Item name="hotspot_categories" label="题材分类">
                            <Select mode="multiple" options={HOTSPOT_CATEGORY_PRESETS} />
                          </Form.Item>
                          <Form.Item name="hotspot_min_selection_score" label="最低命中分">
                            <InputNumber min={0} max={100} style={{ width: '100%' }} />
                          </Form.Item>
                        </div>

                        <div style={twoColumnStyle}>
                          <Form.Item name="hotspot_top_n_per_platform" label="每个平台抓取数量">
                            <InputNumber min={1} max={50} style={{ width: '100%' }} />
                          </Form.Item>
                          <Form.Item name="hotspot_prefer_keywords" label="偏好关键词">
                            <Select mode="tags" tokenSeparators={[',', '，', ';', '；']} />
                          </Form.Item>
                        </div>

                        <Form.Item name="hotspot_exclude_keywords" label="排除关键词">
                          <Select mode="tags" tokenSeparators={[',', '，', ';', '；']} />
                        </Form.Item>
                      </div>
                    ) : (
                      <span style={helperTextStyle}>关闭时不抓取热点，直接使用上方关键词进入内容生产链路。</span>
                    )
                  }
                </Form.Item>
              </Card>
            </section>

            <section style={formGroupStyle}>
              <h3 style={groupTitleStyle}>受众与策略</h3>
              <div style={twoColumnStyle}>
                <Form.Item
                  name="audience_roles"
                  label="目标角色"
                  rules={[{ required: true, message: '请至少选择一个目标角色' }]}
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
              </div>
            </section>

            <section style={formGroupStyle}>
              <h3 style={groupTitleStyle}>流程策略</h3>
              <Card size="small">
                <div style={twoColumnStyle}>
                  <Form.Item name="account_positioning" label="账号定位">
                    <Input placeholder="例如：面向科技商业读者，偏深度解读" />
                  </Form.Item>
                  <Form.Item name="account_fit_tags" label="账号匹配标签">
                    <Select mode="tags" tokenSeparators={[',', '，', ';', '；']} />
                  </Form.Item>
                </div>
                <div style={twoColumnStyle}>
                  <Form.Item name="template_id" label="内容模板">
                    <Select
                      options={[
                        { label: '自动选择', value: 'auto' },
                        { label: '热点解读模板', value: 'hotspot_analysis_v1' },
                        { label: '趋势分析模板', value: 'trend_analysis_v1' },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item name="article_length" label="文章长度">
                    <Select
                      options={[
                        { label: '短篇', value: 'short' },
                        { label: '中篇', value: 'medium' },
                        { label: '长篇', value: 'long' },
                      ]}
                    />
                  </Form.Item>
                </div>
                <div style={twoColumnStyle}>
                  <Form.Item name="review_strictness" label="审核严格度">
                    <Select
                      options={[
                        { label: '宽松', value: 'lenient' },
                        { label: '标准', value: 'standard' },
                        { label: '严格', value: 'strict' },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item name="require_human_review" label="必须人工复核" valuePropName="checked">
                    <Switch checkedChildren="需要" unCheckedChildren="不需要" />
                  </Form.Item>
                </div>
                <div style={twoColumnStyle}>
                  <Form.Item name="search_mode" label="Research depth">
                    <Select
                      options={[
                        { label: 'Quick', value: 'quick' },
                        { label: 'Standard', value: 'standard' },
                        { label: 'Deep', value: 'deep' },
                        { label: 'Strict', value: 'strict' },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item name="freshness_window_days" label="Freshness window days">
                    <InputNumber min={1} max={365} style={{ width: '100%' }} />
                  </Form.Item>
                </div>
                <div style={twoColumnStyle}>
                  <Form.Item name="min_sources" label="Minimum sources">
                    <InputNumber min={1} max={30} style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name="min_official_sources" label="Minimum official sources">
                    <InputNumber min={0} max={10} style={{ width: '100%' }} />
                  </Form.Item>
                </div>
                <div style={twoColumnStyle}>
                  <Form.Item name="min_cross_sources" label="Minimum source domains">
                    <InputNumber min={1} max={20} style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name="require_opposing_view" label="Require risk/opposing view" valuePropName="checked">
                    <Switch checkedChildren="Required" unCheckedChildren="Optional" />
                  </Form.Item>
                </div>
                <Form.Item
                  name="auto_deepen_for_sensitive_categories"
                  label="Auto deepen sensitive categories"
                  valuePropName="checked"
                >
                  <Switch checkedChildren="Auto" unCheckedChildren="Manual" />
                </Form.Item>
                <div style={twoColumnStyle}>
                  <Form.Item name="image_enabled" label="自动出图" valuePropName="checked">
                    <Switch checkedChildren="启用" unCheckedChildren="关闭" />
                  </Form.Item>
                  <Form.Item name="inline_count" label="文内配图数量">
                    <InputNumber min={0} max={4} style={{ width: '100%' }} />
                  </Form.Item>
                </div>
                <Form.Item name="image_style" label="图片风格">
                  <Input placeholder="例如：科技感、克制、留出标题安全区" />
                </Form.Item>
                <Form.Item name="auto_publish_to_draft" label="自动入公众号草稿箱" valuePropName="checked">
                  <Switch checkedChildren="自动" unCheckedChildren="手动" />
                </Form.Item>
              </Card>
            </section>

            <section style={formGroupStyle}>
              <h3 style={groupTitleStyle}>风格补充</h3>
              <Form.Item
                name="style_hint"
                label="风格补充（可选）"
                extra="不填时系统会自动判断；填写后作为语气、结构和叙事重点的补充提示。"
              >
                <Input.TextArea
                  rows={3}
                  maxLength={500}
                  showCount
                  placeholder="例如：面向投资者，语言理性克制，结构偏市场观察与机会判断。"
                  style={{ resize: 'none' }}
                />
              </Form.Item>

              <Form.Item style={{ marginBottom: 0 }}>
                <Button type="primary" htmlType="submit" size="large" block loading={isCreating}>
                  启动创作流程
                </Button>
              </Form.Item>
            </section>
          </div>
        </Form>
      </SectionBlock>
    </div>
  )
}
