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

self.addEventListener('push', (event) => {
  const show = async () => {
    let title = 'AI Factory';
    let body = '';
    let targetUrl = '/admin';
    try {
      if (event.data) {
        const j = await event.data.json();
        title = typeof j.title === 'string' && j.title ? j.title : title;
        body = typeof j.body === 'string' ? j.body : String(j.body || '');
        if (j.data && typeof j.data.url === 'string' && j.data.url) {
          targetUrl = j.data.url;
        }
      }
    } catch {
      try {
        body = event.data ? event.data.text() : '';
      } catch {
        body = '';
      }
    }
    await self.registration.showNotification(title, {
      body: body || 'Factory update',
      data: { url: targetUrl },
    });
  };
  event.waitUntil(show());
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/admin';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const c of clientList) {
        if (c.url && 'focus' in c) return c.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow(url);
    }),
  );
});
