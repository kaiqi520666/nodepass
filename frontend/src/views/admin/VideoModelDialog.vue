<script setup lang="ts">
import { computed, onMounted, reactive, ref, toRaw } from 'vue'
import { Check, Close } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { errorMessage, http } from '../../api/http'
import type { ManagedVideoModel, ModelPrice, Provider, VideoCapabilities } from '../../types/catalog'

const props = defineProps<{ model?: ManagedVideoModel; providers: Provider[] }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const open = ref(true)
const saving = ref(false)
const error = ref('')
const formRef = ref<FormInstance>()
const options = ref<{ id: string; family: string; version: string }[]>([])
const caps: VideoCapabilities = {
  family: 'seedance-2.0', version: '', resolutions: ['720p'], aspect_ratios: ['1:1', '16:9', '9:16'],
  min_seconds: '4', max_seconds: '15', max_reference_images: 9, max_reference_videos: 3,
  max_reference_audios: 3, supports_first_frame: true, supports_last_frame: true,
  defaults: { seconds: '10', resolution: '720p', aspect_ratio: '16:9' },
}
const form = reactive({
  public_id: '', display_name: '', media_type: 'video' as const, provider_id: undefined as number | undefined,
  upstream_model_id: '', capabilities: caps, pricing_dimensions: [] as string[], is_active: false,
  prices: [{ variant: {}, sale_unit: 'video', sale_unit_price: '', cost_unit: 'video', cost_unit_price: '' }] as ModelPrice[],
  ...(props.model ? structuredClone(toRaw(props.model)) : {}),
})
const price = computed(() => form.prices[0]!)
const rules: FormRules = {
  public_id: [{ required: true, pattern: /^[A-Za-z0-9][A-Za-z0-9._-]*$/, message: '请输入有效的本站模型 ID', trigger: 'blur' }],
  display_name: [{ required: true, whitespace: true, message: '请输入显示名称', trigger: 'blur' }],
  provider_id: [{ required: true, message: '请选择供应商', trigger: 'change' }],
  upstream_model_id: [{ required: true, message: '请选择上游型号', trigger: 'change' }],
}
const saleRules = [{ required: true, pattern: /^(0|[1-9]\d{0,15})(\.\d{1,8})?$/, message: '请输入非负金额，最多八位小数', trigger: 'blur' }]
const costRules = [{ required: true, pattern: /^(0|[1-9]\d{0,15})(\.\d{1,8})?$/, message: '请输入非负金额，最多八位小数', trigger: 'blur' }]
function changeModel(id: string) {
  const option = options.value.find(item => item.id === id)!
  form.capabilities.family = option.family
  form.capabilities.version = option.version
  if (!form.public_id) form.public_id = id
  if (!form.display_name) form.display_name = id
}
async function save() {
  if (!await formRef.value?.validate().catch(() => false)) return
  saving.value = true
  error.value = ''
  try {
    const payload = {
      public_id: form.public_id, display_name: form.display_name, media_type: form.media_type,
      provider_id: form.provider_id, upstream_model_id: form.upstream_model_id,
      capabilities: form.capabilities, pricing_dimensions: [], prices: form.prices, is_active: form.is_active,
    }
    if (props.model) await http.put(`/admin/models/${props.model.id}`, payload)
    else await http.post('/admin/models', payload)
    ElMessage.success('视频模型已保存')
    emit('saved')
    open.value = false
  } catch (cause) { error.value = errorMessage(cause) }
  finally { saving.value = false }
}
onMounted(async () => {
  try { options.value = (await http.get('/admin/video-options')).data.data }
  catch (cause) { error.value = errorMessage(cause) }
})
</script>

<template>
  <el-dialog v-model="open" :title="model ? '编辑视频模型' : '新增视频模型'" width="920px" top="5vh" class="video-model-dialog" destroy-on-close :close-on-click-modal="false" :show-close="!saving" :close-on-press-escape="!saving" @closed="emit('close')">
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="form-alert" role="alert" />
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="save">
      <div class="management-form-grid">
        <el-form-item label="本站模型 ID" prop="public_id"><el-input v-model="form.public_id" /></el-form-item>
        <el-form-item label="显示名称" prop="display_name"><el-input v-model="form.display_name" /></el-form-item>
        <el-form-item label="供应商" prop="provider_id"><el-select v-model="form.provider_id"><el-option v-for="provider in providers.filter(item => item.adapter_key === 'meaicc_video')" :key="provider.id" :label="provider.name" :value="provider.id" /></el-select></el-form-item>
        <el-form-item label="上游模型 ID" prop="upstream_model_id"><el-select v-model="form.upstream_model_id" @change="changeModel"><el-option v-for="option in options" :key="option.id" :label="option.id" :value="option.id" /></el-select></el-form-item>
        <el-form-item label="系列"><el-input v-model="form.capabilities.family" /></el-form-item>
        <el-form-item label="版本"><el-input v-model="form.capabilities.version" placeholder="fast / full" /></el-form-item>
      </div>
      <el-form-item label="上架状态"><el-switch v-model="form.is_active" active-text="上架" inactive-text="下架" /></el-form-item>
      <h2 class="section-title">能力参数</h2>
      <div class="management-form-grid">
        <el-form-item label="分辨率"><el-select v-model="form.capabilities.resolutions" multiple filterable allow-create default-first-option><el-option v-for="value in ['480p', '720p', '1080p']" :key="value" :label="value" :value="value" /></el-select></el-form-item>
        <el-form-item label="默认分辨率"><el-select v-model="form.capabilities.defaults.resolution"><el-option v-for="value in form.capabilities.resolutions" :key="value" :label="value" :value="value" /></el-select></el-form-item>
        <el-form-item label="比例"><el-select v-model="form.capabilities.aspect_ratios" multiple filterable allow-create default-first-option><el-option v-for="value in ['1:1', '16:9', '9:16', '4:3', '3:4', '21:9']" :key="value" :label="value" :value="value" /></el-select></el-form-item>
        <el-form-item label="默认比例"><el-select v-model="form.capabilities.defaults.aspect_ratio"><el-option v-for="value in form.capabilities.aspect_ratios" :key="value" :label="value" :value="value" /></el-select></el-form-item>
        <el-form-item label="最短时长（秒）"><el-input v-model="form.capabilities.min_seconds" inputmode="decimal" /></el-form-item>
        <el-form-item label="最长时长（秒）"><el-input v-model="form.capabilities.max_seconds" inputmode="decimal" /></el-form-item>
        <el-form-item label="默认时长（秒）"><el-input v-model="form.capabilities.defaults.seconds" inputmode="decimal" /></el-form-item>
        <el-form-item label="参考图上限"><el-input-number v-model="form.capabilities.max_reference_images" :min="0" :precision="0" /></el-form-item>
        <el-form-item label="参考视频上限"><el-input-number v-model="form.capabilities.max_reference_videos" :min="0" :precision="0" /></el-form-item>
        <el-form-item label="参考音频上限"><el-input-number v-model="form.capabilities.max_reference_audios" :min="0" :precision="0" /></el-form-item>
        <el-form-item label="首帧图片"><el-switch v-model="form.capabilities.supports_first_frame" active-text="支持" /></el-form-item>
        <el-form-item label="尾帧图片"><el-switch v-model="form.capabilities.supports_last_frame" active-text="支持" /></el-form-item>
      </div>
      <h2 class="section-title">计费价格</h2>
      <div class="management-form-grid">
        <el-form-item label="售价计费方式"><el-select v-model="price.sale_unit"><el-option label="按条" value="video" /><el-option label="按秒" value="second" /></el-select></el-form-item>
        <el-form-item label="成本计费方式"><el-select v-model="price.cost_unit"><el-option label="按条" value="video" /><el-option label="按秒" value="second" /></el-select></el-form-item>
        <el-form-item label="售价（积分）" prop="prices.0.sale_unit_price" :rules="saleRules"><el-input v-model="price.sale_unit_price" inputmode="decimal" /></el-form-item>
        <el-form-item label="成本" prop="prices.0.cost_unit_price" :rules="costRules"><el-input v-model="price.cost_unit_price" inputmode="decimal" /></el-form-item>
      </div>
    </el-form>
    <template #footer><el-button :icon="Close" :disabled="saving" @click="open = false">取消</el-button><el-button type="primary" :icon="Check" :loading="saving" @click="save">保存</el-button></template>
  </el-dialog>
</template>
