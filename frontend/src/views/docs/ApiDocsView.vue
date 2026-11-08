<script setup lang="ts">
import { CopyDocument } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AppTable from '../../components/AppTable.vue'
import PageHeader from '../../components/PageHeader.vue'

const origin = window.location.origin
const example = `curl '${origin}/v1/models' \\
  -H 'Authorization: Bearer YOUR_API_KEY'`
const generationExample = `curl '${origin}/v1/images/generations' \\
  -H 'Authorization: Bearer YOUR_API_KEY' \\
  -H 'Content-Type: application/json' \\
  -d '{"model":"YOUR_MODEL_ID","prompt":"A red ceramic cup","n":1}'`

async function copy() {
  try { await navigator.clipboard.writeText(example); ElMessage.success('已复制') }
  catch { ElMessage.error('复制失败，请手动选择') }
}

async function copyGeneration() {
  try { await navigator.clipboard.writeText(generationExample); ElMessage.success('已复制') }
  catch { ElMessage.error('复制失败，请手动选择') }
}
</script>

<template>
  <section class="api-reference">
    <PageHeader eyebrow="开发者" title="API 文档">
      <el-tag type="info" effect="plain">v0.1.0</el-tag>
    </PageHeader>
    <section aria-labelledby="openai-api-title">
      <div class="reference-status"><h2 id="openai-api-title" class="section-title">OpenAI 兼容接口</h2><el-tag type="success" effect="plain">模型列表已开放</el-tag></div>
      <p class="reference-description">Base URL：<code>{{ origin }}/v1</code>。使用本站 API Key 进行 Bearer 鉴权，网页登录状态不能替代 API Key。<router-link to="/console/tokens">前往 API 令牌</router-link>创建 Key。</p>
      <h3>模型列表</h3>
      <div class="endpoint"><el-tag type="success" effect="plain">GET</el-tag><code>/v1/models</code><span>需要 API Key</span></div>
      <p class="reference-description">返回已上架、供应商启用且已配置价格的模型。模型 ID 为本站唯一模型 ID，不返回采购成本、供应商映射或本站价格字段。</p>
      <div class="code-heading"><h3>请求</h3><el-tooltip content="复制请求"><el-button :icon="CopyDocument" class="icon-button" aria-label="复制请求" @click="copy" /></el-tooltip></div>
      <pre><code>{{ example }}</code></pre>
      <h3>响应示例（暂无上架模型）</h3>
      <pre><code>{
  "object": "list",
  "data": []
}</code></pre>
      <AppTable :pagination="false" :data="[
        { field: 'object', description: '固定为 list' },
        { field: 'data[].id', description: '本站唯一模型 ID' },
        { field: 'data[].object', description: '固定为 model' },
        { field: 'data[].created', description: '本站模型创建时间，Unix 秒级时间戳' },
        { field: 'data[].owned_by', description: '固定为 nodepass，不暴露上游供应商' },
      ]">
        <el-table-column prop="field" label="响应字段" min-width="170" />
        <el-table-column prop="description" label="说明" min-width="220" />
      </AppTable>
      <h3 class="section-title">鉴权错误（HTTP 401）</h3>
      <pre><code>{
  "error": {
    "message": "Invalid API key.",
    "type": "invalid_request_error",
    "param": null,
    "code": "invalid_api_key"
  }
}</code></pre>
      <p class="reference-description">缺少、错误或已停用的 Key，以及已停用账户的 Key 均返回 401。本站账户密码和上游供应商 Key 不可用于此接口。</p>
    </section>
    <section aria-labelledby="generation-api-title">
      <div class="reference-status"><h2 id="generation-api-title" class="section-title">图片生成</h2><el-tag type="success" effect="plain">已开放</el-tag></div>
      <p class="reference-description">请求使用本站模型 ID。接口先返回任务编号，后台完成沧元生成、结果转存到本站 OSS 和积分结算后，再通过查询接口获取结果。</p>
      <div class="endpoint"><el-tag type="success" effect="plain">POST</el-tag><code>/v1/images/generations</code><span>需要 API Key</span></div>
      <div class="code-heading"><h3>请求</h3><el-tooltip content="复制请求"><el-button :icon="CopyDocument" class="icon-button" aria-label="复制请求" @click="copyGeneration" /></el-tooltip></div>
      <pre><code>{{ generationExample }}</code></pre>
      <div class="endpoint"><el-tag type="primary" effect="plain">GET</el-tag><code>/v1/images/generations/{id}</code><span>需要 API Key</span></div>
      <p class="reference-description">任务状态包括排队、生成中、转存中、成功和失败。只有 OSS 转存成功后，响应中的 data 才会出现本站结果地址。</p>
    </section>
    <p class="reference-description">模型规格和本站售价请查看<router-link to="/pricing">模型广场</router-link>。</p>
  </section>
</template>
