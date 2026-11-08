import { test, expect, type Page } from '@playwright/test'

const provider = {
  id: 1, name: '沧元测试', adapter_key: 'cangyuan_image',
  base_url: 'https://direct-api.cangyuansuanli.cn', has_credentials: true, is_active: true,
  request_config: { timeout_seconds: 60, poll_interval_seconds: 5 },
}
const user = {
  id: 1, email: 'admin-fixture@example.com', is_admin: true, is_active: true,
  created_at: '2026-11-07T00:00:00Z', account: { available: '0.0000', frozen: '0.0000' },
}
const capabilities = {
  sizes: ['1:1', '9:16'], qualities: ['low', 'high'], tiers: ['web', '1k'],
  series: [], backgrounds: ['auto'], output_formats: [],
  max_reference_images: 9, supports_mask: true, defaults: {},
}

async function asAdministrator(page: Page) {
  await page.route('**/api/account/me', route => route.fulfill({ json: user }))
}

test('provider form validates, saves and preserves hidden credentials', async ({ page }) => {
  await asAdministrator(page)
  let saved = false
  let updated = false
  await page.route('**/api/admin/providers', route => {
    if (route.request().method() === 'POST') {
      const payload = route.request().postDataJSON()
      expect(payload.api_key).toBe('sk-ui-fake-only')
      expect(payload.name).toBe(provider.name)
      saved = true
      return route.fulfill({ status: 201, json: provider })
    }
    return route.fulfill({ json: { data: saved ? [provider] : [] } })
  })
  await page.route('**/api/admin/providers/1', route => {
    expect(route.request().postDataJSON()).not.toHaveProperty('api_key')
    expect(route.request().postDataJSON().is_active).toBe(false)
    updated = true
    return route.fulfill({ json: { ...provider, is_active: false } })
  })
  await page.goto('/admin/providers')
  await page.getByRole('button', { name: '新增供应商', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '新增供应商', exact: true })
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog.getByText('请输入供应商名称')).toBeVisible()
  await expect(dialog.getByText('请输入 API Key', { exact: true })).toBeVisible()
  await dialog.getByLabel('供应商名称', { exact: true }).fill(provider.name)
  await dialog.getByLabel('API Key', { exact: true }).fill('sk-ui-fake-only')
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.getByRole('main').getByText('已配置', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: `编辑 ${provider.name}`, exact: true }).click()
  const edit = page.getByRole('dialog', { name: '编辑供应商', exact: true })
  await expect(edit.getByLabel('替换 API Key（留空保留）', { exact: true })).toHaveValue('')
  await edit.locator('.el-switch').click()
  await edit.getByRole('button', { name: '保存', exact: true }).click()
  await expect(edit).not.toBeVisible()
  expect(updated).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('image configuration saves exact prices, edits and recovers from rejected publish', async ({ page }) => {
  await asAdministrator(page)
  let saved: Record<string, unknown> | undefined
  let reject = true
  await page.route('**/api/admin/providers', route => route.fulfill({ json: { data: [provider] } }))
  await page.route('**/api/admin/image-options', route => route.fulfill({
    json: { data: [{ id: 'gpt-image-2-x', family: 'gpt-image-2', ...capabilities }] },
  }))
  await page.route('**/api/admin/models', route => {
    if (route.request().method() === 'POST') {
      const payload = route.request().postDataJSON()
      expect(payload.prices[0].sale_unit_price).toBe('0.1234')
      expect(payload.prices[0].cost_unit_price).toBe('0.01700000')
      expect(payload.prices[0].variant).toEqual({})
      expect(payload).not.toHaveProperty('id')
      if (reject) return route.fulfill({ status: 422, json: { detail: '默认参数组合没有有效价格' } })
      saved = { ...payload, id: 1, prices: [{ ...payload.prices[0], id: 10 }] }
      return route.fulfill({ status: 201, json: saved })
    }
    return route.fulfill({ json: { data: saved ? [saved] : [] } })
  })
  await page.route('**/api/admin/models/1', route => {
    const payload = route.request().postDataJSON()
    expect(payload.prices[0].id).toBe(10)
    expect(payload.prices[0].sale_unit_price).toBe('0.2345')
    saved = { ...payload, id: 1 }
    return route.fulfill({ json: saved })
  })
  await page.goto('/admin/models')
  await page.getByRole('button', { name: '新增图片模型', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '新增图片模型', exact: true })
  await dialog.getByLabel('本站模型 ID', { exact: true }).fill('image-test')
  await dialog.getByLabel('显示名称', { exact: true }).fill('测试图片')
  await dialog.getByLabel('供应商', { exact: true }).click()
  await page.getByRole('option', { name: provider.name, exact: true }).click()
  await dialog.getByLabel('上游模型 ID', { exact: true }).click()
  await page.getByRole('option', { name: 'gpt-image-2-x', exact: true }).click()
  await dialog.getByRole('combobox', { name: '质量', exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: 'low', exact: true }).click()
  await dialog.getByRole('heading', { name: '能力参数', exact: true }).click()
  await expect(dialog.locator('.el-form-item').filter({ has: page.getByText('质量默认值', { exact: true }) })).toContainText('low')
  await dialog.getByRole('button', { name: '添加价目', exact: true }).click()
  await dialog.getByLabel('售价（积分 / 张）', { exact: true }).fill('0.12345')
  await dialog.getByLabel('成本（原币 / 张）', { exact: true }).fill('0.01700000')
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog.getByText('请输入非负金额，最多四位小数')).toBeVisible()
  await dialog.getByLabel('售价（积分 / 张）', { exact: true }).fill('0.1234')
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog.locator('.form-alert')).toContainText('默认参数组合没有有效价格')
  await expect(dialog.getByLabel('本站模型 ID', { exact: true })).toHaveValue('image-test')
  reject = false
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await page.getByRole('button', { name: '编辑 测试图片', exact: true }).click()
  const edit = page.getByRole('dialog', { name: '编辑图片模型', exact: true })
  await expect(edit.getByLabel('售价（积分 / 张）', { exact: true })).toHaveValue('0.1234')
  await edit.getByLabel('售价（积分 / 张）', { exact: true }).fill('0.2345')
  await page.emulateMedia({ colorScheme: 'dark' })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await edit.getByRole('button', { name: '保存', exact: true }).click()
  await expect(edit).not.toBeVisible()
})

test('regular users cannot enter catalog management or see management navigation', async ({ page }) => {
  await page.route('**/api/account/me', route => route.fulfill({ json: { ...user, is_admin: false } }))
  for (const path of ['/admin/providers', '/admin/models']) {
    await page.goto(path)
    await expect(page).toHaveURL('/console')
    await expect(page.getByRole('navigation', { name: '管理导航', exact: true })).toHaveCount(0)
    await expect(page.getByRole('navigation', { name: '管理移动导航', exact: true })).toHaveCount(0)
  }
})

test('model table groups actual prices independently and filters the catalog', async ({ page }) => {
  await asAdministrator(page)
  const qualities = ['low', 'medium', 'high', 'xhigh', 'max']
  const model = {
    id: 1, public_id: 'gpt-image-2.6-flare-2k', display_name: 'gpt-image-2.6-flare-2k',
    upstream_model_id: 'gpt-image-2.6-flare-2k', provider_id: 1, media_type: 'image', is_active: false,
    capabilities: { ...capabilities, tiers: ['2k'], qualities }, pricing_dimensions: ['quality'],
    prices: qualities.map((quality, index) => ({
      id: index + 1, variant: { quality }, cost_currency: 'CNY', cost_unit: 'image', sale_unit: 'image',
      cost_unit_price: index < 3 ? '0.18000000' : '0.36000000',
      sale_unit_price: index < 2 ? '0.2000' : index === 2 ? '0.2100' : '0.4000',
    })),
  }
  const web = {
    ...model, id: 2, public_id: 'gpt-image-2.6-sunburst', display_name: 'gpt-image-2.6-sunburst',
    upstream_model_id: 'gpt-image-2.6-sunburst', is_active: true,
    capabilities: { ...capabilities, tiers: ['web'] }, pricing_dimensions: [],
    prices: [{ ...model.prices[0], id: 10, variant: {}, cost_unit_price: '0.01500000', sale_unit_price: '0.0150' }],
  }
  const custom = {
    ...model, id: 3, public_id: 'custom-image', display_name: '专属图片', upstream_model_id: 'gpt-image-2-1k',
    capabilities: { ...capabilities, tiers: ['1k'] },
    prices: [
      { ...model.prices[0], id: 11, cost_currency: 'USD', cost_unit_price: '0.00001234' },
      { ...model.prices[1], id: 12, cost_currency: 'USD', cost_unit_price: '0.05000000' },
      { ...model.prices[2], id: 13, cost_currency: 'CNY', cost_unit_price: '0.05000000' },
    ],
  }
  await page.route('**/api/admin/providers', route => route.fulfill({ json: { data: [provider] } }))
  await page.route('**/api/admin/image-options', route => route.fulfill({ json: { data: [] } }))
  await page.route('**/api/admin/models', route => route.fulfill({ json: { data: [model, web, custom] } }))
  await page.goto('/admin/models')
  const rows = page.locator('.managed-model-table .el-table__row')
  await expect(rows).toHaveCount(3)
  const row = rows.filter({ hasText: model.public_id })
  await expect(row.locator('.model-name')).toHaveText('GPT Image 2.6 · Flare')
  await expect(row.locator('code')).toHaveCount(1)
  await expect(page.getByRole('columnheader', { name: '上游模型 ID', exact: true })).toHaveCount(0)
  const cost = page.getByRole('button', { name: `查看 ${model.public_id} 成本明细`, exact: true })
  const sale = page.getByRole('button', { name: `查看 ${model.public_id} 售价明细`, exact: true })
  await expect(cost.locator('.model-price-group')).toHaveCount(2)
  await expect(cost).toContainText('常规')
  await expect(cost).toContainText('¥0.1800')
  await expect(cost).toContainText('¥0.3600')
  await expect(sale.locator('.model-price-group')).toHaveCount(3)
  await expect(sale).toContainText('0.2100')
  await cost.click()
  await expect(cost).toHaveAttribute('aria-expanded', 'true')
  const detail = page.getByRole('table', { name: `${model.public_id} 完整价目`, exact: true })
  await expect(detail.locator('tbody tr')).toHaveCount(5)
  await expect(detail.getByRole('row', { name: 'quality: high ¥0.1800 0.2100', exact: true })).toBeVisible()
  await cost.press('Enter')
  await expect(cost).toHaveAttribute('aria-expanded', 'false')
  await expect(detail).toHaveCount(0)
  const webCost = page.getByRole('button', { name: `查看 ${web.public_id} 成本明细`, exact: true })
  await expect(webCost).toHaveText('¥0.0150')
  const customCost = page.getByRole('button', { name: '查看 custom-image 成本明细', exact: true })
  await expect(customCost.locator('.model-price-group')).toHaveCount(3)
  await expect(customCost).toContainText('$0.00001234')
  await expect(customCost).toContainText('$0.0500')
  await expect(customCost).toContainText('¥0.0500')
  await expect(rows.filter({ hasText: 'custom-image' }).locator('.model-name')).toHaveText('专属图片')

  await page.getByRole('combobox', { name: '筛选模型系列', exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: 'gpt-image-2.6', exact: true }).click()
  await expect(rows).toHaveCount(2)
  await page.getByRole('combobox', { name: '筛选模型档位', exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: 'Web', exact: true }).click()
  await expect(rows).toHaveCount(1)
  await expect(rows).toContainText(web.public_id)
  await page.getByRole('combobox', { name: '筛选上架状态', exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: '已下架', exact: true }).click()
  await expect(page.getByText('没有匹配的图片模型', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('web reference count and mask remain editable without upstream presets', async ({ page }) => {
  await asAdministrator(page)
  const webCapabilities = {
    sizes: [], qualities: [], tiers: [], series: [], backgrounds: [], output_formats: [],
    max_reference_images: 0, supports_mask: false, defaults: {},
  }
  let model = {
    id: 1, public_id: 'gpt-image-2.5-flare', display_name: 'gpt-image-2.5-flare',
    upstream_model_id: 'gpt-image-2.5-flare', media_type: 'image', provider_id: 1,
    capabilities: webCapabilities, pricing_dimensions: [], is_active: true, prices: [],
  }
  await page.route('**/api/admin/providers', route => route.fulfill({ json: { data: [provider] } }))
  await page.route('**/api/admin/image-options', route => route.fulfill({
    json: { data: [{ ...webCapabilities, id: model.upstream_model_id, family: 'gpt-image-2.5', max_reference_images: null }] },
  }))
  await page.route('**/api/admin/models', route => route.fulfill({ json: { data: [model] } }))
  await page.route('**/api/admin/models/1', route => {
    const payload = route.request().postDataJSON()
    expect(payload.capabilities.max_reference_images).toBe(16)
    expect(payload.capabilities.supports_mask).toBe(true)
    model = { ...payload, id: 1 }
    return route.fulfill({ json: model })
  })
  await page.goto('/admin/models')
  await page.getByRole('button', { name: '编辑 gpt-image-2.5-flare', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '编辑图片模型', exact: true })
  const count = dialog.getByRole('spinbutton', { name: '参考图数量上限', exact: true })
  await count.fill('16')
  await count.blur()
  await expect(count).toHaveValue('16')
  const mask = dialog.getByRole('switch', { name: '蒙版编辑', exact: true })
  await expect(mask).toBeEnabled()
  await dialog.locator('.el-switch').nth(1).click()
  await expect(mask).toBeChecked()
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await page.getByRole('button', { name: '编辑 gpt-image-2.5-flare', exact: true }).click()
  await expect(dialog.getByRole('spinbutton', { name: '参考图数量上限', exact: true })).toHaveValue('16')
  await expect(dialog.getByRole('switch', { name: '蒙版编辑', exact: true })).toBeChecked()
})
