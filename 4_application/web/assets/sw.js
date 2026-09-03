self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
    // This allows the app to load over the network
    event.respondWith(fetch(event.request));
});