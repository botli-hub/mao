import axios, { AxiosError } from 'axios'
import toast from 'react-hot-toast'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

// 请求拦截器：自动附加 JWT Token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('mao_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截器：统一错误处理
apiClient.interceptors.response.use(
  (res) => res,
  (err: AxiosError<{ detail: string }>) => {
    const status = err.response?.status
    const detail = err.response?.data?.detail
    if (status === 401) {
      localStorage.removeItem('mao_token')
      window.location.href = '/login'
    } else if (status === 422) {
      toast.error(typeof detail === 'string' ? detail : '请求参数错误')
    } else if (status && status >= 500) {
      toast.error('服务器错误，请稍后重试')
    }
    return Promise.reject(err)
  },
)

/** SSE 连接工厂 —— 返回 EventSource，调用方负责 close() */
export function createSSE(sessionId: string): EventSource {
  const token = localStorage.getItem('mao_token') ?? ''
  return new EventSource(
    `${BASE_URL}/chat/sessions/${sessionId}/stream?token=${encodeURIComponent(token)}`,
  )
}
