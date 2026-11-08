import { test, expect } from '@playwright/test'

const qualities = ['low', 'medium', 'high', 'xhigh', 'max']
const models = [
  {
    id: 'gpt-image-2', name: 'gpt-image-2', media_type: 'image',
    capabilities: { sizes: ['1:1', '16:9'], max_reference_images: 9 },
    prices: [{ variant: {}, unit: 'image', unit_price: '0.0150' }],
  },
  {
    id: 'gpt-image-2-1k', name: 'gpt-image-2-1k', media_type: 'image',
    capabilities: { sizes: ['1:1', '16:9'], qualities, max_reference_images: 9 },
    prices: qualities.map(quality => ({ variant: { quality }, unit: 'image', unit_price: '0.0500' })),
  },
  {
    id: 'gpt-image-2.6-flare-2k', name: 'gpt-image-2.6-flare-2k', media_type: 'image',
    capabilities: { sizes: ['1:1', '16:9'], qualities, max_reference_images: 16, output_formats: ['png', 'webp'] },
    prices: qualities.map((quality, index) => ({
      variant: { quality }, unit: 'image', unit_price: index < 3 ? '0.1800' : '0.3600',
    })),
  },
  {
    id: 'custom-video', name: '视频测试', media_type: 'video',
    capabilities: { resolutions: ['720p', '1080p'] },
    prices: [
      { variant: { resolution: '720p' }, unit: 'second', unit_price: '0.2000' },
      { variant: { resolution: '1080p' }, unit: 'video', unit_price: '0.2000' },
    ],
  },
]

for (const path of ['/models', '/console/models']) {
  test(`pricing catalog summarizes prices, opens structured details and filters ${path}`, async ({ page }) => {
    await page.route('**/api/account/me', route => route.fulfill({
      json: {
        id: 1, email: 'pricing@example.com', is_admin: false, is_active: true,
        created_at: '2026-11-08T00:00:00Z', account: { available: '0.0000', frozen: '0.0000' },
      },
    }))
    await page.route('**/api/public/models', route => route.fulfill({ json: { data: models } }))
    await page.goto(path)
    const rows = page.locator('.catalog-list .catalog-model-card')
    await expect(rows).toHaveCount(path === '/console/models' ? 2 : 4)
    const fixed = rows.filter({ has: page.getByText('gpt-image-2-1k', { exact: true }) })
    await expect(fixed.locator('.catalog-model-id')).toHaveText('gpt-image-2-1k')
    await expect(fixed.locator('code')).toHaveCount(1)
    await expect(fixed).not.toContainText('图片')
    await expect(fixed.locator('.model-name')).toHaveCount(0)
    await expect(fixed.locator('.catalog-price-card')).toHaveCount(1)
    await expect(fixed.locator('.catalog-price-card')).toContainText('0.0500')
    await expect(fixed.locator('.catalog-price-condition')).toHaveText('low / medium / high / xhigh / max')
    const flare = rows.filter({ has: page.getByText('gpt-image-2.6-flare-2k', { exact: true }) })
    if (path === '/models') {
      await expect(flare.locator('.catalog-model-id')).toHaveText('gpt-image-2.6-flare-2k')
      await expect(flare.locator('.catalog-price-card')).toHaveCount(2)
      await expect(flare.locator('.catalog-price-condition').first()).toHaveText('low / medium / high')
      await expect(flare.locator('.catalog-price-condition').last()).toHaveText('xhigh / max')
      await expect(flare).not.toContainText('16:9')
    }
    await expect(page.getByRole('columnheader', { name: '支持参数', exact: true })).toHaveCount(0)
    await expect(page.getByRole('columnheader', { name: '参考图', exact: true })).toHaveCount(0)
    if (path === '/models') await page.getByRole('button', { name: '查看 gpt-image-2.6-flare-2k 详情', exact: true }).click()
    else {
      await page.getByRole('radiogroup', { name: '模型系列' }).getByText('gpt-image-2.6', { exact: true }).click()
      await expect(rows).toHaveCount(1)
      await page.getByRole('button', { name: '查看 gpt-image-2.6-flare-2k 详情', exact: true }).click()
    }
    const dialog = page.getByRole('dialog', { name: 'GPT Image 2.6 · Flare', exact: true })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('16:9', { exact: true })).toBeVisible()
    await expect(dialog.getByText('16 张', { exact: true })).toBeVisible()
    await expect(dialog.getByText('webp', { exact: true })).toBeVisible()
    await expect(dialog.locator('.catalog-detail-prices .el-table__row')).toHaveCount(5)
    await expect(dialog.getByRole('cell', { name: 'quality: max', exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await dialog.locator('.el-dialog__headerbtn').click()

    if (path === '/models') {
      await page.getByRole('combobox', { name: '筛选定价系列', exact: true }).press('ArrowDown')
      await page.getByRole('option', { name: 'GPT Image 2', exact: true }).click()
      await expect(rows).toHaveCount(2)
      await page.getByRole('combobox', { name: '筛选定价档位', exact: true }).press('ArrowDown')
      await page.getByRole('option', { name: 'Web', exact: true }).click()
      await expect(rows).toHaveCount(1)
      await expect(rows.locator('code')).toHaveText('gpt-image-2')
      await page.getByRole('radiogroup', { name: '模型类型' }).getByText('视频', { exact: true }).click()
      await expect(rows).toHaveCount(1)
      await expect(rows.locator('.catalog-model-title')).toHaveText('视频测试')
      await expect(rows.locator('.catalog-price-card')).toHaveCount(2)
      await expect(rows.locator('.catalog-price-card').first()).toContainText('/ 秒')
      await expect(rows.locator('.catalog-price-card').last()).toContainText('/ 条')
    }
    await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })
}
