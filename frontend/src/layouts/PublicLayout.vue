<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Connection, Expand, Right, User, UserFilled } from '@element-plus/icons-vue'
import ContactSupport from '../components/ContactSupport.vue'
import ThemeSwitch from '../components/ThemeSwitch.vue'
import { publicNavigation } from '../router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const auth = useAuthStore()
const mobileOpen = ref(false)
watch(() => route.path, () => {
  mobileOpen.value = false
})
</script>

<template>
  <a class="skip-link" href="#main-content">跳转到主要内容</a>
  <div class="public-shell">
    <header class="public-header">
      <div class="public-header-inner">
        <RouterLink class="brand public-brand" to="/" aria-label="NodePass 首页">
          <span class="brand-mark" aria-hidden="true"><el-icon :size="23"><Connection /></el-icon></span>
          <span>NodePass</span>
        </RouterLink>
        <nav class="public-navigation" aria-label="官网导航">
          <RouterLink v-for="item in publicNavigation" :key="item.path" :to="item.path" :aria-current="route.path === item.path || (item.path === '/pricing' && route.path === '/models') ? 'page' : undefined">{{ item.title }}</RouterLink>
        </nav>
        <div class="public-header-actions">
          <div class="header-utilities" aria-label="客服与主题">
            <ContactSupport />
            <ThemeSwitch />
          </div>
          <RouterLink v-if="auth.user" to="/console" class="header-account public-account" :title="auth.user.email">
            <el-icon aria-hidden="true"><User /></el-icon>
            <span>{{ auth.user.email.split('@')[0] }}</span>
          </RouterLink>
          <template v-else>
            <RouterLink to="/login" class="login-link auth-header-link"><el-icon aria-hidden="true"><Right /></el-icon>登录</RouterLink>
            <RouterLink to="/register" class="public-register auth-header-link"><el-icon aria-hidden="true"><UserFilled /></el-icon>注册</RouterLink>
          </template>
          <el-button class="mobile-menu icon-button" :icon="Expand" aria-label="打开导航" @click="mobileOpen = true" />
        </div>
      </div>
    </header>
    <main id="main-content" tabindex="-1" :class="['public-main', { 'public-home': route.path === '/' }]">
      <RouterView />
    </main>
    <footer class="public-footer">
      <div><strong>NodePass</strong><span>图片与视频 API</span></div>
      <nav aria-label="页脚导航"><RouterLink to="/pricing">模型广场</RouterLink><RouterLink to="/api-docs">API 文档</RouterLink></nav>
    </footer>
  </div>
  <el-drawer v-model="mobileOpen" title="NodePass" direction="rtl" size="280px">
    <nav class="mobile-navigation" aria-label="移动导航">
      <RouterLink v-for="item in publicNavigation" :key="item.path" :to="item.path" class="nav-link" :class="{ 'is-current': route.path === item.path || (item.path === '/pricing' && route.path === '/models') }">{{ item.title }}</RouterLink>
    </nav>
  </el-drawer>
</template>
