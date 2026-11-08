<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Check, CopyDocument, Delete, Edit, Plus, Refresh, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { http, errorMessage } from '../../api/http'
import type { ApiKey } from '../../types'
import AppTable from '../../components/AppTable.vue'

const keys = ref<ApiKey[]>([])
const loading = ref(false)
const creating = ref(false)
const deleting = ref<number | null>(null)
const error = ref('')
const form = ref<FormInstance>()
const createOpen = ref(false)
const values = reactive<{ name: string; expires_at: string | null }>({ name: '', expires_at: null })
const editOpen = ref(false)
const editing = ref<ApiKey | null>(null)
const editValues = reactive<{ name: string; expires_at: string | null }>({ name: '', expires_at: null })
const editSaving = ref(false)
const secret = ref('')
const secretVisible = ref(false)
const secretTitle = ref('查看 API Key')
const rules = { name: [{ required: true, whitespace: true, message: '请输入 Key 名称', trigger: 'blur' }] }

function toApiDate(value: string | null) {
  return value ? new Date(value.replace(' ', 'T')).toISOString() : null
}

function fromApiDate(value: string | null) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date.toISOString().slice(0, 19).replace('T', ' ')
}

function dateTime(value: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN') : '永不过期'
}

function keyStatus(key: ApiKey) {
  if (!key.is_active) return { label: '已停用', type: 'info' as const }
  if (key.expires_at && new Date(key.expires_at).getTime() <= Date.now()) return { label: '已过期', type: 'warning' as const }
  return { label: '可用', type: 'success' as const }
}

function openCreate() {
  values.name = ''
  values.expires_at = null
  error.value = ''
  createOpen.value = true
}

async function load() {
  loading.value = true
  error.value = ''
  try { keys.value = (await http.get<{ data: ApiKey[] }>('/account/keys')).data.data }
  catch (cause) { error.value = errorMessage(cause) }
  finally { loading.value = false }
}

async function create() {
  if (creating.value || !await form.value?.validate().catch(() => false)) return
  creating.value = true
  error.value = ''
  try {
    const response = await http.post<ApiKey & { key: string }>('/account/keys', {
      name: values.name.trim(),
      expires_at: toApiDate(values.expires_at),
    })
    secret.value = response.data.key
    secretTitle.value = 'API Key 已创建'
    secretVisible.value = true
    createOpen.value = false
    await load()
  } catch (cause) { error.value = errorMessage(cause) }
  finally { creating.value = false }
}

async function getSecret(id: number) {
  return (await http.get<{ key: string }>(`/account/keys/${id}/secret`)).data.key
}

async function copySecret(key: ApiKey) {
  try {
    await navigator.clipboard.writeText(await getSecret(key.id))
    ElMessage.success('已复制 API Key')
  } catch (cause) { ElMessage.error(errorMessage(cause)) }
}

async function viewSecret(key: ApiKey) {
  try {
    secret.value = await getSecret(key.id)
    secretTitle.value = '查看 API Key'
    secretVisible.value = true
  } catch (cause) { ElMessage.error(errorMessage(cause)) }
}

function openEdit(key: ApiKey) {
  editing.value = key
  editValues.name = key.name
  editValues.expires_at = fromApiDate(key.expires_at)
  editOpen.value = true
}

async function saveEdit() {
  if (!editing.value || editSaving.value || !editValues.name.trim()) return
  editSaving.value = true
  try {
    const response = await http.put<ApiKey>(`/account/keys/${editing.value.id}`, {
      name: editValues.name.trim(),
      expires_at: toApiDate(editValues.expires_at),
    })
    Object.assign(editing.value, response.data)
    editOpen.value = false
    ElMessage.success('API Key 已更新')
  } catch (cause) { ElMessage.error(errorMessage(cause)) }
  finally { editSaving.value = false }
}

async function remove(key: ApiKey) {
  try {
    await ElMessageBox.confirm(`删除「${key.name}」后，该 Key 将立即失效且无法恢复。`, '删除 API Key', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch { return }
  deleting.value = key.id
  try {
    await http.delete(`/account/keys/${key.id}`)
    keys.value = keys.value.filter(item => item.id !== key.id)
    ElMessage.success('API Key 已删除')
  } catch (cause) { ElMessage.error(errorMessage(cause)) }
  finally { deleting.value = null }
}

async function copyVisibleSecret() {
  try { await navigator.clipboard.writeText(secret.value); ElMessage.success('已复制 API Key') }
  catch { ElMessage.error('复制失败，请手动选择') }
}

onMounted(load)
</script>

<template>
  <section aria-label="API Key">
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
    <div class="api-key-actions">
      <el-button type="primary" :icon="Plus" @click="openCreate">创建 Key</el-button>
      <el-tooltip content="刷新 API Key"><el-button :icon="Refresh" class="icon-button" :loading="loading" aria-label="刷新 API Key" @click="load" /></el-tooltip>
    </div>
    <AppTable :data="keys" :loading="loading" empty-text="暂无 API Key">
      <el-table-column prop="name" label="名称" min-width="150" />
      <el-table-column label="密钥" min-width="260">
        <template #default="{ row }">
          <div class="api-key-cell">
            <code>{{ row.key_prefix }}...</code>
            <span class="api-key-cell-actions">
              <el-tooltip content="查看">
                <el-button :icon="View" class="icon-button" :aria-label="`查看 ${row.name}`" @click="viewSecret(row)" />
              </el-tooltip>
              <el-tooltip content="复制">
                <el-button :icon="CopyDocument" class="icon-button" :aria-label="`复制 ${row.name}`" @click="copySecret(row)" />
              </el-tooltip>
            </span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }"><el-tag :type="keyStatus(row).type" effect="plain">{{ keyStatus(row).label }}</el-tag></template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="165">
        <template #default="{ row }">{{ dateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="过期时间" min-width="165">
        <template #default="{ row }">{{ dateTime(row.expires_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <div class="management-actions">
            <el-tooltip content="编辑"><el-button :icon="Edit" class="icon-button" :aria-label="`编辑 ${row.name}`" @click="openEdit(row)" /></el-tooltip>
            <el-tooltip content="删除"><el-button :icon="Delete" class="icon-button danger-icon" :loading="deleting === row.id" :aria-label="`删除 ${row.name}`" @click="remove(row)" /></el-tooltip>
          </div>
        </template>
      </el-table-column>
    </AppTable>
    <el-dialog v-model="createOpen" title="创建 API Key" width="520px" destroy-on-close>
      <el-form ref="form" :model="values" :rules="rules" label-position="top" @submit.prevent="create">
        <el-form-item label="Key 名称" prop="name">
          <el-input v-model="values.name" maxlength="80" placeholder="例如：本地开发" autocomplete="off" />
        </el-form-item>
        <el-form-item label="过期时间">
          <el-date-picker v-model="values.expires_at" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" placeholder="不设置过期时间" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createOpen = false">取消</el-button>
        <el-button type="primary" :icon="Plus" :loading="creating" @click="create">创建</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="secretVisible" :title="secretTitle" width="560px" destroy-on-close @closed="secret = ''">
      <el-alert title="密钥已加密保存，可随时查看或复制。" type="info" :closable="false" show-icon />
      <el-input :model-value="secret" type="textarea" :rows="3" readonly :aria-label="secretTitle === 'API Key 已创建' ? '新 API Key' : 'API Key'" class="api-key-secret" />
      <template #footer>
        <el-button :icon="CopyDocument" @click="copyVisibleSecret">复制</el-button>
        <el-button type="primary" :icon="Check" @click="secretVisible = false">完成</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="editOpen" title="编辑 API Key" width="520px" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="名称" required><el-input v-model="editValues.name" maxlength="80" /></el-form-item>
        <el-form-item label="过期时间"><el-date-picker v-model="editValues.expires_at" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" placeholder="不设置过期时间" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editOpen = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>
