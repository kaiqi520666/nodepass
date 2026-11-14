<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Box, ChatDotRound, CopyDocument, Grid, Picture, Refresh, Search, VideoCamera, View } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'
import { http, errorMessage } from '../../api/http'
import { copyText } from '../../utils/clipboard'
import type { PublicModel, PublicPrice } from '../../types'
import AppTable from '../../components/AppTable.vue'
import AppPagination from '../../components/AppPagination.vue'
import PageHeader from '../../components/PageHeader.vue'

const models = ref<PublicModel[]>([])
const route = useRoute()
const loading = ref(true)
const error = ref('')
const query = ref('')
const searchField = ref<{ focus: () => void }>()
const type = ref('all')
const family = ref('')
const tier = ref('')
const selectedSeries = ref('gpt-image-2')
const catalogPage = ref(1)
const catalogPageSize = ref(20)
const selected = ref<CatalogRow>()
const detailOpen = ref(false)
const options = [
  { label: '全部', value: 'all', icon: Grid },
  { label: '图片', value: 'image', icon: Picture },
  { label: '视频', value: 'video', icon: VideoCamera },
  { label: '文本', value: 'text', icon: ChatDotRound },
]
const typeLabel = computed(() => options.find(option => option.value === type.value)?.label ?? '全部')
const seriesOptions = computed(() => [...new Set([
  'gpt-image-2', 'gpt-image-2.5',
  ...models.value.filter(model => model.media_type === 'video').map(model => String(model.capabilities.family || '其他视频')),
  ...models.value.filter(model => model.media_type === 'text').map(model => String(model.capabilities.family)),
])])
const units = { image: '张', video: '条', second: '秒', million_tokens: '百万 token' }
const dimensionLabels: Record<string, string> = {
  tier: '档位', series: '分支', quality: '质量', size: '尺寸', resolution: '分辨率', usage: '计费项',
}
const parameterNames: Record<string, string> = {
  sizes: '尺寸 / 比例', qualities: '质量', tiers: '档位', series: '分支',
  backgrounds: '背景', output_formats: '输出格式', resolutions: '分辨率',
  durations: '时长', max_reference_images: '参考图上限', supports_mask: '蒙版编辑',
  aspect_ratios: '比例', min_seconds: '最短时长（秒）', max_seconds: '最长时长（秒）',
  max_reference_videos: '参考视频上限', max_reference_audios: '参考音频上限',
  supports_first_frame: '首帧图片', supports_last_frame: '尾帧图片', family: '系列', version: '版本',
  input_modalities: '输入类型',
}
const parameterOrder = [
  'series', 'max_seconds', 'min_seconds', 'resolutions', 'aspect_ratios',
  'max_reference_images', 'max_reference_videos', 'max_reference_audios',
  'supports_first_frame', 'supports_last_frame',
]

function money(value: string) {
  const [integer, fraction = ''] = value.split('.')
  return `${integer}.${fraction.padEnd(8, '0')}`
}

function shortMoney(value: string) {
  const [integer, fraction = ''] = money(value).split('.')
  let cents = BigInt(integer) * 10000n + BigInt(fraction.slice(0, 4))
  if (fraction[4]! >= '5') cents += 1n
  if (cents === 0n && /[1-9]/.test(fraction)) return '<0.0001'
  const decimals = (cents % 10000n).toString().padStart(4, '0').replace(/0+$/, '')
  return `${cents / 10000n}.${decimals.padEnd(2, '0')}`
}

function variantLabel(variant: Record<string, string>) {
  return Object.entries(variant).map(([key, value]) => `${key}: ${value}`).join(' · ') || '默认'
}

function stringList(value: unknown) {
  return Array.isArray(value) ? value.map(String) : []
}

function capabilityChips(model: PublicModel) {
  const capabilities = model.capabilities
  const chips: string[] = []
  if (model.media_type === 'image') {
    const sizes = stringList(capabilities.sizes)
    if (sizes.length) chips.push(`尺寸 ${sizes.slice(0, 3).join(' / ')}${sizes.length > 3 ? ' 等' : ''}`)
    const qualities = stringList(capabilities.qualities)
    if (qualities.length) chips.push(`质量 ${qualities.join(' / ')}`)
    if (typeof capabilities.max_reference_images === 'number' && capabilities.max_reference_images > 0) chips.push(`参考图 ${capabilities.max_reference_images} 张`)
    if (capabilities.supports_mask === true) chips.push('支持蒙版')
  } else if (model.media_type === 'video') {
    const resolutions = stringList(capabilities.resolutions)
    if (resolutions.length) chips.push(resolutions.join(' / '))
    if (capabilities.min_seconds !== undefined && capabilities.max_seconds !== undefined) chips.push(`${capabilities.min_seconds}–${capabilities.max_seconds} 秒`)
    if (typeof capabilities.max_reference_images === 'number' && capabilities.max_reference_images > 0) chips.push(`参考图 ${capabilities.max_reference_images} 张`)
    if (capabilities.supports_first_frame === true) chips.push('首帧')
    if (capabilities.supports_last_frame === true) chips.push('尾帧')
  } else {
    const modalities = stringList(capabilities.input_modalities)
    if (modalities.length) chips.push(`输入 ${modalities.map(item => item === 'image' ? '图片' : '文本').join(' + ')}`)
    if (model.long_context_threshold) chips.push(`长上下文 ${model.long_context_threshold.toLocaleString('zh-CN')} Token`)
  }
  return chips
}

function priceGroups(prices: PublicPrice[]) {
  const groups = new Map<string, { amount: string; fullAmount: string; unit: PublicPrice['unit']; variants: Record<string, string>[] }>()
  for (const price of prices) {
    const fullAmount = money(price.unit_price)
    const dimensions = Object.entries(price.variant).filter(([key]) => key !== 'quality').sort()
    const key = JSON.stringify([price.unit, fullAmount, dimensions])
    const group = groups.get(key)
    if (group) group.variants.push(price.variant)
    else groups.set(key, { amount: shortMoney(price.unit_price), fullAmount, unit: price.unit, variants: [price.variant] })
  }
  return [...groups.values()].map(group => {
    const detail = group.variants.map(variantLabel).join('；')
    const values = Object.fromEntries(Object.keys(group.variants[0]!).map(key => [
      key, [...new Set(group.variants.map(variant => variant[key]))].join(' / '),
    ]))
    return { ...group, values, detail }
  })
}

function modelInfo(model: PublicModel) {
  const match = model.media_type === 'image' ? /^gpt-image-(2(?:\.5)?)$/.exec(model.id) : null
  const configuredTiers = model.capabilities.tiers
  const resolutions = model.capabilities.resolutions
  const prices: PublicPrice[] = model.token_prices ? [
    { variant: { usage: '输入' }, unit: 'million_tokens', unit_price: model.token_prices.input_price },
    { variant: { usage: '输出（含思考）' }, unit: 'million_tokens', unit_price: model.token_prices.output_price },
    { variant: { usage: '缓存命中' }, unit: 'million_tokens', unit_price: model.token_prices.cache_read_price },
  ] : model.prices
  if (model.long_context_token_prices) {
    const prefix = `输入超过 ${model.long_context_threshold?.toLocaleString('zh-CN')} Token · `
    prices.push(
      { variant: { usage: `${prefix}输入` }, unit: 'million_tokens', unit_price: model.long_context_token_prices.input_price },
      { variant: { usage: `${prefix}输出（含思考）` }, unit: 'million_tokens', unit_price: model.long_context_token_prices.output_price },
      { variant: { usage: `${prefix}缓存命中` }, unit: 'million_tokens', unit_price: model.long_context_token_prices.cache_read_price },
    )
  }
  return {
    displayName: model.name === model.id && match ? `GPT Image ${match[1]}` : model.name,
    family: match ? `GPT Image ${match[1]}` : model.media_type === 'image' ? '其他图片' : String(model.capabilities.family || '其他视频'),
    seriesKey: match ? `gpt-image-${match[1]}` : String(model.capabilities.family || '其他视频'),
    tiers: Array.isArray(configuredTiers) && configuredTiers.length
      ? configuredTiers.map(String) : Array.isArray(resolutions) ? resolutions.map(String) : [],
    prices,
    priceGroups: priceGroups(prices),
    priceDimensions: [...new Set(prices.flatMap(price => Object.keys(price.variant)))],
    chips: capabilityChips(model),
  }
}

type CatalogRow = PublicModel & ReturnType<typeof modelInfo>
const isConsoleModels = computed(() => route.path === '/console/models')
const rows = computed(() => models.value.map(model => ({ ...model, ...modelInfo(model) })))
const typeRows = computed(() => rows.value.filter(model => type.value === 'all' || model.media_type === type.value))
const families = computed(() => [...new Set(typeRows.value.map(model => model.family))])
const tiers = computed(() => [...new Set(typeRows.value.flatMap(model => model.tiers))])
const filtered = computed(() => rows.value.filter(model =>
  (isConsoleModels.value ? model.seriesKey === selectedSeries.value : type.value === 'all' || model.media_type === type.value)
  && (isConsoleModels.value || !family.value || model.family === family.value)
  && (!tier.value || model.tiers.includes(tier.value))
  && `${model.id} ${model.name} ${model.displayName}`.toLowerCase().includes(query.value.trim().toLowerCase()),
))
const displayedRows = computed(() => filtered.value.slice(
  (catalogPage.value - 1) * catalogPageSize.value,
  catalogPage.value * catalogPageSize.value,
))
const parameters = computed(() => Object.entries(selected.value?.capabilities || {})
  .filter(([, value]) => Array.isArray(value) ? value.length : value !== '')
  .map(([key, value]) => ({
    key, label: parameterNames[key] || key,
    values: Array.isArray(value) ? value.map(String)
      : [typeof value === 'boolean' ? (value ? '支持' : '不支持')
        : key === 'max_reference_images' ? (value ? `${value} 张` : '—') : String(value)],
  }))
  .sort((left, right) => {
    const leftIndex = parameterOrder.indexOf(left.key)
    const rightIndex = parameterOrder.indexOf(right.key)
    return (leftIndex < 0 ? parameterOrder.length : leftIndex)
      - (rightIndex < 0 ? parameterOrder.length : rightIndex)
  }))

function changeType() {
  family.value = ''
  tier.value = ''
}

function changeSeries() {
  tier.value = ''
}

function changePage(value: { page: number; pageSize: number }) {
  catalogPage.value = value.page
  catalogPageSize.value = value.pageSize
}

function showDetails(model: CatalogRow) {
  selected.value = model
  detailOpen.value = true
}

async function load() {
  loading.value = true
  error.value = ''
  try { models.value = (await http.get<{ data: PublicModel[] }>('/public/models')).data.data }
  catch (cause) { error.value = errorMessage(cause) }
  finally { loading.value = false }
}

async function copy(value: string) {
  await copyText(value, '已复制模型 ID', '复制失败，请手动选择模型 ID')
}

function focusSearch(event: KeyboardEvent) {
  if (event.key !== '/' || event.metaKey || event.ctrlKey || event.altKey) return
  const target = event.target as HTMLElement
  if (target.closest('input, textarea, select, [contenteditable="true"]')) return
  event.preventDefault()
  searchField.value?.focus()
}

onMounted(() => {
  load()
  window.addEventListener('keydown', focusSearch)
})
onBeforeUnmount(() => window.removeEventListener('keydown', focusSearch))
watch(filtered, () => { catalogPage.value = 1 })
</script>

<template>
  <section aria-labelledby="models-title">
    <PageHeader eyebrow="模型目录" :title="route.meta.title" heading-id="models-title">
      <span class="count-label">{{ models.length }} 个模型</span>
    </PageHeader>
    <div class="filter-bar catalog-toolbar">
      <div class="catalog-filter-options">
        <el-segmented v-if="isConsoleModels" v-model="selectedSeries" :options="seriesOptions" aria-label="模型系列" class="model-series-switch" @change="changeSeries" />
        <el-segmented v-else v-model="type" :options="options" aria-label="模型类型" class="model-type-switch" @change="changeType">
          <template #default="{ item }">
            <span class="model-type-option"><el-icon :size="17" aria-hidden="true"><component :is="item.icon" /></el-icon><span>{{ item.label }}</span></span>
          </template>
        </el-segmented>
        <el-select v-if="!isConsoleModels" v-model="family" clearable placeholder="全部系列" aria-label="筛选定价系列">
          <el-option v-for="value in families" :key="value" :label="value" :value="value" />
        </el-select>
        <el-select v-if="!isConsoleModels" v-model="tier" clearable placeholder="全部档位" aria-label="筛选定价档位">
          <el-option v-for="value in tiers" :key="value" :label="value === 'web' ? 'Web' : value.toUpperCase()" :value="value" />
        </el-select>
      </div>
      <div class="filter-actions">
        <el-input ref="searchField" v-model="query" :prefix-icon="Search" placeholder="搜索模型名称或 ID（按 / 聚焦）" clearable aria-label="搜索模型" aria-keyshortcuts="/" class="model-search" />
        <el-tooltip content="刷新模型" :show-after="400">
          <el-button :icon="Refresh" :loading="loading" class="icon-button" aria-label="刷新模型" @click="load" />
        </el-tooltip>
      </div>
    </div>

    <div class="catalog-content" :aria-busy="loading">
      <el-result v-if="error" icon="warning" title="模型加载失败" :sub-title="error">
        <template #extra><el-button :icon="Refresh" @click="load">重试</el-button></template>
      </el-result>
      <template v-else>
        <p class="catalog-summary" role="status">
          <span><strong>{{ filtered.length }}</strong> 个结果</span>
          <span>{{ isConsoleModels ? selectedSeries : typeLabel }}</span>
          <span>售价以积分计</span>
        </p>
        <div v-if="loading && !models.length" class="catalog-list" aria-busy="true">
          <div v-for="index in 4" :key="index" class="catalog-model-card catalog-skeleton-card"><el-skeleton :rows="4" animated /></div>
        </div>
        <div v-else v-loading="loading && models.length > 0" class="catalog-list">
        <article v-for="row in displayedRows" :key="row.id" class="catalog-model-card">
          <header class="catalog-model-card-header">
            <div class="catalog-model-heading">
              <h2 class="catalog-model-title">{{ row.displayName }}</h2>
              <p v-if="row.media_type === 'video'" class="price-unit">{{ row.tiers.join(' / ') }} · {{ row.capabilities.min_seconds }}–{{ row.capabilities.max_seconds }} 秒</p>
              <div class="catalog-model-id-row">
                <code class="catalog-model-id">{{ row.id }}</code>
                <el-tooltip content="复制模型 ID">
                  <el-button text :icon="CopyDocument" :aria-label="`复制 ${row.id}`" @click="copy(row.id)" />
                </el-tooltip>
              </div>
            </div>
            <el-tooltip content="查看模型参数">
              <el-button class="icon-button catalog-model-detail" :icon="View" :aria-label="`查看 ${row.id} 详情`" @click="showDetails(row)" />
            </el-tooltip>
          </header>
          <div v-if="row.chips.length" class="catalog-chips" :aria-label="`${row.id} 能力`">
            <span v-for="chip in row.chips" :key="chip">{{ chip }}</span>
          </div>
          <ul v-if="row.priceGroups.length" class="catalog-price-list" :aria-label="`${row.id} 价格`">
            <li v-for="(group, index) in row.priceGroups.slice(0, 6)" :key="index" class="catalog-price-card">
              <div class="catalog-price-meta">
                <span v-for="dimension in row.priceDimensions" :key="dimension" class="catalog-price-tag">
                  <span class="catalog-price-dimension">{{ dimensionLabels[dimension] || dimension }}</span>
                  <strong>{{ group.values[dimension] }}</strong>
                </span>
              </div>
              <div class="catalog-price-value">
                <strong class="numeric" :title="`${group.fullAmount} 积分`" :aria-label="`${group.fullAmount} 积分`">{{ group.amount }}</strong>
                <span class="price-unit">/ {{ units[group.unit as keyof typeof units] }}</span>
              </div>
            </li>
          </ul>
          <p v-else class="catalog-no-price">暂无报价</p>
          <p v-if="row.priceGroups.length > 6" class="catalog-price-more">
            另有 {{ row.priceGroups.length - 6 }} 组价目，<button type="button" @click="showDetails(row)">查看完整价目</button>
          </p>
        </article>
          <div v-if="!filtered.length" class="table-empty catalog-empty">
            <el-icon :size="32" aria-hidden="true"><Box /></el-icon>
            <h2>{{ models.length ? '没有匹配的模型' : '暂无上架模型' }}</h2>
            <p>{{ models.length ? '调整搜索或筛选条件后重试。' : '管理员上架模型后，这里会显示模型与价格。' }}</p>
          </div>
        </div>
      </template>
      <AppPagination
        :page="catalogPage" :page-size="catalogPageSize" :total="filtered.length" :disabled="loading"
        @change="changePage"
      />
    </div>
    <el-dialog v-model="detailOpen" :title="selected?.displayName" width="800px" destroy-on-close class="catalog-detail-dialog">
      <template v-if="selected">
        <div class="catalog-detail-id model-id"><code>{{ selected.id }}</code><el-tooltip content="复制模型 ID"><el-button text :icon="CopyDocument" :aria-label="`复制 ${selected.id}`" @click="copy(selected.id)" /></el-tooltip></div>
        <h3 class="section-title">能力参数</h3>
        <dl v-if="parameters.length" class="catalog-parameters">
          <div v-for="parameter in parameters" :key="parameter.key">
            <dt>{{ parameter.label }}</dt>
            <dd><span v-for="value in parameter.values" :key="value">{{ value }}</span></dd>
          </div>
        </dl>
        <p v-else class="price-unit">暂无能力参数</p>
        <h3 class="section-title">完整价目</h3>
        <AppTable :data="selected.prices" :pagination="false" empty-text="暂无报价" class="catalog-detail-prices">
          <el-table-column label="参数组合" min-width="200"><template #default="{ row }">{{ variantLabel(row.variant) }}</template></el-table-column>
          <el-table-column label="售价（积分）" min-width="130" align="right"><template #default="{ row }"><strong class="numeric">{{ money(row.unit_price) }}</strong></template></el-table-column>
          <el-table-column label="单位" width="90"><template #default="{ row }">/ {{ units[row.unit as keyof typeof units] }}</template></el-table-column>
        </AppTable>
      </template>
    </el-dialog>
  </section>
</template>
