import { test, expect } from '@playwright/test'

const calls = Array.from({ length: 24 }, (_, index) => ({
  id: `10000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
  model: index % 2 ? 'fixture-text' : 'gpt-6.1-sol',
  status: ['processing', 'succeeded', 'failed', 'usage_unknown'][index % 4]!,
  created: 1794355200,
  completed: index % 4 ? 1794355235 : null,
  duration_ms: 35000,
  input_tokens: index % 4 === 1 ? 1269 : null,
  output_tokens: index % 4 === 1 ? 1281 : null,
  charge_amount: index % 4 === 1 ? '0.00086333' : index === 2 ? '0.00010000' : null,
}))

test('text log tabs, server filters, pagination, details and retry', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/account/me', route => route.fulfill({
    json: {
      id: 1, email: 'text-log@example.com', is_admin: false, is_active: true,
      created_at: '2026-11-07T00:00:00Z', account: { available: '10.00000000', frozen: '0.00000000' },
    },
  }))
  await page.route('**/api/account/tasks', route => route.fulfill({ json: { data: [] } }))
  let fail = false
  await page.route('**/api/account/text-calls?*', route => {
    if (fail) return route.fulfill({ status: 503, json: { detail: '调用日志暂时不可用' } })
    const params = new URL(route.request().url()).searchParams
    const filtered = calls.filter(call =>
      (!params.get('status') || call.status === params.get('status'))
      && (!params.get('model') || call.model === params.get('model'))
      && (!params.get('query') || call.id.includes(params.get('query')!)))
    const offset = Number(params.get('offset'))
    return route.fulfill({
      json: {
        data: filtered.slice(offset, offset + Number(params.get('limit'))),
        total: filtered.length, models: ['gpt-6.1-sol', 'fixture-text'],
      },
    })
  })
  await page.route('**/api/account/text-calls/*', route => {
    const call = calls.find(call => route.request().url().endsWith(call.id))!
    return route.fulfill({
      json: {
        ...call, endpoint: '/v1/responses', stream: true,
        usage: call.input_tokens === null ? null : { input_tokens: 1269, cached_tokens: 100, output_tokens: 1281, reasoning_tokens: 954 },
        sale_price: { input_price: '2.00000000', output_price: '10.00000000', cache_read_price: '0.10000000', sale_multiplier: '0.20000000', long_context_threshold: 272000, long_context_input_multiplier: '2.00000000', long_context_output_multiplier: '1.50000000' },
        error_message: call.status === 'usage_unknown' ? '调用中断，未取得最终用量' : null,
      },
    })
  })
  await page.goto('/console/tasks')
  await expect(page.getByRole('tab', { name: '生成任务', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByText('暂无匹配的任务', { exact: true })).toBeVisible()
  await page.getByRole('tab', { name: '文本调用', exact: true }).click()
  const logs = page.getByRole('region', { name: '文本调用日志' })
  await expect(logs.getByRole('status')).toContainText('24')
  const first = logs.getByRole('row').filter({ hasText: calls[0]!.id })
  await expect(first).toContainText('调用中')
  await expect(first.getByRole('cell').nth(6)).toHaveText('—')
  const completed = logs.getByRole('row').filter({ hasText: calls[1]!.id })
  await expect(completed).toContainText('0.00086333')
  await completed.getByRole('button', { name: '详情', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '文本调用详情', exact: true })
  await expect(dialog).toContainText('SSE 流式')
  await expect(dialog).toContainText('/v1/responses')
  for (const text of ['普通输入', '缓存命中', '可见输出', '思考输出', '0.20000000', '1,169', '954']) {
    await expect(dialog).toContainText(text)
  }
  await expect(dialog.getByText('0.00086333', { exact: true })).toBeVisible()
  await expect(dialog).not.toContainText('成本')
  await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  await logs.getByRole('button', { name: '下一页', exact: true }).click()
  await expect(logs.getByText(calls[20]!.id, { exact: true })).toBeVisible()
  await logs.locator('.el-select').filter({ has: page.getByRole('combobox', { name: '文本调用状态', exact: true }) }).click()
  await page.getByRole('option', { name: '用量待核实', exact: true }).click()
  await expect(logs.getByRole('status')).toContainText('6')
  const unknown = logs.getByRole('row').filter({ hasText: calls[3]!.id })
  await unknown.getByRole('button', { name: '详情', exact: true }).click()
  await expect(dialog).toContainText('尚未结算')
  await expect(dialog).toContainText('调用中断，未取得最终用量')
  await expect(dialog.getByText('0.00000000', { exact: true })).toHaveCount(0)
  await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  await logs.getByRole('button', { name: '重置', exact: true }).click()
  await logs.locator('.el-select').filter({ has: page.getByRole('combobox', { name: '文本模型', exact: true }) }).click()
  await page.getByRole('option', { name: 'fixture-text', exact: true }).click()
  await expect(logs.getByRole('status')).toContainText('12')
  await logs.getByRole('textbox', { name: '搜索调用 ID', exact: true }).fill(calls[1]!.id)
  await logs.getByRole('button', { name: '查询', exact: true }).click()
  await expect(logs.getByRole('status')).toContainText('1')
  fail = true
  await page.getByRole('button', { name: '刷新日志', exact: true }).click()
  await expect(logs.getByRole('alert')).toContainText('调用日志暂时不可用')
  fail = false
  await page.getByRole('button', { name: '刷新日志', exact: true }).click()
  await expect(logs.getByRole('alert')).toHaveCount(0)
  await expect(logs.getByRole('button', { name: /删除/ })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByRole('tab', { name: '生成任务', exact: true }).click()
  await expect(page.getByText('暂无匹配的任务', { exact: true })).toBeVisible()
  expect(errors).toEqual([])
})

test('dashboard retries unavailable statistics without showing unknown consumption as zero', async ({ page }) => {
  await page.route('**/api/account/me', route => route.fulfill({
    json: {
      id: 1, email: 'stats@example.com', is_admin: false, is_active: true,
      created_at: '2026-11-07T00:00:00Z', account: { available: '1.00000000', frozen: '0.00000000' },
    },
  }))
  let fail = true
  await page.route('**/api/account/tasks', route => route.fulfill({ json: { data: [] } }))
  await page.route('**/api/account/dashboard', route => fail
    ? route.fulfill({ status: 503, json: { detail: '统计暂时不可用' } })
    : route.fulfill({
      json: {
        available: '-0.00000001', consumed: '1.00000001', requests: 1, today_consumed: '1.00000001',
        trend: Array.from({ length: 7 }, (_, index) => ({
          date: `2026-11-${String(9 + index).padStart(2, '0')}`,
          consumed: '0.00000000',
        })),
      },
    }))
  await page.goto('/console')
  await expect(page.getByRole('alert')).toContainText('统计暂时不可用')
  await expect(page.locator('.dashboard-statistic dd')).toHaveText(['1.00000000', '—', '—', '—'])
  fail = false
  await page.getByRole('button', { name: '刷新统计', exact: true }).click()
  await expect(page.locator('.dashboard-statistic dd')).toHaveText(['-0.00000001', '1.00000001', '1', '1.00000001'])
  await expect(page.getByRole('alert')).toHaveCount(0)
})
