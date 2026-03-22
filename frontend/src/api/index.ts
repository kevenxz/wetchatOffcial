import axios from 'axios'

export type ArticleStrategy = 'auto' | 'tech_breakdown' | 'application_review' | 'trend_outlook'

export interface GenerationConfig {
  audience_roles: string[]
  article_strategy: ArticleStrategy
  style_hint: string
}

export const DEFAULT_GENERATION_CONFIG: GenerationConfig = {
  audience_roles: ['泛科技读者'],
  article_strategy: 'auto',
  style_hint: '',
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
  tech_breakdown: '技术揭秘式',
  application_review: '应用评测式',
  trend_outlook: '趋势展望式',
}

export interface CreateTaskRequest {
  keywords: string
  generation_config: GenerationConfig
}

export interface TaskResponse {
  task_id: string
  keywords: string
  generation_config: GenerationConfig
  status: 'pending' | 'running' | 'done' | 'failed'
  created_at: string
  updated_at: string | null
  error: string | null
  user_intent?: Record<string, any> | null
  style_profile?: Record<string, any> | null
  article_blueprint?: Record<string, any> | null
  article_plan?: Record<string, any> | null
  generated_article?: Record<string, any> | null
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

// 响应拦截器：统一提取 data，处理错误
http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const msg: string =
      err.response?.data?.detail ?? err.message ?? '请求失败，请稍后重试'
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

/**
 * 创建到指定任务的 WebSocket 连接。
 * 调用方负责监听 onmessage / onclose 事件。
 */
export function createTaskWs(taskId: string): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return new WebSocket(`${protocol}://${window.location.host}/ws/tasks/${taskId}`)
}

export type StyleConfig = Record<string, string>

export const getStyleConfig = (): Promise<StyleConfig> =>
  http.get('/config/style')

export const updateStyleConfig = (config: StyleConfig): Promise<StyleConfig> =>
  http.put('/config/style', config)

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

export type PresetThemes = Record<string, StyleConfig>

export const getPresetThemes = (): Promise<PresetThemes> =>
  http.get('/config/themes')

export type CustomThemes = Record<string, StyleConfig>

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

// -------- 账号配置相关 --------

export type PlatformType = 'wechat_mp' | 'toutiao'

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

// -------- 鏂囩珷绠＄悊 / 鎺ㄩ€佺浉鍏? --------

export type PushStatus = 'success' | 'failed'

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

// -------- 瀹氭椂浠诲姟 --------

export type ScheduleMode = 'once' | 'interval'
export type ScheduleStatus = 'running' | 'stopped'

export interface ScheduleConfig {
  schedule_id: string
  name: string
  mode: ScheduleMode
  run_at?: string | null
  interval_minutes?: number | null
  theme_name: string
  account_ids: string[]
  hot_topics: string[]
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
  generation_config?: GenerationConfig
  enabled?: boolean
}

export interface ScheduleExecuteResponse {
  message: string
  task_id?: string | null
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
