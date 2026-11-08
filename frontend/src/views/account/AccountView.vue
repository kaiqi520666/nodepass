<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Calendar, Lock, Message, Refresh, User, UserFilled, Wallet } from '@element-plus/icons-vue'
import { errorMessage } from '../../api/http'
import { useAuthStore } from '../../stores/auth'
import PageHeader from '../../components/PageHeader.vue'

const auth = useAuthStore()
const loading = ref(false)
const error = ref('')
async function refresh() {
  loading.value = true
  error.value = ''
  try { await auth.load() }
  catch (cause) { error.value = errorMessage(cause) }
  finally { loading.value = false }
}
onMounted(refresh)
</script>

<template>
  <section v-if="auth.user" aria-labelledby="account-title">
    <PageHeader eyebrow="控制台" title="账户设置" heading-id="account-title">
      <el-tooltip content="刷新账户"><el-button class="icon-button" :icon="Refresh" :loading="loading" aria-label="刷新账户" @click="refresh" /></el-tooltip>
    </PageHeader>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
    <dl class="account-balances" aria-label="账户积分">
      <div class="account-card account-balance-card">
        <dt><span>可用积分</span><el-icon class="statistic-icon-primary" aria-hidden="true"><Wallet /></el-icon></dt>
        <dd class="numeric">{{ auth.user.account.available }}</dd>
      </div>
      <div class="account-card account-balance-card">
        <dt><span>冻结积分</span><el-icon class="statistic-icon-warning" aria-hidden="true"><Lock /></el-icon></dt>
        <dd class="numeric">{{ auth.user.account.frozen }}</dd>
      </div>
    </dl>
    <h2 class="section-title">账户信息</h2>
    <dl class="account-details">
      <div class="account-card"><dt><span>邮箱</span><el-icon aria-hidden="true"><Message /></el-icon></dt><dd>{{ auth.user.email }}</dd></div>
      <div class="account-card"><dt><span>账户 ID</span><el-icon aria-hidden="true"><User /></el-icon></dt><dd class="numeric">{{ auth.user.id }}</dd></div>
      <div class="account-card"><dt><span>身份</span><el-icon aria-hidden="true"><UserFilled /></el-icon></dt><dd><el-tag effect="plain" :type="auth.user.is_admin ? 'warning' : 'info'">{{ auth.user.is_admin ? '管理员' : '普通用户' }}</el-tag></dd></div>
      <div class="account-card"><dt><span>注册时间</span><el-icon aria-hidden="true"><Calendar /></el-icon></dt><dd>{{ new Date(auth.user.created_at).toLocaleString('zh-CN') }}</dd></div>
    </dl>
  </section>
</template>
