/**
 * Minimal service worker — satisfies “fetch handler” for installability while
 * delegating everything to the network (no stale admin JSON/API cache).
 */
self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  event.respondWith(fetch(event.request));
});
