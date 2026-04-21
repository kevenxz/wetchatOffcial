import { create } from 'zustand'
import {
  clearStoredAccessToken,
  getCurrentUser,
  getStoredAccessToken,
  setStoredAccessToken,
  type UserProfile,
} from '@/api'

type AuthState = {
  token: string
  user: UserProfile | null
  initialized: boolean
  bootstrap: () => void
  setSession: (token: string, user: UserProfile) => void
  clearSession: () => void
  refreshCurrentUser: () => Promise<UserProfile | null>
}

const useAuthStore = create<AuthState>((set, get) => ({
  token: '',
  user: null,
  initialized: false,
  bootstrap: () => {
    const token = getStoredAccessToken()
    set({
      token,
      initialized: true,
      user: token ? get().user : null,
    })
  },
  setSession: (token, user) => {
    setStoredAccessToken(token)
    set({ token, user, initialized: true })
  },
  clearSession: () => {
    clearStoredAccessToken()
    set({ token: '', user: null, initialized: true })
  },
  refreshCurrentUser: async () => {
    const { token } = get()
    if (!token) {
      set({ user: null })
      return null
    }
    try {
      const user = await getCurrentUser()
      set({ user })
      return user
    } catch {
      get().clearSession()
      return null
    }
  },
}))

export default useAuthStore
