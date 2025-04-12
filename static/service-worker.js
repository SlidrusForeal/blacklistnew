const CACHE_NAME = "sosmark-cache-v1";
const OFFLINE_URL = "/offline.html";

const STATIC_FILES = [
  "/",
  "/index.html",
  "/css/style.css",
  "/js/checker.js",
  "/js/fullist.js",
  "/pages/fullist.html",
  "/pages/contacts.html",
  "/offline.html",
  "/icons/favicon.ico"
];

// Установка service worker и кэширование статических файлов
self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_FILES))
  );
});

// Активация service worker и удаление старого кэша
self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.map(key => {
          if (key !== CACHE_NAME) return caches.delete(key);
        })
      )
    )
  );
});

// Перехват запросов
self.addEventListener("fetch", event => {
  event.respondWith(
    fetch(event.request)
      .then(response => {
        return response || caches.match(event.request);
      })
      .catch(() => caches.match(event.request).then(res => res || caches.match(OFFLINE_URL)))
  );
});
