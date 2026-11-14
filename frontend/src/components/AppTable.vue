<script setup lang="ts" generic="T extends object">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Box } from '@element-plus/icons-vue'
import AppPagination from './AppPagination.vue'

defineOptions({ inheritAttrs: false })
const props = withDefaults(defineProps<{
  data: T[]
  loading?: boolean
  emptyText?: string
  emptyHint?: string
  pagination?: boolean
  total?: number
}>(), { loading: false, emptyText: '暂无数据', emptyHint: '', pagination: true })
const page = defineModel<number>('page', { default: 1 })
const pageSize = defineModel<number>('pageSize', { default: 20 })
const emit = defineEmits<{ change: [] }>()
const mobileQuery = window.matchMedia('(max-width: 900px)')
const isMobile = ref(mobileQuery.matches)
function updateMobile(event: MediaQueryListEvent) {
  isMobile.value = event.matches
}
onMounted(() => mobileQuery.addEventListener('change', updateMobile))
onBeforeUnmount(() => mobileQuery.removeEventListener('change', updateMobile))
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
    <div v-if="isMobile && $slots.mobile" v-loading="loading && rows.length > 0" class="app-table-cards">
      <el-skeleton v-if="loading && !rows.length" :rows="4" animated class="table-skeleton" />
      <slot v-else-if="rows.length" name="mobile" :rows="rows" />
      <div v-else class="table-empty">
        <el-icon :size="32" aria-hidden="true"><Box /></el-icon>
        <h2>{{ emptyText }}</h2>
        <p v-if="emptyHint">{{ emptyHint }}</p>
      </div>
    </div>
    <div v-else v-loading="loading && rows.length > 0" class="app-table-body">
      <el-table v-bind="$attrs" :data="rows" table-layout="fixed">
        <slot />
        <template #empty>
          <el-skeleton v-if="loading" :rows="4" animated class="table-skeleton" />
          <slot v-else name="empty">
            <div class="table-empty">
              <el-icon :size="32" aria-hidden="true"><Box /></el-icon>
              <h2>{{ emptyText }}</h2>
              <p v-if="emptyHint">{{ emptyHint }}</p>
            </div>
          </slot>
        </template>
      </el-table>
    </div>
    <AppPagination
      v-if="pagination" :page="page" :page-size="pageSize" :total="count" :disabled="loading"
      @change="change"
    />
  </div>
</template>
