<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChatDotRound, Collection, Connection, Key, List, Picture, VideoCamera, Warning } from '@element-plus/icons-vue'
import { ElTabPane, ElTabs } from 'element-plus'
import AppTable from '../../components/AppTable.vue'
import PageHeader from '../../components/PageHeader.vue'
import ApiCodeBlock from './ApiCodeBlock.vue'
import generationBody from './image-generation.example.json'
import editBody from './image-edit.example.json'

const chapters = [
  { id: 'quickstart', title: '快速开始', icon: Connection },
  { id: 'authentication', title: '鉴权', icon: Key },
  { id: 'models', title: '模型列表', icon: Collection },
  { id: 'chat-completions', title: '文本对话', icon: ChatDotRound },
  { id: 'image-generation', title: '图片生成', icon: Picture },
  { id: 'image-edit', title: '图片编辑', icon: Picture },
  { id: 'query-task', title: '查询图片任务', icon: List },
  { id: 'video-generation', title: '视频生成', icon: VideoCamera },
  { id: 'video-query-task', title: '查询视频任务', icon: List },
  { id: 'states-and-errors', title: '状态与错误', icon: Warning },
]
const endpoints = [
  { id: 'models', method: 'GET', path: '/v1/models', title: '模型列表' },
  { id: 'chat-completions', method: 'POST', path: '/v1/chat/completions', title: 'Chat Completions' },
  { id: 'responses', method: 'POST', path: '/v1/responses', title: 'Responses' },
  { id: 'image-generation', method: 'POST', path: '/v1/images/generations', title: '图片生成' },
  { id: 'image-edit', method: 'POST', path: '/v1/images/edits', title: '图片编辑' },
  { id: 'query-task', method: 'GET', path: '/v1/images/generations/{task_id}', title: '查询图片任务' },
  { id: 'video-generation', method: 'POST', path: '/v1/videos', title: '视频生成' },
  { id: 'video-query-task', method: 'GET', path: '/v1/videos/{task_id}', title: '查询视频任务' },
]
const route = useRoute()
const router = useRouter()
const activeChapter = ref('quickstart')
const textProtocol = ref('chat-completions')
const activeEndpoint = computed(() => {
  if (activeChapter.value === 'chat-completions') return textProtocol.value
  return endpoints.some(endpoint => endpoint.id === activeChapter.value) ? activeChapter.value : ''
})
const mobileDirectory = ref<HTMLDetailsElement>()
let observer: IntersectionObserver | undefined

watch(() => route.hash, hash => {
  if (hash === '#chat-completions' || hash === '#responses') {
    textProtocol.value = hash.slice(1)
    activeChapter.value = 'chat-completions'
  }
}, { immediate: true })

function selectTextProtocol(value: string | number) {
  const hash = `#${value}`
  if (route.hash !== hash) void router.push({ hash })
}

onMounted(() => {
  const visible = new Set<string>()
  // Exclude subpixel overlap from the preceding chapter after anchor scrolling.
  observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (entry.isIntersecting) visible.add(entry.target.id)
      else visible.delete(entry.target.id)
    }
    const current = chapters.find(chapter => visible.has(chapter.id))
    if (current) activeChapter.value = current.id
  }, { rootMargin: '-121px 0px -45% 0px' })
  for (const chapter of chapters) {
    const element = document.getElementById(chapter.id)
    if (element) observer.observe(element)
  }
})
onBeforeUnmount(() => observer?.disconnect())

function selectChapter(id: string) {
  activeChapter.value = id
  if (mobileDirectory.value) mobileDirectory.value.open = false
}

function shortPath(path: string) {
  return path.replace('/{task_id}', '/…')
}

const origin = window.location.origin
const setupExample = `export BASE_URL='${origin}/v1'
export API_KEY='YOUR_API_KEY'
export MODEL_ID='YOUR_MODEL_ID'`
const modelsExample = `curl --fail-with-body "$BASE_URL/models" \\
  -H "Authorization: Bearer $API_KEY"`
const generationExample = `curl --fail-with-body "$BASE_URL/images/generations" \\
  -H "Authorization: Bearer $API_KEY" \\
  -H 'Content-Type: application/json' \\
  -d "{\\"model\\":\\"$MODEL_ID\\",\\"prompt\\":\\"${generationBody.prompt}\\",\\"n\\":1}"`
const queryExample = `export TASK_ID='YOUR_TASK_ID'
curl --fail-with-body "$BASE_URL/images/generations/$TASK_ID" \\
  -H "Authorization: Bearer $API_KEY"`
const editExample = `curl --fail-with-body "$BASE_URL/images/edits" \\
  -H "Authorization: Bearer $API_KEY" \\
  -H 'Content-Type: application/json' \\
  -d '${JSON.stringify(editBody)}'`
const videoBody = {
  model: 'YOUR_VIDEO_MODEL_ID',
  prompt: '雨天咖啡馆门口，两个人物并肩走向街道，写实电影感。',
  seconds: 15,
  resolution: '720p',
  aspect_ratio: '9:16',
  references: [{ type: 'reference_image', url: 'https://example.com/reference.png' }],
}
const videoGenerationExample = `curl --fail-with-body "$BASE_URL/videos" \\
  -H "Authorization: Bearer $API_KEY" \\
  -H 'Content-Type: application/json' \\
  -d '${JSON.stringify(videoBody)}'`
const videoQueryExample = `export VIDEO_TASK_ID='YOUR_VIDEO_TASK_ID'
curl --fail-with-body "$BASE_URL/videos/$VIDEO_TASK_ID" \\
  -H "Authorization: Bearer $API_KEY"`
const textExample = (path: string, body: object) => `curl --fail-with-body '${origin}/v1/${path}' \\
  -H 'Authorization: Bearer YOUR_API_KEY' \\
  -H 'Content-Type: application/json' \\
  -d '${JSON.stringify({ model: 'YOUR_TEXT_MODEL_ID', ...body })}'`
const chatExample = textExample('chat/completions', {
  messages: [{ role: 'user', content: '请用一句话介绍自己。' }],
})
const chatVisionExample = textExample('chat/completions', {
  messages: [{ role: 'user', content: [
    { type: 'text', text: '描述图片中的人物和场景。' },
    { type: 'image_url', image_url: { url: 'https://YOUR_MEDIA_DOMAIN/YOUR_IMAGE.png' } },
  ] }],
})
const responsesExample = textExample('responses', {
  input: '请用一句话介绍自己。', store: false,
})
const searchPrompt = '请联网搜索 NASA 的 Artemis II 官方资料，并注明来源。'
const chatSearchExample = textExample('chat/completions', {
  messages: [{ role: 'user', content: searchPrompt }], web_search_options: {},
})
const responsesSearchExample = textExample('responses', {
  input: searchPrompt, tools: [{ type: 'web_search' }],
})
const visionExample = textExample('responses', {
  input: [{ role: 'user', content: [
    { type: 'input_text', text: '描述图片中的人物和场景。' },
    { type: 'input_image', image_url: 'https://YOUR_MEDIA_DOMAIN/YOUR_IMAGE.png' },
  ] }],
})
const outputSchema = {
  name: 'character', strict: true,
  schema: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'], additionalProperties: false },
}
const chatSchemaExample = textExample('chat/completions', {
  messages: [{ role: 'user', content: '提取角色名字：李明是一位摄影师。' }],
  response_format: { type: 'json_schema', json_schema: outputSchema },
})
const responsesSchemaExample = textExample('responses', {
  input: '提取角色名字：李明是一位摄影师。',
  text: { format: { type: 'json_schema', ...outputSchema } },
})
const streamExample = textExample('chat/completions', {
  messages: [{ role: 'user', content: '请用一句话介绍自己。' }],
  stream: true, stream_options: { include_usage: true },
}).replace('curl --fail-with-body', 'curl -N --fail-with-body')
const responsesStreamExample = textExample('responses', {
  input: '请用一句话介绍自己。', stream: true, store: false,
}).replace('curl --fail-with-body', 'curl -N --fail-with-body')
const functionExampleSetup = `from openai import OpenAI

client = OpenAI(base_url="${origin}/v1", api_key="YOUR_API_KEY", max_retries=0)
model = "YOUR_TEXT_MODEL_ID"
lookup = {
    "name": "lookup_character",
    "strict": True,
    "description": "Look up a character by name.",
    "parameters": {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    },
}
prompt = {"role": "user", "content": "查询李明的角色设定，然后用一句话概括。"}
# Demo result; in production run your own authorized function.
result = '{"name":"李明","job":"摄影师"}'
`
const chatFunctionExample = `${functionExampleSetup}
tools = [{"type": "function", "function": lookup}]
first = client.chat.completions.create(
    model=model, messages=[prompt], tools=tools, tool_choice="required"
)
message = first.choices[0].message
outputs = [
    {"role": "tool", "tool_call_id": call.id, "content": result}
    for call in message.tool_calls
]
final = client.chat.completions.create(
    model=model, messages=[prompt, message.model_dump(exclude_unset=True), *outputs],
    tools=tools, tool_choice="none",
)
print(final.choices[0].message.content)`
const responsesFunctionExample = `${functionExampleSetup}
tools = [{"type": "function", **lookup}]
first = client.responses.create(
    model=model, input=[prompt], tools=tools, tool_choice="required"
)
outputs = [
    {"type": "function_call_output", "call_id": item.call_id, "output": result}
    for item in first.output if item.type == "function_call"
]
history = [item.model_dump(exclude_unset=True) for item in first.output]
final = client.responses.create(
    model=model, input=[prompt, *history, *outputs], tools=tools, tool_choice="none"
)
print(final.output_text)`
const chatResponse = {
  id: 'chatcmpl-YOUR_CALL_ID', object: 'chat.completion', created: 1794182400,
  model: 'YOUR_TEXT_MODEL_ID',
  choices: [{ index: 0, message: { role: 'assistant', content: '我是你的 AI 助手。' }, finish_reason: 'stop' }],
  usage: {
    prompt_tokens: 10, completion_tokens: 5, total_tokens: 15,
    prompt_tokens_details: { cached_tokens: 0 }, completion_tokens_details: { reasoning_tokens: 0 },
  },
}
const responsesResponse = {
  id: 'resp_YOUR_CALL_ID', object: 'response', created_at: 1794182400,
  status: 'completed', model: 'YOUR_TEXT_MODEL_ID',
  output: [{
    id: 'msg_YOUR_CALL_ID', type: 'message', role: 'assistant', status: 'completed',
    content: [{ type: 'output_text', text: '我是你的 AI 助手。', annotations: [] }],
  }],
  usage: {
    input_tokens: 10, input_tokens_details: { cached_tokens: 0 },
    output_tokens: 5, output_tokens_details: { reasoning_tokens: 0 }, total_tokens: 15,
  },
  error: null, incomplete_details: null, store: false,
}
const pythonExample = `import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "${origin}/v1"
API_KEY = "YOUR_API_KEY"
MODEL_ID = "YOUR_MODEL_ID"

def request(path, body=None):
    headers = {"Authorization": f"Bearer {API_KEY}"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = Request(BASE_URL + path, data=data, headers=headers)
    try:
        with urlopen(req, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("网络中断或超时，请核实任务记录，不要自动重新提交") from exc

models = request("/models")
if not any(model["id"] == MODEL_ID for model in models["data"]):
    raise RuntimeError("请将 MODEL_ID 替换为当前可用的图片模型 ID")

task = request("/images/generations", {
    "model": MODEL_ID,
    "prompt": "${generationBody.prompt}",
    "n": 1,
})
task_id = task["id"]
print("任务 ID：", task_id, flush=True)

while True:
    result = request(f"/images/generations/{task_id}")
    state = result["status"]
    if state == "succeeded":
        print("图片 URL：", result["data"][0]["url"])
        break
    if state == "failed":
        raise RuntimeError(result["error"]["message"])
    if state == "submission_unknown":
        raise RuntimeError(f"任务 {task_id} 待核实，积分保持冻结，请联系客服")
    if state not in {"queued", "submitting", "pending", "processing", "transferring"}:
        raise RuntimeError(f"未识别状态 {state}，保留任务 {task_id}，不要重新提交")
    time.sleep(5)`
const json = (value: object) => JSON.stringify(value, null, 2)
const queued = {
  id: 'YOUR_TASK_ID', object: 'image.generation', status: 'queued',
  model: 'YOUR_MODEL_ID', created: 1794182400, data: [],
}
const processing = { ...queued, status: 'processing', completed: null, error: null }
const succeeded = {
  ...processing, status: 'succeeded', completed: 1794182425,
  data: [{ url: 'https://YOUR_RESULT_DOMAIN/YOUR_IMAGE_PATH.png' }],
}
const failed = {
  ...processing, status: 'failed', completed: 1794182425,
  error: { message: 'Image generation failed.', type: 'generation_error' },
}
const videoQueued = {
  id: 'YOUR_VIDEO_TASK_ID', object: 'video.generation', status: 'queued',
  model: 'YOUR_VIDEO_MODEL_ID', created: 1794182400, completed: null, timed_out: false, data: [],
}
const videoProcessing = { ...videoQueued, status: 'processing' }
const videoSucceeded = {
  ...videoProcessing, status: 'succeeded', completed: 1794183325,
  data: [{ url: 'https://YOUR_RESULT_DOMAIN/YOUR_VIDEO_PATH.mp4' }],
}
const requestError = {
  error: { message: 'Invalid API key.', type: 'invalid_request_error', param: null, code: 'invalid_api_key' },
}
const requestFields = [
  { field: 'model', type: 'string', required: '必填', description: '本站图片模型 ID，最长 160 字符；从模型广场选择。' },
  { field: 'prompt', type: 'string', required: '必填', description: '非空提示词，描述要生成的图片。' },
  { field: 'n', type: 'integer', required: '可选', description: '默认且仅支持 1，一次生成一张图片。' },
  { field: 'size', type: 'string', required: '按模型', description: '尺寸或比例；允许值、默认值以模型广场为准。' },
  { field: 'quality', type: 'string', required: '按模型', description: '质量；部分模型按此字段计价，允许值以模型广场为准。' },
  { field: 'tier', type: 'string', required: '可选', description: '本站扩展档位参数：web、1k、2k、4k，省略时使用后台配置的默认值。与 size 的尺寸比例分别设置。' },
  { field: 'series', type: 'string', required: '按模型', description: '本站扩展分支参数：gpt-image-2.5 支持 flare、sunburst；gpt-image-2 不支持。省略时使用后台配置的默认值。' },
  { field: 'background', type: 'string', required: '可选', description: '背景选项，仅在模型支持时传入。' },
  { field: 'output_format', type: 'string', required: '可选', description: '输出文件格式，仅在模型支持时传入。' },
  { field: 'response_format', type: 'string', required: '可选', description: '当前不控制返回形式，结果始终以 URL 返回；接入时请省略。' },
  { field: 'user', type: 'string', required: '可选', description: '当前仅记录在请求参数中，不改变任务归属。' },
]
const responseFields = [
  { field: 'id', type: 'string (UUID)', description: '本站任务 ID；提交、查询均返回，用于后续查询和联系客服。' },
  { field: 'object', type: 'string', description: '提交、查询均固定为 image.generation，属于本站扩展值。' },
  { field: 'status', type: 'string', description: '提交时为 queued；查询时返回下方状态表中的当前状态。' },
  { field: 'model', type: 'string', description: '提交、查询均返回创建任务时使用的本站模型 ID。' },
  { field: 'created', type: 'integer', description: '任务创建时间，Unix 秒级时间戳，始终有值。' },
  { field: 'data', type: 'array', description: '提交返回空数组；查询时只有 succeeded 才保证存在 data[].url。' },
  { field: 'data[].url', type: 'string', description: '任务成功后的本站图片结果 URL。' },
  { field: 'completed', type: 'integer | null', description: '仅查询响应包含；未完成时为 null，终态为 Unix 秒级完成时间戳。' },
  { field: 'error', type: 'object | null', description: '仅查询响应包含；failed 时为任务错误对象，其他状态为 null。' },
]
const editFields = [
  { field: 'images', type: 'array', required: '必填', description: '有序参考图数组，至少一张；数量上限以模型广场为准。' },
  { field: 'images[].image_url', type: 'string', required: '必填', description: '公开可访问的 HTTPS 图片 URL；图片顺序与提示词中的图片编号一致。' },
  { field: 'mask.image_url', type: 'string', required: '可选', description: '仅在模型支持 mask 时传入 HTTPS 蒙版 URL；作用于第一张参考图。使用带透明区域的 PNG，透明区域表示编辑范围，尺寸应与第一张参考图相同。' },
]
const videoRequestFields = [
  { field: 'model', type: 'string', required: '必填', description: '本站视频模型 ID，从模型广场选择。' },
  { field: 'prompt', type: 'string', required: '必填', description: '非空视频提示词；需要续集时，必须把上一段视频作为参考素材传入，并在提示词中描述衔接关系。' },
  { field: 'seconds', type: 'number', required: '按模型', description: '视频时长。按秒计费模型必须传入；按次模型可省略，省略时使用模型默认时长。' },
  { field: 'resolution', type: 'string', required: '可选', description: '分辨率；省略时使用模型默认值，传入时必须是该模型支持的值。' },
  { field: 'aspect_ratio', type: 'string', required: '可选', description: '画面比例；省略时使用模型默认值，传入时必须是该模型支持的值。' },
  { field: 'references', type: 'array', required: '可选', description: 'HTTPS 参考素材数组；数量上限和支持类型以模型广场为准。' },
]
const videoReferenceFields = [
  { field: 'first_frame', description: '首帧图片。' },
  { field: 'last_frame', description: '尾帧图片。' },
  { field: 'reference_image', description: '人物、场景等参考图片。' },
  { field: 'reference_video', description: '参考视频；续集应传入上一段视频 URL。' },
  { field: 'reference_audio', description: '参考音频。' },
]
const videoResponseFields = [
  { field: 'id', type: 'string (UUID)', description: '本站视频任务 ID。' },
  { field: 'object', type: 'string', description: '固定为 video.generation。' },
  { field: 'status', type: 'string', description: '当前任务状态，见状态表。' },
  { field: 'model', type: 'string', description: '创建任务时使用的本站视频模型 ID。' },
  { field: 'created', type: 'integer', description: '创建时间，Unix 秒级时间戳。' },
  { field: 'completed', type: 'integer | null', description: '未完成时为 null，终态时为 Unix 秒级完成时间戳。' },
  { field: 'timed_out', type: 'boolean', description: '是否曾超过任务时限；true 不代表失败，任务仍可能成功。' },
  { field: 'data', type: 'array', description: '提交和未完成查询为空；仅 succeeded 保证存在 data[].url。' },
  { field: 'data[].url', type: 'string', description: '成功后的视频结果 URL。' },
  { field: 'error', type: 'object | null', description: '仅 failed 时返回任务错误对象。' },
]
const states = [
  { state: 'queued', meaning: '排队中', action: '继续查询。' },
  { state: 'submitting', meaning: '提交中', action: '继续查询，不要重复提交。' },
  { state: 'pending', meaning: '等待生成', action: '继续查询。' },
  { state: 'processing', meaning: '生成中', action: '继续查询。' },
  { state: 'transferring', meaning: '结果保存中', action: '继续查询，结果保存完成后才会成功并结算。' },
  { state: 'submission_unknown', meaning: '提交结果待核实', action: '积分保持冻结；保留任务 ID，联系客服核实后结算或释放，不要重复提交。' },
  { state: 'succeeded', meaning: '已完成', action: '已结算，读取 data[].url；completed 已写入。' },
  { state: 'failed', meaning: '已失败', action: '冻结已释放，completed 已写入；读取任务 error.message。' },
]
const errors = [
  { http: '401', type: 'invalid_request_error', code: 'invalid_api_key', cause: 'Key 缺失、错误、停用、过期，或账户停用。', action: '检查 API 令牌和账户状态。' },
  { http: '402', type: 'insufficient_quota', code: 'insufficient_quota', cause: '生成任务冻结金额不足；或文本调用前可用积分小于等于零。', action: '补充积分后再提交。' },
  { http: '404', type: 'invalid_request_error', code: 'not_found', cause: '模型不存在；任务不存在或不属于当前账户。', action: '检查模型 / 任务 ID 和 Key 所属账户；不会用 403 泄露其他账户的任务是否存在。' },
  { http: '405', type: 'invalid_request_error', code: 'method_not_allowed', cause: '路径对应的 HTTP 方法不支持。', action: '按文档检查 GET / POST。' },
  { http: '409', type: 'invalid_request_error', code: 'null', cause: '积分账户未初始化。', action: '联系客服核实账户。' },
  { http: '422', type: 'invalid_request_error', code: 'invalid_request', cause: '字段类型错误、未知字段、必填项缺失、n 不等于 1，或任务 ID 不是 UUID。', action: '修正请求结构和字段类型。' },
  { http: '422', type: 'invalid_request_error', code: 'null', cause: '模型不支持参数值、缺少计价参数或没有匹配价格；生成参考素材 URL 无效、超出数量上限或不支持 mask。', action: '查看模型广场的规格，调整参数。' },
  { http: '502', type: 'server_error', code: 'null', cause: '文本请求被拒绝、连接中断、结果无效或缺失最终用量。', action: '不要自动重新提交；保留调用信息，联系客服核实。' },
  { http: '503', type: 'server_error', code: 'service_unavailable', cause: '数据库暂时不可用。', action: '稍后查询；若提交结果不明确，先核实任务记录，不自动重提。' },
  { http: '503', type: 'server_error', code: 'null', cause: '所选模型当前不可用。', action: '查看可用模型并核实状态。' },
  { http: '500', type: 'server_error', code: 'internal_error', cause: '未预期错误。', action: '保留已有任务 ID；提交结果不明确时联系客服，不自动重提。' },
]
const language = ref('curl')
</script>

<template>
  <section class="api-docs">
    <PageHeader eyebrow="开发者" title="API 文档">
      <el-tag type="info" effect="plain">生成与文本 API</el-tag>
    </PageHeader>
    <div class="api-docs-layout">
      <aside class="api-docs-sidebar">
        <nav aria-label="API 文档目录">
          <p class="api-directory-label">接入指南</p>
          <router-link v-for="chapter in chapters" :key="chapter.id" :to="`#${chapter.id}`" :aria-current="activeChapter === chapter.id ? 'location' : undefined" @click="selectChapter(chapter.id)">
            <el-icon aria-hidden="true"><component :is="chapter.icon" /></el-icon>{{ chapter.title }}
          </router-link>
          <router-link to="/pricing" class="api-directory-models">模型规格与定价</router-link>
        </nav>
      </aside>
      <div class="api-docs-content">
        <details ref="mobileDirectory" class="api-mobile-directory">
          <summary>文档目录 · {{ chapters.find(chapter => chapter.id === activeChapter)?.title }}</summary>
          <nav aria-label="API 文档移动目录">
            <router-link v-for="chapter in chapters" :key="chapter.id" :to="`#${chapter.id}`" :aria-current="activeChapter === chapter.id ? 'location' : undefined" @click="selectChapter(chapter.id)">{{ chapter.title }}</router-link>
          </nav>
        </details>

        <section id="quickstart" aria-labelledby="quickstart-title" class="api-chapter">
          <div class="api-chapter-heading"><span>01</span><h2 id="quickstart-title">快速开始</h2></div>
          <p>创建 API Key，选择图片或视频模型，提交生成任务，再查询并获取结果 URL。</p>
          <dl class="api-connection">
            <div><dt>Base URL</dt><dd><code>{{ `${origin}/v1` }}</code></dd></div>
            <div><dt>鉴权方式</dt><dd><code>Authorization: Bearer YOUR_API_KEY</code></dd></div>
          </dl>
          <aside class="api-note" aria-labelledby="compatibility-title">
            <h3 id="compatibility-title">协议兼容性</h3>
            <p>模型列表采用 OpenAI 风格。图片生成、图片编辑和视频生成采用本站异步扩展：提交返回 HTTP 202 和任务 ID；图片任务的 object 为 image.generation，视频为 video.generation。</p>
            <p><code>GET /v1/images/generations/{task_id}</code> 和 <code>GET /v1/videos/{task_id}</code> 是本站查询扩展。路径相同不代表完整协议相同，不能假定 OpenAI SDK 的同步生成调用可以直接使用。</p>
            <p>文本使用 <code>POST /v1/chat/completions</code> 或 <code>POST /v1/responses</code>，支持本文列出的字段、文本与图片输入、JSON 和 SSE；不创建需要轮询的生成任务。</p>
            <p>查询到 <code>succeeded</code> 后再读取 <code>data[].url</code>；当前结果始终以 URL 返回。</p>
          </aside>
          <el-tabs v-model="language" aria-label="示例语言">
            <el-tab-pane label="cURL" name="curl">
              <h3>1. 准备 Key 和模型 ID</h3>
              <p>在<router-link to="/console/tokens">控制台 API 令牌</router-link>创建 Key，在<router-link to="/pricing">模型广场</router-link>选择图片模型。替换下列占位符，在同一终端按顺序执行；需要 cURL。所选模型如要求额外计价参数，请按模型广场补充。</p>
              <ApiCodeBlock title="配置接入参数" :code="setupExample" language="Shell" />
              <h3>2. 确认可调用模型</h3>
              <ApiCodeBlock title="查询模型列表" :code="modelsExample" language="Shell" />
              <h3>3. 提交图片生成</h3>
              <p>提交会冻结积分。保存响应中的 <code>id</code>，它就是下一步的 <code>YOUR_TASK_ID</code>。</p>
              <ApiCodeBlock title="提交生成请求" :code="generationExample" language="Shell" />
              <h3>4. 查询任务，获取结果</h3>
              <p>替换任务 ID，重复执行查询命令；建议间隔 5 秒。只有 <code>succeeded</code> 才读取 <code>data[0].url</code>，其他情况见<a href="#states-and-errors">状态与错误</a>。</p>
              <ApiCodeBlock title="查询生成任务" :code="queryExample" language="Shell" />
            </el-tab-pane>
            <el-tab-pane label="Python" name="python">
              <p>仅使用 Python 3 标准库。替换 Key、模型 ID 后执行；如模型要求额外计价参数，请在提交对象中补充。脚本会输出任务 ID，成功后输出图片 URL。按 Ctrl+C 可停止本地等待，任务仍会继续处理。</p>
              <ApiCodeBlock title="完整异步生成示例" :code="pythonExample" language="Python" />
            </el-tab-pane>
          </el-tabs>
          <p class="api-note">请求超时或网络中断不等于任务失败。已有任务 ID 时继续查询；提交响应丢失时，先到控制台任务日志核实，不要自动重新提交，以免重复生成和冻结积分。</p>
        </section>

        <section id="authentication" aria-labelledby="authentication-title" class="api-chapter">
          <div class="api-chapter-heading"><span>02</span><h2 id="authentication-title">鉴权</h2></div>
          <p>以下接口均需要本站 API Key，网页登录状态不能替代它。请在服务端保管 Key。</p>
          <ApiCodeBlock title="请求头" code="Authorization: Bearer YOUR_API_KEY" language="HTTP" />
          <p>Key 缺失、错误、停用、过期，或所属账户停用时，返回 HTTP 401。同一账户的不同有效 Key 可以查询该账户的任务。</p>
        </section>

        <section id="models" aria-labelledby="models-title" class="api-chapter">
          <div class="api-chapter-heading"><span>03</span><h2 id="models-title">模型列表</h2></div>
          <div class="api-endpoint"><el-tag type="success" effect="plain">GET</el-tag><code>/v1/models</code><span>HTTP 200</span></div>
          <p>无需请求参数。返回当前账户通过 API Key 可访问的已上架、可用且已配置价格的模型。具体图片规格和售价见<router-link to="/pricing">模型广场</router-link>。</p>
          <ApiCodeBlock title="模型列表响应" :code="json({ object: 'list', data: [{ id: 'YOUR_MODEL_ID', object: 'model', created: 1794182400, owned_by: 'nodepass' }] })" />
          <AppTable :pagination="false" :data="[
            { field: 'object', description: '固定为 list。' },
            { field: 'data', description: '模型数组；没有可用模型时为空数组。' },
            { field: 'data[].id', description: '本站唯一模型 ID，作为生成请求的 model。' },
            { field: 'data[].object', description: '固定为 model。' },
            { field: 'data[].created', description: '模型创建时间，Unix 秒级时间戳。' },
            { field: 'data[].owned_by', description: '固定为 nodepass。' },
          ]">
            <el-table-column prop="field" label="响应字段" min-width="170" />
            <el-table-column prop="description" label="说明" min-width="260" />
          </AppTable>
        </section>

        <section id="chat-completions" aria-labelledby="chat-completions-title" class="api-chapter">
          <span id="responses" class="api-protocol-anchor" aria-hidden="true"></span>
          <div class="api-chapter-heading"><span>04</span><h2 id="chat-completions-title">文本对话</h2></div>
          <p>选择一种接口接入。两者均以 JSON 或 SSE 返回文本或函数调用，不需要轮询；消息历史须随每次请求完整传入。</p>
          <el-tabs v-model="textProtocol" aria-label="文本对话接口" @tab-change="selectTextProtocol">
            <el-tab-pane label="Chat Completions" name="chat-completions">
              <div class="api-endpoint"><el-tag type="primary" effect="plain">POST</el-tag><code>/v1/chat/completions</code><span>HTTP 200 · JSON / SSE</span></div>
              <h3>请求参数</h3>
              <p>必填 <code>model</code> 和 <code>messages</code>。消息角色支持 system、developer、user、assistant；内容为字符串，或由 text、image_url 组成的数组。</p>
              <p>可选字段为 <code>stream</code>、<code>stream_options.include_usage</code>、<code>max_completion_tokens</code>、固定为 1 的 <code>n</code>，以及函数调用的 <code>tools</code>、<code>tool_choice</code>。未知字段返回 422。</p>
              <ApiCodeBlock title="Chat Completions 请求" :code="chatExample" language="cURL" />
              <h3>结构化输出</h3>
              <p>通过 <code>response_format</code> 指定 JSON Schema，支持 <code>strict: true</code>；也可使用 <code>{"type":"json_object"}</code> 并在提示词中要求 JSON。</p>
              <ApiCodeBlock title="Chat Completions 结构化输出" :code="chatSchemaExample" language="cURL" />
              <h3>响应与用量</h3>
              <p>返回文本从 <code>choices[0].message.content</code> 读取。finish_reason 为 stop 或 length，后者表示达到输出上限。</p>
              <ApiCodeBlock title="Chat Completions 响应" :code="json(chatResponse)" />
              <p>usage 中的 <code>prompt_tokens</code>、<code>completion_tokens</code> 分别为输入、输出总量；<code>prompt_tokens_details.cached_tokens</code>、<code>completion_tokens_details.reasoning_tokens</code> 分别为缓存命中、思考用量。</p>
              <h3>流式返回</h3>
              <p>设置 stream 为 true，以 SSE 的 <code>choices[].delta.content</code> 接收文本。请求 include_usage 后，最后一个 JSON 块的 choices 为空、usage 为最终累计用量，随后发送 <code>[DONE]</code>。不要将各块用量相加。</p>
              <ApiCodeBlock title="Chat Completions SSE 请求" :code="streamExample" language="cURL" />
              <p>SSE 开始后发生错误时返回带 error 对象的数据块。此时 HTTP 200 不代表完整成功，不要自动重试。</p>
              <h3>工具调用</h3>
              <p>使用 <code>tools[].function</code> 声明函数。普通响应从 <code>message.tool_calls</code> 读取调用；SSE 从 <code>delta.tool_calls</code> 读取，按 index 对应，正常工具调用的 <code>finish_reason</code> 为 <code>tool_calls</code>。下一轮保留原 assistant 消息，每个调用追加一条 <code>role: "tool"</code> 消息，原样回传 <code>tool_call_id</code>，用字符串 <code>content</code> 携带结果。</p>
              <ApiCodeBlock title="Chat Completions 函数调用往返" :code="chatFunctionExample" language="Python" />
              <h3>联网搜索</h3>
              <p>传入 <code>web_search_options: {}</code> 开启搜索。JSON 从 <code>choices[].message.annotations</code> 读取引用。加上 <code>stream: true</code> 后，引用在带 <code>finish_reason</code> 的块中，通过 <code>choices[].delta.annotations</code> 返回（本站扩展）。</p>
              <ApiCodeBlock title="Chat Completions 联网搜索" :code="chatSearchExample" language="cURL" />
              <h3>图片理解</h3>
              <p>图片只能出现在 user 消息中，支持 HTTPS URL 或 base64 data URI；detail 可为 auto、low、high。</p>
              <ApiCodeBlock title="Chat Completions 图片理解" :code="chatVisionExample" language="cURL" />
            </el-tab-pane>
            <el-tab-pane label="Responses" name="responses">
              <div class="api-endpoint"><el-tag type="primary" effect="plain">POST</el-tag><code>/v1/responses</code><span>HTTP 200 · JSON / SSE</span></div>
              <h3>请求参数</h3>
              <p>必填 <code>model</code> 和 <code>input</code>；input 可以是字符串，或带 role、content 的 message 数组，角色支持 system、developer、user、assistant。可选 instructions、stream、max_output_tokens，store 仅接受 false。</p>
              <p>函数调用使用 <code>tools</code>、<code>tool_choice</code>；不支持 <code>previous_response_id</code> 或服务端会话存储，未知字段返回 422。</p>
              <ApiCodeBlock title="Responses 请求" :code="responsesExample" language="cURL" />
              <h3>结构化输出</h3>
              <p>通过 <code>text.format</code> 指定 JSON Schema，支持 <code>strict: true</code>。</p>
              <ApiCodeBlock title="Responses 结构化输出" :code="responsesSchemaExample" language="cURL" />
              <h3>响应与用量</h3>
              <p>JSON 返回的 object 为 response，文本位于 <code>output[].content[].text</code>，对应内容类型为 output_text。达到输出上限时 status 为 incomplete，incomplete_details.reason 为 max_output_tokens，其余正常完成为 completed。</p>
              <ApiCodeBlock title="Responses 响应" :code="json(responsesResponse)" />
              <p>usage 包含 <code>input_tokens</code>、<code>input_tokens_details.cached_tokens</code>、<code>output_tokens</code>、<code>output_tokens_details.reasoning_tokens</code>、<code>total_tokens</code>，分别表示输入总量、缓存命中、输出总量、思考用量和总用量。</p>
              <h3>流式返回</h3>
              <p>设置 stream 为 true，依次接收 response.created、response.in_progress、response.output_item.added、response.content_part.added、response.output_text.delta 及对应 done 事件，最后为 response.completed 或 response.incomplete。事件有递增 sequence_number；文本增量位于 delta，最终累计用量位于 response.usage。</p>
              <ApiCodeBlock title="Responses SSE 请求" :code="responsesStreamExample" language="cURL" />
              <p>SSE 开始后发生错误时返回 error 事件，不会再发送完成事件。此时 HTTP 200 不代表完整成功，不要自动重试。</p>
              <h3>工具调用</h3>
              <p>在 <code>tools</code> 中直接声明 <code>type: "function"</code> 的函数。从 <code>output</code> 读取 <code>function_call</code>；SSE 提供 <code>response.function_call_arguments.delta</code> / <code>.done</code> 事件。下一轮保留原输入和全部输出项（包括 reasoning 及其 encrypted_content），为每个调用追加带原 <code>call_id</code> 及字符串 <code>output</code> 的 <code>function_call_output</code>。可传 <code>include: ["reasoning.encrypted_content"]</code>；接口会请求可回传的加密推理项。</p>
              <ApiCodeBlock title="Responses 函数调用往返" :code="responsesFunctionExample" language="Python" />
              <h3>联网搜索</h3>
              <p>在 <code>tools</code> 中传入 <code>{"type":"web_search"}</code> 开启搜索。实际搜索时，<code>output</code> 中会出现 <code>web_search_call</code>；从消息的 <code>output[].content[].annotations</code> 读取 <code>url_citation</code>。加上 <code>stream: true</code> 后，正文结束时通过 <code>response.output_text.annotation.added</code> 发送引用，最终响应也保留引用。</p>
              <ApiCodeBlock title="Responses 联网搜索" :code="responsesSearchExample" language="cURL" />
              <h3>图片理解</h3>
              <p>图片只能出现在 user 消息中，支持 HTTPS URL 或 base64 data URI；detail 可为 auto、low、high。</p>
              <ApiCodeBlock title="Responses 图片理解" :code="visionExample" language="cURL" />
            </el-tab-pane>
          </el-tabs>
          <p class="api-note">联网搜索支持 <code>gpt-6.1-sol</code>，不可与自定义函数混用。模型自行决定是否搜索，未找到可引用的来源时可能没有引用。引用位置以拼接后的完整正文为准。展示答案时，请把来源显示为可点击的链接。搜索不额外计费。</p>
          <p class="api-note">自定义函数支持 <code>strict: true</code>。<code>tool_choice</code> 可设为 <code>auto</code>、<code>none</code>、<code>required</code> 或指定已声明的函数。NodePass 不执行函数；调用方须校验参数和权限，保留调用 ID 的完整值，回传全部结果。Python 示例使用 <code>openai</code> SDK，每轮模型请求独立按用量计费。</p>
          <h3>Token 与积分</h3>
          <p>两个接口使用相同计费规则：输入总量包含缓存命中，普通输入按输入总量减去缓存命中量计算；输出总量包含思考 token，思考用量不重复计费。</p>
          <p>调用前要求可用积分大于零；完成后按实际用量扣费，允许余额成为负数，后续调用需补充积分。每笔账务四舍五入到八位小数。单价见<router-link to="/pricing">模型广场</router-link>。不提供本站回答缓存，缓存命中以实际返回用量为准。</p>
          <p>客户端断开后仍尽可能读取最终用量并结算。缺失最终用量或提交结果不明确时保留待核实记录，不自动重新调用；联系客服核实扣费。</p>
        </section>

        <section id="image-generation" aria-labelledby="image-generation-title" class="api-chapter">
          <div class="api-chapter-heading"><span>05</span><h2 id="image-generation-title">图片生成</h2></div>
          <div class="api-endpoint"><el-tag type="primary" effect="plain">POST</el-tag><code>/v1/images/generations</code><span>HTTP 202</span></div>
          <p>使用 <code>Content-Type: application/json</code>。请求校验并匹配价格后冻结积分、创建任务；HTTP 202 表示任务已受理，尚未生成完成。</p>
          <ApiCodeBlock title="生成请求 JSON" :code="json(generationBody)" />
          <h3>请求参数</h3>
          <AppTable :pagination="false" :data="requestFields">
            <el-table-column prop="field" label="参数" min-width="160" />
            <el-table-column prop="type" label="类型" width="85" />
            <el-table-column prop="required" label="要求" width="85" />
            <el-table-column prop="description" label="说明" min-width="240" />
          </AppTable>
          <p>不接受未知字段。可选的模型参数省略时使用已配置默认值；若计价维度没有默认值，必须显式提供。参数值不受支持或价格无法匹配时返回 422。</p>
          <ApiCodeBlock title="任务受理响应 · HTTP 202" :code="json(queued)" />
          <p>提交响应中 <code>data</code> 为空，不包含 <code>completed</code> 和 <code>error</code>。请保存任务 ID，使用<router-link to="#query-task">查询图片任务</router-link>获取结果。</p>
        </section>

        <section id="image-edit" aria-labelledby="image-edit-title" class="api-chapter">
          <div class="api-chapter-heading"><span>06</span><h2 id="image-edit-title">图片编辑</h2></div>
          <div class="api-endpoint"><el-tag type="primary" effect="plain">POST</el-tag><code>/v1/images/edits</code><span>HTTP 202</span></div>
          <p>根据提示词和参考图编辑图片。当前支持 <code>Content-Type: application/json</code>，素材仅接受公开可访问的 HTTPS URL，不接收文件上传、文件 ID 或 Base64 素材。</p>
          <p>先按快速开始配置 <code>BASE_URL</code> 和 <code>API_KEY</code>，替换示例中的模型 ID、图片域名和路径后执行。参考图按数组顺序传入，提示词可用“图片 1”“图片 2”对应指定人物或场景。</p>
          <ApiCodeBlock title="编辑请求 JSON" :code="json(editBody)" />
          <ApiCodeBlock title="提交图片编辑" :code="editExample" language="Shell" />
          <h3>编辑参数</h3>
          <AppTable :pagination="false" :data="editFields">
            <el-table-column prop="field" label="参数" min-width="180" />
            <el-table-column prop="type" label="类型" width="85" />
            <el-table-column prop="required" label="要求" width="85" />
            <el-table-column prop="description" label="说明" min-width="280" />
          </AppTable>
          <p>可选蒙版写作 <code>"mask": {"image_url": "https://YOUR_MEDIA_DOMAIN/YOUR_MASK.png"}</code>。不使用蒙版时省略 mask；不支持蒙版或参考图超限会返回 422。接口会校验地址和模型能力，素材格式、可访问性及蒙版尺寸由调用方保证。</p>
          <p><code>model</code>、<code>prompt</code>、<code>n</code>、<code>size</code>、<code>quality</code>、<code>tier</code>、<code>series</code>、<code>background</code>、<code>output_format</code>、<code>user</code> 沿用图片生成的参数规则。n 仍只支持 1；response_format 可省略，传入时仅接受 url。</p>
          <p>默认值与计价维度沿用所选模型配置，参考图数量不额外计价。校验和价格匹配成功后冻结积分；保存结果成功后结算，明确失败释放冻结。提交超时或网络中断不要自动重新提交。</p>
          <ApiCodeBlock title="图片编辑受理响应 · HTTP 202" :code="json(queued)" />
          <p>编辑任务使用 <code>GET /v1/images/generations/{task_id}</code> 查询，响应字段、状态和错误处理与图片生成一致。只有 <code>succeeded</code> 才读取 <code>data[].url</code>。</p>
        </section>

        <section id="query-task" aria-labelledby="query-task-title" class="api-chapter">
          <div class="api-chapter-heading"><span>07</span><h2 id="query-task-title">查询图片任务</h2></div>
          <div class="api-endpoint"><el-tag type="success" effect="plain">GET</el-tag><code>/v1/images/generations/{task_id}</code><span>HTTP 200</span></div>
          <p>图片生成和图片编辑共用此查询接口。路径参数 <code>task_id</code> 必须是提交响应中的 UUID。只能查询当前账户的任务；任务不存在或属于其他账户时均返回 404。</p>
          <ApiCodeBlock title="处理中响应 · HTTP 200" :code="json(processing)" />
          <ApiCodeBlock title="成功响应 · HTTP 200" :code="json(succeeded)" />
          <h3>提交与查询响应字段</h3>
          <AppTable :pagination="false" :data="responseFields">
            <el-table-column prop="field" label="字段" min-width="145" />
            <el-table-column prop="type" label="类型" min-width="140" />
            <el-table-column prop="description" label="出现条件与含义" min-width="280" />
          </AppTable>
          <p><code>created</code> 始终是创建时间；<code>completed</code> 在未完成时为 null，仅在终态有完成时间。两者均使用 Unix 秒级时间戳。</p>
        </section>

        <section id="video-generation" aria-labelledby="video-generation-title" class="api-chapter">
          <div class="api-chapter-heading"><span>08</span><h2 id="video-generation-title">视频生成</h2></div>
          <p>视频接口是本站异步扩展，仅支持提交任务和查询任务两个接口。提交成功后返回 HTTP 202；视频生成、结果转存和结算完成前，不会返回结果 URL。</p>
          <div class="api-endpoint"><el-tag type="primary" effect="plain">POST</el-tag><code>/v1/videos</code><span>HTTP 202</span></div>
          <p>提交会先校验参数和价格并冻结积分。参考素材只接受 HTTPS URL；需要生成续集时，必须把上一段视频作为 <code>reference_video</code> 传入，模型不会自动记住之前的任务。</p>
          <ApiCodeBlock title="视频生成请求 JSON" :code="json(videoBody)" />
          <ApiCodeBlock title="提交视频生成" :code="videoGenerationExample" language="Shell" />
          <h3>请求参数</h3>
          <AppTable :pagination="false" :data="videoRequestFields">
            <el-table-column prop="field" label="参数" min-width="150" />
            <el-table-column prop="type" label="类型" width="90" />
            <el-table-column prop="required" label="要求" width="90" />
            <el-table-column prop="description" label="说明" min-width="280" />
          </AppTable>
          <h3>参考素材类型</h3>
          <AppTable :pagination="false" :data="videoReferenceFields">
            <el-table-column prop="field" label="type" width="190" />
            <el-table-column prop="description" label="说明" min-width="280" />
          </AppTable>
          <p>提交响应示例：</p>
          <ApiCodeBlock title="任务受理响应 · HTTP 202" :code="json(videoQueued)" />
        </section>

        <section id="video-query-task" aria-labelledby="video-query-task-title" class="api-chapter">
          <div class="api-chapter-heading"><span>09</span><h2 id="video-query-task-title">查询视频任务</h2></div>
          <div class="api-endpoint"><el-tag type="success" effect="plain">GET</el-tag><code>/v1/videos/{task_id}</code><span>HTTP 200</span></div>
          <p>使用提交响应中的任务 ID查询当前状态。任务不存在或不属于当前账户时均返回 404；不要因为网络超时或 <code>timed_out: true</code> 重新提交。</p>
          <ApiCodeBlock title="查询视频任务" :code="videoQueryExample" language="Shell" />
          <ApiCodeBlock title="视频生成中 · HTTP 200" :code="json(videoProcessing)" />
          <ApiCodeBlock title="视频生成成功 · HTTP 200" :code="json(videoSucceeded)" />
          <h3>响应字段</h3>
          <AppTable :pagination="false" :data="videoResponseFields">
            <el-table-column prop="field" label="字段" min-width="150" />
            <el-table-column prop="type" label="类型" min-width="140" />
            <el-table-column prop="description" label="出现条件与含义" min-width="300" />
          </AppTable>
          <p>只有 <code>succeeded</code> 才读取 <code>data[].url</code>。<code>failed</code> 表示明确失败并已释放冻结积分；<code>submission_unknown</code> 需要人工核实，积分保持冻结。</p>
        </section>

        <section id="states-and-errors" aria-labelledby="states-and-errors-title" class="api-chapter">
          <div class="api-chapter-heading"><span>10</span><h2 id="states-and-errors-title">状态与错误</h2></div>
          <p>下面的任务状态用于图片和视频生成；文本接口直接返回结果或 SSE，不使用这些任务状态。</p>
          <h3>任务状态</h3>
          <AppTable :pagination="false" :data="states">
            <el-table-column prop="state" label="status" min-width="190" />
            <el-table-column prop="meaning" label="含义" min-width="125" />
            <el-table-column prop="action" label="调用方处理" min-width="280" />
          </AppTable>
          <p>遇到未识别状态时，不判定成功或失败，不重新提交，保留任务 ID；可以继续查询，持续无法识别时联系客服。示例脚本会停止本地轮询并保留任务 ID。</p>
          <p>超时不等于失败，不会仅因超时释放冻结积分。任务仍会继续处理，后续成功则交付并结算。<code>submission_unknown</code> 需要人工核实，单靠轮询不会自动恢复。</p>
          <p>需要人工协助时，请保留任务 ID，通过官网右上角的“联系客服”入口联系。当前客服二维码尚待配置，正式接入前请确认该入口可用。</p>

          <h3 id="request-errors">请求失败 · HTTP 非 2xx</h3>
          <p>读取顶层 <code>error.type</code>、<code>error.code</code>、<code>error.message</code>。<code>param</code> 当前为 null。按 HTTP 状态和 type 判断类别，code 非空时再细分，不按 message 文案判断程序分支。</p>
          <ApiCodeBlock title="请求失败示例 · HTTP 401" :code="json(requestError)" />
          <AppTable :pagination="false" :data="errors" class="api-error-table">
            <el-table-column prop="http" label="HTTP" width="75" />
            <el-table-column label="type / code" min-width="210">
              <template #default="{ row }"><code>{{ row.type }}</code><br><code class="api-muted">{{ row.code }}</code></template>
            </el-table-column>
            <el-table-column label="触发原因与处理" min-width="300">
              <template #default="{ row }"><p>{{ row.cause }}</p><p class="api-muted">{{ row.action }}</p></template>
            </el-table-column>
          </AppTable>

          <h3 id="task-errors">任务失败 · HTTP 200 + status: failed</h3>
          <p>HTTP 200 仅表示查询成功。任务 <code>status</code> 为 <code>failed</code> 才表示生成失败，读取任务中的 <code>error.message</code> 和 <code>error.type</code>。</p>
          <ApiCodeBlock title="任务失败响应 · HTTP 200" :code="json(failed)" />
          <AppTable :pagination="false" :data="[
            { field: 'error.message', description: '任务失败说明，string。' },
            { field: 'error.type', description: '固定为 generation_error。' },
          ]">
            <el-table-column prop="field" label="任务错误字段" min-width="170" />
            <el-table-column prop="description" label="说明" min-width="260" />
          </AppTable>
          <p>任务错误对象没有 <code>code</code> 和 <code>param</code>。此时冻结已释放，并写入 <code>completed</code>；成功任务则已结算并提供 <code>data[].url</code>。</p>
        </section>
      </div>
      <aside class="api-docs-toc" aria-label="接口速览">
        <nav>
          <p class="api-directory-label">接口速览</p>
          <router-link v-for="endpoint in endpoints" :key="endpoint.id" :to="`#${endpoint.id}`" :aria-current="activeEndpoint === endpoint.id ? 'location' : undefined">
            <span class="api-toc-method" :data-method="endpoint.method">{{ endpoint.method }}</span>
            <span class="api-toc-path"><code :title="endpoint.path">{{ shortPath(endpoint.path) }}</code><small>{{ endpoint.title }}</small></span>
          </router-link>
        </nav>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.api-docs { width: 100%; }
.api-docs-layout { display: grid; grid-template-columns: 190px minmax(0, 1fr) 230px; align-items: start; gap: 32px; }
.api-docs-sidebar { position: sticky; top: 108px; padding-right: 20px; border-right: 1px solid var(--app-border); }
.api-directory-label { margin: 0 10px 12px; color: var(--app-muted); font-size: 12px; }
.api-docs-sidebar a { display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 10px; margin-bottom: 4px; border-radius: 6px; color: var(--app-muted); }
.api-docs-sidebar a:hover, .api-docs-sidebar a[aria-current="location"] { color: var(--el-color-primary); background: var(--app-active); }
.api-docs-sidebar a[aria-current="location"] { font-weight: 600; }
.api-docs-sidebar .api-directory-models { margin-top: 24px; border-top: 1px solid var(--app-border); border-radius: 0; font-size: 13px; }
.api-docs-content { min-width: 0; }
.api-chapter { min-width: 0; padding: 36px 0; border-top: 1px solid var(--app-border); scroll-margin-top: 120px; }
.api-protocol-anchor { display: block; scroll-margin-top: 120px; }
.api-chapter:first-of-type { padding-top: 0; border-top: 0; }
.api-chapter-heading { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
.api-chapter-heading > span { color: var(--el-color-primary); font-size: 12px; font-family: monospace; }
.api-chapter h2 { font-size: 22px; font-weight: 650; }
.api-chapter h3 { margin: 28px 0 12px; font-size: 16px; scroll-margin-top: 120px; }
.api-chapter p { margin: 14px 0; line-height: 1.8; overflow-wrap: anywhere; }
.api-chapter p code { padding: 2px 4px; background: var(--app-code); border-radius: 3px; font-size: 12px; }
.api-connection { margin: 24px 0; }
.api-connection > div { display: grid; grid-template-columns: 100px minmax(0, 1fr); gap: 12px; padding: 10px 0; }
.api-connection dt { color: var(--app-muted); }
.api-connection dd { margin: 0; overflow-wrap: anywhere; }
.api-note { padding: 16px 18px; border-left: 3px solid var(--el-color-primary); background: var(--app-active); }
.api-note h3 { margin: 0 0 10px; }
.api-note p { margin: 8px 0; }
.api-endpoint { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; padding: 10px 14px; margin-bottom: 16px; border: 1px solid var(--app-border); border-left: 3px solid var(--el-color-primary); border-radius: 6px; background: var(--app-surface); }
.api-endpoint .el-tag { font-family: monospace; font-weight: 600; }
.api-endpoint code { overflow-wrap: anywhere; font-size: 13px; }
.api-endpoint > span:last-child { margin-left: auto; color: var(--app-muted); font-size: 12px; }
.api-docs-toc { position: sticky; top: 108px; padding-left: 20px; border-left: 1px solid var(--app-border); }
.api-docs-toc nav { display: grid; gap: 4px; }
.api-docs-toc a { display: flex; align-items: flex-start; gap: 8px; padding: 8px; border-radius: 6px; color: var(--app-muted); }
.api-docs-toc a:hover, .api-docs-toc a[aria-current="location"] { background: var(--app-active); color: var(--el-color-primary); }
.api-docs-toc a[aria-current="location"] .api-toc-path small { color: var(--el-color-primary); }
.api-toc-method { flex-shrink: 0; padding-top: 1px; font-family: monospace; font-size: 10px; font-weight: 700; letter-spacing: .04em; }
.api-toc-method[data-method="GET"] { color: var(--el-color-success); }
.api-toc-method[data-method="POST"] { color: var(--el-color-primary); }
.api-toc-path { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.api-toc-path code { font-size: 11px; overflow-wrap: anywhere; }
.api-toc-path small { color: var(--app-faint); font-size: 11px; }
.api-muted { color: var(--app-muted); }
.api-error-table p { margin: 0; font-size: 13px; }
.api-error-table code { font-size: 12px; }
.api-mobile-directory { display: none; }
@media (max-width: 1100px) {
  .api-docs-layout { grid-template-columns: 190px minmax(0, 1fr); gap: 32px; }
  .api-docs-toc { display: none; }
}
@media (max-width: 900px) {
  .api-docs-layout { grid-template-columns: minmax(0, 1fr); gap: 0; }
  .api-docs-sidebar { display: none; }
  .api-mobile-directory { display: block; margin-bottom: 28px; border-block: 1px solid var(--app-border); }
  .api-mobile-directory summary { padding: 14px 0; cursor: pointer; color: var(--el-color-primary); }
  .api-mobile-directory nav { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; padding-bottom: 16px; }
  .api-mobile-directory a { min-height: 44px; padding: 10px 8px; color: var(--app-text); border-radius: 4px; }
  .api-mobile-directory a[aria-current="location"] { background: var(--app-active); color: var(--el-color-primary); }
}
@media (max-width: 560px) {
  .api-chapter p { font-size: 16px; }
  .api-connection > div { grid-template-columns: minmax(0, 1fr); gap: 4px; }
  .api-connection code { font-size: 12px; }
  .api-note { padding: 14px; }
  .api-endpoint > span:last-child { margin-left: 0; }
}
</style>
