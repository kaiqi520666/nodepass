<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CircleCheck, Lock, Message, Right, UserFilled } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import { errorMessage } from '../../api/http'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const form = ref<FormInstance>()
const data = reactive({ email: '', password: '', confirmation: '' })
const register = computed(() => route.path === '/register')
const busy = ref(false)
const error = ref('')
watch(() => route.path, () => {
  data.password = ''
  data.confirmation = ''
  error.value = ''
  form.value?.clearValidate()
})
const rules = computed<FormRules>(() => ({
  email: [{ required: true, message: '请输入邮箱', trigger: 'blur' }, { type: 'email', message: '请输入有效的邮箱', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 8, max: 128, message: '密码长度为 8–128 个字符', trigger: 'blur' }],
  confirmation: [{
    validator: (_rule, value, callback) => value === data.password ? callback() : callback(new Error('两次密码不一致')),
    trigger: 'blur',
  }],
}))

async function submit() {
  if (busy.value || !await form.value?.validate().catch(() => false)) return
  busy.value = true
  error.value = ''
  try {
    await auth.submit(register.value ? 'register' : 'login', data.email, data.password)
    data.password = ''
    data.confirmation = ''
    const redirect = route.query.redirect
    const destination = typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//') && !['/login', '/register'].includes(redirect.split('?')[0]!) ? redirect : '/console'
    await router.replace(destination)
  } catch (cause) { error.value = errorMessage(cause) }
  finally { busy.value = false }
}
</script>

<template>
  <section class="auth-page" :key="route.path">
    <h1>{{ register ? '创建账户' : '欢迎回来' }}</h1>
    <p class="auth-switch">
      {{ register ? '已有账户？' : '还没有账户？' }}
      <RouterLink :to="register ? '/login' : '/register'">{{ register ? '登录' : '注册' }}</RouterLink>
    </p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" class="form-alert" />
    <el-form ref="form" :model="data" :rules="rules" label-position="top" size="large" @submit.prevent="submit">
      <el-form-item label="邮箱" prop="email" for="auth-email">
        <el-input id="auth-email" v-model="data.email" type="email" autocomplete="email" :disabled="busy" :prefix-icon="Message" placeholder="name@example.com" />
      </el-form-item>
      <el-form-item label="密码" prop="password" for="auth-password">
        <el-input id="auth-password" v-model="data.password" type="password" show-password :prefix-icon="Lock" :autocomplete="register ? 'new-password' : 'current-password'" :disabled="busy" :maxlength="128" placeholder="至少 8 个字符" />
      </el-form-item>
      <el-form-item v-if="register" label="确认密码" prop="confirmation" for="auth-confirmation">
        <el-input id="auth-confirmation" v-model="data.confirmation" type="password" show-password :prefix-icon="CircleCheck" autocomplete="new-password" :disabled="busy" :maxlength="128" />
      </el-form-item>
      <el-button type="primary" native-type="submit" :loading="busy" :icon="register ? UserFilled : Right" class="auth-submit">{{ register ? '注册' : '登录' }}</el-button>
    </el-form>
  </section>
</template>
