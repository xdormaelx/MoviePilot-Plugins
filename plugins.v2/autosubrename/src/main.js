import { createApp } from 'vue'
import Page from './components/Page.vue'

createApp(Page, { api: { get: async () => ({}), put: async () => ({ success: true }) } }).mount('#app')
