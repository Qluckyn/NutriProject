// 在线优先：筛查、模型推理与共享历史必须使用服务器最新数据。
self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()))
self.addEventListener('fetch', () => {})

