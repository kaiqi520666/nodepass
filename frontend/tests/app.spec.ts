import { test, expect, type Page } from '@playwright/test'

async function assertPrimaryContrast(page: Page) {
  const controls = [
    page.getByRole('link', { name: '注册', exact: true }),
    page.getByRole('radiogroup', { name: '模型类型' }).locator('.el-segmented__item.is-selected'),
  ]
  for (const control of controls) {
    await expect.poll(() => control.evaluate(element => {
      const style = getComputedStyle(element)
      const selectionBackground = element
        .closest('.el-segmented')
        ?.querySelector('.el-segmented__item-selected')
      const luminance = (color: string) => {
        const channels = color.match(/[\d.]+/g)!.slice(0, 3).map(value => {
          const channel = Number(value) / 255
          return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
        })
        return channels[0]! * 0.2126 + channels[1]! * 0.7152 + channels[2]! * 0.0722
      }
      const background = selectionBackground
        ? getComputedStyle(selectionBackground).backgroundColor
        : style.backgroundColor
      const values = [luminance(style.color), luminance(background)].sort((a, b) => b - a)
      return (values[0]! + 0.05) / (values[1]! + 0.05)
    })).toBeGreaterThanOrEqual(4.5)
  }
}

test('public models, search and API reference', async ({ page }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/public/models', route => route.fulfill({ json: { data: [] } }))
  await page.goto('/models')
  await expect(page.getByRole('heading', { name: '模型广场' })).toBeVisible()
  await expect(page.locator('.console-shell')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '公告', exact: true })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '暂无上架模型' })).toBeVisible()
  await page.getByRole('textbox', { name: '搜索模型' }).fill('not-configured')
  await expect(page.getByRole('heading', { name: '暂无上架模型' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('models-light.png'), fullPage: true })
  await page.goto('/api-docs')
  await expect(page.getByRole('heading', { name: 'API 文档' })).toBeVisible()
  await expect(page.getByRole('region', { name: '快速开始', exact: true })).toContainText('HTTP 202')
  await expect(page.getByRole('region', { name: '模型列表', exact: true })).toContainText('/v1/models')
  await expect(page.getByRole('region', { name: '图片生成', exact: true })).toContainText('/v1/images/generations')
  await expect(page.getByRole('main')).not.toContainText('/api/public/models')
  const unauthenticated = await page.request.get('/v1/models')
  expect(unauthenticated.status()).toBe(401)
  expect((await unauthenticated.json()).error.code).toBe('invalid_api_key')
  await page.emulateMedia({ colorScheme: 'light' })
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect(page.locator('html')).toHaveClass(/dark/)
  if (testInfo.project.name === 'mobile') {
    await page.setViewportSize({ width: 320, height: 812 })
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  expect(errors).toEqual([])
})

test('theme follows system, persists manual choice and ignores later system changes', async ({ page }, testInfo) => {
  await page.emulateMedia({ colorScheme: 'light' })
  await page.goto('/models')
  await expect(page.locator('html')).not.toHaveClass(/dark/)
  await assertPrimaryContrast(page)
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect(page.locator('html')).toHaveClass(/dark/)
  await assertPrimaryContrast(page)
  await page.getByRole('button', { name: '切换主题' }).click()
  await page.getByRole('menuitem', { name: '明亮', exact: true }).click()
  await expect(page.locator('html')).not.toHaveClass(/dark/)
  await page.emulateMedia({ colorScheme: 'light' })
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect(page.locator('html')).not.toHaveClass(/dark/)
  await page.reload()
  await expect(page.locator('html')).not.toHaveClass(/dark/)
  await page.getByRole('button', { name: '切换主题' }).click()
  await page.getByRole('menuitem', { name: '暗黑', exact: true }).click()
  await expect(page.locator('html')).toHaveClass(/dark/)
  await expect(page.getByRole('menu', { name: '切换主题' })).not.toBeVisible()
  await assertPrimaryContrast(page)
  await page.screenshot({ path: testInfo.outputPath('models-dark.png'), fullPage: true })
  await page.getByRole('button', { name: '切换主题' }).click()
  await page.getByRole('menuitem', { name: '跟随系统', exact: true }).click()
  await page.emulateMedia({ colorScheme: 'light' })
  await expect(page.locator('html')).not.toHaveClass(/dark/)
})

test('protected routes, registration validation and invalid login', async ({ page }, testInfo) => {
  await page.goto('/admin/users')
  await expect(page).toHaveURL(/\/login\?redirect=/)
  await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible()
  await expect(page.getByText('NodePass 账户', { exact: true })).toHaveCount(0)
  await expect(page.locator('.el-input:has(#auth-email) .el-input__prefix')).toHaveCount(1)
  await expect(page.locator('.el-input:has(#auth-password) .el-input__prefix')).toHaveCount(1)
  await expect(page.locator('form').getByRole('button', { name: '登录', exact: true }).locator('.el-icon')).toHaveCount(1)
  await page.getByLabel('邮箱', { exact: true }).fill('missing@example.com')
  await page.getByLabel('密码', { exact: true }).fill('wrong-password')
  await page.locator('form').getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('邮箱或密码不正确')
  await page.goto('/register')
  await expect(page.getByText('NodePass 账户', { exact: true })).toHaveCount(0)
  await page.getByLabel('邮箱', { exact: true }).fill('user@example.com')
  await page.getByLabel('密码', { exact: true }).fill('valid-password')
  await page.getByLabel('确认密码', { exact: true }).fill('does-not-match')
  await page.locator('form').getByRole('button', { name: '注册', exact: true }).click()
  await expect(page.getByText('两次密码不一致')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('registration.png'), fullPage: true })
})

test('catalog has a recoverable network error state', async ({ page }) => {
  let fail = true
  await page.route('**/api/public/models', route => fail
    ? route.fulfill({ status: 503, json: { detail: '暂时不可用' } })
    : route.fulfill({ json: { data: [] } }))
  await page.goto('/models')
  await expect(page.getByText('模型加载失败', { exact: true })).toBeVisible()
  fail = false
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await expect(page.getByRole('heading', { name: '暂无上架模型' })).toBeVisible()
})

test('mobile navigation and not-found route', async ({ page }, testInfo) => {
  await page.goto('/models')
  if (testInfo.project.name === 'mobile') {
    await page.getByRole('button', { name: '打开导航' }).click()
    await page.getByRole('navigation', { name: '移动导航' }).getByRole('link', { name: 'API 文档' }).click()
    await expect(page.getByRole('heading', { name: 'API 文档' })).toBeVisible()
    await expect(page.getByRole('dialog')).not.toBeVisible()
    await page.setViewportSize({ width: 812, height: 375 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  }
  await page.goto('/does-not-exist')
  await expect(page.getByRole('main').getByText('页面不存在', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '返回模型目录' }).click()
  await expect(page).toHaveURL('/models')
})

test('configured catalog renders and filters fixture data without overflowing', async ({ page }) => {
  const longId = `image-${'reference-'.repeat(14)}model`
  await page.route('**/api/public/models', route => route.fulfill({
    json: {
      data: [
        { id: longId, name: '测试图片模型', media_type: 'image', capabilities: { sizes: ['1024x1024'] }, prices: [{ variant: {}, unit: 'image', unit_price: '0.1234' }] },
        { id: 'test-video', name: '测试视频模型', media_type: 'video', capabilities: { resolutions: ['720p', '1080p'] }, prices: [{ variant: { resolution: '720p' }, unit: 'second', unit_price: '0.2000' }] },
      ],
    },
  }))
  await page.goto('/models')
  await expect(page.getByRole('radiogroup', { name: '模型类型' }).locator('.model-type-option .el-icon')).toHaveCount(4)
  await expect(page.getByText(longId, { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByRole('radiogroup', { name: '模型类型' }).getByText('视频', { exact: true }).click()
  await expect(page.getByRole('radio', { name: '视频', exact: true })).toBeChecked()
  await expect(page.getByText('测试视频模型', { exact: true })).toBeVisible()
  await expect(page.getByText('测试图片模型', { exact: true })).not.toBeVisible()
  await page.getByRole('textbox', { name: '搜索模型' }).fill('no-match')
  await expect(page.getByRole('heading', { name: '没有匹配的模型' })).toBeVisible()
})

for (const isAdmin of [false, true]) {
  test(`account and admin navigation with ${isAdmin ? 'admin' : 'user'} response fixture`, async ({ page }, testInfo) => {
    const user = {
      id: 1, email: `${'long-account-'.repeat(5)}@example.com`,
      is_admin: isAdmin, is_active: true, created_at: '2026-11-07T00:00:00Z',
      account: { available: '0.0000', frozen: '0.0000' },
    }
    await page.route('**/api/account/me', route => route.fulfill({ json: user }))
    await page.route('**/api/account/keys', route => route.fulfill({ json: { data: [] } }))
    await page.route('**/api/admin/users?*', route => route.fulfill({ json: { data: [user], total: 1 } }))
    await page.goto('/admin/users')
    if (isAdmin) {
      await expect(page.getByRole('heading', { name: '用户管理' })).toBeVisible()
      await expect(page.getByRole('main').getByRole('cell', { name: user.email, exact: true })).toBeVisible()
      await expect(page.locator('.topbar').getByRole('link', { name: '用户管理', exact: true })).toHaveClass(/el-button/)
    } else {
      await expect(page).toHaveURL('/console')
    }
    await page.goto('/account')
    await expect(page).toHaveURL('/console/settings')
    await expect(page.getByRole('heading', { name: '账户设置' })).toBeVisible()
    await expect(page.locator('.account-balances .account-card')).toHaveCount(2)
    await expect(page.locator('.account-details .account-card')).toHaveCount(4)
    await expect(page.getByRole('main').getByText(user.email, { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('account-fixture.png'), fullPage: true })
    await page.getByRole('button', { name: '退出登录', exact: true }).click()
    await expect(page.getByRole('link', { name: '登录', exact: true })).toBeVisible()
  })
}

test('API Key creation, one-time display and revocation with response fixtures', async ({ page }, testInfo) => {
  const rawKey = `sk-nodepass-${'t'.repeat(43)}`
  const key = {
    id: 1, name: '本地开发', key_prefix: rawKey.slice(0, 19), is_active: true,
    created_at: '2026-11-07T00:00:00Z', expires_at: null, last_used_at: null,
  }
  let exists = false
  let deleted = false
  await page.route('**/api/account/me', route => route.fulfill({
    json: {
      id: 1, email: 'key-ui@example.com', is_admin: false, is_active: true,
      created_at: '2026-11-07T00:00:00Z', account: { available: '0.0000', frozen: '0.0000' },
    },
  }))
  await page.route('**/api/account/keys', route => {
    if (route.request().method() === 'POST') {
      expect(route.request().postDataJSON()).toEqual({ name: '本地开发', expires_at: null })
      exists = true
      return route.fulfill({ status: 201, json: { ...key, key: rawKey } })
    }
    return route.fulfill({ json: { data: exists && !deleted ? [key] : [] } })
  })
  await page.route('**/api/account/keys/1/secret', route => {
    return route.fulfill({ json: { key: rawKey } })
  })
  await page.route('**/api/account/keys/1', route => {
    if (route.request().method() === 'PUT') return route.fulfill({ json: { ...key, name: '更新后的 Key' } })
    deleted = true
    return route.fulfill({ status: 204 })
  })
  await page.goto('/console/tokens')
  const keys = page.getByRole('region', { name: 'API Key', exact: true })
  await expect(page.getByRole('heading', { name: 'API Key', exact: true })).toHaveCount(0)
  await expect(keys.getByRole('button', { name: '刷新 API Key', exact: true })).toBeVisible()
  await expect(keys.getByText('暂无 API Key')).toBeVisible()
  await keys.getByRole('button', { name: '创建 Key', exact: true }).click()
  const createDialog = page.getByRole('dialog', { name: '创建 API Key' })
  await expect(createDialog).toBeVisible()
  await createDialog.getByLabel('Key 名称').fill('  本地开发  ')
  await createDialog.getByRole('button', { name: '创建', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'API Key 已创建' })
  await expect(dialog.getByRole('textbox', { name: '新 API Key' })).toHaveValue(rawKey)
  await expect(dialog).toContainText('密钥已加密保存')
  await expect.poll(() => dialog.evaluate(element => element.contains(document.activeElement))).toBe(true)
  expect(await page.evaluate(key => JSON.stringify(localStorage).includes(key) || JSON.stringify(sessionStorage).includes(key), rawKey)).toBe(false)
  await page.screenshot({ path: testInfo.outputPath('key-created-fixture-light.png'), animations: 'disabled' })
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.screenshot({ path: testInfo.outputPath('key-created-fixture-dark.png'), animations: 'disabled' })
  await dialog.getByRole('button', { name: '完成', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.getByRole('textbox', { name: '新 API Key' })).toHaveCount(0)
  await expect(keys.getByText(`${key.key_prefix}...`, { exact: true })).toBeVisible()
  await keys.getByRole('button', { name: '查看 本地开发' }).click()
  const viewDialog = page.getByRole('dialog', { name: '查看 API Key', exact: true })
  await expect(viewDialog.getByRole('textbox', { name: 'API Key' })).toHaveValue(rawKey)
  await viewDialog.getByRole('button', { name: '完成', exact: true }).click()
  await keys.getByRole('button', { name: '编辑 本地开发' }).click()
  const editDialog = page.getByRole('dialog', { name: '编辑 API Key' })
  await editDialog.getByRole('textbox', { name: '名称' }).fill('更新后的 Key')
  await editDialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(keys.getByText('更新后的 Key', { exact: true })).toBeVisible()
  await keys.getByRole('button', { name: '删除 更新后的 Key' }).click()
  const confirmation = page.getByRole('dialog', { name: '删除 API Key' })
  await confirmation.getByRole('button', { name: '删除', exact: true }).click()
  await expect(keys.getByText('暂无 API Key')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('keys-account-fixture-dark.png'), fullPage: true, animations: 'disabled' })
})

test('public homepage, image placeholders and navigation use the website layout', async ({ page }, testInfo) => {
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /一个 Key/ })).toBeVisible()
  await expect(page.locator('.console-shell')).toHaveCount(0)
  await expect(page.locator('.home-terminal')).toBeVisible()
  await expect(page.getByRole('img', { name: '图片效果展示占位' })).toBeVisible()
  await expect(page.getByRole('img', { name: '视频效果展示占位' })).toBeVisible()
  await expect(page.getByText('服务正常', { exact: true })).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath('home-light.png'), fullPage: true, animations: 'disabled' })
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect(page.locator('html')).toHaveClass(/dark/)
  await page.screenshot({ path: testInfo.outputPath('home-dark.png'), fullPage: true, animations: 'disabled' })
  if (testInfo.project.name === 'mobile') {
    await page.setViewportSize({ width: 320, height: 812 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.getByRole('button', { name: '打开导航' }).click()
    const navigation = page.getByRole('navigation', { name: '移动导航', exact: true })
    await expect(navigation.getByRole('link')).toHaveText(['首页', '模型广场', 'API 文档'])
    await navigation.getByRole('link', { name: '模型广场' }).click()
    await expect(page.getByRole('dialog')).not.toBeVisible()
  } else {
    const navigation = page.getByRole('navigation', { name: '官网导航', exact: true })
    await expect(navigation.getByRole('link')).toHaveText(['首页', '模型广场', 'API 文档'])
    await navigation.getByRole('link', { name: '模型广场' }).click()
  }
  await expect(page).toHaveURL('/pricing')
  await expect(page.getByRole('heading', { name: '模型广场' })).toBeVisible()
  const utilities = page.locator('.header-utilities')
  await expect(utilities.getByRole('button', { name: '联系客服', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '公告', exact: true })).toHaveCount(0)
  await expect(utilities.getByRole('button', { name: '切换主题', exact: true })).toBeVisible()
  for (const name of ['登录', '注册']) {
    await expect(page.locator('.public-header').getByRole('link', { name, exact: true }).locator('.el-icon')).toHaveCount(1)
  }
  await utilities.getByRole('button', { name: '联系客服', exact: true }).click()
  const qr = page.getByRole('img', { name: '客服二维码占位' })
  await expect(qr).toBeVisible()
  await utilities.getByRole('button', { name: '联系客服', exact: true }).press('Escape')
  await expect(qr).not.toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('every console page requires login and preserves its destination', async ({ page }) => {
  for (const path of ['/console', '/console/models', '/console/tokens', '/console/tasks', '/console/settings']) {
    await page.goto(path)
    await expect(page).toHaveURL(url => url.pathname === '/login' && url.searchParams.get('redirect') === path)
    await expect(page.locator('.public-shell')).toBeVisible()
    await expect(page.locator('.console-shell')).toHaveCount(0)
  }
})

test('signed-in visitors keep the website layout and enter the five-menu console through their account', async ({ page }, testInfo) => {
  const user = {
    id: 1, email: `${'long-account-'.repeat(5)}@example.com`, is_admin: false, is_active: true,
    created_at: '2026-11-07T00:00:00Z', account: { available: '12.3456', frozen: '1.0000' },
  }
  await page.route('**/api/account/me', route => route.fulfill({ json: user }))
  await page.route('**/api/account/tasks', route => route.fulfill({ json: { data: [] } }))
  await page.route('**/api/account/dashboard', route => route.fulfill({
    json: {
      available: '12.34560000', consumed: '3.60035201', requests: 7, today_consumed: '1.80035201',
      trend: [
        { date: '2026-11-09', consumed: '0.10000000' },
        { date: '2026-11-10', consumed: '0.20000000' },
        { date: '2026-11-11', consumed: '0.00000000' },
        { date: '2026-11-12', consumed: '0.40000000' },
        { date: '2026-11-13', consumed: '0.50000000' },
        { date: '2026-11-14', consumed: '0.60000000' },
        { date: '2026-11-15', consumed: '1.80035201' },
      ],
    },
  }))
  await page.goto('/')
  const account = page.locator('.public-header').getByRole('link', { name: user.email.split('@')[0], exact: true })
  await expect(account).toBeVisible()
  await expect(page.getByRole('link', { name: '登录', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '公告', exact: true })).toHaveCount(0)
  await expect(page.locator('.console-shell')).toHaveCount(0)
  if (testInfo.project.name === 'mobile') await page.setViewportSize({ width: 320, height: 812 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await account.click()
  await expect(page).toHaveURL('/console')
  await expect(page.getByRole('heading', { name: '仪表盘', exact: true })).toBeVisible()
  await expect(page.getByText('12.34560000', { exact: true })).toBeVisible()
  const statistics = page.locator('.dashboard-statistics')
  await expect(statistics.locator('.dashboard-statistic')).toHaveCount(4)
  await expect(statistics.locator('dt')).toHaveText(['可用积分', '已用积分', '请求次数', '今日消耗'])
  await expect(statistics.locator('dd')).toHaveText(['12.34560000', '3.60035201', '7', '1.80035201'])
  await expect(statistics.getByLabel('暂无数据')).toHaveCount(0)
  await expect(page.getByRole('navigation', { name: '快捷入口', exact: true })).toHaveCount(0)
  await expect(page.locator('.topbar .header-account')).toHaveCount(0)
  await expect(page.locator('.topbar').getByRole('link', { name: '返回官网', exact: true })).toHaveClass(/el-button/)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await expect(page.locator('.public-shell')).toHaveCount(0)
  await expect(page.getByRole('link', { name: '用户管理', exact: true })).toHaveCount(0)
  const utilities = page.locator('.topbar .header-utilities')
  await expect(utilities.getByRole('button', { name: '切换主题', exact: true })).toBeVisible()
  await utilities.getByRole('button', { name: '联系客服', exact: true }).click()
  const qr = page.getByRole('img', { name: '客服二维码占位' })
  await expect(qr).toBeVisible()
  await utilities.getByRole('button', { name: '公告', exact: true }).click()
  await expect(qr).not.toBeVisible()
  const announcements = page.getByRole('dialog', { name: '公告', exact: true })
  await expect(announcements).toBeVisible()
  await expect(announcements.locator('.el-timeline')).toContainText('暂无公告')
  await announcements.press('Escape')
  await expect(announcements).not.toBeVisible()
  if (testInfo.project.name === 'mobile') await page.getByRole('button', { name: '打开导航' }).click()
  const navigation = page.getByRole('navigation', { name: testInfo.project.name === 'mobile' ? '控制台移动导航' : '控制台导航', exact: true })
  await expect(navigation.getByRole('link')).toHaveText(['仪表盘', '模型定价', 'API 令牌', '任务日志', '账户设置'])
  await navigation.getByRole('link', { name: '模型定价', exact: true }).click()
  await expect(page.getByRole('heading', { name: '模型定价', exact: true })).toBeVisible()
  await expect(page.locator('.sidebar .nav-link.is-current')).toHaveText('模型定价')
  await page.goto('/console/tasks')
  await expect(page.getByText('暂无匹配的任务', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('console-layout.png'), fullPage: true, animations: 'disabled' })
  await page.getByRole('link', { name: '返回官网', exact: true }).click()
  await expect(page).toHaveURL('/')
  await expect(account).toBeVisible()
  await expect(page.getByRole('button', { name: '公告', exact: true })).toHaveCount(0)
})

test('successful login returns to the requested console page', async ({ page }) => {
  const user = {
    id: 1, email: 'login-ui@example.com', is_admin: false, is_active: true,
    created_at: '2026-11-07T00:00:00Z', account: { available: '0.0000', frozen: '0.0000' },
  }
  await page.route('**/api/account/me', route => route.fulfill({ status: 401, json: { detail: '请先登录' } }))
  await page.route('**/api/account/login', route => route.fulfill({ json: user }))
  await page.route('**/api/account/keys', route => route.fulfill({ json: { data: [] } }))
  await page.goto('/console/tokens')
  await page.getByLabel('邮箱', { exact: true }).fill(user.email)
  await page.getByLabel('密码', { exact: true }).fill('valid-password')
  await page.locator('form').getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL('/console/tokens')
  await expect(page.getByRole('heading', { name: 'API 令牌', exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: 'API Key', exact: true })).toBeVisible()
})
