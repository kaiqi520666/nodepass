<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Check, Close, Connection, Key, Link, Refresh } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { errorMessage, http } from '../../api/http'
import PageHeader from '../../components/PageHeader.vue'

type OssSettings = {
  endpoint: string
  region: string
  bucket: string
  access_key_id: string
  public_base_url: string
  object_prefix: string
  is_active: boolean
  has_credentials: boolean
}

const ossFormRef = ref<FormInstance>()
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const error = ref('')
const ossFormError = ref('')
const ossForm = ref({
  endpoint: '',
  region: '',
  bucket: '',
  access_key_id: '',
  access_key_secret: '',
  public_base_url: '',
  object_prefix: 'generated',
  is_active: false,
  has_credentials: false,
})

const rules: FormRules = {
  endpoint: [{ required: true, message: '请输入 OSS Endpoint', trigger: 'blur' }],
  region: [{ required: true, message: '请输入 OSS Region', trigger: 'blur' }],
  bucket: [{ required: true, message: '请输入 Bucket', trigger: 'blur' }],
  access_key_id: [{ required: true, message: '请输入 AccessKey ID', trigger: 'blur' }],
  public_base_url: [{ required: true, message: '请输入结果访问域名', trigger: 'blur' }],
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await http.get<OssSettings>('/admin/settings/oss')
    Object.assign(ossForm.value, data, { access_key_secret: '' })
  } catch (cause) { error.value = errorMessage(cause) }
  finally { loading.value = false }
}

async function save() {
  if (!await ossFormRef.value?.validate().catch(() => false)) return
  saving.value = true
  ossFormError.value = ''
  try {
    const { has_credentials: _hasCredentials, ...settings } = ossForm.value
    await http.put('/admin/settings/oss', {
      ...settings,
      access_key_secret: settings.access_key_secret || undefined,
    })
    ossForm.value.access_key_secret = ''
    ElMessage.success('OSS 设置已保存')
    await load()
  } catch (cause) { ossFormError.value = errorMessage(cause) }
  finally { saving.value = false }
}

async function testOss() {
  testing.value = true
  try {
    const { data } = await http.post<{ ok: boolean; message: string }>('/admin/settings/oss/test')
    if (data.ok) ElMessage.success(data.message)
    else ElMessage.warning(data.message)
  } catch (cause) { ElMessage.error(errorMessage(cause)) }
  finally { testing.value = false }
}

onMounted(load)
</script>

<template>
  <section aria-labelledby="system-settings-title">
    <PageHeader eyebrow="管理" title="系统设置" heading-id="system-settings-title">
      <el-button class="icon-button" :icon="Refresh" :loading="loading" aria-label="刷新设置" title="刷新设置" @click="load" />
    </PageHeader>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="form-alert" />
    <el-card class="settings-card" shadow="never">
      <template #header><div class="settings-card-title"><span>阿里云 OSS</span><el-tag :type="ossForm.is_active ? 'success' : 'info'" effect="plain">{{ ossForm.is_active ? '已启用' : '未启用' }}</el-tag></div></template>
      <el-alert title="生成结果会统一转存到 OSS，访问地址使用下面配置的独立域名。" type="info" :closable="false" show-icon class="form-alert" />
      <el-alert v-if="!ossForm.has_credentials && !ossForm.access_key_secret" title="尚未配置完整凭证，首次保存时必须填写 AccessKey Secret。" type="warning" :closable="false" show-icon class="form-alert" />
      <el-alert v-if="ossFormError" :title="ossFormError" type="error" :closable="false" show-icon class="form-alert" />
      <el-form ref="ossFormRef" :model="ossForm" :rules="rules" label-position="top" @submit.prevent="save">
        <div class="management-form-grid">
          <el-form-item label="Endpoint" prop="endpoint"><el-input v-model="ossForm.endpoint" :prefix-icon="Link" placeholder="oss-cn-hongkong.aliyuncs.com" /></el-form-item>
          <el-form-item label="Region" prop="region"><el-input v-model="ossForm.region" placeholder="cn-hongkong" /></el-form-item>
          <el-form-item label="Bucket" prop="bucket"><el-input v-model="ossForm.bucket" /></el-form-item>
          <el-form-item label="对象前缀"><el-input v-model="ossForm.object_prefix" /></el-form-item>
        </div>
        <div class="management-form-grid">
          <el-form-item label="AccessKey ID" prop="access_key_id"><el-input v-model="ossForm.access_key_id" :prefix-icon="Key" autocomplete="off" /></el-form-item>
          <el-form-item label="AccessKey Secret"><el-input v-model="ossForm.access_key_secret" :prefix-icon="Key" type="password" show-password autocomplete="new-password" placeholder="留空表示保持原凭证" /></el-form-item>
        </div>
        <el-form-item label="结果访问域名" prop="public_base_url"><el-input v-model="ossForm.public_base_url" :prefix-icon="Link" placeholder="https://image.nodepass.net" /></el-form-item>
        <el-form-item label="状态"><el-switch v-model="ossForm.is_active" active-text="启用" inactive-text="停用" /></el-form-item>
        <div class="settings-actions">
          <el-button :icon="Close" :disabled="saving || testing" @click="load">重置</el-button>
          <el-button :icon="Connection" :loading="testing" :disabled="saving" @click="testOss">测试 OSS</el-button>
          <el-button type="primary" :icon="Check" :loading="saving" :disabled="testing" @click="save">保存设置</el-button>
        </div>
      </el-form>
    </el-card>
  </section>
</template>
