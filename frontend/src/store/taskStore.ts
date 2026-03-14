import { create } from 'zustand'
import { createTask as apiCreateTask, type TaskResponse } from '@/api'

interface TaskState {
  currentTask: TaskResponse | null
  isCreating: boolean
  error: string | null
  createTask: (keywords: string) => Promise<string>
  clearError: () => void
}

const useTaskStore = create<TaskState>()((set) => ({
  currentTask: null,
  isCreating: false,
  error: null,

  createTask: async (keywords: string) => {
    set({ isCreating: true, error: null })
    try {
      const task = await apiCreateTask(keywords)
      set({ currentTask: task, isCreating: false })
      return task.task_id
    } catch (err) {
      const msg = err instanceof Error ? err.message : '创建任务失败'
      set({ isCreating: false, error: msg })
      throw new Error(msg)
    }
  },

  clearError: () => set({ error: null }),
}))

export default useTaskStore
