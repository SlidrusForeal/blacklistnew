/* service-worker.js */

// Cache names and versions
const CACHE_VERSION = 'v3';
const STATIC_CACHE = `static-cache-${CACHE_VERSION}`;
const RUNTIME_CACHE = `runtime-cache-${CACHE_VERSION}`;
const FONT_CACHE = `font-cache-${CACHE_VERSION}`;
const IMAGE_CACHE = `image-cache-${CACHE_VERSION}`;
const API_CACHE = `api-cache-${CACHE_VERSION}`;
const OFFLINE_URL = '/offline';

// Resources to precache
const PRECACHE_URLS = [
  '/',
  OFFLINE_URL,
  '/static/css/style.css',
  '/static/css/theme.css',
  '/static/js/ave-effects.js',
  '/static/js/filter-list.js',
  '/static/js/random_video.js',
  '/static/js/sw-register.js',
  '/static/manifest.json',
  '/static/icons/favicon.ico',
  '/static/icons/android-chrome-192x192.png',
  '/static/icons/icon-512x512.png'
];

// Cache limits
const CACHE_LIMITS = {
  [RUNTIME_CACHE]: 50,
  [IMAGE_CACHE]: 30,
  [API_CACHE]: 20,
  [FONT_CACHE]: 10
};

// Cache expiration times (in milliseconds)
const CACHE_EXPIRATION = {
  [API_CACHE]: 5 * 60 * 1000, // 5 minutes
  [RUNTIME_CACHE]: 24 * 60 * 60 * 1000, // 24 hours
  [IMAGE_CACHE]: 7 * 24 * 60 * 60 * 1000 // 7 days
};

// Utility: Cache trimming with expiration
async function trimCache(cacheName, maxEntries) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  
  // Remove expired entries
  const now = Date.now();
  const expiration = CACHE_EXPIRATION[cacheName];
  if (expiration) {
    for (const request of keys) {
      const response = await cache.match(request);
      const timestamp = response.headers.get('sw-timestamp');
      if (timestamp && (now - Number(timestamp)) > expiration) {
        await cache.delete(request);
      }
    }
  }
  
  // Trim by max entries
  if (keys.length > maxEntries) {
    await cache.delete(keys[0]);
    await trimCache(cacheName, maxEntries);
  }
}

// Utility: Add timestamp to response
function addTimestamp(response) {
  const headers = new Headers(response.headers);
  headers.append('sw-timestamp', Date.now().toString());
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers
  });
}

// IndexedDB for POST request queue
function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('sw-db', 2);
    
    request.onupgradeneeded = e => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains('post-requests')) {
        db.createObjectStore('post-requests', { autoIncrement: true });
      }
      if (!db.objectStoreNames.contains('cache-metadata')) {
        db.createObjectStore('cache-metadata', { keyPath: 'url' });
      }
    };
    
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

// Save failed POST request to queue
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
  
  await store.put({
    url: request.url,
    method: request.method,
    headers: Array.from(request.headers.entries()),
    body,
    timestamp: Date.now()
  });
  
  return tx.complete;
}

// Process queued requests
async function processQueue() {
  const db = await openDatabase();
  const tx = db.transaction('post-requests', 'readwrite');
  const store = tx.objectStore('post-requests');
  
  const keys = await store.getAllKeys();
  const requests = await store.getAll();
  
  for (let i = 0; i < requests.length; i++) {
    const entry = requests[i];
    const key = keys[i];
    
    try {
      const response = await fetch(entry.url, {
        method: entry.method,
        headers: new Headers(entry.headers),
        body: JSON.stringify(entry.body)
      });
      
      if (response.ok) {
        await store.delete(key);
      }
    } catch (err) {
      console.error('Failed to replay request:', err);
      // Only keep requests for 24 hours
      if (Date.now() - entry.timestamp > 24 * 60 * 60 * 1000) {
        await store.delete(key);
      }
    }
  }
  
  return tx.complete;
}

// Fetch and cache latest data
async function fetchAndCacheLatestData() {
  const urls = ['/api/latest-data', '/api/stats'];
  
  for (const url of urls) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        const cache = await caches.open(API_CACHE);
        await cache.put(url, addTimestamp(response.clone()));
      }
    } catch (err) {
      console.error('Failed to update cache:', err);
    }
  }
}

// Installation: precache static assets
self.addEventListener('install', event => {
  event.waitUntil(
    Promise.all([
      caches.open(STATIC_CACHE)
        .then(cache => cache.addAll(PRECACHE_URLS)),
      self.skipWaiting()
    ])
  );
});

// Activation: clean old caches
self.addEventListener('activate', event => {
  const currentCaches = [
    STATIC_CACHE,
    RUNTIME_CACHE,
    FONT_CACHE,
    IMAGE_CACHE,
    API_CACHE
  ];
  
  event.waitUntil(
    Promise.all([
      // Clean old caches
      caches.keys().then(keys =>
        Promise.all(
          keys.map(key => {
            if (!currentCaches.includes(key)) {
              return caches.delete(key);
            }
          })
        )
      ),
      // Enable navigation preload
      self.registration.navigationPreload?.enable(),
      // Claim clients
      self.clients.claim()
    ])
  );
});

// Request handling
self.addEventListener('fetch', event => {
  const { request } = event;
  
  // Exclude admin panel from offline handling
  if (request.mode === 'navigate') {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/admin')) {
      return event.respondWith(fetch(request));
    }
  }
  
  // 1. Navigation requests: Network-first with offline fallback
  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        // Try preloaded response
        const preloadResponse = await event.preloadResponse;
        if (preloadResponse) return preloadResponse;
        
        // Try network
        const networkResponse = await fetch(request);
        if (networkResponse.ok) return networkResponse;
        
        throw new Error('Network response was not ok');
      } catch {
        // Fallback to offline page
        const cache = await caches.match(OFFLINE_URL);
        return cache || new Response('Offline page not found', {
          status: 503,
          statusText: 'Service Unavailable'
        });
      }
    })());
    return;
  }
  
  // 2. POST requests: Try network, queue on failure
  if (request.method === 'POST') {
    event.respondWith(
      fetch(request.clone())
        .catch(() => 
          saveRequestToQueue(request)
            .then(() => new Response(
              JSON.stringify({ queued: true, timestamp: Date.now() }),
              { 
                headers: {
                  'Content-Type': 'application/json',
                  'Cache-Control': 'no-store'
                }
              }
            ))
        )
    );
    return;
  }
  
  // 3. API requests: Network-first with timeout
  if (request.url.includes('/api/')) {
    event.respondWith((async () => {
      const cache = await caches.open(API_CACHE);
      
      try {
        // Try network with timeout
        const networkResponse = await Promise.race([
          fetch(request),
          new Promise((_, reject) => 
            setTimeout(() => reject(new Error('Network timeout')), 3000)
          )
        ]);
        
        if (networkResponse.ok) {
          await cache.put(request, addTimestamp(networkResponse.clone()));
          return networkResponse;
        }
        
        throw new Error('Network response was not ok');
      } catch {
        // Fallback to cache
        const cachedResponse = await cache.match(request);
        if (cachedResponse) {
          // Check expiration
          const timestamp = cachedResponse.headers.get('sw-timestamp');
          if (timestamp && (Date.now() - Number(timestamp)) <= CACHE_EXPIRATION[API_CACHE]) {
            return cachedResponse;
          }
        }
        
        // Return stale data with warning
        if (cachedResponse) {
          const headers = new Headers(cachedResponse.headers);
          headers.append('X-Cache-Warning', 'Data may be stale');
          return new Response(cachedResponse.body, {
            status: cachedResponse.status,
            statusText: 'Stale data',
            headers
          });
        }
        
        return new Response(
          JSON.stringify({ error: 'Failed to fetch data' }),
          { 
            status: 503,
            headers: { 'Content-Type': 'application/json' }
          }
        );
      }
    })());
    return;
  }
  
  // 4. Font requests: Cache-first
  if (request.url.includes('fonts.googleapis.com') || request.url.includes('fonts.gstatic.com')) {
    event.respondWith(
      caches.open(FONT_CACHE).then(cache =>
        cache.match(request).then(response =>
          response || fetch(request).then(networkResponse => {
            cache.put(request, networkResponse.clone());
            trimCache(FONT_CACHE, CACHE_LIMITS[FONT_CACHE]);
            return networkResponse;
          })
        )
      )
    );
    return;
  }
  
  // 5. Image requests: Cache-first with background update
  if (request.destination === 'image') {
    event.respondWith(
      caches.open(IMAGE_CACHE).then(async cache => {
        const cachedResponse = await cache.match(request);
        
        // Background fetch for cache update
        if (cachedResponse) {
          fetch(request).then(networkResponse => {
            if (networkResponse.ok) {
              cache.put(request, addTimestamp(networkResponse));
              trimCache(IMAGE_CACHE, CACHE_LIMITS[IMAGE_CACHE]);
            }
          }).catch(() => {});
        }
        
        return cachedResponse || fetch(request).then(networkResponse => {
          if (networkResponse.ok) {
            cache.put(request, addTimestamp(networkResponse.clone()));
            trimCache(IMAGE_CACHE, CACHE_LIMITS[IMAGE_CACHE]);
          }
          return networkResponse;
        });
      })
    );
    return;
  }
  
  // 6. Static assets: Stale-while-revalidate
  if (request.method === 'GET' && request.url.startsWith(self.location.origin)) {
    event.respondWith((async () => {
      const cache = await caches.open(RUNTIME_CACHE);
      const cachedResponse = await cache.match(request);
      
      const networkPromise = fetch(request).then(networkResponse => {
        if (networkResponse.ok) {
          cache.put(request, addTimestamp(networkResponse.clone()));
          trimCache(RUNTIME_CACHE, CACHE_LIMITS[RUNTIME_CACHE]);
        }
        return networkResponse;
      }).catch(() => null);
      
      return cachedResponse || networkPromise;
    })());
    return;
  }
  
  // 7. Other requests: Network-only
  event.respondWith(fetch(request));
});

// Background sync
self.addEventListener('sync', event => {
  if (event.tag === 'sync-queue') {
    event.waitUntil(processQueue());
  }
});

// Periodic sync
self.addEventListener('periodicsync', event => {
  if (event.tag === 'periodic-update') {
    event.waitUntil(fetchAndCacheLatestData());
  }
});

// Push notifications
self.addEventListener('push', event => {
  const defaultData = {
    title: 'Новое уведомление',
    body: 'Откройте приложение',
    icon: '/static/icons/android-chrome-192x192.png'
  };
  
  let data = defaultData;
  try {
    data = { ...defaultData, ...event.data.json() };
  } catch {}
  
  const options = {
    body: data.body,
    icon: data.icon,
    badge: '/static/icons/icon-192x192.png',
    vibrate: [100, 50, 100],
    data: { url: data.url },
    actions: [
      {
        action: 'open',
        title: 'Открыть'
      },
      {
        action: 'close',
        title: 'Закрыть'
      }
    ]
  };
  
  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// Notification click
self.addEventListener('notificationclick', event => {
  event.notification.close();
  
  if (event.action === 'close') return;
  
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then(windowClients => {
      const url = event.notification.data?.url || '/';
      
      // Focus existing window if open
      for (const client of windowClients) {
        if (client.url === url && 'focus' in client) {
          return client.focus();
        }
      }
      
      // Open new window
      if (clients.openWindow) {
        return clients.openWindow(url);
      }
    })
  );
}); 