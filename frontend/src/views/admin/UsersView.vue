<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Operation, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { http, errorMessage } from '../../api/http'
import type { User } from '../../types'
import AppTable from '../../components/AppTable.vue'
import PageHeader from '../../components/PageHeader.vue'

const users = ref<User[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const error = ref('')
const creditDialog = ref(false)
const creditSaving = ref(false)
const creditUser = ref<User | null>(null)
const passwordDialog = ref(false)
const passwordSaving = ref(false)
const passwordUser = ref<User | null>(null)
const credit = reactive<{ direction: 'increase' | 'decrease'; amount: string; reason: string }>({ direction: 'increase', amount: '', reason: '' })
const password = reactive({ value: '', confirmation: '' })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await http.get<{ data: User[]; total: number }>('/admin/users', { params: { offset: (page.value - 1) * pageSize.value, limit: pageSize.value } })
    users.value = response.data.data
    total.value = response.data.total
  } catch (cause) { error.value = errorMessage(cause) }
  finally { loading.value = false }
}

function openCredit(user: User) {
  creditUser.value = user
  credit.direction = 'increase'
  credit.amount = ''
  credit.reason = ''
  creditDialog.value = true
}

function openPassword(user: User) {
  passwordUser.value = user
  password.value = ''
  password.confirmation = ''
  passwordDialog.value = true
}

async function submitCredit() {
  if (!creditUser.value || creditSaving.value || !credit.amount || !credit.reason.trim()) return
  creditSaving.value = true
  try {
    const response = await http.post<User>(`/admin/users/${creditUser.value.id}/credits`, {
      direction: credit.direction,
      amount: credit.amount,
      reason: credit.reason.trim(),
    })
    const index = users.value.findIndex(user => user.id === response.data.id)
    if (index >= 0) users.value[index] = response.data
    creditDialog.value = false
    ElMessage.success(credit.direction === 'increase' ? '积分已增加' : '积分已扣除')
  } catch (cause) { ElMessage.error(errorMessage(cause)) }
  finally { creditSaving.value = false }
}

async function submitPassword() {
  if (!passwordUser.value || passwordSaving.value) return
  if (password.value.length < 8) {
    ElMessage.error('密码至少 8 位')
    return
  }
  if (password.value !== password.confirmation) {
    ElMessage.error('两次输入的密码不一致')
    return
  }
  passwordSaving.value = true
  try {
    await http.post(`/admin/users/${passwordUser.value.id}/password`, { password: password.value })
    passwordDialog.value = false
    ElMessage.success('密码已修改')
  } catch (cause) { ElMessage.error(errorMessage(cause)) }
  finally { passwordSaving.value = false }
}

onMounted(load)
</script>

<template>
  <section>
    <PageHeader eyebrow="管理" title="用户管理">
      <el-button :icon="Refresh" class="icon-button" :loading="loading" aria-label="刷新用户" @click="load" />
    </PageHeader>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
    <AppTable v-model:page="page" v-model:page-size="pageSize" :data="users" :total="total" :loading="loading" empty-text="暂无用户" @change="load">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="email" label="邮箱" min-width="230" />
      <el-table-column label="身份" width="110"><template #default="{ row }">{{ row.is_admin ? '管理员' : '普通用户' }}</template></el-table-column>
      <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'danger'" effect="plain">{{ row.is_active ? '正常' : '已停用' }}</el-tag></template></el-table-column>
      <el-table-column label="可用积分" min-width="150"><template #default="{ row }"><span class="numeric">{{ row.account.available }}</span></template></el-table-column>
      <el-table-column label="冻结积分" min-width="150"><template #default="{ row }"><span class="numeric">{{ row.account.frozen }}</span></template></el-table-column>
      <el-table-column label="操作" width="110" fixed="right">
        <template #default="{ row }">
          <el-dropdown trigger="click">
            <el-tooltip content="操作">
              <el-button :icon="Operation" class="icon-button" :aria-label="`管理 ${row.email}`" />
            </el-tooltip>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="openCredit(row)">积分调整</el-dropdown-item>
                <el-dropdown-item @click="openPassword(row)">修改密码</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </el-table-column>
    </AppTable>
    <el-dialog v-model="creditDialog" title="积分调整" width="480px" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="用户"><el-input :model-value="creditUser?.email || ''" disabled /></el-form-item>
        <el-form-item label="调整方式" required><el-segmented v-model="credit.direction" :options="[{ label: '增加', value: 'increase' }, { label: '扣除', value: 'decrease' }]" /></el-form-item>
        <el-form-item label="积分数量" required><el-input v-model="credit.amount" inputmode="decimal" placeholder="最多四位小数" /></el-form-item>
        <el-form-item label="备注" required><el-input v-model="credit.reason" maxlength="240" placeholder="填写本次调整原因" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="creditDialog = false">取消</el-button>
        <el-button type="primary" :loading="creditSaving" @click="submitCredit">确认</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="passwordDialog" title="修改密码" width="480px" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="用户"><el-input :model-value="passwordUser?.email || ''" disabled /></el-form-item>
        <el-form-item label="新密码" required><el-input v-model="password.value" type="password" show-password autocomplete="new-password" placeholder="至少 8 位" /></el-form-item>
        <el-form-item label="确认密码" required><el-input v-model="password.confirmation" type="password" show-password autocomplete="new-password" placeholder="再次输入新密码" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialog = false">取消</el-button>
        <el-button type="primary" :loading="passwordSaving" @click="submitPassword">确认</el-button>
      </template>
    </el-dialog>
  </section>
</template>
