import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

createApp(App).mount('#app')

// 开发服务器与 PWA 静态缓存会让 Pad 继续使用过期的 Vue 源文件；主动清理旧 worker 和缓存。
if ('serviceWorker' in navigator) {
  window.addEventListener('load', async () => {
    const registrations = await navigator.serviceWorker.getRegistrations()
    await Promise.all(registrations.map((registration) => registration.unregister()))
    const keys = await caches.keys()
    await Promise.all(keys.filter((key) => key.startsWith('nutri-static-')).map((key) => caches.delete(key)))
  })
}
