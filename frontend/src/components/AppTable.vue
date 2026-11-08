<script setup lang="ts">
import { computed, watch } from 'vue'
import { Box } from '@element-plus/icons-vue'
import AppPagination from './AppPagination.vue'

defineOptions({ inheritAttrs: false })
const props = withDefaults(defineProps<{
  data: object[]
  loading?: boolean
  emptyText?: string
  pagination?: boolean
  total?: number
}>(), { loading: false, emptyText: '暂无数据', pagination: true })
const page = defineModel<number>('page', { default: 1 })
const pageSize = defineModel<number>('pageSize', { default: 20 })
const emit = defineEmits<{ change: [] }>()
const count = computed(() => props.total ?? props.data.length)
const rows = computed(() => props.pagination && props.total === undefined
  ? props.data.slice((page.value - 1) * pageSize.value, page.value * pageSize.value)
  : props.data)

function change(value: { page: number; pageSize: number }) {
  page.value = value.page
  pageSize.value = value.pageSize
  emit('change')
}

watch(() => props.data, () => {
  if (props.total === undefined) page.value = 1
})
watch([count, () => props.loading], () => {
  if (props.loading || !props.pagination) return
  const lastPage = Math.max(1, Math.ceil(count.value / pageSize.value))
  if (page.value > lastPage) change({ page: lastPage, pageSize: pageSize.value })
})
</script>

<template>
  <div class="app-table" :aria-busy="loading">
    <div v-loading="loading" class="app-table-body">
      <el-table v-bind="$attrs" :data="rows" table-layout="fixed">
        <slot />
        <template #empty>
          <slot v-if="!loading" name="empty">
            <div class="table-empty"><el-icon :size="32" aria-hidden="true"><Box /></el-icon><p>{{ emptyText }}</p></div>
          </slot>
          <span v-else class="table-loading">正在加载…</span>
        </template>
      </el-table>
    </div>
    <AppPagination
      v-if="pagination" :page="page" :page-size="pageSize" :total="count" :disabled="loading"
      @change="change"
    />
  </div>
</template>
