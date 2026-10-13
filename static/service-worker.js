// V14: Cache only the app shell/static icons, NEVER weather or any API result.
// This prevents stale API data being replayed as if current when offline.
const CACHE_NAME = 'duong-den-truong-an-toan-v14-3-saved-home';
const STATIC_ASSETS = [
  '/',
  '/static/logo-web-icon.png',
  '/static/icon-192.png',
  '/static/icon-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME)
    .then(cache => cache.addAll(STATIC_ASSETS))
    .catch(() => undefined));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(name => name !== CACHE_NAME).map(name => caches.delete(name))
  )));
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  // ALWAYS ask the network for current weather, GPS-derived values, school/route APIs.
  // Never use cached API responses as a fallback.
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(event.request));
    return;
  }

  event.respondWith(fetch(event.request).then(response => {
    if (response.ok && (url.pathname === '/' || url.pathname.startsWith('/static/'))) {
      const copy = response.clone();
      caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy)).catch(() => undefined);
    }
    return response;
  }).catch(() => caches.match(event.request).then(cached => {
    if (cached) return cached;
    if (event.request.mode === 'navigate') return caches.match('/');
    return Response.error();
  })));
});
