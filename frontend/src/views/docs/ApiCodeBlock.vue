<script setup lang="ts">
import { CopyDocument } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{ title: string; code: string; language?: string }>()

async function copy() {
  try { await navigator.clipboard.writeText(props.code); ElMessage.success('已复制') }
  catch { ElMessage.error('复制失败，请手动选择') }
}
</script>

<template>
  <figure class="api-code-block">
    <figcaption>
      <span>{{ title }}</span>
      <div>
        <span class="api-code-language">{{ language ?? 'JSON' }}</span>
        <el-tooltip :content="`复制${title}`">
          <el-button :icon="CopyDocument" class="icon-button" :aria-label="`复制${title}`" @click="copy" />
        </el-tooltip>
      </div>
    </figcaption>
    <pre tabindex="0" :aria-label="title"><code>{{ code }}</code></pre>
  </figure>
</template>

<style scoped>
.api-code-block { min-width: 0; margin: 16px 0 24px; overflow: hidden; border: 1px solid var(--app-border); border-radius: 8px; background: var(--app-code); }
figcaption { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 12px 8px 18px; border-bottom: 1px solid var(--app-border); font-size: 13px; font-weight: 600; }
figcaption > div { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.api-code-language { color: var(--app-muted); font-size: 12px; font-weight: 400; }
pre { margin: 0; padding: 18px; border: 0; border-radius: 0; white-space: pre; overflow-wrap: normal; font-size: 13px; line-height: 1.8; }
pre:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: -3px; }
</style>
