import axios from 'axios'

export interface CreateTaskRequest {
  keywords: string
}

export interface TaskResponse {
  task_id: string
  keywords: string
  status: 'pending' | 'running' | 'done' | 'failed'
  created_at: string
  updated_at: string | null
  error: string | null
  generated_article?: Record<string, any> | null
  draft_info?: Record<string, any> | null
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

export const createTask = (keywords: string): Promise<TaskResponse> =>
  http.post('/tasks', { keywords } satisfies CreateTaskRequest)

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
