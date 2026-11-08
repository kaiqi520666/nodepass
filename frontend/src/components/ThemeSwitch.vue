<script setup lang="ts">
import { computed, ref } from 'vue'
import { Monitor, Moon, Sunny } from '@element-plus/icons-vue'
import { useThemeStore, type ThemeMode } from '../stores/theme'

const theme = useThemeStore()
const menuOpen = ref(false)
const options = [
  { value: 'light', label: '明亮', icon: Sunny },
  { value: 'dark', label: '暗黑', icon: Moon },
  { value: 'system', label: '跟随系统', icon: Monitor },
] as const
const current = computed(() => options.find(option => option.value === theme.mode)!)
</script>

<template>
  <el-tooltip :content="`主题：${current.label}`" :show-after="400" :disabled="menuOpen" :enterable="false" placement="left">
    <span class="theme-control">
      <el-dropdown trigger="click" @command="theme.setMode($event as ThemeMode)" @visible-change="menuOpen = $event">
        <el-button :icon="current.icon" class="icon-button" aria-label="切换主题" />
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-for="option in options"
              :key="option.value"
              :command="option.value"
              :icon="option.icon"
              :class="{ 'selected-theme': theme.mode === option.value }"
            >
              {{ option.label }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </span>
  </el-tooltip>
</template>
