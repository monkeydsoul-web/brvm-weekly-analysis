// Le worker d'alertes prix ne sert plus. Cette version se retire toute seule.
self.addEventListener('install', function (event) {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (cles) {
      return Promise.all(cles.filter(function (nom) {
        return nom.indexOf('brvm-sw-') === 0;
      }).map(function (nom) {
        return caches.delete(nom);
      }));
    }).then(function () {
      return self.registration.unregister();
    })
  );
});
