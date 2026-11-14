import { test, expect } from '@playwright/test'

const qualities = ['low', 'medium', 'high', 'xhigh', 'max']
const tiers = ['web', '1k', '2k', '4k']
const models = [
  {
    id: 'gpt-image-2', name: 'GPT Image 2', media_type: 'image',
    capabilities: { tiers, sizes: ['1:1', '16:9'], qualities, max_reference_images: 9 },
    prices: tiers.map((tier, index) => ({
      variant: { tier }, unit: 'image', unit_price: ['0.0170', '0.0550', '0.0700', '0.0800'][index],
    })),
  },
  {
    id: 'gpt-image-2.5', name: 'GPT Image 2.5', media_type: 'image',
    capabilities: { series: ['flare', 'sunburst'], tiers, sizes: ['1:1', '16:9'], qualities, max_reference_images: 9 },
    prices: ['flare', 'sunburst'].flatMap(series => tiers.flatMap(tier => qualities.map(quality => ({
      variant: { series, tier, quality }, unit: 'image',
      unit_price: tier === 'web' ? '0.0250' : quality === 'xhigh' || quality === 'max' ? '0.3600' : '0.1800',
    })))),
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
  test(`two parameterized models show structured prices and details ${path}`, async ({ page }) => {
    await page.route('**/api/account/me', route => route.fulfill({
      json: {
        id: 1, email: 'pricing@example.com', is_admin: false, is_active: true,
        created_at: '2026-11-08T00:00:00Z', account: { available: '0.0000', frozen: '0.0000' },
      },
    }))
    await page.route('**/api/public/models', route => route.fulfill({ json: { data: models } }))
    await page.goto(path)
    const rows = page.locator('.catalog-list .catalog-model-card')
    await expect(rows).toHaveCount(path === '/console/models' ? 1 : 3)
    const image = rows.filter({ has: page.getByText('gpt-image-2', { exact: true }) })
    await expect(image.locator('code')).toHaveCount(1)
    await expect(image.locator('.catalog-price-card')).toHaveCount(4)
    await expect(image).toContainText('0.055')
    await expect(image.locator('.catalog-price-value strong').nth(1)).toHaveAttribute('title', '0.05500000 积分')
    await expect(image).not.toContainText('图片')
    await expect(page.getByText('gpt-image-2.6', { exact: true })).toHaveCount(0)

    if (path === '/console/models') {
      await page.getByRole('radiogroup', { name: '模型系列' }).getByText('gpt-image-2.5', { exact: true }).click()
      await expect(rows).toHaveCount(1)
    }
    const combined = rows.filter({ has: page.getByText('gpt-image-2.5', { exact: true }) })
    await expect(combined.locator('.catalog-price-card')).toHaveCount(6)
    await expect(combined).toContainText('low / medium / high')
    await expect(combined).toContainText('xhigh / max')
    await expect(combined.getByText('档位', { exact: true }).first()).toBeVisible()
    await expect(combined.getByText('分支', { exact: true }).first()).toBeVisible()
    await expect(combined.getByText('质量', { exact: true }).first()).toBeVisible()
    await expect(combined.getByText('另有 8 组价目', { exact: false })).toBeVisible()
    await page.getByRole('button', { name: '查看 gpt-image-2.5 详情', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: 'GPT Image 2.5', exact: true })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('16:9', { exact: true })).toBeVisible()
    await expect(dialog.getByText('9 张', { exact: true })).toBeVisible()
    await expect(dialog.locator('.catalog-detail-prices .el-table__row')).toHaveCount(40)
    await expect(dialog.getByText('0.02500000', { exact: true }).first()).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await dialog.locator('.el-dialog__headerbtn').click()

    if (path === '/models') {
      await page.getByRole('combobox', { name: '筛选定价系列', exact: true }).press('ArrowDown')
      await page.getByRole('option', { name: 'GPT Image 2', exact: true }).click()
      await expect(rows).toHaveCount(1)
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
