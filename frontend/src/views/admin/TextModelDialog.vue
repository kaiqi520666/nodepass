<script setup lang="ts">
import { reactive, ref, toRaw } from 'vue'
import { Check, Close } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { errorMessage, http } from '../../api/http'
import type { ManagedTextModel, Provider } from '../../types/catalog'

const props = defineProps<{ model?: ManagedTextModel; providers: Provider[] }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const open = ref(true)
const saving = ref(false)
const error = ref('')
const formRef = ref<FormInstance>()
const models = ['gpt-6.1-sol']
const priceFields = [
  { key: 'sale_multiplier', label: '销售倍率' },
  { key: 'cost_multiplier', label: '上游成本倍率' },
  { key: 'input_price', label: '输入基准价 / 百万 token' },
  { key: 'output_price', label: '输出基准价 / 百万 token' },
  { key: 'cache_read_price', label: '缓存命中基准价 / 百万 token' },
  { key: 'long_context_input_multiplier', label: '长上下文输入与缓存倍率' },
  { key: 'long_context_output_multiplier', label: '长上下文输出倍率' },
] as const
const form = reactive({
  public_id: '', display_name: '', media_type: 'text' as const,
  provider_id: undefined as number | undefined, upstream_model_id: models[0]!,
  capabilities: { family: 'gpt', input_modalities: ['text', 'image'] },
  pricing_dimensions: [], prices: [], is_active: false,
  token_price: { input_price: '2', output_price: '10', cache_read_price: '0.1', cost_multiplier: '0.2', sale_multiplier: '0.2', long_context_threshold: 272000, long_context_input_multiplier: '2', long_context_output_multiplier: '1.5' },
  ...(props.model ? structuredClone(toRaw(props.model)) : {}),
})
const rules: FormRules = {
  public_id: [{ required: true, pattern: /^[A-Za-z0-9][A-Za-z0-9._-]*$/, message: '请输入有效的本站模型 ID', trigger: 'blur' }],
  display_name: [{ required: true, whitespace: true, message: '请输入显示名称', trigger: 'blur' }],
  provider_id: [{ required: true, message: '请选择供应商', trigger: 'change' }],
}
const priceRules = [{ required: true, pattern: /^(0|[1-9]\d{0,15})(\.\d{1,8})?$/, message: '请输入非负数，最多八位小数', trigger: 'blur' }]
async function save() {
  if (!await formRef.value?.validate().catch(() => false)) return
  saving.value = true
  error.value = ''
  try {
    const { id: _id, ...payload } = { id: props.model?.id, ...form }
    if (props.model) await http.put(`/admin/models/${props.model.id}`, payload)
    else await http.post('/admin/models', payload)
    ElMessage.success('文本模型与计价已保存')
    emit('saved')
    open.value = false
  } catch (cause) { error.value = errorMessage(cause) }
  finally { saving.value = false }
}
</script>

<template>
  <el-dialog v-model="open" :title="model ? '编辑文本模型' : '新增文本模型'" width="760px" destroy-on-close :close-on-click-modal="false" :show-close="!saving" :close-on-press-escape="!saving" @closed="emit('close')">
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="form-alert" role="alert" />
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="save">
      <div class="management-form-grid">
        <el-form-item label="本站模型 ID" prop="public_id"><el-input v-model="form.public_id" /></el-form-item>
        <el-form-item label="显示名称" prop="display_name"><el-input v-model="form.display_name" /></el-form-item>
        <el-form-item label="供应商" prop="provider_id"><el-select v-model="form.provider_id"><el-option v-for="provider in providers.filter(item => item.adapter_key === 'modelgate_openai')" :key="provider.id" :label="provider.name" :value="provider.id" /></el-select></el-form-item>
        <el-form-item label="上游模型 ID"><el-select v-model="form.upstream_model_id"><el-option v-for="id in models" :key="id" :label="id" :value="id" /></el-select></el-form-item>
      </div>
      <el-form-item label="输入类型"><el-checkbox-group v-model="form.capabilities.input_modalities"><el-checkbox value="text" disabled>文本</el-checkbox><el-checkbox value="image">图片</el-checkbox></el-checkbox-group></el-form-item>
      <h2 class="section-title">Token 计价</h2>
      <div class="management-form-grid">
        <el-form-item v-for="field in priceFields" :key="field.key" :label="field.label" :prop="`token_price.${field.key}`" :rules="priceRules"><el-input v-model="form.token_price[field.key]" inputmode="decimal" /></el-form-item>
        <el-form-item label="长上下文阈值（输入 Token，超过时生效）"><el-input-number v-model="form.token_price.long_context_threshold" :min="1" :precision="0" /></el-form-item>
      </div>
      <el-form-item label="上架状态"><el-switch v-model="form.is_active" active-text="上架" inactive-text="下架" /></el-form-item>
    </el-form>
    <template #footer><el-button :icon="Close" :disabled="saving" @click="open = false">取消</el-button><el-button type="primary" :icon="Check" :loading="saving" @click="save">保存</el-button></template>
  </el-dialog>
</template>
