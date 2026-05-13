// BRVM Dashboard — Service Worker v1
const CACHE = 'brvm-sw-v1';

self.addEventListener('install', e => {
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(clients.claim());
});

// Réception d'un message depuis la page (price check)
self.addEventListener('message', e => {
  if (e.data && e.data.type === 'CHECK_ALERTS') {
    checkPriceAlerts(e.data.alerts, e.data.prices);
  }
  if (e.data && e.data.type === 'SCHEDULE_CHECK') {
    schedulePeriodicCheck(e.data.intervalMs || 300000);
  }
});

let _checkTimer = null;
function schedulePeriodicCheck(intervalMs) {
  if (_checkTimer) clearInterval(_checkTimer);
  _checkTimer = setInterval(() => fetchAndCheck(), intervalMs);
}

async function fetchAndCheck() {
  try {
    // Lire les alertes depuis IndexedDB-like via clients broadcast
    const allClients = await clients.matchAll({ type: 'window' });
    if (allClients.length === 0) {
      // Aucune page ouverte : on récupère les prix directement
      const res = await fetch('/api/live');
      const data = await res.json();
      const alerts = await getStoredAlerts();
      checkPriceAlerts(alerts, data.prices || {});
    } else {
      // Page ouverte : déléguer
      allClients.forEach(c => c.postMessage({ type: 'SW_TRIGGER_CHECK' }));
    }
  } catch (e) {}
}

async function getStoredAlerts() {
  // Les alertes sont dans localStorage de la page — on ne peut pas y accéder
  // depuis le SW. On les récupère via un endpoint dédié ou on les reçoit
  // via message. Retourne un tableau vide si pas de contexte.
  return [];
}

function checkPriceAlerts(alerts, prices) {
  if (!Array.isArray(alerts) || !alerts.length) return;
  alerts.forEach(alert => {
    const live = prices[alert.ticker];
    if (!live || !live.price) return;
    const price = live.price;
    let triggered = false;
    let body = '';

    if (alert.type === 'above' && price >= alert.target) {
      triggered = true;
      body = `${alert.ticker} atteint ${price.toLocaleString('fr-FR')} XOF ≥ cible ${alert.target.toLocaleString('fr-FR')} XOF`;
    } else if (alert.type === 'below' && price <= alert.target) {
      triggered = true;
      body = `${alert.ticker} tombe à ${price.toLocaleString('fr-FR')} XOF ≤ seuil ${alert.target.toLocaleString('fr-FR')} XOF`;
    }

    if (triggered) {
      self.registration.showNotification('📈 BRVM Alerte Prix', {
        body,
        icon: '/favicon.ico',
        badge: '/favicon.ico',
        tag: `brvm-alert-${alert.ticker}`,
        renotify: true,
        data: { ticker: alert.ticker, url: '/' },
        actions: [
          { action: 'open', title: '→ Voir la fiche' },
          { action: 'dismiss', title: 'Ignorer' }
        ]
      });
    }
  });
}

// Clic sur la notification
self.addEventListener('notificationclick', e => {
  e.notification.close();
  if (e.action === 'dismiss') return;
  const ticker = e.notification.data?.ticker || '';
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      if (list.length > 0) {
        list[0].focus();
        list[0].postMessage({ type: 'OPEN_TICKER', ticker });
      } else {
        clients.openWindow('/');
      }
    })
  );
});
