<script setup lang="ts">
import { computed, onMounted, reactive, ref, toRaw } from 'vue'
import { ArrowDown, ArrowUp, Check, Close, CopyDocument, Delete, Edit, Plus, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { http, errorMessage } from '../../api/http'
import type { ImageCapabilities, ImageProfile, ManagedModel, ModelPrice, Provider } from '../../types/catalog'
import AppTable from '../../components/AppTable.vue'
import PageHeader from '../../components/PageHeader.vue'

type FormPrice = ModelPrice & { default_price: boolean }
const models = ref<ManagedModel[]>([])
const providers = ref<Provider[]>([])
const profiles = ref<ImageProfile[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const formError = ref('')
const query = ref('')
const familyFilter = ref('')
const tierFilter = ref('')
const statusFilter = ref('')
const expandedRows = ref<number[]>([])
const dialogOpen = ref(false)
const editingId = ref<number>()
const formRef = ref<FormInstance>()
const capabilityFields = [
  { parameter: 'size', field: 'sizes', label: '尺寸 / 比例' },
  { parameter: 'quality', field: 'qualities', label: '质量' },
  { parameter: 'tier', field: 'tiers', label: '档位' },
  { parameter: 'series', field: 'series', label: '分支' },
  { parameter: 'background', field: 'backgrounds', label: '背景' },
  { parameter: 'output_format', field: 'output_formats', label: '输出格式' },
] as const
const dimensions = capabilityFields.slice(0, 4)
function emptyCapabilities(): ImageCapabilities {
  return { sizes: [], qualities: [], tiers: [], series: [], backgrounds: [], output_formats: [], max_reference_images: 0, supports_mask: false, defaults: {} }
}
function emptyPrice(): FormPrice {
  return { variant: {}, sale_unit: 'image', sale_unit_price: '', cost_unit: 'image', cost_unit_price: '', cost_currency: 'CNY', default_price: true }
}
function emptyForm() {
  return {
    public_id: '', display_name: '', media_type: 'image' as const, provider_id: undefined as number | undefined,
    upstream_model_id: '', capabilities: emptyCapabilities(), pricing_dimensions: [] as string[],
    prices: [] as FormPrice[], is_active: false,
  }
}
const form = reactive(emptyForm())
const profile = computed(() => profiles.value.find(item => item.id === form.upstream_model_id))
function modelInfo(model: ManagedModel) {
  const match = /^gpt-image-(2(?:\.5|\.6)?)(?:-(flare|sunburst))?(?:-(1k|2k|4k))?$/.exec(model.upstream_model_id)
  const family = profiles.value.find(item => item.id === model.upstream_model_id)?.family
    || (match ? `gpt-image-${match[1]}` : '其他')
  const name = match ? `GPT Image ${match[1]}${match[2] ? ` · ${match[2] === 'flare' ? 'Flare' : 'Sunburst'}` : ''}` : model.display_name
  return {
    family,
    name: model.display_name !== model.public_id && model.display_name !== model.upstream_model_id ? model.display_name : name,
    tiers: match ? [match[3] || 'web'] : model.capabilities.tiers,
  }
}

// Only trim trailing zeros: price display and grouping must not pass through floating point.
function money(value: string) {
  const [integer, fraction = ''] = value.split('.')
  return `${integer}.${fraction.replace(/0+$/, '').padEnd(4, '0')}`
}

function variantLabel(variant: Record<string, string>) {
  return Object.entries(variant).map(([key, value]) => `${key}: ${value}`).join(' · ') || '默认'
}

function priceGroups(prices: ModelPrice[], kind: 'cost' | 'sale') {
  const groups = new Map<string, { amount: string; currency: string; variants: Record<string, string>[] }>()
  for (const price of prices) {
    const amount = money(kind === 'cost' ? price.cost_unit_price : price.sale_unit_price)
    const currency = kind === 'cost' ? price.cost_currency : ''
    const key = `${currency}:${amount}`
    const group = groups.get(key)
    if (group) group.variants.push(price.variant)
    else groups.set(key, { amount, currency, variants: [price.variant] })
  }
  return [...groups.values()].map(group => {
    const qualities = group.variants.map(variant => variant.quality).sort().join(',')
    const qualityOnly = group.variants.every(variant => Object.keys(variant).length === 1 && variant.quality)
    const detail = group.variants.map(variantLabel).join('；')
    const label = groups.size === 1 ? '' : qualityOnly && qualities === 'high,low,medium' ? '常规'
      : qualityOnly && qualities === 'max,xhigh' ? '高质量' : detail
    return { ...group, label, detail }
  })
}

const rows = computed(() => models.value.map(model => ({
  ...model, ...modelInfo(model),
  providerName: providers.value.find(provider => provider.id === model.provider_id)?.name || '—',
  costGroups: priceGroups(model.prices, 'cost'),
  saleGroups: priceGroups(model.prices, 'sale'),
})))
const families = computed(() => [...new Set(rows.value.map(model => model.family))])
const hasFilters = computed(() => !!(query.value.trim() || familyFilter.value || tierFilter.value || statusFilter.value))
const filtered = computed(() => rows.value.filter(model =>
  `${model.public_id} ${model.display_name} ${model.name}`.toLowerCase().includes(query.value.trim().toLowerCase())
  && (!familyFilter.value || model.family === familyFilter.value)
  && (!tierFilter.value || model.tiers.includes(tierFilter.value))
  && (!statusFilter.value || model.is_active === (statusFilter.value === 'active')),
))

function togglePrices(id: number) {
  expandedRows.value = expandedRows.value.includes(id) ? expandedRows.value.filter(value => value !== id) : [...expandedRows.value, id]
}

async function copyId(id: string) {
  try {
    await navigator.clipboard.writeText(id)
    ElMessage.success('模型 ID 已复制')
  } catch { ElMessage.error('复制失败，请手动复制模型 ID') }
}
const rules: FormRules = {
  public_id: [
    { required: true, message: '请输入本站模型 ID', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9][A-Za-z0-9._-]*$/, message: '仅允许字母、数字、点、下划线和连字符', trigger: 'blur' },
  ],
  display_name: [{ required: true, whitespace: true, message: '请输入显示名称', trigger: 'blur' }],
  provider_id: [{ required: true, message: '请选择供应商', trigger: 'change' }],
  upstream_model_id: [{ required: true, message: '请选择上游模型 ID', trigger: 'change' }],
}
const saleRules = [
  { required: true, message: '请输入售价', trigger: 'blur' },
  { pattern: /^(0|[1-9]\d{0,15})(\.\d{1,4})?$/, message: '请输入非负金额，最多四位小数', trigger: 'blur' },
]
const costRules = [
  { required: true, message: '请输入成本价', trigger: 'blur' },
  { pattern: /^(0|[1-9]\d{0,15})(\.\d{1,8})?$/, message: '请输入非负金额，最多八位小数', trigger: 'blur' },
]

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [modelResponse, providerResponse, optionResponse] = await Promise.all([
      http.get<{ data: ManagedModel[] }>('/admin/models'),
      http.get<{ data: Provider[] }>('/admin/providers'),
      http.get<{ data: ImageProfile[] }>('/admin/image-options'),
    ])
    models.value = modelResponse.data.data
    providers.value = providerResponse.data.data
    profiles.value = optionResponse.data.data
  } catch (cause) { error.value = errorMessage(cause) }
  finally { loading.value = false }
}

function edit(model?: ManagedModel) {
  editingId.value = model?.id
  const values = model ? structuredClone(toRaw(model)) : undefined
  Object.assign(form, emptyForm(), values ? {
    ...values, capabilities: { ...emptyCapabilities(), ...values.capabilities },
    prices: values.prices.map(price => ({ ...price, default_price: !Object.keys(price.variant).length })),
  } : {})
  formError.value = ''
  dialogOpen.value = true
}

function resetCapabilities() {
  form.capabilities = emptyCapabilities()
  form.pricing_dimensions = []
  form.prices = []
}

function updateOptions(parameter: string, field: typeof capabilityFields[number]['field']) {
  const values = form.capabilities[field]
  if (!values.includes(form.capabilities.defaults[parameter] || '')) {
    if (values.length) form.capabilities.defaults[parameter] = values[0]!
    else delete form.capabilities.defaults[parameter]
  }
}

function updateDimensions() {
  for (const price of form.prices) {
    price.variant = Object.fromEntries(Object.entries(price.variant).filter(([key]) => form.pricing_dimensions.includes(key)))
    if (!form.pricing_dimensions.length) price.default_price = true
  }
}

async function save() {
  if (!await formRef.value?.validate().catch(() => false)) return
  saving.value = true
  formError.value = ''
  try {
    const payload = {
      public_id: form.public_id, display_name: form.display_name, media_type: form.media_type,
      provider_id: form.provider_id, upstream_model_id: form.upstream_model_id,
      capabilities: form.capabilities, pricing_dimensions: form.pricing_dimensions, is_active: form.is_active,
      prices: form.prices.map(({ default_price, ...price }) => ({ ...price, variant: default_price ? {} : price.variant })),
    }
    if (editingId.value) await http.put(`/admin/models/${editingId.value}`, payload)
    else await http.post('/admin/models', payload)
    dialogOpen.value = false
    ElMessage.success('模型与价格已保存')
    await load()
  } catch (cause) { formError.value = errorMessage(cause) }
  finally { saving.value = false }
}
onMounted(load)
</script>

<template>
  <section aria-labelledby="managed-models-title">
    <PageHeader eyebrow="管理" title="模型与价格" heading-id="managed-models-title">
      <div class="management-actions">
        <el-button :icon="Refresh" class="icon-button" :loading="loading" aria-label="刷新配置" title="刷新配置" @click="load" />
        <el-button type="primary" :icon="Plus" :disabled="loading || !!error" @click="edit()">新增图片模型</el-button>
      </div>
    </PageHeader>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="form-alert" role="alert" />
    <div class="managed-model-filters">
      <el-input v-model="query" :prefix-icon="Search" class="model-search" clearable placeholder="搜索模型名称或 ID" aria-label="搜索配置模型" />
      <el-select v-model="familyFilter" clearable placeholder="全部系列" aria-label="筛选模型系列">
        <el-option v-for="family in families" :key="family" :label="family" :value="family" />
      </el-select>
      <el-select v-model="tierFilter" clearable placeholder="全部档位" aria-label="筛选模型档位">
        <el-option v-for="tier in ['web', '1k', '2k', '4k']" :key="tier" :label="tier === 'web' ? 'Web' : tier.toUpperCase()" :value="tier" />
      </el-select>
      <el-select v-model="statusFilter" clearable placeholder="全部状态" aria-label="筛选上架状态">
        <el-option label="已上架" value="active" /><el-option label="已下架" value="inactive" />
      </el-select>
    </div>
    <AppTable class="managed-model-table" :data="filtered" :loading="loading" row-key="id" :expand-row-keys="expandedRows" :empty-text="hasFilters ? '没有匹配的图片模型' : '暂无图片模型'" @expand-change="(_row: ManagedModel, expanded: ManagedModel[]) => expandedRows = expanded.map(item => item.id)">
        <el-table-column type="expand" width="44">
          <template #default="{ row }">
            <div :id="`model-prices-${row.id}`" class="model-price-details">
              <table :aria-label="`${row.public_id} 完整价目`">
                <caption>完整价目 <span>{{ row.public_id }}</span></caption>
                <thead><tr><th scope="col">参数组合</th><th scope="col">成本（原币 / 张）</th><th scope="col">售价（积分 / 张）</th></tr></thead>
                <tbody>
                  <tr v-for="(price, index) in row.prices" :key="price.id ?? index">
                    <th scope="row">{{ variantLabel(price.variant) }}</th>
                    <td class="numeric">{{ price.cost_currency === 'USD' ? '$' : '¥' }}{{ money(price.cost_unit_price) }}</td>
                    <td class="numeric">{{ money(price.sale_unit_price) }}</td>
                  </tr>
                  <tr v-if="!row.prices.length"><td colspan="3">暂无价目</td></tr>
                </tbody>
              </table>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="模型" min-width="290">
          <template #default="{ row }">
            <strong class="model-name">{{ row.name }}</strong>
            <div class="model-id">
              <code>{{ row.public_id }}</code>
              <el-tooltip content="复制模型 ID" placement="top">
                <el-button text :icon="CopyDocument" :aria-label="`复制 ${row.public_id}`" @click="copyId(row.public_id)" />
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="档位" width="90"><template #default="{ row }"><span class="model-tier">{{ row.tiers.map((tier: string) => tier === 'web' ? 'Web' : tier.toUpperCase()).join(' / ') || '—' }}</span></template></el-table-column>
        <el-table-column label="供应商" min-width="110"><template #default="{ row }">{{ row.providerName }}</template></el-table-column>
        <el-table-column v-for="column in [{ key: 'costGroups', label: '成本（原币 / 张）' }, { key: 'saleGroups', label: '售价（积分 / 张）' }]" :key="column.key" :label="column.label" min-width="185" align="right">
          <template #default="{ row }">
            <button v-if="row.prices.length" type="button" class="model-price-summary" :aria-label="`查看 ${row.public_id} ${column.key === 'costGroups' ? '成本' : '售价'}明细`" :aria-expanded="expandedRows.includes(row.id)" :aria-controls="`model-prices-${row.id}`" @click="togglePrices(row.id)">
              <span v-for="group in row[column.key]" :key="`${group.currency}:${group.amount}`" class="model-price-group" :title="group.detail">
                <span v-if="group.label" class="model-price-quality">{{ group.label }}</span>
                <strong class="numeric">{{ group.currency ? (group.currency === 'USD' ? '$' : '¥') : '' }}{{ group.amount }}</strong>
              </span>
              <el-icon class="model-price-chevron" aria-hidden="true"><ArrowUp v-if="expandedRows.includes(row.id)" /><ArrowDown v-else /></el-icon>
            </button>
            <span v-else class="price-unit">未配置</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'" effect="plain">{{ row.is_active ? '已上架' : '已下架' }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="76" fixed="right"><template #default="{ row }"><el-tooltip content="编辑模型与价格" placement="top"><el-button class="icon-button" :icon="Edit" :aria-label="`编辑 ${row.display_name}`" @click="edit(models.find(model => model.id === row.id))" /></el-tooltip></template></el-table-column>
    </AppTable>
    <el-dialog v-model="dialogOpen" :title="editingId ? '编辑图片模型' : '新增图片模型'" width="960px" destroy-on-close :close-on-click-modal="false" :close-on-press-escape="!saving" :show-close="!saving">
      <el-alert v-if="formError" :title="formError" type="error" :closable="false" show-icon class="form-alert" role="alert" />
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="save">
        <div class="management-form-grid">
          <el-form-item label="本站模型 ID" prop="public_id"><el-input v-model="form.public_id" maxlength="160" /></el-form-item>
          <el-form-item label="显示名称" prop="display_name"><el-input v-model="form.display_name" maxlength="160" /></el-form-item>
          <el-form-item label="供应商" prop="provider_id">
            <el-select v-model="form.provider_id" filterable placeholder="选择供应商">
              <el-option v-for="provider in providers" :key="provider.id" :label="`${provider.name}${provider.is_active ? '' : '（已停用）'}`" :value="provider.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="上游模型 ID" prop="upstream_model_id">
            <el-select v-model="form.upstream_model_id" filterable placeholder="选择具体型号" @change="resetCapabilities">
              <el-option-group v-for="family in [...new Set(profiles.map(item => item.family))]" :key="family" :label="family">
                <el-option v-for="option in profiles.filter(item => item.family === family)" :key="option.id" :label="option.id" :value="option.id" />
              </el-option-group>
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="上架状态"><el-switch v-model="form.is_active" active-text="上架" inactive-text="下架" /></el-form-item>
        <template v-if="profile">
          <h2 class="section-title">能力参数</h2>
          <div v-for="field in capabilityFields.filter(item => profile![item.field].length)" :key="field.parameter" class="capability-form-row">
            <el-form-item :label="field.label">
              <el-select v-model="form.capabilities[field.field]" multiple filterable :allow-create="field.parameter === 'size'" default-first-option @change="updateOptions(field.parameter, field.field)">
                <el-option v-for="value in profile[field.field]" :key="value" :label="value" :value="value" />
              </el-select>
            </el-form-item>
            <el-form-item :label="`${field.label}默认值`">
              <el-select v-model="form.capabilities.defaults[field.parameter]" :disabled="!form.capabilities[field.field].length">
                <el-option v-for="value in form.capabilities[field.field]" :key="value" :label="value" :value="value" />
              </el-select>
            </el-form-item>
          </div>
          <div class="management-form-grid">
            <el-form-item label="参考图数量上限"><el-input-number v-model="form.capabilities.max_reference_images" :min="0" :max="profile.max_reference_images ?? 16" :precision="0" /></el-form-item>
            <el-form-item label="蒙版编辑"><el-switch v-model="form.capabilities.supports_mask" active-text="允许" inactive-text="关闭" /></el-form-item>
          </div>
        </template>
        <h2 class="section-title">计费价格</h2>
        <el-form-item label="计价维度">
          <el-checkbox-group v-model="form.pricing_dimensions" @change="updateDimensions">
            <el-checkbox v-for="field in dimensions" :key="field.parameter" :value="field.parameter" :disabled="!form.capabilities[field.field].length && !form.pricing_dimensions.includes(field.parameter)">{{ field.label }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <div v-for="(price, index) in form.prices" :key="index" class="price-editor">
          <div class="price-editor-heading">
            <strong>价目 {{ index + 1 }}</strong>
            <el-switch v-model="price.default_price" active-text="默认价" :disabled="!form.pricing_dimensions.length" />
            <el-button :icon="Delete" class="icon-button" :aria-label="`删除价目 ${index + 1}`" title="删除价目" @click="form.prices.splice(index, 1)" />
          </div>
          <div v-if="!price.default_price" class="management-form-grid">
            <el-form-item v-for="field in dimensions.filter(item => form.pricing_dimensions.includes(item.parameter))" :key="field.parameter" :label="field.label">
              <el-select v-model="price.variant[field.parameter]"><el-option v-for="value in form.capabilities[field.field]" :key="value" :label="value" :value="value" /></el-select>
            </el-form-item>
          </div>
          <div class="price-form-grid">
            <el-form-item label="售价（积分 / 张）" :prop="`prices.${index}.sale_unit_price`" :rules="saleRules"><el-input v-model="price.sale_unit_price" inputmode="decimal" maxlength="21" /></el-form-item>
            <el-form-item label="成本（原币 / 张）" :prop="`prices.${index}.cost_unit_price`" :rules="costRules"><el-input v-model="price.cost_unit_price" inputmode="decimal" maxlength="25" /></el-form-item>
            <el-form-item label="成本币种"><el-select v-model="price.cost_currency"><el-option label="人民币 CNY" value="CNY" /><el-option label="美元 USD" value="USD" /></el-select></el-form-item>
          </div>
        </div>
        <el-button :icon="Plus" @click="form.prices.push(emptyPrice())">添加价目</el-button>
      </el-form>
      <template #footer>
        <el-button :icon="Close" :disabled="saving" @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :icon="Check" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>
