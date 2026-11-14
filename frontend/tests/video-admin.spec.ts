import { test, expect, type Page } from '@playwright/test'

const provider = {
  id: 2, name: 'MEAICC', adapter_key: 'meaicc_video', base_url: 'https://api.meaicc.com',
  is_active: false, has_credentials: false,
  request_config: { timeout_seconds: 60, poll_interval_seconds: 60, task_timeout_seconds: 21600 },
}
const video = {
  id: 21, public_id: 'sd-2-c4', display_name: 'Seedance 2.0 Fast', media_type: 'video',
  provider_id: 2, upstream_model_id: 'sd-2-c4', is_active: false, pricing_dimensions: [],
  capabilities: {
    family: 'seedance-2.0', version: 'fast', resolutions: ['720p'], aspect_ratios: ['1:1', '16:9', '9:16'],
    min_seconds: '4', max_seconds: '15', max_reference_images: 9, max_reference_videos: 3,
    max_reference_audios: 3, supports_first_frame: true, supports_last_frame: true,
    defaults: { seconds: '10', resolution: '720p', aspect_ratio: '16:9' },
  },
  prices: [{ id: 50, variant: {}, sale_unit: 'video', cost_unit: 'video', sale_unit_price: '1.8000', cost_unit_price: '1.80000000' }],
}
async function administrator(page: Page) {
  await page.route('**/api/account/me', route => route.fulfill({ json: {
    id: 1, email: 'admin@example.com', is_admin: true, is_active: true,
    created_at: '2026-11-09T00:00:00Z', account: { available: '0.0000', frozen: '0.0000' },
  } }))
  await page.route('**/api/admin/providers', route => route.fulfill({ json: { data: [provider] } }))
}

test('video editor preserves IDs, editable capabilities and exact unit prices', async ({ page }) => {
  await administrator(page)
  let saved = false
  await page.route('**/api/admin/models', route => route.fulfill({ json: { data: [video] } }))
  await page.route('**/api/admin/image-options', route => route.fulfill({ json: { data: [] } }))
  await page.route('**/api/admin/video-options', route => route.fulfill({ json: { data: [
    { id: 'sd-2-c4', family: 'seedance-2.0', version: 'fast' },
  ] } }))
  await page.route('**/api/admin/models/21', route => {
    const payload = route.request().postDataJSON()
    expect(payload).not.toHaveProperty('id')
    expect(payload.pricing_dimensions).toEqual([])
    expect(payload.capabilities.defaults.resolution).toBe('720p')
    expect(payload.capabilities.max_reference_images).toBe(42)
    expect(payload.prices[0]).toMatchObject({ id: 50, sale_unit: 'second', cost_unit: 'video', sale_unit_price: '0.1234' })
    saved = true
    return route.fulfill({ json: { ...payload, id: 21 } })
  })
  await page.goto('/admin/models')
  await page.getByRole('button', { name: `编辑 ${video.display_name}`, exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '编辑视频模型', exact: true })
  await expect(dialog.getByLabel('默认时长（秒）', { exact: true })).toHaveValue('10')
  await expect(dialog.getByLabel('售价（积分）', { exact: true })).toHaveValue('1.8000')
  await dialog.getByRole('spinbutton', { name: '参考图上限', exact: true }).fill('42')
  await dialog.getByRole('combobox', { name: '售价计费方式', exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: '按秒', exact: true }).click()
  await dialog.getByLabel('售价（积分）', { exact: true }).fill('0.1234')
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  expect(saved).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('provider time inputs allow long video tasks and preserve snapshot semantics', async ({ page }) => {
  await administrator(page)
  let saved = false
  await page.route('**/api/admin/providers/2', route => {
    const payload = route.request().postDataJSON()
    expect(payload.request_config).toEqual({
      timeout_seconds: 900, poll_interval_seconds: 7200, task_timeout_seconds: 43200,
    })
    expect(payload).not.toHaveProperty('api_key')
    saved = true
    return route.fulfill({ json: { ...provider, ...payload } })
  })
  await page.goto('/admin/providers')
  await page.getByRole('button', { name: '编辑 MEAICC', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '编辑供应商', exact: true })
  await expect(dialog.getByText('时间配置仅对新任务生效；超时任务继续查询，不会自动退款。')).toBeVisible()
  await dialog.getByRole('spinbutton', { name: '请求超时（秒）', exact: true }).fill('900')
  await dialog.getByRole('spinbutton', { name: '查询间隔（秒）', exact: true }).fill('7200')
  await dialog.getByRole('spinbutton', { name: '任务超时（小时）', exact: true }).fill('12')
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  expect(saved).toBe(true)
})

test('console pricing filters video series without overflowing mobile width', async ({ page }) => {
  await administrator(page)
  await page.route('**/api/public/models', route => route.fulfill({ json: { data: [
    {
      id: 'sd-2-c4', name: 'Seedance 2.0 Fast', media_type: 'video', capabilities: video.capabilities,
      prices: [{ variant: {}, unit: 'video', unit_price: '1.8000' }],
    },
    {
      id: 'sd-2.5-d1-720', name: 'Seedance 2.5', media_type: 'video',
      capabilities: { ...video.capabilities, family: 'seedance-2.5', max_seconds: '30' },
      prices: [{ variant: {}, unit: 'second', unit_price: '0.5400' }],
    },
  ] } }))
  await page.goto('/console/models')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByRole('radiogroup', { name: '模型系列' }).getByText('seedance-2.0', { exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Seedance 2.0 Fast', exact: true })).toBeVisible()
  await page.getByRole('radiogroup', { name: '模型系列' }).getByText('seedance-2.5', { exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Seedance 2.5', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '查看 sd-2.5-d1-720 详情', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('最短时长（秒）')
  await expect(page.getByRole('dialog')).toContainText('参考视频上限')
})
