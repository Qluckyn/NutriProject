// 旧版 Service Worker 仅用于自我注销，避免缓存开发服务器的 Vue 模块。
self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (event) => event.waitUntil(
  self.registration.unregister().then(() => caches.keys()).then((keys) =>
    Promise.all(keys.filter((key) => key.startsWith('nutri-static-')).map((key) => caches.delete(key)))
  ).then(() => self.clients.claim())
))
