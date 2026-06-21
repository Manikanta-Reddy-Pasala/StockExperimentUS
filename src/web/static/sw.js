// Service worker — fast shell + SWR for HTML pages + cache-first for static.
// Bump CACHE_VERSION on any UI change so old clients refetch.
const CACHE_VERSION = 'v29-2026-06-21-rebal-time';
const STATIC_CACHE = 'trading-pwa-static-' + CACHE_VERSION;
const PAGE_CACHE   = 'trading-pwa-pages-'  + CACHE_VERSION;
// Bump ?v= on every icon-affecting change. URL-keyed, so any old cached
// /static/icon.svg entry just sits there and never gets requested again
// because pages reference /static/icon.svg?v=N now.
const ICON_VERSION = '5';

const PRECACHE_URLS = [
  '/static/icon.svg?v=' + ICON_VERSION,
  '/static/icon-mono.svg?v=' + ICON_VERSION,
  '/static/icon-192.png?v=' + ICON_VERSION,
  '/static/icon-512.png?v=' + ICON_VERSION,
  '/static/apple-touch-icon.png?v=' + ICON_VERSION,
  '/static/css/custom.css',
];

// Top-level navigations to seed in page cache so first tab tap is instant.
const PRECACHE_PAGES = [
  '/dashboard', '/picks', '/portfolio', '/history', '/settings',
];

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const sc = await caches.open(STATIC_CACHE);
    await sc.addAll(PRECACHE_URLS);
    // Best-effort warm of page cache; ignore failures (e.g. 302 to /login).
    const pc = await caches.open(PAGE_CACHE);
    await Promise.all(PRECACHE_PAGES.map((p) =>
      fetch(p, { credentials: 'include' })
        .then((r) => r.ok && pc.put(p, r.clone()))
        .catch(() => {})
    ));
    await self.skipWaiting();
  })());
});

// Listen for SKIP_WAITING message from the page so a freshly-installed
// worker activates immediately (instead of waiting for all tabs to close).
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names
      .filter((n) => n.startsWith('trading-pwa-') &&
                     n !== STATIC_CACHE && n !== PAGE_CACHE)
      .map((n) => caches.delete(n)));
    await self.clients.claim();
  })());
});

// Routes that must always go to network (live data, do not cache).
function isApiOrLive(pathname) {
  return pathname.startsWith('/api/')
      || pathname.startsWith('/admin/')   // model trade-history etc.
      || pathname === '/health'
      || pathname === '/login'
      || pathname === '/logout'
      || pathname === '/sw.js'
      || pathname === '/manifest.json';
}

// Pages we will SWR-cache (HTML routes for the 5 tabs).
function isCacheablePage(pathname) {
  return pathname === '/' || PRECACHE_PAGES.includes(pathname);
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // 1. Static assets — cache-first.
  if (url.pathname.startsWith('/static/') || url.pathname === '/favicon.ico') {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok) caches.open(STATIC_CACHE).then((c) => c.put(req, res.clone()));
        return res;
      }))
    );
    return;
  }

  // 2. APIs / live endpoints — network-only, no cache (always live data).
  if (isApiOrLive(url.pathname)) {
    event.respondWith(fetch(req));
    return;
  }

  // 3. Cacheable page HTML — stale-while-revalidate.
  //    Phone sees cached page instantly; fresh copy fetched in background.
  if (isCacheablePage(url.pathname)) {
    event.respondWith((async () => {
      const cached = await caches.match(req);
      const fetchPromise = fetch(req).then((res) => {
        if (res.ok) caches.open(PAGE_CACHE).then((c) => c.put(req, res.clone()));
        return res;
      }).catch(() => cached);
      return cached || fetchPromise;
    })());
    return;
  }

  // 4. Everything else — network-first w/ offline fallback.
  event.respondWith(
    fetch(req).catch(() => caches.match(req).then((hit) => hit ||
      new Response('<h1>Offline</h1><p>No cached copy. Reconnect and retry.</p>',
                   { headers: { 'Content-Type': 'text/html' } })))
  );
});
