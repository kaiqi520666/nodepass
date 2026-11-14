export type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

const taskStatusLabels: Record<string, string> = {
  queued: '排队中',
  submitting: '提交中',
  pending: '等待上游',
  processing: '生成中',
  transferring: '转存中',
  succeeded: '已完成',
  failed: '失败',
  submission_unknown: '待核实',
}

const textStatusLabels: Record<string, string> = {
  processing: '调用中',
  succeeded: '已结算',
  failed: '失败',
  usage_unknown: '待核实',
  settled_manually: '人工已结算',
  closed_no_charge: '已关闭未扣费',
}

export function statusLabel(scope: 'task' | 'text', status: string) {
  return (scope === 'task' ? taskStatusLabels[status] : textStatusLabels[status]) || status
}

export function statusType(scope: 'task' | 'text', status: string): TagType {
  if (scope === 'task') {
    if (status === 'succeeded') return 'success'
    if (status === 'failed') return 'danger'
    if (status === 'submission_unknown') return 'warning'
    return 'info'
  }
  if (status === 'succeeded' || status === 'settled_manually') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'usage_unknown') return 'warning'
  return 'info'
}

export const adminActionLabels: Record<string, string> = {
  'task.requery': '重新查询',
  'task.retry_transfer': '重试转存',
  'task.release': '释放冻结',
  'text.mark_unknown': '标记待核实',
  'text.manual_charge': '人工扣费',
  'text.close_no_charge': '关闭不扣费',
  'user.credit_increase': '增加积分',
  'user.credit_decrease': '扣除积分',
}

export function actionLabel(action: string) {
  return adminActionLabels[action] || action
}

export function actionType(action: string): TagType {
  if (action.endsWith('.release') || action === 'text.manual_charge') return 'danger'
  if (action === 'text.mark_unknown' || action === 'user.credit_decrease') return 'warning'
  if (action === 'user.credit_increase') return 'success'
  return 'info'
}

const allowedActionLabels: Record<string, string> = {
  requery: '重新查询',
  retry_transfer: '重试转存',
  release: '释放',
  mark_unknown: '标记待核实',
  manual_charge: '人工扣费',
  close_no_charge: '关闭不扣费',
}

export function allowedActionLabel(action: string) {
  return allowedActionLabels[action] || action
}

const targetTypeLabels: Record<string, string> = {
  task: '生成任务',
  text_call: '文本调用',
  user: '用户',
}

export function targetTypeLabel(targetType: string) {
  return targetTypeLabels[targetType] || targetType
}

const resolutionLabels: Record<string, string> = {
  manual_requeued: '已重新处理',
  manual_retry_transfer: '已重试转存',
  manual_released: '已人工释放',
  manual_marked_unknown: '已标记待核实',
  manual_charged: '已人工扣费',
  manual_closed_no_charge: '已关闭未扣费',
}

export function resolutionLabel(resolution: string | null) {
  return resolution ? resolutionLabels[resolution] || resolution : '—'
}

export function moneyScaled(value: string) {
  const match = /^(\d+)(?:\.(\d{1,8}))?$/.exec(value.trim())
  if (!match) return null
  return BigInt(match[1]! + (match[2] ?? '').padEnd(8, '0'))
}

export function formatEpoch(seconds: number | null | undefined) {
  return seconds == null ? '—' : new Date(seconds * 1000).toLocaleString('zh-CN')
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN')
}

export function formatSeconds(seconds: number | null | undefined) {
  if (seconds == null) return '—'
  const total = Math.max(0, Math.floor(seconds))
  if (total < 60) return `${total} 秒`
  const minutes = Math.floor(total / 60)
  if (minutes < 60) return `${minutes} 分`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时 ${minutes % 60} 分`
  return `${Math.floor(hours / 24)} 天 ${hours % 24} 小时`
}
