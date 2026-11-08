<script setup lang="ts">
import { Back } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
const router = useRouter()
</script>

<template>
  <el-result title="404" sub-title="页面不存在">
    <template #extra><el-button :icon="Back" @click="router.push('/models')">返回模型目录</el-button></template>
  </el-result>
</template>
