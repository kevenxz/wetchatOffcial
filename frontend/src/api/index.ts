import axios from 'axios'

export type ArticleStrategy = 'auto' | 'tech_breakdown' | 'application_review' | 'trend_outlook'

export interface AccountProfileConfig {
  positioning: string
  target_readers: string[]
  fit_tags: string[]
  avoid_topics: string[]
}

export interface ContentTemplateConfig {
  template_id: string
  name: string
  preferred_framework: string
  article_length: 'short' | 'medium' | 'long'
  tone: string
}

export interface ReviewPolicyConfig {
  strictness: 'lenient' | 'standard' | 'strict'
  auto_rewrite: boolean
  require_human_review: boolean
  block_high_risk: boolean
  max_revision_rounds: number
}

export interface WorkflowImagePolicyConfig {
  enabled: boolean
  cover_enabled: boolean
  inline_enabled: boolean
  inline_count: number
  style: string
  brand_colors: string[]
  title_safe_area: boolean
}

export interface PublishPolicyConfig {
  auto_publish_to_draft: boolean
  require_manual_confirmation: boolean
}

export interface GenerationConfig {
  audience_roles: string[]
  article_strategy: ArticleStrategy
  style_hint: string
  account_profile?: AccountProfileConfig
  content_template?: ContentTemplateConfig
  review_policy?: ReviewPolicyConfig
  image_policy?: WorkflowImagePolicyConfig
  publish_policy?: PublishPolicyConfig
}

export const DEFAULT_GENERATION_CONFIG: GenerationConfig = {
  audience_roles: ['泛科技读者'],
  article_strategy: 'auto',
  style_hint: '',
  account_profile: {
    positioning: '',
    target_readers: [],
    fit_tags: [],
    avoid_topics: [],
  },
  content_template: {
    template_id: 'auto',
    name: '自动选择',
    preferred_framework: '',
    article_length: 'medium',
    tone: '',
  },
  review_policy: {
    strictness: 'standard',
    auto_rewrite: true,
    require_human_review: false,
    block_high_risk: true,
    max_revision_rounds: 1,
  },
  image_policy: {
    enabled: true,
    cover_enabled: true,
    inline_enabled: true,
    inline_count: 1,
    style: '',
    brand_colors: [],
    title_safe_area: true,
  },
  publish_policy: {
    auto_publish_to_draft: true,
    require_manual_confirmation: false,
  },
}

export const GENERATION_ROLE_PRESETS = [
  '泛科技读者',
  '开发者',
  '产品经理',
  '投资者',
  '企业管理者',
]

export const ARTICLE_STRATEGY_LABELS: Record<ArticleStrategy, string> = {
  auto: '自动判断',
  tech_breakdown: '技术拆解',
  application_review: '应用评测',
  trend_outlook: '趋势展望',
}

export interface CreateTaskRequest {
  keywords: string
  generation_config: GenerationConfig
  hotspot_capture_config?: HotspotCaptureConfig | null
}

export type PushStatus = 'success' | 'failed'

export type PlatformType = 'wechat_mp' | 'toutiao'

export interface PushRecord {
  push_id: string
  account_id: string
  account_name: string
  platform: PlatformType
  pushed_at: string
  status: PushStatus
  draft_info?: Record<string, any> | null
  error?: string | null
}

export interface TaskResponse {
  task_id: string
  mode?: string | null
  keywords: string
  original_keywords?: string | null
  generation_config: GenerationConfig
  status: 'pending' | 'running' | 'done' | 'failed'
  created_at: string
  updated_at: string | null
  error: string | null
  hotspot_capture_config?: HotspotCaptureConfig | null
  config_snapshot?: Record<string, any> | null
  hotspot_candidates?: TopHubHotItem[]
  selected_hotspot?: TopHubHotItem | null
  selected_topic?: Record<string, any> | null
  hotspot_capture_error?: string | null
  human_review_required?: boolean
  task_brief?: Record<string, any> | null
  planning_state?: Record<string, any> | null
  research_state?: Record<string, any> | null
  writing_state?: Record<string, any> | null
  visual_state?: Record<string, any> | null
  quality_state?: Record<string, any> | null
  quality_report?: Record<string, any> | null
  user_intent?: Record<string, any> | null
  style_profile?: Record<string, any> | null
  article_blueprint?: Record<string, any> | null
  article_plan?: Record<string, any> | null
  outline_result?: Record<string, any> | null
  generated_article?: Record<string, any> | null
  final_article?: Record<string, any> | null
  draft_info?: Record<string, any> | null
  article_theme?: string | null
  push_records?: PushRecord[]
}

export interface WsMessage {
  task_id: string
  status: string
  current_skill: string
  progress: number
  message: string
  result: unknown
}

const http = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

const ACCESS_TOKEN_KEY = 'wechat_project_access_token'

export const getStoredAccessToken = (): string => {
  if (typeof window === 'undefined') return ''
  return window.localStorage.getItem(ACCESS_TOKEN_KEY) ?? ''
}

export const setStoredAccessToken = (token: string): void => {
  if (typeof window === 'undefined') return
  if (token) {
    window.localStorage.setItem(ACCESS_TOKEN_KEY, token)
    return
  }
  window.localStorage.removeItem(ACCESS_TOKEN_KEY)
}

export const clearStoredAccessToken = (): void => {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(ACCESS_TOKEN_KEY)
}

http.interceptors.request.use((config) => {
  const token = getStoredAccessToken()
  if (!token) return config
  config.headers = config.headers ?? {}
  config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const msg: string = err.response?.data?.detail ?? err.message ?? '请求失败，请稍后重试'
    return Promise.reject(new Error(msg))
  },
)

export const createTask = (data: CreateTaskRequest): Promise<TaskResponse> =>
  http.post('/tasks', data)

export const getTask = (taskId: string): Promise<TaskResponse> =>
  http.get(`/tasks/${taskId}`)

export const listTasks = (): Promise<TaskResponse[]> => http.get('/tasks')

export const deleteTask = (taskId: string): Promise<void> =>
  http.delete(`/tasks/${taskId}`)

export const retryTask = (taskId: string): Promise<TaskResponse> =>
  http.post(`/tasks/${taskId}/retry`)

export function createTaskWs(taskId: string): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return new WebSocket(`${protocol}://${window.location.host}/ws/tasks/${taskId}`)
}

export type StyleConfig = Record<string, string>
export type PresetThemes = Record<string, StyleConfig>
export type CustomThemes = Record<string, StyleConfig>

export const getStyleConfig = (): Promise<StyleConfig> =>
  http.get('/config/style')

export const updateStyleConfig = (config: StyleConfig): Promise<StyleConfig> =>
  http.put('/config/style', config)

export const getPresetThemes = (): Promise<PresetThemes> =>
  http.get('/config/themes')

export const getCustomThemes = (): Promise<CustomThemes> =>
  http.get('/config/themes/custom')

export const createCustomTheme = (name: string, config: StyleConfig): Promise<CustomThemes> =>
  http.post('/config/themes/custom', { name, config })

export const updateCustomTheme = (themeName: string, name: string, config: StyleConfig): Promise<CustomThemes> =>
  http.put(`/config/themes/custom/${encodeURIComponent(themeName)}`, { name, config })

export const deleteCustomTheme = (themeName: string): Promise<CustomThemes> =>
  http.delete(`/config/themes/custom/${encodeURIComponent(themeName)}`)

export const importCustomThemes = (themes: CustomThemes): Promise<CustomThemes> =>
  http.post('/config/themes/custom/import', themes)

export interface TextModelConfig {
  api_key: string
  base_url?: string | null
  model: string
}

export interface ImageModelConfig {
  enabled: boolean
  api_key: string
  base_url?: string | null
  model: string
}

export interface ModelConfig {
  text: TextModelConfig
  image: ImageModelConfig
}

export const getModelConfig = (): Promise<ModelConfig> =>
  http.get('/config/model')

export const updateModelConfig = (config: ModelConfig): Promise<ModelConfig> =>
  http.put('/config/model', config)

export interface AccountConfig {
  account_id: string
  name: string
  platform: PlatformType
  app_id: string
  app_secret: string
  enabled: boolean
  created_at: string
  updated_at: string | null
}

export interface CreateAccountRequest {
  name: string
  platform: PlatformType
  app_id: string
  app_secret: string
  enabled: boolean
}

export interface UpdateAccountRequest {
  name?: string
  platform?: PlatformType
  app_id?: string
  app_secret?: string
  enabled?: boolean
}

export interface TestConnectionResponse {
  success: boolean
  message: string
}

export const listAccounts = (): Promise<AccountConfig[]> =>
  http.get('/accounts')

export const createAccount = (data: CreateAccountRequest): Promise<AccountConfig> =>
  http.post('/accounts', data)

export const updateAccount = (accountId: string, data: UpdateAccountRequest): Promise<AccountConfig> =>
  http.put(`/accounts/${accountId}`, data)

export const deleteAccount = (accountId: string): Promise<void> =>
  http.delete(`/accounts/${accountId}`)

export const testAccountConnection = (accountId: string): Promise<TestConnectionResponse> =>
  http.post(`/accounts/${accountId}/test`)

export interface BatchPushResponse {
  total: number
  success: number
  failed: number
  results: Array<{
    task_id: string
    account_id: string
    account_name: string
    status: PushStatus
    draft_info?: Record<string, any> | null
    error?: string | null
  }>
}

export const listArticles = (): Promise<TaskResponse[]> =>
  http.get('/articles')

export const pushArticle = (
  taskId: string,
  accountIds: string[],
  themeName?: string,
): Promise<BatchPushResponse> =>
  http.post(`/articles/${taskId}/push`, { account_ids: accountIds, theme_name: themeName })

export const batchPushArticles = (
  taskIds: string[],
  accountIds: string[],
  taskThemes?: Record<string, string>,
): Promise<BatchPushResponse> =>
  http.post('/articles/batch-push', { task_ids: taskIds, account_ids: accountIds, task_themes: taskThemes })

export const updateArticleTheme = (
  taskId: string,
  themeName: string,
): Promise<TaskResponse> =>
  http.put(`/articles/${taskId}/theme`, { theme_name: themeName })

export type ScheduleMode = 'once' | 'interval'
export type ScheduleStatus = 'running' | 'stopped'
export type HotspotSource = 'tophub'

export interface HotspotFilters {
  top_n_per_platform: number
  min_selection_score: number
  exclude_keywords: string[]
  prefer_keywords: string[]
}

export interface HotspotPlatformConfig {
  name: string
  path: string
  weight: number
  enabled: boolean
}

export interface HotspotCaptureConfig {
  enabled: boolean
  source: HotspotSource
  categories: string[]
  platforms: HotspotPlatformConfig[]
  filters: HotspotFilters
  fallback_topics: string[]
}

export interface TopHubHotItem {
  source: HotspotSource
  category: string
  platform_name: string
  platform_path: string
  platform_weight?: number
  title: string
  url: string
  rank: number
  extra_text?: string
  hot_value?: number | null
  selection_score?: number
  selection_star?: number
  captured_at?: string
}

export interface ScheduleConfig {
  schedule_id: string
  name: string
  mode: ScheduleMode
  run_at?: string | null
  interval_minutes?: number | null
  theme_name: string
  account_ids: string[]
  hot_topics: string[]
  hotspot_capture: HotspotCaptureConfig
  generation_config: GenerationConfig
  status: ScheduleStatus
  enabled: boolean
  last_run_at?: string | null
  next_run_at?: string | null
  last_error?: string | null
  created_at: string
  updated_at?: string | null
}

export interface CreateScheduleRequest {
  name: string
  mode: ScheduleMode
  run_at?: string | null
  interval_minutes?: number | null
  theme_name: string
  account_ids: string[]
  hot_topics: string[]
  hotspot_capture: HotspotCaptureConfig
  generation_config: GenerationConfig
  enabled: boolean
}

export interface UpdateScheduleRequest {
  name?: string
  mode?: ScheduleMode
  run_at?: string | null
  interval_minutes?: number | null
  theme_name?: string
  account_ids?: string[]
  hot_topics?: string[]
  hotspot_capture?: HotspotCaptureConfig
  generation_config?: GenerationConfig
  enabled?: boolean
}

export interface ScheduleExecuteResponse {
  message: string
  task_id?: string | null
}

export interface HotspotPreviewRequest {
  keywords: string
  hotspot_capture: HotspotCaptureConfig
}

export interface HotspotPreviewResponse {
  keywords: string
  original_keywords: string
  hotspot_capture_config: HotspotCaptureConfig
  hotspot_candidates: TopHubHotItem[]
  selected_hotspot?: TopHubHotItem | null
  hotspot_capture_error?: string | null
}

export interface HotspotMonitorItem {
  topic_id: string
  title: string
  summary: string
  source: string
  url?: string | null
  category: string
  tags: string[]
  status: TopicStatus
  task_id?: string | null
  hot_score: number
  account_fit_score: number
  risk_score: number
  channel_count: number
  recommended: boolean
  captured_at?: string | null
  updated_at?: string | null
  metadata: Record<string, any>
}

export interface HotspotMonitorStats {
  total: number
  recommended: number
  high_risk: number
  source_count: number
  latest_captured_at?: string | null
}

export interface HotspotMonitorResponse {
  items: HotspotMonitorItem[]
  stats: HotspotMonitorStats
  updated_at: string
  capture_error?: string | null
}

export interface HotspotMonitorParams {
  status?: TopicStatus | 'all'
  category?: string
  recommended_only?: boolean
  limit?: number
}

export interface HotspotMonitorCaptureRequest {
  keywords: string
  hotspot_capture: HotspotCaptureConfig
}

export const listSchedules = (): Promise<ScheduleConfig[]> =>
  http.get('/schedules')

export const createSchedule = (data: CreateScheduleRequest): Promise<ScheduleConfig> =>
  http.post('/schedules', data)

export const updateSchedule = (scheduleId: string, data: UpdateScheduleRequest): Promise<ScheduleConfig> =>
  http.put(`/schedules/${scheduleId}`, data)

export const deleteSchedule = (scheduleId: string): Promise<void> =>
  http.delete(`/schedules/${scheduleId}`)

export const startSchedule = (scheduleId: string): Promise<ScheduleConfig> =>
  http.post(`/schedules/${scheduleId}/start`)

export const stopSchedule = (scheduleId: string): Promise<ScheduleConfig> =>
  http.post(`/schedules/${scheduleId}/stop`)

export const runScheduleNow = (scheduleId: string): Promise<ScheduleExecuteResponse> =>
  http.post(`/schedules/${scheduleId}/run-now`)

export const previewHotspots = (data: HotspotPreviewRequest): Promise<HotspotPreviewResponse> =>
  http.post('/hotspots/preview', data)

export const getHotspotMonitor = (params: HotspotMonitorParams = {}): Promise<HotspotMonitorResponse> => {
  const query = { ...params }
  if (query.status === 'all') delete query.status
  return http.get('/hotspots/monitor', { params: query })
}

export const captureHotspotMonitor = (data: HotspotMonitorCaptureRequest): Promise<HotspotMonitorResponse> =>
  http.post('/hotspots/monitor/capture', data)

export type TopicStatus = 'pending' | 'ignored' | 'converted'

export interface TopicCandidate {
  topic_id: string
  title: string
  summary?: string
  source?: string
  url?: string | null
  score?: number | null
  tags?: string[]
  status: TopicStatus
  task_id?: string | null
  metadata?: Record<string, any>
  created_at?: string | null
  updated_at?: string | null
  source_cluster?: string[]
  angle?: string
  category?: string | null
  hot_score?: number
  account_fit_score?: number
  risk_score?: number
}

export interface ListTopicsParams {
  status?: TopicStatus | 'all'
  limit?: number
}

export const listTopics = (params: ListTopicsParams = {}): Promise<TopicCandidate[]> => {
  const query = { ...params }
  if (query.status === 'all') delete query.status
  return http.get('/topics', { params: query })
}

export const ignoreTopic = (topicId: string): Promise<TopicCandidate> =>
  http.post(`/topics/${encodeURIComponent(topicId)}/ignore`)

export const convertTopicToTask = (topicId: string): Promise<TaskResponse> =>
  http.post(`/topics/${encodeURIComponent(topicId)}/convert-to-task`, {})

export type ReviewStatus = 'pending' | 'approved' | 'rejected' | 'revision_requested'
export type ReviewTargetType = 'topic' | 'task' | 'article' | 'workflow_step' | 'custom'
export type ReviewDecisionAction = 'approve' | 'reject' | 'request_revision'

export interface ReviewRiskIssue {
  code?: string | null
  message: string
  severity?: 'low' | 'medium' | 'high' | 'critical' | string
  source?: string | null
}

export interface ReviewDecision {
  review_id: string
  target_type: ReviewTargetType
  target_id?: string
  title?: string
  payload?: Record<string, any>
  status: ReviewStatus
  decision?: ReviewStatus | null
  comment?: string | null
  reviewer_id?: string | null
  task_id?: string | null
  reviewer?: string | null
  risk_summary?: string | null
  risk_issues?: ReviewRiskIssue[]
  article_score?: number | null
  visual_score?: number | null
  blocking_reasons?: string[]
  revision_guidance?: string[]
  created_at?: string | null
  updated_at?: string | null
  decided_at?: string | null
}

export interface ListReviewsParams {
  status?: ReviewStatus | 'all'
  limit?: number
}

export interface ReviewDecisionRequest {
  action: ReviewDecisionAction
  comment?: string
}

export const listReviews = (params: ListReviewsParams = {}): Promise<ReviewDecision[]> => {
  const query = { ...params }
  if (query.status === 'all') delete query.status
  return http.get('/reviews', { params: query })
}

export const approveReview = (reviewId: string, comment?: string): Promise<ReviewDecision> =>
  http.post(`/reviews/${encodeURIComponent(reviewId)}/approve`, { comment })

export const rejectReview = (reviewId: string, comment?: string): Promise<ReviewDecision> =>
  http.post(`/reviews/${encodeURIComponent(reviewId)}/reject`, { comment })

export const requestReviewRevision = (reviewId: string, comment?: string): Promise<ReviewDecision> =>
  http.post(`/reviews/${encodeURIComponent(reviewId)}/request-revision`, { comment })

export type UserRole = 'admin' | 'operator'

export interface UserProfile {
  user_id: string
  username: string
  display_name: string
  role: UserRole
  enabled: boolean
  created_at: string
  updated_at?: string | null
  last_login_at?: string | null
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: UserProfile
}

export interface CreateUserRequest {
  username: string
  password: string
  display_name: string
  role: UserRole
  enabled: boolean
}

export interface UpdateUserRequest {
  display_name?: string
  role?: UserRole
  enabled?: boolean
  password?: string
}

export const login = (data: LoginRequest): Promise<LoginResponse> =>
  http.post('/auth/login', data)

export const getCurrentUser = (): Promise<UserProfile> =>
  http.get('/auth/me')

export const listUsers = (): Promise<UserProfile[]> =>
  http.get('/users')

export const createUser = (data: CreateUserRequest): Promise<UserProfile> =>
  http.post('/users', data)

export const updateUser = (userId: string, data: UpdateUserRequest): Promise<UserProfile> =>
  http.put(`/users/${userId}`, data)

export const deleteUser = (userId: string): Promise<void> =>
  http.delete(`/users/${userId}`)
