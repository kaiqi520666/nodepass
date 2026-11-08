import { ref } from 'vue'
import { defineStore } from 'pinia'
import { http } from '../api/http'
import type { User } from '../types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  let initialized = false
  let pending: Promise<void> | null = null

  async function load() {
    const response = await http.get<User>('/account/me')
    user.value = response.data
    initialized = true
  }

  async function ensureLoaded() {
    if (initialized) return
    pending ??= load()
      .catch(() => { user.value = null })
      .finally(() => { pending = null; initialized = true })
    await pending
  }

  async function submit(mode: 'login' | 'register', email: string, password: string) {
    const response = await http.post<User>(`/account/${mode}`, { email: email.trim(), password })
    user.value = response.data
    initialized = true
  }

  async function logout() {
    await http.post('/account/logout')
    user.value = null
    initialized = true
  }

  return { user, load, ensureLoaded, submit, logout }
})
