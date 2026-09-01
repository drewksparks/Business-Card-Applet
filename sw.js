/* Offline shell for the digital card.
   The whole point of this thing is that it works when you are standing in a
   convention hall on 1 bar of signal, so every asset is precached on install
   and served cache-first. Bump CACHE when any of them changes. */
const CACHE = 'dl-card-v3';

const ASSETS = [
  './',
  './index.html',
  './qr.js',
  './manifest.json',
  './drew-sparks.vcf',
  './drew-sparks.min.vcf',
  './assets/headshot.png',
  './assets/headshot-cutout.png',
  './assets/knox-BG.png',
  './assets/icon-192.png',
  './assets/icon-512.png',
  './assets/icon-maskable-512.png',
  './assets/icon-monochrome-512.png',
  './assets/icon-badge-96.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((c) => c.addAll(ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

/* Tapping the pinned notification should wake the card that is already open
   rather than stacking up new windows, so focus an existing client where there
   is one and ask it to show the code. Only fall back to openWindow if nothing
   is running. */
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || './index.html?view=qr';

  event.waitUntil((async () => {
    const clientList = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of clientList) {
      if ('focus' in client) {
        client.postMessage({ action: 'show-qr' });
        return client.focus();
      }
    }
    return self.clients.openWindow(target);
  })());
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  /* Google Fonts: network first, fall back to whatever was cached last time.
     Montserrat missing only costs us the fallback font stack, so this must
     never be allowed to fail the request. */
  if (url.origin !== self.location.origin) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  /* Same-origin: cache first, and refresh the entry in the background so a
     redeploy is picked up on the following visit. */
  event.respondWith(
    caches.match(req).then((hit) => {
      const net = fetch(req)
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
          }
          return res;
        })
        .catch(() => hit);
      return hit || net;
    })
  );
});
