import axios from 'axios'

export const http = axios.create({
  baseURL: '/api',
  timeout: 15_000,
  withCredentials: true,
})

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail: unknown = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (!error.response) return '连接失败，请检查网络后重试'
  }
  return '操作未完成，请稍后重试'
}
