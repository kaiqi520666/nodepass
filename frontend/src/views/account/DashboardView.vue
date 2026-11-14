<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Connection, Refresh, Timer, TrendCharts, Wallet } from '@element-plus/icons-vue'
import { errorMessage, http } from '../../api/http'
import { useAuthStore } from '../../stores/auth'
import PageHeader from '../../components/PageHeader.vue'
const auth = useAuthStore()
const summary = ref<{ available: string; consumed: string; requests: number; today_consumed: string } | null>(null)
const loading = ref(false)
const error = ref('')
const statistics = computed(() => [
  { label: '可用积分', value: summary.value?.available ?? auth.user?.account.available, icon: Wallet, tone: 'primary' },
  { label: '已用积分', value: summary.value?.consumed ?? '—', icon: TrendCharts, tone: 'success' },
  { label: '请求次数', value: summary.value?.requests ?? '—', icon: Connection, tone: 'info' },
  { label: '今日消耗', value: summary.value?.today_consumed ?? '—', icon: Timer, tone: 'warning' },
])

async function load() {
  loading.value = true
  error.value = ''
  try {
    summary.value = (await http.get('/account/dashboard')).data
  } catch (cause) {
    error.value = errorMessage(cause)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section v-if="auth.user" aria-labelledby="dashboard-title">
    <PageHeader eyebrow="控制台" title="仪表盘" heading-id="dashboard-title">
      <el-button class="icon-button" :icon="Refresh" :loading="loading" aria-label="刷新统计" title="刷新统计" @click="load" />
    </PageHeader>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="form-alert" />
    <dl class="dashboard-statistics" aria-label="账户统计" :aria-busy="loading">
      <div v-for="statistic in statistics" :key="statistic.label" class="dashboard-statistic">
        <dt>
          <span>{{ statistic.label }}</span>
          <el-icon :size="20" :class="['statistic-icon', `statistic-icon-${statistic.tone}`]" aria-hidden="true"><component :is="statistic.icon" /></el-icon>
        </dt>
        <dd class="numeric" :aria-label="statistic.value === '—' ? '暂无数据' : undefined">{{ statistic.value }}</dd>
      </div>
    </dl>
  </section>
</template>
