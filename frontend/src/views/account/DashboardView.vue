<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Connection, Refresh, Timer, TrendCharts, Wallet } from '@element-plus/icons-vue'
import { errorMessage, http } from '../../api/http'
import { useAuthStore } from '../../stores/auth'
import PageHeader from '../../components/PageHeader.vue'

type DailyConsumption = { date: string; consumed: string }
type DashboardSummary = {
  available: string
  consumed: string
  requests: number
  today_consumed: string
  trend?: DailyConsumption[]
}
type Task = {
  id: string
  model: string
  model_name: string
  media_type: 'image' | 'video'
  status: string
  created: number
  billing_status: string
  frozen_amount: string
  consumed_amount: string
}

const auth = useAuthStore()
const summary = ref<DashboardSummary | null>(null)
const recent = ref<Task[]>([])
const loading = ref(false)
const recentLoading = ref(false)
const error = ref('')
const recentError = ref('')
const statistics = computed(() => [
  { label: '可用积分', value: summary.value?.available ?? auth.user?.account.available, icon: Wallet, tone: 'primary' },
  { label: '已用积分', value: summary.value?.consumed ?? '—', icon: TrendCharts, tone: 'success' },
  { label: '请求次数', value: summary.value?.requests ?? '—', icon: Connection, tone: 'info' },
  { label: '今日消耗', value: summary.value?.today_consumed ?? '—', icon: Timer, tone: 'warning' },
])
const trend = computed(() => summary.value?.trend ?? [])
const trendLabel = computed(() => trend.value
  .map(item => `${item.date} ${item.consumed} 积分`)
  .join('；'))
const sparkline = computed(() => {
  const values = trend.value.map(item => Number(item.consumed))
  const max = Math.max(...values, 0.00000001)
  const width = 240
  const height = 56
  const padding = 4
  const step = values.length > 1 ? (width - padding * 2) / (values.length - 1) : 0
  const points = values.map((value, index) => {
    const x = padding + index * step
    const y = height - padding - (value / max) * (height - padding * 2)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  return {
    points: points.join(' '),
    area: points.length ? `${padding},${height - padding} ${points.join(' ')} ${width - padding},${height - padding}` : '',
  }
})
const statusLabels: Record<string, string> = {
  queued: '排队中',
  submitting: '提交中',
  pending: '等待上游',
  processing: '生成中',
  transferring: '转存中',
  succeeded: '已完成',
  failed: '失败',
  submission_unknown: '待核实',
}

function statusLabel(status: string) {
  return statusLabels[status] || status
}

function statusType(status: string) {
  return status === 'succeeded' ? 'success' : status === 'failed' ? 'danger' : status === 'submission_unknown' ? 'warning' : 'info'
}

function formatDate(timestamp: number) {
  return new Date(timestamp * 1000).toLocaleString('zh-CN')
}

function billingAmount(task: Task) {
  return task.billing_status === 'held' ? task.frozen_amount : task.consumed_amount
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    summary.value = (await http.get<DashboardSummary>('/account/dashboard')).data
  } catch (cause) {
    error.value = errorMessage(cause)
  } finally {
    loading.value = false
  }
}

async function loadRecent() {
  recentLoading.value = true
  recentError.value = ''
  try {
    recent.value = (await http.get<{ data: Task[] }>('/account/tasks')).data.data.slice(0, 5)
  } catch (cause) {
    recentError.value = errorMessage(cause)
  } finally {
    recentLoading.value = false
  }
}

function refresh() {
  load()
  loadRecent()
}

onMounted(refresh)
</script>

<template>
  <section v-if="auth.user" aria-labelledby="dashboard-title">
    <PageHeader eyebrow="控制台" title="仪表盘" heading-id="dashboard-title">
      <el-button class="icon-button" :icon="Refresh" :loading="loading" aria-label="刷新统计" title="刷新统计" @click="refresh" />
    </PageHeader>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="form-alert" />
    <el-skeleton v-if="loading && !summary" :rows="3" animated class="dashboard-skeleton" />
    <template v-else>
      <dl class="dashboard-statistics" aria-label="账户统计" :aria-busy="loading">
        <div
          v-for="(statistic, index) in statistics" :key="statistic.label"
          :class="['dashboard-statistic', { 'dashboard-statistic-primary': index === 0 }]"
        >
          <dt>
            <span>{{ statistic.label }}</span>
            <el-icon :size="20" :class="['statistic-icon', `statistic-icon-${statistic.tone}`]" aria-hidden="true"><component :is="statistic.icon" /></el-icon>
          </dt>
          <dd class="numeric" :aria-label="statistic.value === '—' ? '暂无数据' : undefined">{{ statistic.value }}</dd>
        </div>
      </dl>

      <div class="dashboard-grid">
        <section class="dashboard-panel" aria-labelledby="trend-title">
          <div class="dashboard-panel-heading">
            <div>
              <h2 id="trend-title">近 7 日消耗</h2>
              <p>按北京时间统计已结算与文本扣费。</p>
            </div>
            <span v-if="trend.length" class="numeric">{{ summary?.today_consumed ?? '—' }} <small>今日</small></span>
          </div>
          <svg
            v-if="trend.length" class="dashboard-sparkline" viewBox="0 0 240 56"
            preserveAspectRatio="none" role="img" :aria-label="`近 7 日消耗：${trendLabel}`"
          >
            <polygon class="sparkline-area" :points="sparkline.area" />
            <polyline :points="sparkline.points" />
          </svg>
          <p v-else class="dashboard-panel-empty">近 7 日暂无消耗记录。</p>
          <div v-if="trend.length" class="dashboard-trend-axis">
            <span>{{ trend[0]?.date }}</span>
            <span>{{ trend[trend.length - 1]?.date }}</span>
          </div>
        </section>

        <section class="dashboard-panel" aria-labelledby="recent-title">
          <div class="dashboard-panel-heading">
            <div>
              <h2 id="recent-title">最近任务</h2>
              <p>最近 5 条生成任务。</p>
            </div>
            <RouterLink to="/console/tasks">查看全部</RouterLink>
          </div>
          <p v-if="recentError" class="dashboard-panel-empty">最近任务暂时不可用，请稍后刷新。</p>
          <el-skeleton v-else-if="recentLoading && !recent.length" :rows="4" animated />
          <div v-else-if="!recent.length" class="table-empty dashboard-recent-empty">
            <h2>暂无生成任务</h2>
            <p>通过开发者接口提交任务后，这里会显示最近记录。</p>
          </div>
          <ul v-else class="dashboard-recent">
            <li v-for="task in recent" :key="task.id">
              <div class="dashboard-recent-main">
                <strong>{{ task.model_name || task.model }}</strong>
                <span>{{ task.model }} · {{ formatDate(task.created) }}</span>
              </div>
              <el-tag :type="statusType(task.status)" effect="plain">{{ statusLabel(task.status) }}</el-tag>
              <span class="numeric dashboard-recent-amount">{{ billingAmount(task) }}</span>
            </li>
          </ul>
        </section>
      </div>
    </template>
  </section>
</template>
