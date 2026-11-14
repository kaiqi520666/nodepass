import { test, expect, type Page } from '@playwright/test'

const admin = {
  id: 1,
  email: 'admin@example.com',
  is_admin: true,
  is_active: true,
  created_at: '2026-11-15T00:00:00Z',
  account: { available: '10.00000000', frozen: '0.00000000' },
}

const taskId = '11111111-1111-4111-8111-111111111111'
const callId = '22222222-2222-4222-8222-222222222222'
const task = {
  id: taskId,
  user: { id: 7, email: 'task-owner@example.com' },
  model: 'gpt-image-2',
  media_type: 'image',
  status: 'submission_unknown',
  billing_status: 'held',
  frozen_amount: '1.23000000',
  created: 1763150000,
  updated: 1763150300,
  waiting_seconds: 5400,
  idle_seconds: 3300,
  upstream_status: null,
  has_upstream_id: true,
  has_ready_result: false,
  review_required: true,
  resolution: null,
  allowed_actions: ['requery', 'release'],
  last_action: null,
}
const textCall = {
  id: callId,
  user: { id: 8, email: 'text-owner@example.com', available: '1.50000000' },
  model: 'gpt-6.1-sol',
  endpoint: '/v1/responses',
  status: 'usage_unknown',
  created: 1763150000,
  updated: 1763150300,
  waiting_seconds: 3600,
  idle_seconds: 3300,
  charge_amount: null,
  error_message: '调用已中断，用量待核实',
  has_late_usage: true,
  late_usage_at: '2026-11-15T12:30:00Z',
  resolution: null,
  allowed_actions: ['manual_charge', 'close_no_charge'],
  last_action: null,
}
const audit = {
  id: 13,
  actor: { id: 1, email: 'admin@example.com' },
  action: 'task.requery',
  target_type: 'task',
  target_id: taskId,
  amount: null,
  reason: '核实上游后重新查询',
  credit_entry_id: null,
  created_at: '2026-11-15T12:00:00Z',
}

async function administrator(page: Page) {
  await page.route('**/api/account/me', route => route.fulfill({ json: admin }))
}

test('admin exception center lists tasks and text calls with audit timeline', async ({ page }, testInfo) => {
  await administrator(page)
  await page.route('**/api/admin/exceptions/summary', route => route.fulfill({
    json: {
      tasks: {
        submission_unknown: 2,
        stuck_queued: 1,
        stuck_submitting: 0,
        stuck_processing: 1,
        stuck_transferring: 0,
        review_required: 3,
      },
      text_calls: { usage_unknown: 1, stuck_processing: 1, late_usage: 1 },
      oldest_waiting_seconds: 5400,
    },
  }))
  await page.route('**/api/admin/exceptions/tasks?*', route => route.fulfill({ json: { data: [task], total: 1 } }))
  await page.route('**/api/admin/exceptions/text-calls?*', route => route.fulfill({ json: { data: [textCall], total: 1 } }))
  await page.route('**/api/admin/audit-actions?*', route => route.fulfill({ json: { data: [audit], total: 1 } }))

  await page.goto('/admin/exceptions')
  await expect(page.getByRole('heading', { name: '异常处理' })).toBeVisible()
  await expect(page.locator('.dashboard-statistic').filter({ hasText: '待核实任务' }).locator('dd')).toHaveText('2')
  await expect(page.locator('.dashboard-statistic').filter({ hasText: '卡住任务' }).locator('dd')).toHaveText('2')
  await expect(page.locator('.dashboard-statistic').filter({ hasText: '最久等待' }).locator('dd')).toHaveText('1 小时 30 分')
  await expect(page.getByText('task-owner@example.com', { exact: true })).toBeVisible()
  await expect(page.getByText('待核实', { exact: true }).first()).toBeVisible()
  if (testInfo.project.name === 'mobile') await expect(page.locator('.el-tab-pane:visible .mobile-card')).toHaveCount(1)

  await page.locator('.el-tab-pane:visible').getByRole('button', { name: '详情', exact: true }).first().click()
  const taskDrawer = page.getByRole('dialog', { name: '生成任务详情' })
  await expect(taskDrawer).toBeVisible()
  await expect(taskDrawer.getByRole('button', { name: '重新查询', exact: true })).toBeVisible()
  await expect(taskDrawer.getByRole('button', { name: '释放', exact: true })).toBeVisible()
  await expect(taskDrawer.getByText('核实上游后重新查询', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(taskDrawer).toBeHidden()

  await page.getByRole('tab', { name: '文本调用' }).click()
  await expect(page.getByText('text-owner@example.com', { exact: true })).toBeVisible()
  await expect(page.getByText('有迟到用量', { exact: true }).first()).toBeVisible()
  if (testInfo.project.name === 'mobile') await expect(page.locator('.el-tab-pane:visible .mobile-card')).toHaveCount(1)
  await page.locator('.el-tab-pane:visible').getByRole('button', { name: '详情', exact: true }).first().click()
  const textDrawer = page.getByRole('dialog', { name: '文本调用详情' })
  await expect(textDrawer).toBeVisible()
  await expect(textDrawer.getByRole('button', { name: '人工扣费', exact: true })).toBeVisible()
  await expect(textDrawer.getByRole('button', { name: '关闭不扣费', exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(textDrawer).toBeHidden()
  if (testInfo.project.name === 'mobile') {
    const filterWidth = await page.locator('.el-tab-pane:visible .filter-actions > .el-select').first()
      .evaluate(element => element.getBoundingClientRect().width)
    expect(filterWidth).toBeGreaterThan(250)
  }

  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('admin-exceptions.png'), fullPage: true })
})

test('admin audit detail is read-only and shows before and after snapshots', async ({ page }, testInfo) => {
  await administrator(page)
  await page.route('**/api/admin/audit-actions?*', route => route.fulfill({ json: { data: [audit], total: 1 } }))
  await page.route('**/api/admin/audit-actions/13', route => route.fulfill({
    json: {
      ...audit,
      before_snapshot: { status: 'pending', review_required: false },
      after_snapshot: { status: 'pending', review_required: false, resolution: 'manual_requeued' },
    },
  }))

  await page.goto('/admin/audit')
  await expect(page.getByRole('heading', { name: '操作审计' })).toBeVisible()
  await expect(page.getByText('核实上游后重新查询', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /删除|编辑/ })).toHaveCount(0)
  if (testInfo.project.name === 'mobile') await expect(page.locator('.mobile-card')).toHaveCount(1)

  await page.getByRole('button', { name: '详情', exact: true }).first().click()
  await expect(page.getByText('审计详情', { exact: true })).toBeVisible()
  await expect(page.getByText('操作前快照', { exact: true })).toBeVisible()
  await expect(page.getByText('操作后快照', { exact: true })).toBeVisible()
  await expect(page.locator('pre').nth(1)).toContainText('manual_requeued')
  await expect(page.getByRole('button', { name: /删除|编辑/ })).toHaveCount(0)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', { name: '审计详情' })).toBeHidden()

  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('admin-audit.png'), fullPage: true })
})

test('admin actions send reasons, amounts and request ids', async ({ page }) => {
  await administrator(page)
  await page.route('**/api/admin/exceptions/summary', route => route.fulfill({
    json: {
      tasks: { submission_unknown: 2, stuck_queued: 0, stuck_submitting: 0, stuck_processing: 0, stuck_transferring: 0, review_required: 1 },
      text_calls: { usage_unknown: 1, stuck_processing: 0, late_usage: 0 },
      oldest_waiting_seconds: 60,
    },
  }))
  await page.route('**/api/admin/exceptions/tasks?*', route => route.fulfill({ json: { data: [task], total: 1 } }))
  await page.route('**/api/admin/exceptions/text-calls?*', route => route.fulfill({ json: { data: [textCall], total: 1 } }))
  await page.route('**/api/admin/audit-actions?*', route => route.fulfill({ json: { data: [], total: 0 } }))
  const taskBodies: Array<Record<string, unknown>> = []
  await page.route('**/api/admin/tasks/*/resolve', async route => {
    taskBodies.push(route.request().postDataJSON())
    await route.fulfill({ json: {} })
  })
  const textBodies: Array<Record<string, unknown>> = []
  await page.route('**/api/admin/text-calls/*/resolve', async route => {
    textBodies.push(route.request().postDataJSON())
    await route.fulfill({ json: {} })
  })
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

  await page.goto('/admin/exceptions')
  await page.locator('.el-tab-pane:visible').getByRole('button', { name: '详情', exact: true }).first().click()
  const taskDrawer = page.getByRole('dialog', { name: '生成任务详情' })
  await taskDrawer.getByRole('button', { name: '重新查询', exact: true }).click()
  const requeryDialog = page.getByRole('dialog', { name: '重新查询' })
  await requeryDialog.getByPlaceholder('至少 4 个字符，填写核实依据或上游账单信息').fill('核实上游后重新查询')
  await requeryDialog.getByRole('button', { name: '确认', exact: true }).click()
  await expect(page.getByText('重新查询已提交', { exact: true })).toBeVisible()
  await expect(taskDrawer).toBeHidden()
  expect(taskBodies).toHaveLength(1)
  expect(taskBodies[0]).toMatchObject({ action: 'requery', reason: '核实上游后重新查询' })
  expect(taskBodies[0]!.request_id).toMatch(uuid)

  await page.locator('.el-tab-pane:visible').getByRole('button', { name: '详情', exact: true }).first().click()
  const releaseDrawer = page.getByRole('dialog', { name: '生成任务详情' })
  await releaseDrawer.getByRole('button', { name: '释放', exact: true }).click()
  const releaseDialog = page.getByRole('dialog', { name: '释放' })
  await releaseDialog.getByPlaceholder('至少 4 个字符，填写核实依据或上游账单信息').fill('上游未受理，关闭任务')
  await releaseDialog.getByRole('button', { name: '确认', exact: true }).click()
  await page.getByRole('button', { name: '确认释放', exact: true }).click()
  await expect(releaseDrawer).toBeHidden()
  expect(taskBodies).toHaveLength(2)
  expect(taskBodies[1]).toMatchObject({ action: 'release', reason: '上游未受理，关闭任务' })
  expect(taskBodies[1]!.request_id).toMatch(uuid)
  expect(taskBodies[1]!.request_id).not.toBe(taskBodies[0]!.request_id)

  await page.getByRole('tab', { name: '文本调用' }).click()
  await page.locator('.el-tab-pane:visible').getByRole('button', { name: '详情', exact: true }).first().click()
  const textDrawer = page.getByRole('dialog', { name: '文本调用详情' })
  await textDrawer.getByRole('button', { name: '人工扣费', exact: true }).click()
  const chargeDialog = page.getByRole('dialog', { name: '人工扣费' })
  await chargeDialog.getByPlaceholder('大于零，最多八位小数').fill('0.86000000')
  await chargeDialog.getByPlaceholder('至少 4 个字符，填写核实依据或上游账单信息').fill('按上游账单人工核定')
  await chargeDialog.getByRole('button', { name: '确认', exact: true }).click()
  await page.getByRole('button', { name: '确认扣费', exact: true }).click()
  await expect(textDrawer).toBeHidden()
  expect(textBodies).toHaveLength(1)
  expect(textBodies[0]).toMatchObject({
    action: 'manual_charge',
    amount: '0.86000000',
    reason: '按上游账单人工核定',
  })
  expect(textBodies[0]!.request_id).toMatch(uuid)
})
