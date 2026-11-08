<script setup lang="ts">
import { computed } from 'vue'
import { Connection, Timer, TrendCharts, Wallet } from '@element-plus/icons-vue'
import { useAuthStore } from '../../stores/auth'
import PageHeader from '../../components/PageHeader.vue'
const auth = useAuthStore()
const statistics = computed(() => [
  { label: '可用积分', value: auth.user?.account.available, icon: Wallet, tone: 'primary' },
  { label: '已用积分', value: '—', icon: TrendCharts, tone: 'success' },
  { label: '请求次数', value: '—', icon: Connection, tone: 'info' },
  { label: '今日消耗', value: '—', icon: Timer, tone: 'warning' },
])
</script>

<template>
  <section v-if="auth.user" aria-labelledby="dashboard-title">
    <PageHeader eyebrow="控制台" title="仪表盘" heading-id="dashboard-title" />
    <dl class="dashboard-statistics" aria-label="账户统计">
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
