import { onScopeDispose, ref, watch } from 'vue'
import { defineStore } from 'pinia'

export type ThemeMode = 'light' | 'dark' | 'system'

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>(
    (document.documentElement.dataset.themeMode as ThemeMode) || 'system',
  )
  const system = window.matchMedia('(prefers-color-scheme: dark)')

  function apply() {
    const dark = mode.value === 'dark' || (mode.value === 'system' && system.matches)
    document.documentElement.classList.toggle('dark', dark)
    document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
    document.documentElement.dataset.themeMode = mode.value
  }

  function setMode(value: ThemeMode) {
    if (!['light', 'dark', 'system'].includes(value)) return
    mode.value = value
  }

  watch(mode, () => {
    apply()
    try { localStorage.setItem('nodepass.theme', mode.value) } catch {}
  }, { flush: 'sync' })
  system.addEventListener('change', apply)
  onScopeDispose(() => system.removeEventListener('change', apply))
  apply()

  return { mode, setMode }
})
