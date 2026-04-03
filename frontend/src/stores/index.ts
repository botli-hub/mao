import { create } from 'zustand'
import type { User, Session, Message, Task } from '../types'

interface AuthStore {
  user: User | null
  token: string | null
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  setUser: (user: User | null) => void
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  token: localStorage.getItem('mao_token'),
  login: async (email: string, password: string) => {
    const token = 'mock_token_' + Date.now()
    localStorage.setItem('mao_token', token)
    set({ token, user: { user_id: '1', username: email, email, role: 'user' } })
  },
  logout: () => {
    localStorage.removeItem('mao_token')
    set({ user: null, token: null })
  },
  setUser: (user) => set({ user }),
}))

interface ChatStore {
  sessions: Session[]
  currentSessionId: string | null
  messages: Message[]
  isLoading: boolean
  transientStream: string
  setSessions: (sessions: Session[]) => void
  setCurrentSession: (sessionId: string | null) => void
  setMessages: (messages: Message[]) => void
  addMessage: (message: Message) => void
  setIsLoading: (loading: boolean) => void
  appendTransientStream: (delta: string) => void
  clearTransientStream: () => void
}

export const useChatStore = create<ChatStore>((set) => ({
  sessions: [],
  currentSessionId: null,
  messages: [],
  isLoading: false,
  transientStream: '',
  setSessions: (sessions) => set({ sessions }),
  setCurrentSession: (sessionId) => set({ currentSessionId: sessionId, transientStream: '' }),
  setMessages: (messages) => set({ messages }),
  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  setIsLoading: (loading) => set({ isLoading: loading }),
  appendTransientStream: (delta) => set((state) => ({ transientStream: state.transientStream + delta })),
  clearTransientStream: () => set({ transientStream: '' }),
}))

interface AdminStore {
  activeTasks: Task[]
  selectedTaskId: string | null
  setActiveTasks: (tasks: Task[]) => void
  setSelectedTask: (taskId: string | null) => void
}

export const useAdminStore = create<AdminStore>((set) => ({
  activeTasks: [],
  selectedTaskId: null,
  setActiveTasks: (tasks) => set({ activeTasks: tasks }),
  setSelectedTask: (taskId) => set({ selectedTaskId: taskId }),
}))
