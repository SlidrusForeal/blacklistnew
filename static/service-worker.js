/* service-worker.js */

// Названия кешей и версии
const CACHE_VERSION = 'v2';
const STATIC_CACHE  = `static-cache-${CACHE_VERSION}`;
const RUNTIME_CACHE = `runtime-cache-${CACHE_VERSION}`;
const FONT_CACHE    = `font-cache-${CACHE_VERSION}`;
const OFFLINE_URL   = '/offline';

// Список для предзагрузки
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

// Максимальное число записей в RUNTIME_CACHE
const RUNTIME_MAX_ENTRIES = 50;

// Утилита: тримминг кеша
async function trimCache(cacheName, maxEntries) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  if (keys.length > maxEntries) {
    await cache.delete(keys[0]);
    await trimCache(cacheName, maxEntries);
  }
}

// Утилита: IndexedDB для очереди POST-запросов
function openDatabase() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('sw-db', 1);
    req.onupgradeneeded = e => {
      e.target.result.createObjectStore('post-requests', { autoIncrement: true });
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
  return tx.complete;
}

async function processQueue() {
  const db = await openDatabase();
  const tx = db.transaction('post-requests', 'readwrite');
  const store = tx.objectStore('post-requests');
  const allKeysReq = store.getAllKeys();
  const allReqsReq = store.getAll();
  await Promise.all([allKeysReq, allReqsReq]);
  const keys = allKeysReq.result;
  const requests = allReqsReq.result;
  for (let i = 0; i < requests.length; i++) {
    const entry = requests[i];
    const key   = keys[i];
    try {
      const response = await fetch(entry.url, {
        method: entry.method,
        headers: new Headers(entry.headers),
        body: JSON.stringify(entry.body)
      });
      if (response.ok) store.delete(key);
    } catch (err) {
      console.error('Replay failed', err);
    }
  }
  return tx.complete;
}

async function fetchAndCacheLatestData() {
  const url = '/api/latest-data';
  try {
    const response = await fetch(url);
    if (response.ok) {
      const cache = await caches.open(RUNTIME_CACHE);
      cache.put(url, response.clone());
    }
  } catch (err) {
    console.error('Periodic update failed', err);
  }
}

// Установка: предзагрузка
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

// Активация: очистка старых кешей и включение навигационного preload
self.addEventListener('activate', event => {
  const current = [STATIC_CACHE, RUNTIME_CACHE, FONT_CACHE];
  event.waitUntil(
    Promise.all([
      caches.keys().then(keys =>
        Promise.all(
          keys.map(key => {
            if (!current.includes(key)) return caches.delete(key);
          })
        )
      ),
      self.registration.navigationPreload.enable()
    ]).then(() => self.clients.claim())
  );
});

// Обработка запросов
self.addEventListener('fetch', event => {
  const { request } = event;

  // ——————————————————————————————————————————————
  // Исключаем админ-панель из оффлайн-подмены
  if (request.mode === 'navigate') {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/admin')) {
      return event.respondWith(fetch(request));
    }
  }
  // ——————————————————————————————————————————————

  // 1) Навигация → network-first + оффлайн
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

  // 2) POST-запросы → пробуем сеть, на ошибку ставим в очередь
  if (request.method === 'POST') {
    event.respondWith(
      fetch(request.clone())
        .catch(() => saveRequestToQueue(request).then(() =>
          new Response(JSON.stringify({ queued: true }), { headers:{ 'Content-Type':'application/json' }})
        ))
    );
    return;
  }

  // 3) API-запросы → network-first с таймаутом
  if (request.url.includes('/api/')) {
    event.respondWith((async () => {
      const timeout = new Promise((_, rej) => setTimeout(rej, 3000));
      const net = fetch(request).then(resp => {
        if (resp.ok) {
          const copy = resp.clone();
          caches.open(RUNTIME_CACHE).then(cache => cache.put(request, copy));
          return resp;
        }
        throw new Error();
      });
      try {
        return await Promise.race([net, timeout]);
      } catch {
        return caches.match(request);
      }
    })());
    return;
  }

  // 4) Шрифты (Google Fonts)
  if (request.url.includes('fonts.googleapis.com') || request.url.includes('fonts.gstatic.com')) {
    event.respondWith(
      caches.open(FONT_CACHE).then(cache =>
        cache.match(request).then(resp =>
          resp || fetch(request).then(net => { cache.put(request, net.clone()); return net; })
        )
      )
    );
    return;
  }

  // 6) Остальная статика → stale-while-revalidate
  if (request.method === 'GET' && request.url.startsWith(self.location.origin)) {
    event.respondWith((async () => {
      const cached = await caches.match(request);
      const net = fetch(request).then(resp => {
        if (resp.ok) {
          const copy = resp.clone();
          caches.open(RUNTIME_CACHE).then(cache => {
            cache.put(request, copy);
            trimCache(RUNTIME_CACHE, RUNTIME_MAX_ENTRIES);
          });
        }
        return resp;
      }).catch(() => {});
      return cached || net;
    })());
    return;
  }

  // Прочие запросы — просто сеть
});

// Background Sync
self.addEventListener('sync', event => {
  if (event.tag === 'sync-queue') event.waitUntil(processQueue());
});

// Periodic Sync
self.addEventListener('periodicsync', event => {
  if (event.tag === 'periodic-update') event.waitUntil(fetchAndCacheLatestData());
});

// Push-уведомления
self.addEventListener('push', event => {
  let data = { title: 'Новое уведомление', body: 'Откройте приложение' };
  try { data = event.data.json(); } catch{}
  const options = {
    body: data.body,
    icon: '/static/icons/android-chrome-192x192.png',
    data: { url: data.url }
  };
  event.waitUntil(self.registration.showNotification(data.title, options));
});

// Клик по уведомлению
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = event.notification.data.url;
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then(windows => {
      for (const w of windows) if (w.url === url && 'focus' in w) return w.focus();
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});

// Сообщения от клиента
self.addEventListener('message', event => {
  if (event.data === 'CLEAR_CACHE') caches.keys().then(keys => keys.forEach(key => caches.delete(key)));
});
