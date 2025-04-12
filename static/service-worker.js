const CACHE_NAME = "sosmark-cache-v1";
const OFFLINE_URL = "/offline";

// List the static assets to cache. Adjust as needed.
const STATIC_FILES = [
  "/",                                       // The home route (Flask renders the index page)
  "/offline",                                // The offline route (serves the offline page)
  "/static/css/style.css",                   // Main stylesheet
  "/static/manifest.json",                   // Manifest file for PWA
  "/static/icons/favicon.ico"                // Favicon
  // Add more static assets as needed, e.g. images or additional CSS/JS if used.
];

// Installation: Cache static assets.
self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(STATIC_FILES);
    })
  );
});

// Activation: Delete outdated caches.
self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.map(key => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      )
    )
  );
});

// Fetching: Serve requests from network; fall back to cache, then offline page.
self.addEventListener("fetch", event => {
  event.respondWith(
    fetch(event.request)
      .then(response => {
        return response || caches.match(event.request);
      })
      .catch(() => caches.match(event.request).then(res => res || caches.match(OFFLINE_URL)))
  );
});
