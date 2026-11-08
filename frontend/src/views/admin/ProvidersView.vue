<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Check, Close, Edit, Key, Link, Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { http, errorMessage } from '../../api/http'
import type { Provider } from '../../types/catalog'
import AppTable from '../../components/AppTable.vue'
import PageHeader from '../../components/PageHeader.vue'

const providers = ref<Provider[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const formError = ref('')
const dialogOpen = ref(false)
const editingId = ref<number>()
const formRef = ref<FormInstance>()
const emptyForm = () => ({
  name: '', adapter_key: 'cangyuan_image', base_url: 'https://direct-api.cangyuansuanli.cn',
  api_key: '', is_active: true, request_config: { timeout_seconds: 60, poll_interval_seconds: 5 },
})
const form = reactive(emptyForm())
const rules: FormRules = {
  name: [{ required: true, whitespace: true, message: '请输入供应商名称', trigger: 'blur' }],
  api_key: [{
    validator: (_rule, value, callback) => {
      if (!editingId.value && !value.trim()) callback(new Error('请输入 API Key'))
      else if (value && /\s/.test(value.trim())) callback(new Error('API Key 不能包含空白字符'))
      else callback()
    }, trigger: 'blur',
  }],
}

async function load() {
  loading.value = true
  error.value = ''
  try { providers.value = (await http.get<{ data: Provider[] }>('/admin/providers')).data.data }
  catch (cause) { error.value = errorMessage(cause) }
  finally { loading.value = false }
}

function edit(provider?: Provider) {
  editingId.value = provider?.id
  Object.assign(form, emptyForm(), provider ? {
    name: provider.name, adapter_key: provider.adapter_key, base_url: provider.base_url,
    is_active: provider.is_active, request_config: { ...provider.request_config },
  } : {})
  formError.value = ''
  dialogOpen.value = true
}

async function save() {
  if (!await formRef.value?.validate().catch(() => false)) return
  saving.value = true
  formError.value = ''
  try {
    const payload = { ...form, api_key: form.api_key.trim() || undefined }
    if (editingId.value) await http.put(`/admin/providers/${editingId.value}`, payload)
    else await http.post('/admin/providers', payload)
    form.api_key = ''
    dialogOpen.value = false
    ElMessage.success('供应商已保存')
    await load()
  } catch (cause) { formError.value = errorMessage(cause) }
  finally { saving.value = false }
}
onMounted(load)
</script>

<template>
  <section aria-labelledby="providers-title">
    <PageHeader eyebrow="管理" title="供应商配置" heading-id="providers-title">
      <div class="management-actions">
        <el-button :icon="Refresh" class="icon-button" :loading="loading" aria-label="刷新供应商" title="刷新供应商" @click="load" />
        <el-button type="primary" :icon="Plus" @click="edit()">新增供应商</el-button>
      </div>
    </PageHeader>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
    <AppTable :data="providers" :loading="loading" empty-text="暂无供应商">
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column prop="base_url" label="接口地址" min-width="260" />
        <el-table-column label="密钥" width="100"><template #default="{ row }"><el-tag :type="row.has_credentials ? 'success' : 'warning'" effect="plain">{{ row.has_credentials ? '已配置' : '未配置' }}</el-tag></template></el-table-column>
        <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'" effect="plain">{{ row.is_active ? '已启用' : '已停用' }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="76" fixed="right">
          <template #default="{ row }"><el-button :icon="Edit" class="icon-button" :aria-label="`编辑 ${row.name}`" title="编辑供应商" @click="edit(row)" /></template>
        </el-table-column>
    </AppTable>
    <el-dialog v-model="dialogOpen" :title="editingId ? '编辑供应商' : '新增供应商'" width="640px" destroy-on-close :close-on-click-modal="false" :close-on-press-escape="!saving" :show-close="!saving" @closed="form.api_key = ''">
      <el-alert v-if="formError" :title="formError" type="error" :closable="false" show-icon class="form-alert" role="alert" />
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="save">
        <el-form-item label="供应商名称" prop="name"><el-input v-model="form.name" maxlength="120" /></el-form-item>
        <div class="management-form-grid">
          <el-form-item label="接入方式"><el-select v-model="form.adapter_key"><el-option label="沧元图片" value="cangyuan_image" /></el-select></el-form-item>
          <el-form-item label="状态"><el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" /></el-form-item>
        </div>
        <el-form-item label="接口地址"><el-input v-model="form.base_url" :prefix-icon="Link" readonly /></el-form-item>
        <el-form-item :label="editingId ? '替换 API Key（留空保留）' : 'API Key'" prop="api_key">
          <el-input v-model="form.api_key" :prefix-icon="Key" type="password" show-password autocomplete="new-password" maxlength="4096" />
        </el-form-item>
        <div class="management-form-grid">
          <el-form-item label="请求超时（秒）"><el-input-number v-model="form.request_config.timeout_seconds" :min="10" :max="600" :precision="0" /></el-form-item>
          <el-form-item label="查询间隔（秒）"><el-input-number v-model="form.request_config.poll_interval_seconds" :min="5" :max="60" :precision="0" /></el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button :icon="Close" :disabled="saving" @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :icon="Check" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>
