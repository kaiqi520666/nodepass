<script setup lang="ts">
defineProps<{ page: number; pageSize: number; total: number; disabled?: boolean }>()
const emit = defineEmits<{ change: [value: { page: number; pageSize: number }] }>()
</script>

<template>
  <div class="app-pagination">
    <span class="pagination-total" role="status">共 <strong>{{ total }}</strong> 条</span>
    <el-select
      :model-value="pageSize" :disabled="disabled" aria-label="每页条数" class="pagination-size"
      @update:model-value="emit('change', { page: 1, pageSize: $event })"
    >
      <el-option v-for="size in [20, 50, 100]" :key="size" :label="`${size} 条 / 页`" :value="size" />
    </el-select>
    <el-pagination
      :current-page="page" :page-size="pageSize" :total="total" :disabled="disabled"
      :pager-count="5" background layout="prev, pager, next" aria-label="表格分页"
      @update:current-page="emit('change', { page: $event, pageSize })"
    />
  </div>
</template>
