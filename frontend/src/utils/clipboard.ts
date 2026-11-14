import { ref } from 'vue'
import { ElMessage } from 'element-plus'

export const copyAnnouncement = ref('')
let timer: ReturnType<typeof setTimeout> | undefined

function announce(message: string) {
  copyAnnouncement.value = message
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => { copyAnnouncement.value = '' }, 2000)
}

export async function copyText(text: string, success: string, failure: string) {
  try {
    await navigator.clipboard.writeText(text)
    announce(success)
    ElMessage.success(success)
    return true
  } catch {
    announce(failure)
    ElMessage.error(failure)
    return false
  }
}
