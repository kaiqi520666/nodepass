<script setup lang="ts">
import { ElConfigProvider } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { copyAnnouncement } from './utils/clipboard'
</script>

<template>
  <ElConfigProvider :locale="zhCn">
    <p class="sr-only" aria-live="polite" aria-atomic="true">{{ copyAnnouncement }}</p>
    <RouterView />
  </ElConfigProvider>
</template>
