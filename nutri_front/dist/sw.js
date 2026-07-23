// 接口数据保持在线优先；仅缓存静态资源，缩短后续刷新时的首屏等待。
const STATIC_CACHE = 'nutri-static-v2'

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (event) => event.waitUntil(
  caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== STATIC_CACHE).map((key) => caches.delete(key))))
    .then(() => self.clients.claim())
))

self.addEventListener('fetch', (event) => {
  const request = event.request
  const url = new URL(request.url)
  const isStaticAsset = url.origin === self.location.origin
    && ['script', 'style', 'font', 'image'].includes(request.destination)
  if (!isStaticAsset) return

  event.respondWith(caches.open(STATIC_CACHE).then(async (cache) => {
    const cached = await cache.match(request)
    if (cached) return cached
    const response = await fetch(request)
    if (response.ok) cache.put(request, response.clone())
    return response
  }))
})
