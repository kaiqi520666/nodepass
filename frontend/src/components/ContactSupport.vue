<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ChatDotRound, Picture } from '@element-plus/icons-vue'

const route = useRoute()
const open = ref(false)
watch(() => route.path, () => { open.value = false })
</script>

<template>
  <el-popover v-model:visible="open" trigger="click" placement="bottom-end" title="联系客服" :width="224" :persistent="false">
    <template #reference>
      <el-button :icon="ChatDotRound" class="icon-button" aria-label="联系客服" title="联系客服" @keydown.esc="open = false" />
    </template>
    <div class="support-qr-placeholder" role="img" aria-label="客服二维码占位">
      <el-icon :size="32" aria-hidden="true"><Picture /></el-icon>
      <span>二维码占位</span>
    </div>
  </el-popover>
</template>
