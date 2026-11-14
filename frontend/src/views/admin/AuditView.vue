<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { CopyDocument, Refresh } from '@element-plus/icons-vue'
import { http, errorMessage } from '../../api/http'
import { copyText } from '../../utils/clipboard'
import { actionLabel, actionType, adminActionLabels, formatDateTime, targetTypeLabel } from '../../utils/admin'
import type { AdminAuditDetail, AdminAuditRow } from '../../types/admin'
import AppTable from '../../components/AppTable.vue'
import PageHeader from '../../components/PageHeader.vue'

const rows = ref<AdminAuditRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const error = ref('')
const detailOpen = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const selected = ref<AdminAuditDetail | null>(null)
const filters = reactive({
  actorId: undefined as number | undefined,
  action: '',
  targetType: '',
  targetId: '',
  dates: null as [Date, Date] | null,
})
const actionOptions = Object.entries(adminActionLabels).map(([value, label]) => ({ value, label }))
const targetTypeOptions = [
  { value: 'task', label: '生成任务' },
  { value: 'text_call', label: '文本调用' },
  { value: 'user', label: '用户' },
]

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, unknown> = {
      offset: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
    }
    if (filters.actorId != null) params.actor_user_id = filters.actorId
    if (filters.action) params.action = filters.action
    if (filters.targetType) params.target_type = filters.targetType
    if (filters.targetId.trim()) params.target_id = filters.targetId.trim()
    if (filters.dates) {
      params.created_from = Math.floor(filters.dates[0].getTime() / 1000)
      params.created_to = Math.floor(filters.dates[1].getTime() / 1000) + 86399
    }
    const response = await http.get<{ data: AdminAuditRow[]; total: number }>('/admin/audit-actions', { params })
    rows.value = response.data.data
    total.value = response.data.total
  } catch (cause) {
    error.value = errorMessage(cause)
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  page.value = 1
  load()
}

function resetFilters() {
  filters.actorId = undefined
  filters.action = ''
  filters.targetType = ''
  filters.targetId = ''
  filters.dates = null
  applyFilters()
}

async function openDetail(row: AdminAuditRow) {
  detailOpen.value = true
  detailLoading.value = true
  detailError.value = ''
  selected.value = null
  try {
    selected.value = (await http.get<AdminAuditDetail>(`/admin/audit-actions/${row.id}`)).data
  } catch (cause) {
    detailError.value = errorMessage(cause)
  } finally {
    detailLoading.value = false
  }
}

function formatSnapshot(snapshot: Record<string, unknown>) {
  return JSON.stringify(snapshot, null, 2)
}

async function copyTargetId(id: string) {
  await copyText(id, '目标 ID 已复制', '复制失败，请手动复制')
}

onMounted(load)
</script>

<template>
  <section aria-labelledby="audit-title">
    <PageHeader eyebrow="管理" title="操作审计" heading-id="audit-title">
      <el-button :icon="Refresh" class="icon-button" :loading="loading" aria-label="刷新操作审计" title="刷新操作审计" @click="load" />
    </PageHeader>

    <div class="filter-bar task-filters audit-filters">
      <div class="filter-actions">
        <el-input-number v-model="filters.actorId" :min="1" :controls="false" placeholder="操作人 ID" aria-label="筛选操作人 ID" />
        <el-select v-model="filters.action" class="task-filter-select" placeholder="全部动作" aria-label="筛选动作">
          <el-option label="全部动作" value="" />
          <el-option v-for="option in actionOptions" :key="option.value" :label="option.label" :value="option.value" />
        </el-select>
        <el-select v-model="filters.targetType" class="task-filter-select" placeholder="全部目标" aria-label="筛选目标类型">
          <el-option label="全部目标" value="" />
          <el-option v-for="option in targetTypeOptions" :key="option.value" :label="option.label" :value="option.value" />
        </el-select>
        <el-input v-model="filters.targetId" clearable placeholder="目标 ID" aria-label="筛选目标 ID" />
        <el-date-picker
          v-model="filters.dates" type="daterange" range-separator="至"
          start-placeholder="开始日期" end-placeholder="结束日期" aria-label="筛选操作日期"
        />
        <el-button type="primary" @click="applyFilters">筛选</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
    <AppTable
      v-model:page="page" v-model:page-size="pageSize" :data="rows" :total="total"
      :loading="loading" empty-text="暂无审计记录" empty-hint="管理员调账和异常处理动作会显示在这里。" @change="load"
    >
      <el-table-column label="时间" width="180">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作人" min-width="190">
        <template #default="{ row }"><span class="task-muted">{{ row.actor.email }}</span></template>
      </el-table-column>
      <el-table-column label="动作" width="145">
        <template #default="{ row }"><el-tag :type="actionType(row.action)" effect="plain">{{ actionLabel(row.action) }}</el-tag></template>
      </el-table-column>
      <el-table-column label="目标" min-width="220">
        <template #default="{ row }">
          <div>{{ targetTypeLabel(row.target_type) }}</div>
          <div class="task-id">
            <code>{{ row.target_id }}</code>
            <el-button :icon="CopyDocument" class="icon-button task-copy-button" :aria-label="`复制目标 ID ${row.target_id}`" @click="copyTargetId(row.target_id)" />
          </div>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="130">
        <template #default="{ row }"><span class="numeric">{{ row.amount ?? '—' }}</span></template>
      </el-table-column>
      <el-table-column label="原因" min-width="200">
        <template #default="{ row }"><span class="audit-reason">{{ row.reason }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="90" fixed="right">
        <template #default="{ row }"><el-button class="task-detail-button" @click="openDetail(row)">详情</el-button></template>
      </el-table-column>
      <template #mobile="{ rows }">
        <article v-for="row in rows" :key="row.id" class="mobile-card">
          <header class="mobile-card-header">
            <div class="mobile-card-title">
              <strong>{{ actionLabel(row.action) }}</strong>
              <span>{{ row.actor.email }} · {{ formatDateTime(row.created_at) }}</span>
            </div>
            <el-tag :type="actionType(row.action)" effect="plain">{{ targetTypeLabel(row.target_type) }}</el-tag>
          </header>
          <div class="task-id">
            <code>{{ row.target_id }}</code>
            <el-button :icon="CopyDocument" class="icon-button task-copy-button" :aria-label="`复制目标 ID ${row.target_id}`" @click="copyTargetId(row.target_id)" />
          </div>
          <dl class="mobile-card-grid">
            <div><dt>金额</dt><dd class="numeric">{{ row.amount ?? '—' }}</dd></div>
            <div><dt>账务流水</dt><dd>{{ row.credit_entry_id ?? '—' }}</dd></div>
            <div class="task-detail-item-wide"><dt>原因</dt><dd>{{ row.reason }}</dd></div>
          </dl>
          <footer class="mobile-card-actions">
            <el-button size="small" @click="openDetail(row)">详情</el-button>
          </footer>
        </article>
      </template>
    </AppTable>

    <el-drawer v-model="detailOpen" title="审计详情" size="min(620px, 92vw)" destroy-on-close>
      <el-skeleton v-if="detailLoading" :rows="5" animated />
      <el-alert v-else-if="detailError" :title="detailError" type="error" :closable="false" show-icon />
      <template v-else-if="selected">
        <div class="task-detail-summary">
          <div class="task-detail-item">
            <span class="task-detail-label">动作</span>
            <el-tag :type="actionType(selected.action)" effect="plain">{{ actionLabel(selected.action) }}</el-tag>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">操作人</span>
            <span class="task-detail-value">{{ selected.actor.email }}（ID {{ selected.actor.id }}）</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">目标类型</span>
            <span class="task-detail-value">{{ targetTypeLabel(selected.target_type) }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">目标 ID</span>
            <div class="task-id">
              <code>{{ selected.target_id }}</code>
              <el-button :icon="CopyDocument" class="icon-button task-copy-button" :aria-label="`复制目标 ID ${selected.target_id}`" @click="copyTargetId(selected.target_id)" />
            </div>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">金额</span>
            <span class="task-detail-value numeric">{{ selected.amount ?? '—' }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">账务流水</span>
            <span class="task-detail-value">{{ selected.credit_entry_id ?? '—' }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">操作时间</span>
            <span class="task-detail-value">{{ formatDateTime(selected.created_at) }}</span>
          </div>
          <div class="task-detail-item task-detail-item-wide">
            <span class="task-detail-label">原因</span>
            <span class="task-detail-value">{{ selected.reason }}</span>
          </div>
        </div>
        <h3 class="section-title">操作前快照</h3>
        <pre class="task-params">{{ formatSnapshot(selected.before_snapshot) }}</pre>
        <h3 class="section-title">操作后快照</h3>
        <pre class="task-params">{{ formatSnapshot(selected.after_snapshot) }}</pre>
      </template>
    </el-drawer>
  </section>
</template>
