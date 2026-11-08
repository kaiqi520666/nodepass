import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    title: string
    requiresAuth?: boolean
    admin?: boolean
  }
}

export const publicNavigation = [
  { path: '/', title: '首页' },
  { path: '/pricing', title: '模型广场' },
  { path: '/api-docs', title: 'API 文档' },
] as const

export const consoleNavigation = [
  { path: '/console', title: '仪表盘', icon: 'dashboard' },
  { path: '/console/models', title: '模型定价', icon: 'models' },
  { path: '/console/tokens', title: 'API 令牌', icon: 'tokens' },
  { path: '/console/tasks', title: '任务日志', icon: 'tasks' },
  { path: '/console/settings', title: '账户设置', icon: 'settings' },
] as const

export const adminNavigation = [
  { path: '/admin/users', title: '用户管理', icon: 'users' },
  { path: '/admin/providers', title: '供应商配置', icon: 'providers' },
  { path: '/admin/models', title: '模型与价格', icon: 'models' },
  { path: '/admin/settings', title: '系统设置', icon: 'settings' },
] as const

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    {
      path: '/',
      component: () => import('../layouts/PublicLayout.vue'),
      children: [
        {
          path: '',
          component: () => import('../views/home/HomeView.vue'),
          meta: { title: '首页' },
        },
        {
          path: 'pricing',
          alias: '/models',
          component: () => import('../views/models/ModelsView.vue'),
          meta: { title: '模型广场' },
        },
        {
          path: 'api-docs',
          component: () => import('../views/docs/ApiDocsView.vue'),
          meta: { title: 'API 文档' },
        },
        {
          path: 'login',
          component: () => import('../views/auth/AuthView.vue'),
          meta: { title: '登录' },
        },
        {
          path: 'register',
          component: () => import('../views/auth/AuthView.vue'),
          meta: { title: '注册' },
        },
        {
          path: ':pathMatch(.*)*',
          component: () => import('../views/NotFoundView.vue'),
          meta: { title: '页面不存在' },
        },
      ],
    },
    {
      path: '/console',
      component: () => import('../layouts/ConsoleLayout.vue'),
      meta: { title: '控制台', requiresAuth: true },
      children: [
        {
          path: '',
          component: () => import('../views/account/DashboardView.vue'),
          meta: { title: '仪表盘' },
        },
        {
          path: 'models',
          component: () => import('../views/models/ModelsView.vue'),
          meta: { title: '模型定价' },
        },
        {
          path: 'tokens',
          component: () => import('../views/account/TokensView.vue'),
          meta: { title: 'API 令牌' },
        },
        {
          path: 'tasks',
          component: () => import('../views/account/TasksView.vue'),
          meta: { title: '任务日志' },
        },
        {
          path: 'settings',
          component: () => import('../views/account/AccountView.vue'),
          meta: { title: '账户设置' },
        },
      ],
    },
    {
      path: '/account',
      redirect: '/console/settings',
    },
    {
      path: '/admin',
      component: () => import('../layouts/ConsoleLayout.vue'),
      meta: { title: '管理', requiresAuth: true, admin: true },
      children: [
        { path: '', redirect: '/admin/users' },
        {
          path: 'users',
          component: () => import('../views/admin/UsersView.vue'),
          meta: { title: '用户管理' },
        },
        {
          path: 'providers',
          component: () => import('../views/admin/ProvidersView.vue'),
          meta: { title: '供应商配置' },
        },
        {
          path: 'models',
          component: () => import('../views/admin/ModelsView.vue'),
          meta: { title: '模型与价格' },
        },
        {
          path: 'settings',
          component: () => import('../views/admin/SettingsView.vue'),
          meta: { title: '系统设置' },
        },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.ensureLoaded()
  if (to.meta.requiresAuth && !auth.user) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.meta.admin && !auth.user?.is_admin) return '/console'
  if (auth.user && ['/login', '/register'].includes(to.path)) return '/console'
})

router.afterEach((to) => {
  document.title = `${to.meta.title} · NodePass`
  requestAnimationFrame(() => document.getElementById('main-content')?.focus())
})

export default router
