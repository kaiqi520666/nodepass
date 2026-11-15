<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { CopyDocument, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, ElTabPane, ElTabs } from 'element-plus'
import { http, errorMessage } from '../../api/http'
import { copyText } from '../../utils/clipboard'
import {
  actionLabel,
  actionType,
  allowedActionLabel,
  formatDateTime,
  formatEpoch,
  formatSeconds,
  moneyScaled,
  resolutionLabel,
  statusLabel,
  statusType,
} from '../../utils/admin'
import type { AdminAuditRow, AdminExceptionSummary, AdminTaskRow, AdminTextRow } from '../../types/admin'
import AppTable from '../../components/AppTable.vue'
import PageHeader from '../../components/PageHeader.vue'

const summary = ref<AdminExceptionSummary | null>(null)
const summaryLoading = ref(false)
const summaryError = ref('')
const activeTab = ref<'tasks' | 'text'>('tasks')
const filters = reactive({
  status: '',
  idle: undefined as number | undefined,
  userId: undefined as number | undefined,
  id: '',
})
const taskStatusOptions = [
  { label: '全部状态', value: '' },
  { label: '排队中', value: 'queued' },
  { label: '提交中', value: 'submitting' },
  { label: '等待上游', value: 'pending' },
  { label: '生成中', value: 'processing' },
  { label: '转存中', value: 'transferring' },
  { label: '待核实', value: 'submission_unknown' },
  { label: '已完成', value: 'succeeded' },
  { label: '失败', value: 'failed' },
]
const textStatusOptions = [
  { label: '全部状态', value: '' },
  { label: '调用中', value: 'processing' },
  { label: '待核实', value: 'usage_unknown' },
  { label: '已结算', value: 'succeeded' },
  { label: '失败', value: 'failed' },
  { label: '人工已结算', value: 'settled_manually' },
  { label: '已关闭未扣费', value: 'closed_no_charge' },
]
const tasks = ref<AdminTaskRow[]>([])
const taskTotal = ref(0)
const taskPage = ref(1)
const taskPageSize = ref(20)
const taskLoading = ref(false)
const taskError = ref('')
const textCalls = ref<AdminTextRow[]>([])
const textTotal = ref(0)
const textPage = ref(1)
const textPageSize = ref(20)
const textLoading = ref(false)
const textError = ref('')
const detailOpen = ref(false)
const detailKind = ref<'task' | 'text'>('task')
const selectedTask = ref<AdminTaskRow | null>(null)
const selectedText = ref<AdminTextRow | null>(null)
const timeline = ref<AdminAuditRow[]>([])
const timelineLoading = ref(false)
const timelineError = ref('')
const actionOpen = ref(false)
const actionSaving = ref(false)
const actionError = ref('')
const actionKind = ref<'task' | 'text'>('task')
const actionName = ref('')
const actionTargetId = ref('')
const actionRequestId = ref('')
const actionReason = ref('')
const actionAmount = ref('')
const actionTask = ref<AdminTaskRow | null>(null)
const actionText = ref<AdminTextRow | null>(null)
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

const statistics = computed(() => {
  const taskSummary = summary.value?.tasks
  const textSummary = summary.value?.text_calls
  const stuck = taskSummary
    ? taskSummary.stuck_queued + taskSummary.stuck_submitting + taskSummary.stuck_processing + taskSummary.stuck_transferring
    : null
  return [
    { label: '待核实任务', value: taskSummary ? String(taskSummary.review_required) : '—' },
    { label: '卡住任务', value: stuck == null ? '—' : String(stuck) },
    { label: '待核实文本调用', value: textSummary ? String(textSummary.usage_unknown) : '—' },
    {
      label: '最久等待',
      value: summary.value?.oldest_waiting_seconds ? formatSeconds(summary.value.oldest_waiting_seconds) : '—',
    },
  ]
})
const currentLoading = computed(() => activeTab.value === 'tasks' ? taskLoading.value : textLoading.value)
const detailTitle = computed(() => detailKind.value === 'task' ? '生成任务详情' : '文本调用详情')
const actionTitle = computed(() => allowedActionLabel(actionName.value))
const actionHint = computed(() => {
  if (actionName.value === 'retry_submit') {
    return '恢复后将提交上游并可能产生费用；沿用原任务快照，请先核实配置已修复且该任务从未提交。'
  }
  if (actionName.value === 'release') {
    return `任务将标记为失败，冻结积分 ${actionTask.value?.frozen_amount ?? '—'} 退回可用余额，且不可恢复。`
  }
  if (actionName.value === 'manual_charge') {
    return `扣费后允许余额为负；当前可用余额 ${actionText.value?.user.available ?? '—'}。`
  }
  if (actionName.value === 'close_no_charge') {
    return '调用将关闭并保持零扣费；之后到达的用量只记录为迟到用量。'
  }
  if (actionName.value === 'mark_unknown') {
    return '调用将转为待核实；之后到达的可靠用量仍会自动结算。'
  }
  if (actionName.value === 'retry_transfer') {
    return '任务会重新进入转存队列，不会重新生成。'
  }
  return '任务会重新进入查询队列，不会再次提交上游。'
})

async function loadSummary() {
  summaryLoading.value = true
  summaryError.value = ''
  try {
    summary.value = (await http.get<AdminExceptionSummary>('/admin/exceptions/summary')).data
  } catch (cause) {
    summaryError.value = errorMessage(cause)
  } finally {
    summaryLoading.value = false
  }
}

async function loadTasks() {
  taskLoading.value = true
  taskError.value = ''
  try {
    const params: Record<string, unknown> = {
      offset: (taskPage.value - 1) * taskPageSize.value,
      limit: taskPageSize.value,
    }
    if (filters.status) params.status = filters.status
    if (filters.idle != null) params.min_idle_minutes = filters.idle
    if (filters.userId != null) params.user_id = filters.userId
    const id = filters.id.trim()
    if (id) {
      if (!uuidPattern.test(id)) {
        taskError.value = '请输入有效的任务 UUID'
        return
      }
      params.task_id = id
    }
    const response = await http.get<{ data: AdminTaskRow[]; total: number }>('/admin/exceptions/tasks', { params })
    tasks.value = response.data.data
    taskTotal.value = response.data.total
  } catch (cause) {
    taskError.value = errorMessage(cause)
  } finally {
    taskLoading.value = false
  }
}

async function loadTextCalls() {
  textLoading.value = true
  textError.value = ''
  try {
    const params: Record<string, unknown> = {
      offset: (textPage.value - 1) * textPageSize.value,
      limit: textPageSize.value,
    }
    if (filters.status) params.status = filters.status
    if (filters.idle != null) params.min_idle_minutes = filters.idle
    if (filters.userId != null) params.user_id = filters.userId
    const id = filters.id.trim()
    if (id) {
      if (!uuidPattern.test(id)) {
        textError.value = '请输入有效的调用 UUID'
        return
      }
      params.call_id = id
    }
    const response = await http.get<{ data: AdminTextRow[]; total: number }>('/admin/exceptions/text-calls', { params })
    textCalls.value = response.data.data
    textTotal.value = response.data.total
  } catch (cause) {
    textError.value = errorMessage(cause)
  } finally {
    textLoading.value = false
  }
}

function loadCurrent() {
  return activeTab.value === 'tasks' ? loadTasks() : loadTextCalls()
}

function applyFilters() {
  taskPage.value = 1
  textPage.value = 1
  loadCurrent()
}

function resetFilters() {
  filters.status = ''
  filters.idle = undefined
  filters.userId = undefined
  filters.id = ''
  applyFilters()
}

function refresh() {
  loadSummary()
  loadCurrent()
}

function openTaskDetail(row: AdminTaskRow) {
  selectedTask.value = row
  selectedText.value = null
  detailKind.value = 'task'
  detailOpen.value = true
  loadTimeline('task', row.id)
}

function openTextDetail(row: AdminTextRow) {
  selectedText.value = row
  selectedTask.value = null
  detailKind.value = 'text'
  detailOpen.value = true
  loadTimeline('text', row.id)
}

let timelineRequest = 0

async function loadTimeline(kind: 'task' | 'text', id: string) {
  const request = ++timelineRequest
  timelineLoading.value = true
  timelineError.value = ''
  timeline.value = []
  try {
    const response = await http.get<{ data: AdminAuditRow[]; total: number }>('/admin/audit-actions', {
      params: {
        target_type: kind === 'task' ? 'task' : 'text_call',
        target_id: id,
        limit: 50,
      },
    })
    if (request === timelineRequest) timeline.value = response.data.data
  } catch (cause) {
    if (request === timelineRequest) timelineError.value = errorMessage(cause)
  } finally {
    if (request === timelineRequest) timelineLoading.value = false
  }
}

function lastActionText(action: AdminTaskRow['last_action']) {
  return action ? `${actionLabel(action.action)} · ${action.actor_email}` : '—'
}

function allowedActionsText(actions: string[]) {
  return actions.length ? actions.map(allowedActionLabel).join('、') : '—'
}

async function copyId(id: string, label: string) {
  await copyText(id, `${label}已复制`, '复制失败，请手动复制')
}

function actionButtonType(action: string): '' | 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  if (action === 'release' || action === 'manual_charge') return 'danger'
  if (action === 'mark_unknown') return 'warning'
  if (action === 'retry_submit' || action === 'requery' || action === 'retry_transfer') return 'primary'
  return ''
}

function openAction(kind: 'task' | 'text', action: string) {
  const target = kind === 'task' ? selectedTask.value : selectedText.value
  if (!target) return
  actionKind.value = kind
  actionName.value = action
  actionTargetId.value = target.id
  actionTask.value = kind === 'task' ? selectedTask.value : null
  actionText.value = kind === 'text' ? selectedText.value : null
  actionRequestId.value = crypto.randomUUID()
  actionReason.value = ''
  actionAmount.value = ''
  actionError.value = ''
  actionOpen.value = true
}

async function submitAction() {
  if (actionSaving.value) return
  const reason = actionReason.value.trim()
  if (reason.length < 4) {
    actionError.value = '原因至少 4 个字符'
    return
  }
  let amount: string | undefined
  if (actionName.value === 'manual_charge') {
    const value = actionAmount.value.trim()
    const scaled = moneyScaled(value)
    if (scaled === null || scaled <= 0n) {
      actionError.value = '请输入大于零且最多八位小数的扣费金额'
      return
    }
    amount = value
  }
  if (actionName.value === 'release') {
    try {
      await ElMessageBox.confirm(
        `确认释放 ${actionTask.value?.frozen_amount ?? '—'} 冻结积分？任务将标记为失败且不可恢复。`,
        '释放冻结积分',
        { type: 'warning', confirmButtonText: '确认释放', cancelButtonText: '取消' },
      )
    } catch { return }
  }
  if (actionName.value === 'retry_submit') {
    try {
      await ElMessageBox.confirm(
        '确认恢复此任务？后台将按原任务快照提交上游，可能产生费用。',
        '确认恢复提交',
        { type: 'warning', confirmButtonText: '确认恢复', cancelButtonText: '取消' },
      )
    } catch { return }
  }
  if (actionName.value === 'manual_charge') {
    try {
      await ElMessageBox.confirm(
        `确认扣费 ${amount} 积分？当前可用余额 ${actionText.value?.user.available ?? '—'}，扣费后允许为负。`,
        '人工扣费',
        { type: 'warning', confirmButtonText: '确认扣费', cancelButtonText: '取消' },
      )
    } catch { return }
  }
  actionSaving.value = true
  actionError.value = ''
  try {
    const payload: Record<string, unknown> = {
      action: actionName.value,
      reason,
      request_id: actionRequestId.value,
    }
    if (amount !== undefined) payload.amount = amount
    const path = actionKind.value === 'task'
      ? `/admin/tasks/${actionTargetId.value}/resolve`
      : `/admin/text-calls/${actionTargetId.value}/resolve`
    await http.post(path, payload)
    actionOpen.value = false
    detailOpen.value = false
    ElMessage.success(`${actionTitle.value}已提交`)
    await Promise.all([loadSummary(), loadCurrent()])
  } catch (cause) {
    actionError.value = errorMessage(cause)
  } finally {
    actionSaving.value = false
  }
}

watch(activeTab, () => {
  filters.status = ''
  filters.id = ''
  filters.idle = undefined
  filters.userId = undefined
  taskPage.value = 1
  textPage.value = 1
  loadCurrent()
})

onMounted(() => {
  loadSummary()
  loadTasks()
})
</script>

<template>
  <section aria-labelledby="exceptions-title">
    <PageHeader eyebrow="管理" title="异常处理" heading-id="exceptions-title">
      <el-button
        :icon="Refresh" class="icon-button" :loading="summaryLoading || currentLoading"
        aria-label="刷新异常列表" title="刷新异常列表" @click="refresh"
      />
    </PageHeader>
    <el-alert v-if="summaryError" :title="summaryError" type="error" :closable="false" show-icon role="alert" class="form-alert" />

    <dl class="dashboard-statistics" aria-label="异常汇总" :aria-busy="summaryLoading">
      <div v-for="statistic in statistics" :key="statistic.label" class="dashboard-statistic">
        <dt>{{ statistic.label }}</dt>
        <dd class="numeric">{{ statistic.value }}</dd>
      </div>
    </dl>

    <el-tabs v-model="activeTab" class="task-log-tabs">
      <el-tab-pane label="生成任务" name="tasks">
        <div class="filter-bar task-filters exception-filters">
          <div class="filter-actions">
            <el-select v-model="filters.status" class="task-filter-select" placeholder="全部状态" aria-label="筛选任务状态">
              <el-option v-for="option in taskStatusOptions" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
            <el-input-number v-model="filters.idle" :min="0" :controls="false" placeholder="空闲至少(分钟)" aria-label="空闲至少多少分钟" />
            <el-input-number v-model="filters.userId" :min="1" :controls="false" placeholder="用户 ID" aria-label="筛选用户 ID" />
            <el-input v-model="filters.id" clearable placeholder="任务 UUID" aria-label="筛选任务 UUID" />
            <el-button type="primary" @click="applyFilters">筛选</el-button>
            <el-button @click="resetFilters">重置</el-button>
          </div>
        </div>
        <el-alert v-if="taskError" :title="taskError" type="error" :closable="false" show-icon role="alert" />
        <AppTable
          v-model:page="taskPage" v-model:page-size="taskPageSize" :data="tasks" :total="taskTotal"
          :loading="taskLoading" empty-text="暂无异常任务" empty-hint="卡住或待核实的生成任务会显示在这里。" @change="loadTasks"
        >
          <el-table-column label="任务 ID" min-width="220">
            <template #default="{ row }">
              <div class="task-id">
                <code>{{ row.id }}</code>
                <el-tooltip content="复制任务 ID">
                  <el-button :icon="CopyDocument" class="icon-button task-copy-button" :aria-label="`复制任务 ID ${row.id}`" @click="copyId(row.id, '任务 ID')" />
                </el-tooltip>
              </div>
              <div class="task-created">{{ formatEpoch(row.created) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="用户" min-width="190">
            <template #default="{ row }"><span class="task-muted">{{ row.user.email }}</span></template>
          </el-table-column>
          <el-table-column label="模型" min-width="150">
            <template #default="{ row }"><code>{{ row.model || '—' }}</code></template>
          </el-table-column>
          <el-table-column label="状态" width="105">
            <template #default="{ row }">
              <el-tag :type="statusType('task', row.status)" effect="plain">{{ statusLabel('task', row.status) }}</el-tag>
              <el-tag v-if="row.review_required" type="warning" effect="plain">待核实</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="冻结积分" width="130">
            <template #default="{ row }"><span class="numeric">{{ row.frozen_amount }}</span></template>
          </el-table-column>
          <el-table-column label="等待 / 空闲" width="150">
            <template #default="{ row }">
              <span>{{ formatSeconds(row.waiting_seconds) }}</span>
              <span class="task-created">空闲 {{ formatSeconds(row.idle_seconds) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="最近动作" min-width="190">
            <template #default="{ row }">
              <template v-if="row.last_action">
                <el-tag :type="actionType(row.last_action.action)" effect="plain">{{ actionLabel(row.last_action.action) }}</el-tag>
                <div class="task-created">{{ row.last_action.actor_email }} · {{ formatDateTime(row.last_action.created_at) }}</div>
              </template>
              <span v-else class="task-muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ row }"><el-button class="task-detail-button" @click="openTaskDetail(row)">详情</el-button></template>
          </el-table-column>
          <template #mobile="{ rows }">
            <article v-for="row in rows" :key="row.id" class="mobile-card">
              <header class="mobile-card-header">
                <div class="mobile-card-title">
                  <strong>{{ row.user.email }}</strong>
                  <span>{{ row.model || '—' }} · {{ row.media_type === 'image' ? '图片' : '视频' }}</span>
                </div>
                <div>
                  <el-tag :type="statusType('task', row.status)" effect="plain">{{ statusLabel('task', row.status) }}</el-tag>
                  <el-tag v-if="row.review_required" type="warning" effect="plain">待核实</el-tag>
                </div>
              </header>
              <div class="task-id">
                <code>{{ row.id }}</code>
                <el-button :icon="CopyDocument" class="icon-button task-copy-button" :aria-label="`复制任务 ID ${row.id}`" @click="copyId(row.id, '任务 ID')" />
              </div>
              <dl class="mobile-card-grid">
                <div><dt>冻结积分</dt><dd class="numeric">{{ row.frozen_amount }}</dd></div>
                <div><dt>等待 / 空闲</dt><dd>{{ formatSeconds(row.waiting_seconds) }} / {{ formatSeconds(row.idle_seconds) }}</dd></div>
                <div><dt>可执行</dt><dd>{{ allowedActionsText(row.allowed_actions) }}</dd></div>
                <div><dt>最近动作</dt><dd>{{ lastActionText(row.last_action) }}</dd></div>
              </dl>
              <footer class="mobile-card-actions">
                <el-button size="small" @click="openTaskDetail(row)">详情</el-button>
              </footer>
            </article>
          </template>
        </AppTable>
      </el-tab-pane>

      <el-tab-pane label="文本调用" name="text" lazy>
        <div class="filter-bar task-filters exception-filters">
          <div class="filter-actions">
            <el-select v-model="filters.status" class="task-filter-select" placeholder="全部状态" aria-label="筛选文本调用状态">
              <el-option v-for="option in textStatusOptions" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
            <el-input-number v-model="filters.idle" :min="0" :controls="false" placeholder="空闲至少(分钟)" aria-label="空闲至少多少分钟" />
            <el-input-number v-model="filters.userId" :min="1" :controls="false" placeholder="用户 ID" aria-label="筛选用户 ID" />
            <el-input v-model="filters.id" clearable placeholder="调用 UUID" aria-label="筛选调用 UUID" />
            <el-button type="primary" @click="applyFilters">筛选</el-button>
            <el-button @click="resetFilters">重置</el-button>
          </div>
        </div>
        <el-alert v-if="textError" :title="textError" type="error" :closable="false" show-icon role="alert" />
        <AppTable
          v-model:page="textPage" v-model:page-size="textPageSize" :data="textCalls" :total="textTotal"
          :loading="textLoading" empty-text="暂无异常文本调用" empty-hint="用量待核实或长时间未完成的调用会显示在这里。" @change="loadTextCalls"
        >
          <el-table-column label="调用 ID" min-width="220">
            <template #default="{ row }">
              <div class="task-id">
                <code>{{ row.id }}</code>
                <el-tooltip content="复制调用 ID">
                  <el-button :icon="CopyDocument" class="icon-button task-copy-button" :aria-label="`复制调用 ID ${row.id}`" @click="copyId(row.id, '调用 ID')" />
                </el-tooltip>
              </div>
              <div class="task-created">{{ formatEpoch(row.created) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="用户" min-width="190">
            <template #default="{ row }"><span class="task-muted">{{ row.user.email }}</span></template>
          </el-table-column>
          <el-table-column label="模型 / 接口" min-width="180">
            <template #default="{ row }"><div>{{ row.model || '—' }}</div><div class="task-created">{{ row.endpoint }}</div></template>
          </el-table-column>
          <el-table-column label="状态" width="135">
            <template #default="{ row }">
              <el-tag :type="statusType('text', row.status)" effect="plain">{{ statusLabel('text', row.status) }}</el-tag>
              <span v-if="row.has_late_usage" class="task-timeout">有迟到用量</span>
            </template>
          </el-table-column>
          <el-table-column label="扣费" width="130">
            <template #default="{ row }"><span class="numeric">{{ row.charge_amount ?? '—' }}</span></template>
          </el-table-column>
          <el-table-column label="等待 / 空闲" width="150">
            <template #default="{ row }">
              <span>{{ formatSeconds(row.waiting_seconds) }}</span>
              <span class="task-created">空闲 {{ formatSeconds(row.idle_seconds) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="最近动作" min-width="190">
            <template #default="{ row }">
              <template v-if="row.last_action">
                <el-tag :type="actionType(row.last_action.action)" effect="plain">{{ actionLabel(row.last_action.action) }}</el-tag>
                <div class="task-created">{{ row.last_action.actor_email }} · {{ formatDateTime(row.last_action.created_at) }}</div>
              </template>
              <span v-else class="task-muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ row }"><el-button class="task-detail-button" @click="openTextDetail(row)">详情</el-button></template>
          </el-table-column>
          <template #mobile="{ rows }">
            <article v-for="row in rows" :key="row.id" class="mobile-card">
              <header class="mobile-card-header">
                <div class="mobile-card-title">
                  <strong>{{ row.user.email }}</strong>
                  <span>{{ row.model || '—' }} · {{ row.endpoint }}</span>
                </div>
                <el-tag :type="statusType('text', row.status)" effect="plain">{{ statusLabel('text', row.status) }}</el-tag>
              </header>
              <div class="task-id">
                <code>{{ row.id }}</code>
                <el-button :icon="CopyDocument" class="icon-button task-copy-button" :aria-label="`复制调用 ID ${row.id}`" @click="copyId(row.id, '调用 ID')" />
              </div>
              <dl class="mobile-card-grid">
                <div><dt>扣费</dt><dd class="numeric">{{ row.charge_amount ?? '—' }}</dd></div>
                <div><dt>等待 / 空闲</dt><dd>{{ formatSeconds(row.waiting_seconds) }} / {{ formatSeconds(row.idle_seconds) }}</dd></div>
                <div><dt>可执行</dt><dd>{{ allowedActionsText(row.allowed_actions) }}</dd></div>
                <div><dt>最近动作</dt><dd>{{ lastActionText(row.last_action) }}</dd></div>
              </dl>
              <p v-if="row.has_late_usage" class="task-timeout">有迟到用量</p>
              <footer class="mobile-card-actions">
                <el-button size="small" @click="openTextDetail(row)">详情</el-button>
              </footer>
            </article>
          </template>
        </AppTable>
      </el-tab-pane>
    </el-tabs>

    <el-drawer v-model="detailOpen" :title="detailTitle" size="min(620px, 92vw)" destroy-on-close>
      <template v-if="selectedTask">
        <div class="task-detail-summary">
          <div class="task-detail-item task-detail-item-wide">
            <span class="task-detail-label">任务 ID</span>
            <div class="task-id">
              <code>{{ selectedTask.id }}</code>
              <el-button :icon="CopyDocument" class="icon-button task-copy-button" :aria-label="`复制任务 ID ${selectedTask.id}`" @click="copyId(selectedTask.id, '任务 ID')" />
            </div>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">用户</span>
            <span class="task-detail-value">{{ selectedTask.user.email }}（ID {{ selectedTask.user.id }}）</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">模型</span>
            <code class="task-detail-value">{{ selectedTask.model || '—' }}</code>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">状态</span>
            <el-tag :type="statusType('task', selectedTask.status)" effect="plain">{{ statusLabel('task', selectedTask.status) }}</el-tag>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">冻结积分</span>
            <span class="task-detail-value numeric">{{ selectedTask.frozen_amount }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">创建时间</span>
            <span class="task-detail-value">{{ formatEpoch(selectedTask.created) }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">最后更新</span>
            <span class="task-detail-value">{{ formatEpoch(selectedTask.updated) }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">上游状态</span>
            <span class="task-detail-value">{{ selectedTask.upstream_status || '—' }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">上游任务 ID</span>
            <span class="task-detail-value">{{ selectedTask.has_upstream_id ? '已保存' : '未保存' }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">就绪结果</span>
            <span class="task-detail-value">{{ selectedTask.has_ready_result ? '存在' : '无' }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">待核实标记</span>
            <span class="task-detail-value">{{ selectedTask.review_required ? '是' : '否' }}</span>
          </div>
          <div v-if="selectedTask.error_message" class="task-detail-item task-detail-item-wide">
            <span class="task-detail-label">暂停原因</span>
            <span class="task-detail-value">{{ selectedTask.error_message }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">人工处理结果</span>
            <span class="task-detail-value">{{ resolutionLabel(selectedTask.resolution) }}</span>
          </div>
        </div>
        <div class="admin-action-bar" aria-label="可执行动作">
          <el-button
            v-for="action in selectedTask.allowed_actions" :key="action"
            :type="actionButtonType(action)" :disabled="actionSaving" @click="openAction('task', action)"
          >{{ allowedActionLabel(action) }}</el-button>
          <span v-if="!selectedTask.allowed_actions.length" class="task-muted">当前没有可执行动作。</span>
        </div>
      </template>

      <template v-else-if="selectedText">
        <div class="task-detail-summary">
          <div class="task-detail-item task-detail-item-wide">
            <span class="task-detail-label">调用 ID</span>
            <div class="task-id">
              <code>{{ selectedText.id }}</code>
              <el-button :icon="CopyDocument" class="icon-button task-copy-button" :aria-label="`复制调用 ID ${selectedText.id}`" @click="copyId(selectedText.id, '调用 ID')" />
            </div>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">用户</span>
            <span class="task-detail-value">{{ selectedText.user.email }}（ID {{ selectedText.user.id }}）</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">模型</span>
            <span class="task-detail-value">{{ selectedText.model || '—' }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">接口</span>
            <code class="task-detail-value">{{ selectedText.endpoint }}</code>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">状态</span>
            <el-tag :type="statusType('text', selectedText.status)" effect="plain">{{ statusLabel('text', selectedText.status) }}</el-tag>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">扣费</span>
            <span class="task-detail-value numeric">{{ selectedText.charge_amount ?? '—' }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">可用余额</span>
            <span class="task-detail-value numeric">{{ selectedText.user.available ?? '—' }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">创建时间</span>
            <span class="task-detail-value">{{ formatEpoch(selectedText.created) }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">最后更新</span>
            <span class="task-detail-value">{{ formatEpoch(selectedText.updated) }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">迟到用量</span>
            <span class="task-detail-value">{{ selectedText.has_late_usage ? `已记录于 ${formatDateTime(selectedText.late_usage_at)}` : '无' }}</span>
          </div>
          <div class="task-detail-item">
            <span class="task-detail-label">人工处理结果</span>
            <span class="task-detail-value">{{ resolutionLabel(selectedText.resolution) }}</span>
          </div>
          <div v-if="selectedText.error_message" class="task-detail-item task-detail-item-wide">
            <span class="task-detail-label">错误信息</span>
            <span class="task-detail-value">{{ selectedText.error_message }}</span>
          </div>
        </div>
        <div class="admin-action-bar" aria-label="可执行动作">
          <el-button
            v-for="action in selectedText.allowed_actions" :key="action"
            :type="actionButtonType(action)" :disabled="actionSaving" @click="openAction('text', action)"
          >{{ allowedActionLabel(action) }}</el-button>
          <span v-if="!selectedText.allowed_actions.length" class="task-muted">当前没有可执行动作。</span>
        </div>
      </template>

      <h3 class="section-title">操作审计</h3>
      <el-skeleton v-if="timelineLoading" :rows="3" animated />
      <el-alert v-else-if="timelineError" :title="timelineError" type="error" :closable="false" show-icon />
      <el-timeline v-else-if="timeline.length" class="audit-timeline">
        <el-timeline-item v-for="action in timeline" :key="action.id" :timestamp="formatDateTime(action.created_at)" placement="top">
          <div class="audit-timeline-entry">
            <div>
              <el-tag :type="actionType(action.action)" effect="plain">{{ actionLabel(action.action) }}</el-tag>
              <strong>{{ action.actor.email }}</strong>
              <span v-if="action.amount" class="numeric">{{ action.amount }}</span>
            </div>
            <p>{{ action.reason }}</p>
          </div>
        </el-timeline-item>
      </el-timeline>
      <p v-else class="task-muted">暂无人工操作记录。</p>
    </el-drawer>

    <el-dialog v-model="actionOpen" :title="actionTitle" width="520px" destroy-on-close>
      <el-alert v-if="actionError" :title="actionError" type="error" :closable="false" show-icon class="form-alert" />
      <p class="admin-action-hint">{{ actionHint }}</p>
      <el-form label-position="top">
        <el-form-item v-if="actionName === 'manual_charge'" label="扣费金额" required>
          <el-input v-model="actionAmount" inputmode="decimal" placeholder="大于零，最多八位小数" aria-label="扣费金额" />
        </el-form-item>
        <el-form-item label="原因" required>
          <el-input
            v-model="actionReason" type="textarea" :rows="3" maxlength="240" show-word-limit
            placeholder="至少 4 个字符，填写核实依据或上游账单信息" aria-label="操作原因"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="actionOpen = false">取消</el-button>
        <el-button :type="actionButtonType(actionName)" :loading="actionSaving" @click="submitAction">确认</el-button>
      </template>
    </el-dialog>
  </section>
</template>
