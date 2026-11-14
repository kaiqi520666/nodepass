<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { CopyDocument, Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { errorMessage, http } from '../../api/http'
import { copyText } from '../../utils/clipboard'
import AppTable from '../../components/AppTable.vue'

type TextCall = {
  id: string
  model: string
  status: 'processing' | 'succeeded' | 'failed' | 'usage_unknown'
  created: number
  completed: number | null
  duration_ms: number
  input_tokens: number | null
  output_tokens: number | null
  charge_amount: string | null
}
type TextCallDetail = TextCall & {
  endpoint: string
  stream: boolean | null
  usage: { input_tokens: number; cached_tokens: number; output_tokens: number; reasoning_tokens: number } | null
  sale_price: { input_price: string; output_price: string; cache_read_price: string; sale_multiplier: string; long_context_threshold: number; long_context_input_multiplier: string; long_context_output_multiplier: string }
  error_message: string | null
}

const calls = ref<TextCall[]>([])
const total = ref(0)
const models = ref<string[]>([])
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const error = ref('')
const detailOpen = ref(false)
const detailLoading = ref('')
const selected = ref<TextCallDetail | null>(null)
const filters = reactive({ query: '', model: 'all', status: 'all', dates: null as [Date, Date] | null })
const statusOptions = {
  processing: { label: '调用中', type: 'info' },
  succeeded: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
  usage_unknown: { label: '用量待核实', type: 'warning' },
} as const
const usageRows = computed(() => {
  if (!selected.value) return []
  const { usage, sale_price: price } = selected.value
  return [
    { label: '普通输入', tokens: usage ? usage.input_tokens - usage.cached_tokens : null, price: price.input_price },
    { label: '缓存命中', tokens: usage?.cached_tokens, price: price.cache_read_price },
    { label: '可见输出', tokens: usage ? usage.output_tokens - usage.reasoning_tokens : null, price: price.output_price },
    { label: '思考输出', tokens: usage?.reasoning_tokens, price: price.output_price },
  ]
})

function formatDate(timestamp: number | null) {
  return timestamp === null ? '—' : new Date(timestamp * 1000).toLocaleString('zh-CN')
}

function formatDuration(duration: number) {
  const seconds = Math.floor(duration / 1000)
  return seconds < 60 ? `${seconds} 秒` : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
}

function tokenCount(count: number | null | undefined) {
  return count == null ? '—' : count.toLocaleString('zh-CN')
}

async function copyId(id: string) {
  await copyText(id, '调用 ID 已复制', '复制失败，请手动复制调用 ID')
}

async function load() {
  loading.value = true
  error.value = ''
  const end = filters.dates ? new Date(filters.dates[1]) : null
  if (end) end.setDate(end.getDate() + 1)
  try {
    const response = await http.get<{ data: TextCall[]; total: number; models: string[] }>('/account/text-calls', {
      params: {
        offset: (page.value - 1) * pageSize.value,
        limit: pageSize.value,
        query: filters.query.trim() || undefined,
        model: filters.model === 'all' ? undefined : filters.model,
        status: filters.status === 'all' ? undefined : filters.status,
        created_from: filters.dates ? Math.floor(filters.dates[0].getTime() / 1000) : undefined,
        created_to: end ? Math.floor(end.getTime() / 1000) : undefined,
      },
    })
    calls.value = response.data.data
    total.value = response.data.total
    models.value = response.data.models
  } catch (cause) {
    error.value = errorMessage(cause)
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  load()
}

function resetFilters() {
  Object.assign(filters, { query: '', model: 'all', status: 'all', dates: null })
  search()
}

async function showDetails(call: TextCall) {
  detailLoading.value = call.id
  try {
    selected.value = (await http.get<TextCallDetail>(`/account/text-calls/${call.id}`)).data
    detailOpen.value = true
  } catch (cause) {
    ElMessage.error(errorMessage(cause))
  } finally {
    detailLoading.value = ''
  }
}

defineExpose({ refresh: load, loading })
onMounted(load)
</script>

<template>
  <section aria-label="文本调用日志">
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="form-alert" />
    <form class="filter-bar task-filters" @submit.prevent="search">
      <el-input v-model="filters.query" :disabled="loading" clearable :prefix-icon="Search" placeholder="搜索调用 ID" aria-label="搜索调用 ID" @clear="search" />
      <el-select v-model="filters.model" :disabled="loading" aria-label="文本模型" class="task-filter-select" @change="search">
        <el-option label="全部模型" value="all" />
        <el-option v-for="model in models" :key="model" :label="model" :value="model" />
      </el-select>
      <el-select v-model="filters.status" :disabled="loading" aria-label="文本调用状态" class="task-filter-select" @change="search">
        <el-option label="全部状态" value="all" />
        <el-option v-for="(option, status) in statusOptions" :key="status" :label="option.label" :value="status" />
      </el-select>
      <el-date-picker
        v-model="filters.dates" :disabled="loading" type="daterange" range-separator="至"
        start-placeholder="开始日期" end-placeholder="结束日期" aria-label="文本调用日期" @change="search"
      />
      <el-button :icon="Search" :disabled="loading" native-type="submit">查询</el-button>
      <el-button :disabled="loading" @click="resetFilters">重置</el-button>
    </form>
    <AppTable
      v-model:page="page" v-model:page-size="pageSize" :data="calls" :total="total"
      :loading="loading" empty-text="暂无匹配的文本调用" empty-hint="调整筛选条件后重试。" @change="load"
    >
      <el-table-column label="调用信息" min-width="310">
        <template #default="{ row }">
          <div class="task-id">
            <code>{{ row.id }}</code>
            <el-tooltip content="复制调用 ID">
              <el-button :icon="CopyDocument" class="icon-button task-copy-button" :aria-label="`复制调用 ID ${row.id}`" @click="copyId(row.id)" />
            </el-tooltip>
          </div>
          <div class="task-created">{{ formatDate(row.created) }}</div>
        </template>
      </el-table-column>
      <el-table-column label="使用模型" min-width="220">
        <template #default="{ row }"><code>{{ row.model }}</code></template>
      </el-table-column>
      <el-table-column label="状态" width="130">
        <template #default="{ row }">
          <el-tag :type="statusOptions[row.status as TextCall['status']].type" effect="plain">{{ statusOptions[row.status as TextCall['status']].label }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column width="145" align="right">
        <template #header><el-tooltip content="包含缓存命中的输入 token"><span>输入 Token</span></el-tooltip></template>
        <template #default="{ row }"><span class="numeric">{{ tokenCount(row.input_tokens) }}</span></template>
      </el-table-column>
      <el-table-column width="145" align="right">
        <template #header><el-tooltip content="包含思考输出的 token"><span>输出 Token</span></el-tooltip></template>
        <template #default="{ row }"><span class="numeric">{{ tokenCount(row.output_tokens) }}</span></template>
      </el-table-column>
      <el-table-column label="耗时" width="120">
        <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
      </el-table-column>
      <el-table-column label="扣除积分" width="175" align="center">
        <template #default="{ row }"><strong class="numeric">{{ row.charge_amount ?? '—' }}</strong></template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right" align="right">
        <template #default="{ row }">
          <el-button class="task-detail-button" :loading="detailLoading === row.id" :disabled="Boolean(detailLoading)" @click="showDetails(row)">详情</el-button>
        </template>
      </el-table-column>
    </AppTable>
    <el-dialog v-model="detailOpen" title="文本调用详情" width="760px" destroy-on-close>
      <template v-if="selected">
        <div class="task-detail-summary">
          <div class="task-detail-item task-detail-item-wide">
            <span class="task-detail-label">调用 ID</span>
            <div class="task-id">
              <code>{{ selected.id }}</code>
              <el-button :icon="CopyDocument" class="icon-button task-copy-button" aria-label="复制调用 ID" title="复制调用 ID" @click="copyId(selected.id)" />
            </div>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">模型</span><code class="task-detail-value">{{ selected.model }}</code>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">状态</span>
            <el-tag :type="statusOptions[selected.status].type" effect="plain">{{ statusOptions[selected.status].label }}</el-tag>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">调用接口</span><code class="task-detail-value">{{ selected.endpoint }}</code>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">返回方式</span><span class="task-detail-value">{{ selected.stream === null ? '—' : selected.stream ? 'SSE 流式' : 'JSON' }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">创建时间</span><span class="task-detail-value">{{ formatDate(selected.created) }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">完成时间</span><span class="task-detail-value">{{ formatDate(selected.completed) }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">耗时</span><span class="task-detail-value">{{ formatDuration(selected.duration_ms) }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">扣除积分</span><strong class="numeric task-detail-value">{{ selected.charge_amount ?? '—' }}</strong>
          </div>
        </div>
        <el-alert
          v-if="selected.status === 'usage_unknown'" title="用量待核实，尚未结算，请保留调用 ID 联系客服。"
          type="warning" :closable="false" show-icon class="task-detail-error"
        />
        <el-alert v-if="selected.error_message" :title="selected.error_message" type="error" :closable="false" show-icon class="task-detail-error" />
        <h3 class="section-title">用量与计价</h3>
        <AppTable :data="usageRows" :pagination="false">
          <el-table-column prop="label" label="用量类型" min-width="110" />
          <el-table-column label="Token" min-width="100" align="right">
            <template #default="{ row }"><span class="numeric">{{ tokenCount(row.tokens) }}</span></template>
          </el-table-column>
          <el-table-column label="基准价 / 百万 Token" min-width="190" align="right">
            <template #default="{ row }"><span class="numeric">{{ row.price }}</span></template>
          </el-table-column>
        </AppTable>
        <p class="text-call-pricing">销售倍率 <strong class="numeric">{{ selected.sale_price.sale_multiplier }}</strong>；按本次调用的用量与计价快照结算。</p>
        <p v-if="selected.usage && selected.usage.input_tokens > selected.sale_price.long_context_threshold" class="text-call-pricing">本次输入超过 {{ tokenCount(selected.sale_price.long_context_threshold) }} Token：输入与缓存价格再乘 {{ selected.sale_price.long_context_input_multiplier }}，输出价格再乘 {{ selected.sale_price.long_context_output_multiplier }}。</p>
      </template>
      <template #footer><el-button @click="detailOpen = false">关闭</el-button></template>
    </el-dialog>
  </section>
</template>
