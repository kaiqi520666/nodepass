import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  ElAlert, ElButton, ElCheckbox, ElCheckboxGroup, ElDialog, ElDrawer, ElDropdown, ElDropdownItem, ElDropdownMenu,
  ElDatePicker, ElForm, ElFormItem, ElIcon, ElInput, ElInputNumber, ElLoading, ElOption, ElOptionGroup, ElPagination, ElPopover, ElResult,
  ElSegmented, ElSelect, ElSwitch, ElTable, ElTableColumn, ElTag, ElTimeline, ElTimelineItem, ElTooltip,
} from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import './assets/main.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(createPinia())
app.use(router)
const components = {
  ElAlert, ElButton, ElCheckbox, ElCheckboxGroup, ElDialog, ElDrawer, ElDropdown, ElDropdownItem, ElDropdownMenu,
  ElDatePicker, ElForm, ElFormItem, ElIcon, ElInput, ElInputNumber, ElOption, ElOptionGroup, ElPagination, ElPopover, ElResult,
  ElSegmented, ElSelect, ElSwitch, ElTable, ElTableColumn, ElTag, ElTimeline, ElTimelineItem, ElTooltip,
}
for (const [name, component] of Object.entries(components)) app.component(name, component)
app.directive('loading', ElLoading.directive)
app.mount('#app')
