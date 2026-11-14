<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { CopyDocument, Download, Refresh, Search, View } from '@element-plus/icons-vue'
import { ElImageViewer, ElTabPane, ElTabs } from 'element-plus'
import { errorMessage, http } from '../../api/http'
import { copyText } from '../../utils/clipboard'
import PageHeader from '../../components/PageHeader.vue'
import AppTable from '../../components/AppTable.vue'
import TextCalls from './TextCalls.vue'

type Task = {
  id: string
  status: string
  model: string
  model_name: string
  media_type: 'image' | 'video'
  created: number
  billing_status: string
  frozen_amount: string
  consumed_amount: string
  completed: number | null
  duration_ms: number | null
  timed_out: boolean
  request_params: Record<string, unknown>
  upstream_status: string | null
  error_message: string | null
  data: { url: string }[]
}

const tasks = ref<Task[]>([])
const activeTab = ref('generation')
const textCalls = ref<InstanceType<typeof TextCalls> | null>(null)
const loading = ref(false)
const error = ref('')
const detailOpen = ref(false)
const selected = ref<Task | null>(null)
const imageViewerOpen = ref(false)
const imagePreviewUrls = ref<string[]>([])
const imagePreviewIndex = ref(0)
const videoViewerOpen = ref(false)
const videoPreviewUrl = ref('')
const videoPreviewTitle = ref('视频预览')
const filters = reactive({
  query: '',
  mediaType: 'all',
  status: 'all',
  model: 'all',
  dates: null as [Date, Date] | null,
})

const statusOptions = [
  { label: '全部状态', value: 'all' },
  { label: '排队中', value: 'queued' },
  { label: '提交中', value: 'submitting' },
  { label: '等待上游', value: 'pending' },
  { label: '生成中', value: 'processing' },
  { label: '转存中', value: 'transferring' },
  { label: '已完成', value: 'succeeded' },
  { label: '失败', value: 'failed' },
  { label: '待核实', value: 'submission_unknown' },
]

const modelOptions = computed(() => [...new Set(tasks.value.map(task => task.model))])
const filteredTasks = computed(() => {
  const query = filters.query.trim().toLowerCase()
  return tasks.value.filter(task => {
    const matchesQuery = !query || task.id.toLowerCase().includes(query)
    const matchesType = filters.mediaType === 'all' || task.media_type === filters.mediaType
    const matchesStatus = filters.status === 'all' || task.status === filters.status
    const matchesModel = filters.model === 'all' || task.model === filters.model
    const created = task.created * 1000
    const matchesDates = !filters.dates
      || (created >= filters.dates[0].getTime() && created <= filters.dates[1].getTime())
    return matchesQuery && matchesType && matchesStatus && matchesModel && matchesDates
  })
})

function statusLabel(status: string) {
  return statusOptions.find(option => option.value === status)?.label || status
}

function statusType(status: string) {
  return status === 'succeeded' ? 'success' : status === 'failed' ? 'danger' : status === 'submission_unknown' ? 'warning' : 'info'
}

function billingStatusLabel(status: string) {
  return {
    held: '积分冻结中',
    settled: '已结算',
    released: '已释放',
    refunded: '已退款',
  }[status] || '未知'
}

function billingAmount(task: Task) {
  return task.billing_status === 'held' ? task.frozen_amount : task.consumed_amount
}

function billingShortLabel(status: string) {
  return {
    held: '冻结中',
    settled: '已结算',
    released: '已释放',
    refunded: '已释放',
  }[status] || '未知'
}

function billingStatusType(status: string) {
  return {
    held: 'warning',
    settled: 'success',
    released: 'info',
    refunded: 'info',
  }[status] || 'info'
}

function mediaTypeLabel(type: Task['media_type']) {
  return type === 'video' ? '视频' : '图片'
}

function formatDate(timestamp: number | null) {
  return timestamp ? new Date(timestamp * 1000).toLocaleString('zh-CN') : '—'
}

function formatDuration(duration: number | null) {
  if (duration === null) return '—'
  const seconds = Math.floor(duration / 1000)
  if (seconds < 60) return `${seconds} 秒`
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
}

function formatParams(params: Record<string, unknown>) {
  return JSON.stringify(params, null, 2)
}

function showDetails(task: Task) {
  selected.value = task
  detailOpen.value = true
}

function showImage(task: Task, index: number) {
  imagePreviewUrls.value = task.data.map(result => result.url)
  imagePreviewIndex.value = index
  imageViewerOpen.value = true
}

function showVideo(task: Task, index: number) {
  videoPreviewUrl.value = task.data[index]?.url || ''
  videoPreviewTitle.value = `${task.model_name || task.model} · 视频预览`
  videoViewerOpen.value = Boolean(videoPreviewUrl.value)
}

async function copyTaskId(id: string) {
  await copyText(id, '任务 ID 已复制', '复制失败，请手动复制任务 ID')
}

function resetFilters() {
  filters.query = ''
  filters.mediaType = 'all'
  filters.status = 'all'
  filters.model = 'all'
  filters.dates = null
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    tasks.value = (await http.get<{ data: Task[] }>('/account/tasks')).data.data
  } catch (cause) {
    error.value = errorMessage(cause)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section aria-labelledby="tasks-title">
    <PageHeader eyebrow="控制台" title="任务日志" heading-id="tasks-title">
      <el-button
        class="icon-button" :icon="Refresh"
        :loading="activeTab === 'generation' ? loading : textCalls?.loading"
        aria-label="刷新日志" title="刷新日志"
        @click="activeTab === 'generation' ? load() : textCalls?.refresh()"
      />
    </PageHeader>
    <el-tabs v-model="activeTab" class="task-log-tabs" aria-label="日志分类">
      <el-tab-pane label="生成任务" name="generation">
        <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="form-alert" />
        <div class="filter-bar task-filters">
          <el-input v-model="filters.query" clearable :prefix-icon="Search" placeholder="搜索任务 ID" aria-label="搜索任务 ID" />
          <el-segmented v-model="filters.mediaType" :options="[{ label: '全部', value: 'all' }, { label: '图片', value: 'image' }, { label: '视频', value: 'video' }]" />
          <el-select v-model="filters.status" aria-label="筛选状态" class="task-filter-select">
            <el-option v-for="option in statusOptions" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
          <el-select v-model="filters.model" aria-label="筛选模型" class="task-filter-select" placeholder="全部模型">
            <el-option label="全部模型" value="all" />
            <el-option v-for="model in modelOptions" :key="model" :label="model" :value="model" />
          </el-select>
          <el-date-picker
            v-model="filters.dates" type="daterange" range-separator="至"
            start-placeholder="开始日期" end-placeholder="结束日期" aria-label="筛选日期"
          />
          <el-button @click="resetFilters">重置</el-button>
        </div>
        <AppTable :data="filteredTasks" :loading="loading" empty-text="暂无匹配的任务" empty-hint="调整筛选条件后重试；生成任务通过开发者接口提交。">
          <el-table-column label="任务信息" min-width="300">
            <template #default="{ row }">
              <div class="task-id">
                <code>{{ row.id }}</code>
                <el-tooltip content="复制任务 ID">
                  <el-button :icon="CopyDocument" class="icon-button task-copy-button" :aria-label="`复制任务 ID ${row.id}`" @click="copyTaskId(row.id)" />
                </el-tooltip>
              </div>
              <div class="task-created">{{ formatDate(row.created) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="90">
            <template #default="{ row }">
              <el-tag :type="row.media_type === 'video' ? 'warning' : 'success'" effect="plain">
                {{ mediaTypeLabel(row.media_type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="使用模型" min-width="190">
            <template #default="{ row }"><code>{{ row.model }}</code></template>
          </el-table-column>
          <el-table-column label="状态" width="130">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" effect="plain">{{ statusLabel(row.status) }}</el-tag>
              <span v-if="row.timed_out" class="task-timeout">曾超时</span>
            </template>
          </el-table-column>
          <el-table-column label="耗时" width="120">
            <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
          </el-table-column>
          <el-table-column label="扣除积分" width="250" align="center">
            <template #default="{ row }">
              <div class="task-billing">
                <strong class="numeric">{{ billingAmount(row) }}</strong>
                <el-tag :type="billingStatusType(row.billing_status)" effect="plain">{{ billingShortLabel(row.billing_status) }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" min-width="190" fixed="right" align="right">
            <template #default="{ row }">
              <div class="task-actions">
                <template v-if="row.data.length">
                  <el-tooltip v-for="(result, index) in row.data" :key="result.url" :content="`${row.media_type === 'video' ? '查看视频' : '查看图片'}${row.data.length > 1 ? ` ${Number(index) + 1}` : ''}`">
                    <button
                      v-if="row.media_type === 'image'"
                      type="button"
                      class="task-action-link"
                      :aria-label="`查看图片${row.data.length > 1 ? ` ${Number(index) + 1}` : ''}`"
                      @click="showImage(row, Number(index))"
                    >
                      <el-icon><View /></el-icon>
                    </button>
                    <button
                      v-else
                      type="button"
                      class="task-action-link"
                      :aria-label="`查看视频${row.data.length > 1 ? ` ${Number(index) + 1}` : ''}`"
                      @click="showVideo(row, Number(index))"
                    >
                      <el-icon><View /></el-icon>
                    </button>
                  </el-tooltip>
                  <el-tooltip v-for="(result, index) in row.data" :key="`download-${result.url}`" content="下载">
                    <a class="task-action-link" :href="result.url" :download="`${row.id}-${Number(index) + 1}`" aria-label="下载">
                      <el-icon><Download /></el-icon>
                    </a>
                  </el-tooltip>
                </template>
                <el-tooltip content="详情">
                  <el-button class="task-detail-button" @click="showDetails(row)">详情</el-button>
                </el-tooltip>
              </div>
            </template>
          </el-table-column>
        </AppTable>
      </el-tab-pane>
      <el-tab-pane label="文本调用" name="text" lazy>
        <TextCalls ref="textCalls" />
      </el-tab-pane>
    </el-tabs>
    <el-dialog v-model="detailOpen" title="任务详情" width="720px" destroy-on-close>
      <template v-if="selected">
        <div class="task-detail-summary">
          <div class="task-detail-item task-detail-item-wide">
            <span class="task-detail-label">任务 ID</span>
            <code class="task-detail-value">{{ selected.id }}</code>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">类型</span>
            <span class="task-detail-value">{{ mediaTypeLabel(selected.media_type) }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">模型</span>
            <span class="task-detail-value">{{ selected.model_name || selected.model }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">状态</span>
            <el-tag :type="statusType(selected.status)" effect="plain">{{ statusLabel(selected.status) }}</el-tag>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">计费状态</span>
            <span class="task-detail-value">{{ billingStatusLabel(selected.billing_status) }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">创建时间</span>
            <span class="task-detail-value">{{ formatDate(selected.created) }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">完成时间</span>
            <span class="task-detail-value">{{ formatDate(selected.completed) }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">耗时</span>
            <span class="task-detail-value">{{ formatDuration(selected.duration_ms) }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">扣除积分</span>
            <div class="task-billing task-detail-value">
              <strong class="numeric">{{ billingAmount(selected) }}</strong>
              <el-tag :type="billingStatusType(selected.billing_status)" effect="plain">{{ billingShortLabel(selected.billing_status) }}</el-tag>
            </div>
          </div>
        </div>
        <el-alert v-if="selected.error_message" :title="selected.error_message" type="error" :closable="false" show-icon class="task-detail-error" />
        <h3 class="section-title">请求参数</h3>
        <pre class="task-params">{{ formatParams(selected.request_params) }}</pre>
      </template>
      <template #footer><el-button @click="detailOpen = false">关闭</el-button></template>
    </el-dialog>
    <ElImageViewer
      v-if="imageViewerOpen"
      :url-list="imagePreviewUrls"
      :initial-index="imagePreviewIndex"
      @close="imageViewerOpen = false"
    />
    <el-dialog
      v-model="videoViewerOpen"
      :title="videoPreviewTitle"
      width="min(960px, 90vw)"
      class="video-preview-dialog"
      destroy-on-close
    >
      <video
        v-if="videoPreviewUrl"
        class="task-video-player"
        :src="videoPreviewUrl"
        controls
        playsinline
        preload="metadata"
      />
    </el-dialog>
  </section>
</template>
