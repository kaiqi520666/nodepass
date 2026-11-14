<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell, Connection, Document, Expand, Grid, Histogram, House, Key, List, Setting, SwitchButton, UserFilled, Warning } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { errorMessage } from '../api/http'
import { adminNavigation, consoleNavigation } from '../router'
import { useAuthStore } from '../stores/auth'
import ThemeSwitch from '../components/ThemeSwitch.vue'
import ContactSupport from '../components/ContactSupport.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const mobileOpen = ref(false)
const announcementsOpen = ref(false)
const health = ref<'loading' | 'ok' | 'error'>('loading')
const icons = {
  dashboard: Histogram,
  models: Grid,
  tokens: Key,
  tasks: List,
  settings: Setting,
  users: UserFilled,
  providers: Connection,
  exceptions: Warning,
  audit: Document,
}
watch(() => route.path, () => {
  mobileOpen.value = false
  announcementsOpen.value = false
})
onMounted(async () => {
  try {
    const response = await fetch('/health/ready')
    health.value = response.ok ? 'ok' : 'error'
  } catch { health.value = 'error' }
})

async function logout() {
  try {
    await auth.logout()
    await router.push('/')
  } catch (error) { ElMessage.error(errorMessage(error)) }
}
</script>

<template>
  <a class="skip-link" href="#main-content">跳转到主要内容</a>
  <div class="app-shell console-shell">
    <aside class="sidebar desktop-sidebar">
      <RouterLink class="brand" to="/console" aria-label="NodePass 控制台">
        <span class="brand-mark" aria-hidden="true"><img src="/brand-mark.svg" alt="" width="20" height="20" /></span>
        <span>NodePass</span>
      </RouterLink>
      <div class="side-navigation">
      <nav aria-label="控制台导航">
        <div class="nav-group">
          <p class="nav-group-title">控制台</p>
          <RouterLink
            v-for="item in consoleNavigation"
            :key="item.path"
            :to="item.path"
            class="nav-link"
            :aria-current="route.path === item.path ? 'page' : undefined"
            :class="{ 'is-current': route.path === item.path }"
          >
            <el-icon :size="18" aria-hidden="true"><component :is="icons[item.icon]" /></el-icon>
            <span>{{ item.title }}</span>
          </RouterLink>
        </div>
      </nav>
      <nav v-if="auth.user?.is_admin" aria-label="管理导航" class="nav-group">
        <p class="nav-group-title">管理</p>
        <RouterLink v-for="item in adminNavigation" :key="item.path" :to="item.path" class="nav-link" :class="{ 'is-current': route.path === item.path }" :aria-current="route.path === item.path ? 'page' : undefined">
          <el-icon :size="18" aria-hidden="true"><component :is="icons[item.icon]" /></el-icon><span>{{ item.title }}</span>
        </RouterLink>
      </nav>
      </div>
      <div class="sidebar-bottom">
        <span class="service-status" role="status">
          <span class="status-dot" :data-status="health"></span>
          {{ health === 'ok' ? '服务正常' : health === 'error' ? '服务未连接' : '正在连接' }}
        </span>
        <span class="version">v0.1.0</span>
      </div>
    </aside>

    <div class="workspace">
      <header class="topbar">
        <div class="topbar-location">
          <el-button class="mobile-menu icon-button" :icon="Expand" aria-label="打开导航" @click="mobileOpen = true" />
        </div>
        <div class="topbar-actions">
          <div class="header-utilities" aria-label="客服、公告与主题">
            <ContactSupport />
            <el-tooltip content="公告" :show-after="400">
              <el-button :icon="Bell" class="icon-button" aria-label="公告" @click="announcementsOpen = true" />
            </el-tooltip>
            <ThemeSwitch />
          </div>
          <RouterLink to="/" class="el-button console-nav-button" aria-label="返回官网" title="返回官网">
            <el-icon aria-hidden="true"><House /></el-icon><span>返回官网</span>
          </RouterLink>
          <RouterLink v-if="auth.user?.is_admin" to="/admin/users" class="el-button console-nav-button" aria-label="用户管理" title="用户管理" :aria-current="route.meta.admin ? 'page' : undefined">
            <el-icon aria-hidden="true"><UserFilled /></el-icon><span>用户管理</span>
          </RouterLink>
          <template v-if="auth.user">
            <el-tooltip content="退出登录" :show-after="400">
              <el-button class="icon-button" :icon="SwitchButton" aria-label="退出登录" @click="logout" />
            </el-tooltip>
          </template>
        </div>
      </header>
      <main id="main-content" tabindex="-1" class="main-content">
        <RouterView v-slot="{ Component }">
          <Transition name="page" mode="out-in">
            <component :is="Component" :key="route.path" />
          </Transition>
        </RouterView>
      </main>
    </div>
  </div>

  <el-drawer v-model="mobileOpen" title="NodePass" direction="ltr" size="280px">
    <nav class="mobile-navigation" aria-label="控制台移动导航">
      <RouterLink
        v-for="item in consoleNavigation"
        :key="item.path"
        :to="item.path"
        class="nav-link"
        :aria-current="route.path === item.path ? 'page' : undefined"
        :class="{ 'is-current': route.path === item.path }"
      >
        <el-icon :size="18" aria-hidden="true"><component :is="icons[item.icon]" /></el-icon>
        <span>{{ item.title }}</span>
      </RouterLink>
    </nav>
    <nav v-if="auth.user?.is_admin" class="mobile-navigation" aria-label="管理移动导航">
      <p class="nav-group-title">管理</p>
      <RouterLink v-for="item in adminNavigation" :key="item.path" :to="item.path" class="nav-link" :class="{ 'is-current': route.path === item.path }" :aria-current="route.path === item.path ? 'page' : undefined">
        <el-icon :size="18" aria-hidden="true"><component :is="icons[item.icon]" /></el-icon><span>{{ item.title }}</span>
      </RouterLink>
    </nav>
  </el-drawer>
  <el-dialog v-model="announcementsOpen" title="公告" width="520px" destroy-on-close>
    <el-timeline class="announcements-timeline">
      <el-timeline-item>
        <p class="announcement-empty">暂无公告</p>
      </el-timeline-item>
    </el-timeline>
  </el-dialog>
</template>
