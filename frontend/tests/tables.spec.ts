import { test, expect } from '@playwright/test'

const user = {
  id: 1, email: 'table-fixture@example.com', is_admin: true, is_active: true,
  created_at: '2026-11-07T00:00:00Z', account: { available: '0.0000', frozen: '0.0000' },
}

test('shared table paginates filtered rows, resets page size and handles empty results', async ({ page }) => {
  const data = Array.from({ length: 27 }, (_, index) => ({
    id: `image-${index + 1}`, name: `分页模型${String(index + 1).padStart(2, '0')}`,
    media_type: 'image', capabilities: {}, prices: [{ variant: {}, unit: 'image', unit_price: '0.1234' }],
  }))
  await page.route('**/api/public/models', route => route.fulfill({ json: { data } }))
  await page.goto('/pricing')
  const table = page.locator('.catalog-content')
  const rows = table.locator('.catalog-model-card')
  const pager = table.locator('.app-pagination')
  await expect(rows).toHaveCount(20)
  await expect(pager.getByRole('status')).toHaveText('共 27 条')
  await pager.locator('.btn-next').click()
  await expect(rows).toHaveCount(7)
  await expect(table.getByText('分页模型21', { exact: true })).toBeVisible()

  await page.getByRole('textbox', { name: '搜索模型', exact: true }).fill('分页模型27')
  await expect(rows).toHaveCount(1)
  await expect(table.getByText('分页模型27', { exact: true })).toBeVisible()
  await expect(pager.locator('.btn-prev')).toBeDisabled()
  await page.getByRole('textbox', { name: '搜索模型', exact: true }).fill('no-match')
  await expect(page.getByRole('heading', { name: '没有匹配的模型' })).toBeVisible()
  await expect(pager.getByRole('status')).toHaveText('共 0 条')
  await expect(pager.locator('.btn-next')).toBeDisabled()

  await page.getByRole('textbox', { name: '搜索模型', exact: true }).fill('')
  await pager.locator('.btn-next').click()
  await pager.getByRole('combobox', { name: '每页条数' }).press('ArrowDown')
  await page.getByRole('option', { name: '50 条 / 页', exact: true }).click()
  await expect(rows).toHaveCount(27)
  await expect(pager.locator('.btn-prev')).toBeDisabled()
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' })
  await expect(page.locator('html')).toHaveClass(/dark/)
  await expect.poll(() => table.locator('.catalog-model-card').first().evaluate(element => getComputedStyle(element).backgroundColor)).toBe('rgb(32, 35, 37)')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('server pagination preserves totals, disables while loading and resets offset on size change', async ({ page }) => {
  const users = Array.from({ length: 57 }, (_, index) => ({ ...user, id: index + 1, email: `user-${index + 1}@example.com` }))
  const requests: { offset: number; limit: number }[] = []
  let finishPage: (() => void) | undefined
  await page.route('**/api/account/me', route => route.fulfill({ json: user }))
  await page.route('**/api/admin/users?*', async route => {
    const url = new URL(route.request().url())
    const offset = Number(url.searchParams.get('offset'))
    const limit = Number(url.searchParams.get('limit'))
    requests.push({ offset, limit })
    if (offset === 20) await new Promise<void>(resolve => { finishPage = resolve })
    await route.fulfill({ json: { data: users.slice(offset, offset + limit), total: users.length } })
  })
  await page.goto('/admin/users')
  const table = page.locator('.app-table')
  const pager = table.locator('.app-pagination')
  await expect(table.getByRole('cell', { name: 'user-1@example.com', exact: true })).toBeVisible()
  await expect(pager.getByRole('status')).toHaveText('共 57 条')
  await pager.locator('.btn-next').click()
  await expect(pager.locator('.btn-next')).toBeDisabled()
  await expect(pager.getByRole('combobox', { name: '每页条数' })).toBeDisabled()
  await expect.poll(() => Boolean(finishPage)).toBe(true)
  finishPage!()
  await expect(table.getByRole('cell', { name: 'user-21@example.com', exact: true })).toBeVisible()
  await expect(pager.locator('.btn-next')).toBeEnabled()
  await pager.getByText('20 条 / 页', { exact: true }).click()
  await page.getByRole('option', { name: '50 条 / 页', exact: true }).click()
  await expect(table.locator('.el-table__body tbody tr')).toHaveCount(50)
  expect(requests).toEqual([{ offset: 0, limit: 20 }, { offset: 20, limit: 20 }, { offset: 0, limit: 50 }])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('all console pages fill the available width and omit breadcrumbs', async ({ page }, testInfo) => {
  await page.route('**/api/account/me', route => route.fulfill({ json: user }))
  await page.route('**/api/account/keys', route => route.fulfill({ json: { data: [] } }))
  await page.route('**/api/public/models', route => route.fulfill({ json: { data: [] } }))
  await page.route('**/api/admin/**', route => route.fulfill({ json: { data: [], total: 0 } }))
  if (testInfo.project.name === 'desktop') await page.setViewportSize({ width: 1920, height: 1080 })
  for (const path of ['/console', '/console/models', '/console/tokens', '/console/tasks', '/console/settings', '/admin/users', '/admin/providers', '/admin/models']) {
    await page.goto(path)
    await expect(page.getByRole('main').getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.getByRole('main').locator('.page-header')).toHaveCount(1)
    await expect(page.getByRole('main').locator('.page-header-accent')).toBeVisible()
    await expect(page.locator('.breadcrumb-separator, .el-breadcrumb')).toHaveCount(0)
    await expect(page.locator('.topbar-location')).toHaveText('')
    const layout = await page.getByRole('main').evaluate(element => {
      const main = element.getBoundingClientRect()
      const content = element.firstElementChild!.getBoundingClientRect()
      const style = getComputedStyle(element)
      return {
        right: main.right, width: main.width, contentWidth: content.width,
        padding: parseFloat(style.paddingLeft) + parseFloat(style.paddingRight),
        maxWidth: style.maxWidth,
      }
    })
    expect(layout.maxWidth).toBe('none')
    expect(layout.right).toBe(page.viewportSize()!.width)
    expect(layout.contentWidth).toBeCloseTo(layout.width - layout.padding, 0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  }
})
