{% load static %}
/* ==========================================================================
   BARKOL PWA SERVICE WORKER
   Версия: barkol-pwa-v1.0.0
   ========================================================================== */

const CACHE_NAME = 'barkol-pwa-v1.0.0';
const OFFLINE_URL = '/offline/';

// Критические статические ресурсы для офлайн-старта и мгновенного кэширования
const PRECACHE_ASSETS = [
    OFFLINE_URL,
    '{% static "admin_templates/img/logo.png" %}',
    '{% static "favicon.png" %}',
    '{% static "customers_app/css/mobile_app.css" %}',
    '{% static "manifest.json" %}'
];

// УСТАНОВКА (INSTALL): Кэширование базовой статики
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(PRECACHE_ASSETS);
        }).then(() => self.skipWaiting())
    );
});

// АКТИВАЦИЯ (ACTIVATE): Очистка старых версий кэша
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// ОБРАБОТКА СЕТЕВЫХ ЗАПРОСОВ (FETCH)
self.addEventListener('fetch', (event) => {
    const request = event.request;

    // Не перехватываем non-GET запросы (POST, PUT, DELETE) и обращения к админке/WebSocket
    if (request.method !== 'GET') {
        return;
    }

    const url = new URL(request.url);

    // 1. НАВИГАЦИОННЫЕ ЗАПРОСЫ (HTML страницы): Стратегия Network First -> Fallback Offline
    if (request.mode === 'navigate') {
        event.respondWith(
            fetch(request)
                .then((networkResponse) => {
                    return networkResponse;
                })
                .catch(async () => {
                    const cache = await caches.open(CACHE_NAME);
                    const cachedResponse = await cache.match(request);
                    if (cachedResponse) {
                        return cachedResponse;
                    }
                    return cache.match(OFFLINE_URL);
                })
        );
        return;
    }

    // 2. СТАТИЧЕСКИЕ РЕСУРСЫ (/static/): Стратегия Stale-While-Revalidate
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(request).then((cachedResponse) => {
                const fetchPromise = fetch(request).then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200) {
                        const responseClone = networkResponse.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(request, responseClone);
                        });
                    }
                    return networkResponse;
                }).catch(() => cachedResponse);

                return cachedResponse || fetchPromise;
            })
        );
        return;
    }

    // Остальные запросы — по умолчанию через сеть
    event.respondWith(
        fetch(request).catch(() => caches.match(request))
    );
});

// ОБРАБОТКА WEB PUSH УВЕДОМЛЕНИЙ
self.addEventListener('push', (event) => {
    let data = {
        title: 'Портал БАРКОЛ',
        body: 'Новое системное уведомление',
        url: '/',
        icon: '{% static "android/mipmap-xxhdpi/ic_launcher.png" %}',
        badge: '{% static "android/mipmap-mdpi/ic_launcher.png" %}'
    };

    if (event.data) {
        try {
            data = Object.assign(data, event.data.json());
        } catch (e) {
            data.body = event.data.text();
        }
    }

    const options = {
        body: data.body,
        icon: data.icon,
        badge: data.badge,
        data: { url: data.url },
        vibrate: [100, 50, 100],
        actions: data.actions || []
    };

    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

// КЛИК ПО УВЕДОМЛЕНИЮ
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const targetUrl = event.notification.data && event.notification.data.url ? event.notification.data.url : '/';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            for (let client of clientList) {
                if (client.url === targetUrl && 'focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});
