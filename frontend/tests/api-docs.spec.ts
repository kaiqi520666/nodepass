import { test, expect } from '@playwright/test'
import { execFile } from 'node:child_process'
import { createServer } from 'node:http'
import { promisify } from 'node:util'
import generationBody from '../src/views/docs/image-generation.example.json' with { type: 'json' }
import editBody from '../src/views/docs/image-edit.example.json' with { type: 'json' }

const execute = promisify(execFile)
const chapters = ['quickstart', 'authentication', 'models', 'chat-completions', 'image-generation', 'image-edit', 'query-task', 'video-generation', 'video-query-task', 'states-and-errors']

test('text docs share one chapter with protocol tabs and direct links', async ({ page, context }, testInfo) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.goto('/api-docs#chat-completions')
  const chapter = page.getByRole('region', { name: '文本对话', exact: true })
  const chat = chapter.getByRole('tab', { name: 'Chat Completions', exact: true })
  const responses = chapter.getByRole('tab', { name: 'Responses', exact: true })
  await expect(chat).toHaveAttribute('aria-selected', 'true')
  expect(await page.locator('.api-chapter').evaluateAll(elements => elements.map(element => element.id))).toEqual(chapters)
  const desktopDirectory = page.getByRole('navigation', { name: 'API 文档目录', exact: true })
  await expect(desktopDirectory.locator('a[href$="#responses"]')).toHaveCount(0)
  await expect(chapter.getByRole('heading', { name: 'Token 与积分', exact: true })).toHaveCount(1)

  for (const [tab, title, path, inputField] of [
    [chat, 'Chat Completions', '/v1/chat/completions', 'messages'],
    [responses, 'Responses', '/v1/responses', 'input'],
  ] as const) {
    await tab.click()
    await expect(tab).toHaveAttribute('aria-selected', 'true')
    const panel = chapter.getByRole('tabpanel', { name: title, exact: true })
    await expect(panel.locator('.api-endpoint code')).toHaveText(path)
    await panel.getByRole('button', { name: `复制${title} 请求`, exact: true }).click()
    const command = await page.evaluate(() => navigator.clipboard.readText())
    expect(command).toContain(path)
    const body = JSON.parse(command.split("  -d '")[1]!.slice(0, -1))
    expect(body.model).toBe('YOUR_TEXT_MODEL_ID')
    expect(body).toHaveProperty(inputField)
    expect(body).not.toHaveProperty(inputField === 'messages' ? 'input' : 'messages')
    await expect(panel.locator(`pre[aria-label="${title} SSE 请求"]`)).toContainText('curl -N')
    await expect(panel.locator(`pre[aria-label="${title} 函数调用往返"]`)).toContainText(
      title === 'Responses' ? 'function_call_output' : 'tool_call_id',
    )
    const searchCommand = await panel.locator(`pre[aria-label="${title} 联网搜索"]`).innerText()
    expect(searchCommand).toContain(path)
    const searchBody = JSON.parse(searchCommand.split("  -d '")[1]!.slice(0, -1))
    expect(searchBody).toHaveProperty(inputField)
    expect(searchBody).not.toHaveProperty('stream')
    if (title === 'Responses') expect(searchBody.tools).toEqual([{ type: 'web_search' }])
    else expect(searchBody.web_search_options).toEqual({})
    await expect(panel.getByText(
      title === 'Responses' ? 'response.output_text.annotation.added' : 'choices[].delta.annotations',
      { exact: true },
    )).toBeVisible()
    for (const media of ['图片理解', '结构化输出']) {
      await expect(panel.locator(`pre[aria-label="${title} ${media}"]`)).toContainText(path)
    }
    await expect(panel).not.toContainText('video_url')
    await expect(panel).not.toContainText('input_video')
    const response = JSON.parse(await panel.locator(`pre[aria-label="${title} 响应"]`).innerText())
    expect(response.object).toBe(title === 'Responses' ? 'response' : 'chat.completion')
    expect(response.usage.total_tokens).toBe(15)
  }
  await expect(page).toHaveURL('/api-docs#responses')
  await page.reload()
  await expect(responses).toHaveAttribute('aria-selected', 'true')
  await expect(chapter.getByRole('heading', { name: '文本对话', exact: true })).toBeInViewport()
  await page.goBack()
  await expect(chat).toHaveAttribute('aria-selected', 'true')
  await expect(page).toHaveURL('/api-docs#chat-completions')
  await page.goForward()
  await expect(responses).toHaveAttribute('aria-selected', 'true')

  if (testInfo.project.name === 'mobile') await page.locator('.api-mobile-directory summary').click()
  const directory = page.getByRole('navigation', { name: testInfo.project.name === 'mobile' ? 'API 文档移动目录' : 'API 文档目录', exact: true })
  await directory.getByRole('link', { name: '文本对话', exact: true }).click()
  await expect(chat).toHaveAttribute('aria-selected', 'true')
  const directorySelector = testInfo.project.name === 'mobile' ? '.api-mobile-directory' : '.api-docs-sidebar'
  await expect(page.locator(`${directorySelector} a[href$="#chat-completions"]`)).toHaveAttribute('aria-current', 'location')
  if (testInfo.project.name === 'mobile') {
    await page.setViewportSize({ width: 320, height: 812 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
})

test('API docs navigation, response examples and themes match the contract', async ({ page, context }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.goto('/api-docs#image-generation')
  await expect(page.getByRole('heading', { name: '图片生成', exact: true })).toBeInViewport()
  await expect(page.locator('.api-chapter')).toHaveCount(chapters.length)
  await expect(page.locator('.api-code-block pre[aria-label="生成请求 JSON"]')).toHaveText(JSON.stringify(generationBody, null, 2))
  await expect(page.locator('pre[aria-label="编辑请求 JSON"]')).toHaveText(JSON.stringify(editBody, null, 2))
  await expect(page.locator('#image-edit .api-endpoint code')).toHaveText('/v1/images/edits')
  await expect(page.locator('#query-task')).toContainText('图片生成和图片编辑共用此查询接口')
  for (const theme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const color = await page.locator('.api-code-block pre').first().evaluate(element => getComputedStyle(element).color)
    expect(color).not.toBe('rgba(0, 0, 0, 0)')
  }
  if (testInfo.project.name === 'mobile') {
    await page.locator('.api-mobile-directory summary').click()
  }
  const directory = page.getByRole('navigation', { name: testInfo.project.name === 'mobile' ? 'API 文档移动目录' : 'API 文档目录', exact: true })
  await directory.getByRole('link', { name: '查询图片任务', exact: true }).click()
  await expect(page).toHaveURL('/api-docs#query-task')
  await expect(page.getByRole('heading', { name: '查询图片任务', exact: true })).toBeInViewport()
  if (testInfo.project.name === 'mobile') {
    await expect(page.locator('.api-mobile-directory')).not.toHaveAttribute('open')
  }
  await page.reload()
  await expect(page.getByRole('heading', { name: '查询图片任务', exact: true })).toBeInViewport()
  await page.goBack()
  await expect(page).toHaveURL('/api-docs#image-generation')
  await expect(page.getByRole('heading', { name: '图片生成', exact: true })).toBeInViewport()
  await page.getByRole('button', { name: '复制生成请求 JSON', exact: true }).click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(JSON.stringify(generationBody, null, 2))

  const accepted = JSON.parse(await page.getByRole('region', { name: '图片生成', exact: true }).locator('pre').last().innerText())
  expect(accepted.status).toBe('queued')
  expect(accepted.data).toEqual([])
  expect(accepted).not.toHaveProperty('completed')
  const failure = JSON.parse(await page.locator('pre[aria-label="任务失败响应 · HTTP 200"]').innerText())
  expect(failure.status).toBe('failed')
  expect(failure.error).toEqual({ message: 'Image generation failed.', type: 'generation_error' })
  expect(failure.completed).toEqual(expect.any(Number))
  const stateTable = page.locator('#states-and-errors .app-table').first()
  for (const state of ['queued', 'submitting', 'pending', 'processing', 'transferring', 'submission_unknown', 'succeeded', 'failed']) {
    await expect(stateTable.getByRole('cell', { name: state, exact: true })).toHaveCount(1)
  }
  const httpCodes = await page.locator('.api-error-table tbody tr td:first-child').allTextContents()
  expect(httpCodes.map(value => value.trim())).toEqual(['401', '402', '404', '405', '409', '422', '422', '502', '503', '503', '500'])
  const content = await page.locator('.api-docs').innerText()
  for (const internal of ['供应商', '上游任务', 'OSS', '成本', '/api/account', '/api/public', 'b64_json']) {
    expect(content).not.toContain(internal)
  }
  for (const id of chapters) await expect(page.locator(`#${id}`)).toHaveCount(1)
  if (testInfo.project.name === 'mobile') {
    for (const viewport of [{ width: 320, height: 812 }, { width: 812, height: 375 }]) {
      await page.setViewportSize(viewport)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    }
  }
  expect(errors).toEqual([])
})

test('copied cURL and Python examples execute against a local API fixture', async ({ page }) => {
  const requests: { method: string; path: string; body?: unknown }[] = []
  const taskId = '00000000-0000-4000-8000-000000000001'
  const server = createServer(async (request, response) => {
    const chunks = []
    for await (const chunk of request) chunks.push(chunk)
    const body = Buffer.concat(chunks).toString()
    requests.push({ method: request.method!, path: request.url!, ...(body ? { body: JSON.parse(body) } : {}) })
    response.setHeader('Content-Type', 'application/json')
    if (request.headers.authorization !== 'Bearer fixture-key') {
      response.writeHead(401).end(JSON.stringify({ error: { message: 'Invalid API key.' } }))
    } else if (request.url === '/v1/models') {
      response.end(JSON.stringify({ data: [{ id: 'fixture-model' }], object: 'list' }))
    } else if (request.method === 'POST' && ['/v1/images/generations', '/v1/images/edits'].includes(request.url!)) {
      response.writeHead(202).end(JSON.stringify({ id: taskId, status: 'queued', data: [] }))
    } else if (request.url === `/v1/images/generations/${taskId}`) {
      response.end(JSON.stringify({ id: taskId, status: 'succeeded', data: [{ url: 'https://result.invalid/image.png' }] }))
    } else {
      response.writeHead(404).end('{}')
    }
  })
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  if (!address || typeof address === 'string') throw new Error('Local fixture server did not start')
  const baseUrl = `http://127.0.0.1:${address.port}/v1`
  try {
    await page.goto('/api-docs')
    const source = (title: string) => page.locator(`pre[aria-label="${title}"]`).innerText()
    const setup = (await source('配置接入参数'))
      .replace('http://127.0.0.1:5173/v1', baseUrl)
      .replace('YOUR_API_KEY', 'fixture-key')
      .replace('YOUR_MODEL_ID', 'fixture-model')
    for (const title of ['查询模型列表', '提交生成请求', '查询生成任务', '提交图片编辑', '查询生成任务']) {
      const command = (await source(title)).replace('YOUR_TASK_ID', taskId).replace('YOUR_MODEL_ID', 'fixture-model')
      const result = await execute('/bin/sh', ['-ec', `${setup}\n${command}`], { timeout: 10000 })
      expect(JSON.parse(result.stdout)).toBeTruthy()
    }
    await page.getByRole('tab', { name: 'Python', exact: true }).click()
    const python = (await source('完整异步生成示例'))
      .replace('http://127.0.0.1:5173/v1', baseUrl)
      .replace('YOUR_API_KEY', 'fixture-key')
      .replace('YOUR_MODEL_ID', 'fixture-model')
    const result = await execute('python3', ['-c', python], { timeout: 10000 })
    expect(result.stdout).toContain(taskId)
    expect(result.stdout).toContain('https://result.invalid/image.png')
    expect(requests.map(request => `${request.method} ${request.path}`)).toEqual([
      'GET /v1/models', 'POST /v1/images/generations', `GET /v1/images/generations/${taskId}`,
      'POST /v1/images/edits', `GET /v1/images/generations/${taskId}`,
      'GET /v1/models', 'POST /v1/images/generations', `GET /v1/images/generations/${taskId}`,
    ])
    for (const request of requests.filter(request => request.method === 'POST')) {
      expect(request.body).toEqual({ ...(request.path === '/v1/images/edits' ? editBody : generationBody), model: 'fixture-model' })
    }
  } finally {
    await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()))
  }
})
