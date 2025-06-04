const CACHE_VERSION = 'v2';
const STATIC_CACHE  = `static-cache-${CACHE_VERSION}`;
const RUNTIME_CACHE = `runtime-cache-${CACHE_VERSION}`;
const FONT_CACHE    = `font-cache-${CACHE_VERSION}`;
const OFFLINE_URL   = '/offline';

const PRECACHE_URLS = [
  '/', OFFLINE_URL,
  '/static/css/style.css',
  '/static/js/ave-effects.js',
  '/static/js/filter-list.js',
  '/static/js/random_video.js',
  '/static/js/sw-register.js',
  '/static/manifest.json',
  '/static/icons/favicon.ico'
];

const RUNTIME_MAX_ENTRIES = 50;

async function trimCache(cacheName, maxEntries) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  if (keys.length > maxEntries) {
    await cache.delete(keys[0]);
    await trimCache(cacheName, maxEntries);
  }
}

function openDatabase() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('sw-db', 1);
    req.onupgradeneeded = e => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains('post-requests')) {
        db.createObjectStore('post-requests', { autoIncrement: true });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror   = () => reject(req.error);
  });
}

async function saveRequestToQueue(request) {
  const db = await openDatabase();
  const tx = db.transaction('post-requests', 'readwrite');
  const store = tx.objectStore('post-requests');

  let body;
  try {
    body = await request.clone().json();
  } catch {
    body = await request.clone().text();
  }

  store.put({
    url: request.url,
    method: request.method,
    headers: [...request.headers],
    body
  });

  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function processQueue() {
  const db = await openDatabase();
  const tx = db.transaction('post-requests', 'readwrite');
  const store = tx.objectStore('post-requests');

  const requests = await new Promise((resolve, reject) => {
    const getAll = store.getAll();
    getAll.onsuccess = () => resolve(getAll.result.map((req, i) => [i + 1, req])); // keys start from 1
    getAll.onerror = () => reject(getAll.error);
  });

  for (const [key, entry] of requests) {
    try {
      const response = await fetch(entry.url, {
        method: entry.method,
        headers: new Headers(entry.headers),
        body: typeof entry.body === 'string' ? entry.body : JSON.stringify(entry.body),
        mode: 'no-cors' // для Cloudflare
      });
      if (response.ok || response.type === 'opaque') {
        store.delete(key);
      }
    } catch (err) {
      console.warn('Replay failed', err);
    }
  }

  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  const current = [STATIC_CACHE, RUNTIME_CACHE, FONT_CACHE];
  event.waitUntil(
    Promise.all([
      caches.keys().then(keys =>
        Promise.all(keys.map(key => {
          if (!current.includes(key)) return caches.delete(key);
        }))
      ),
      self.registration.navigationPreload.enable()
    ]).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Исключаем Cloudflare Insights
  if (url.hostname.includes('cloudflareinsights.com')) return;

  // Исключаем админку
  if (request.mode === 'navigate' && url.pathname.startsWith('/admin')) {
    return event.respondWith(fetch(request));
  }

  // Навигация
  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const preload = await event.preloadResponse;
        if (preload) return preload;
        const net = await fetch(request);
        if (net.ok) return net;
        throw new Error();
      } catch {
        return caches.match(OFFLINE_URL);
      }
    })());
    return;
  }

  // POST → если ошибка, ставим в очередь
  if (request.method === 'POST') {
    event.respondWith(
      fetch(request.clone())
        .catch(() =>
          saveRequestToQueue(request).then(() =>
            new Response(JSON.stringify({ queued: true }), {
              headers: { 'Content-Type': 'application/json' }
            })
          )
        )
    );
    return;
  }

  // API → network-first
  if (request.url.includes('/api/')) {
    event.respondWith((async () => {
      try {
        const resp = await Promise.race([
          fetch(request),
          new Promise((_, reject) => setTimeout(() => reject(new Error()), 3000))
        ]);
        if (resp.ok) {
          const copy = resp.clone();
          caches.open(RUNTIME_CACHE).then(cache => cache.put(request, copy));
          return resp;
        }
        throw new Error();
      } catch {
        return caches.match(request);
      }
    })());
    return;
  }

  // Google Fonts → cache-first
  if (request.url.includes('fonts.googleapis.com') || request.url.includes('fonts.gstatic.com')) {
    event.respondWith(
      caches.match(request).then(cached => {
        return cached || fetch(request).then(resp => {
          const copy = resp.clone();
          caches.open(FONT_CACHE).then(cache => {
            cache.put(request, copy);
            trimCache(FONT_CACHE, 10);
          });
          return resp;
        });
      })
    );
    return;
  }

  // Остальное → cache-first
  event.respondWith(
    caches.match(request).then(cached => {
      return cached || fetch(request).then(resp => {
        const copy = resp.clone();
        caches.open(RUNTIME_CACHE).then(cache => {
          cache.put(request, copy);
          trimCache(RUNTIME_CACHE, RUNTIME_MAX_ENTRIES);
        });
        return resp;
      });
    })
  );
});

// Фоновая синхронизация очереди при выходе в онлайн
self.addEventListener('sync', event => {
  if (event.tag === 'post-queue-sync') {
    event.waitUntil(processQueue());
  }
});

// Сразу обработать очередь при старте
self.addEventListener('message', event => {
  if (event.data === 'syncPosts') {
    processQueue();
  }
});
