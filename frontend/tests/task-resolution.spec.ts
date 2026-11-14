import { test, expect } from '@playwright/test'

const user = {
  id: 1,
  email: 'task-resolution@example.com',
  is_admin: false,
  is_active: true,
  created_at: '2026-11-15T00:00:00Z',
  account: { available: '1.00000000', frozen: '0.00000000' },
}

const base = {
  model: 'gpt-image-2',
  model_name: 'GPT Image 2',
  media_type: 'image',
  created: 1763150000,
  completed: 1763150060,
  duration_ms: 60000,
  timed_out: false,
  request_params: {},
  upstream_status: null,
  data: [],
}

test('account tasks show manual closure and transitional resolution without internals', async ({ page }) => {
  await page.route('**/api/account/me', route => route.fulfill({ json: user }))
  await page.route('**/api/account/tasks', route => route.fulfill({
    json: {
      data: [
        {
          ...base,
          id: '11111111-1111-4111-8111-111111111111',
          status: 'failed',
          billing_status: 'released',
          frozen_amount: '1.00000000',
          consumed_amount: '0.00000000',
          error_message: '任务已关闭，冻结积分已释放',
          resolution: 'manual_released',
        },
        {
          ...base,
          id: '22222222-2222-4222-8222-222222222222',
          status: 'pending',
          billing_status: 'held',
          frozen_amount: '1.00000000',
          consumed_amount: '0.00000000',
          completed: null,
          resolution: 'manual_requeued',
        },
      ],
    },
  }))

  await page.goto('/console/tasks')
  await expect(page.getByRole('heading', { name: '任务日志' })).toBeVisible()
  await expect(page.getByText('已关闭', { exact: true })).toBeVisible()
  await expect(page.getByText('已重新处理', { exact: true })).toBeVisible()
  await expect(page.getByText('manual_released')).toHaveCount(0)
  await expect(page.getByText('manual_requeued')).toHaveCount(0)
})
