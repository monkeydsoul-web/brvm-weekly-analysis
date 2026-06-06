// dashboard/signaux_v2.js — Fusion Signaux + Valorisation + Alertes (sprints 4a + 4b)

function injectEpurationSignaux() {
  if (document.getElementById('epuration-signaux')) return;
  var style = document.createElement('style');
  style.id = 'epuration-signaux';
  style.textContent = [
    // Valorisation — (i) retour, (ii) titre .ph, beginner-banner, (iii) bandeaux aide
    '#page-signals #page-valuation .brvm-back-btn { display:none !important; }',
    '#page-signals #page-valuation .ph { display:none !important; }',
    '#page-signals #page-valuation .beginner-banner { display:none !important; }',
    '#page-signals #valuation-tab-cibles details { display:none !important; }',
    '#page-signals #valuation-tab-perf > details { display:none !important; }',
    // Alertes — (iv) retour, (v) titre .ph premier enfant seulement (h2+p), (vi) bandeau aide
    '#page-signals #page-alerts .brvm-back-btn { display:none !important; }',
    '#page-signals #page-alerts .ph > div:first-child { display:none !important; }',
    '#page-signals #page-alerts > details { display:none !important; }',
  ].join('\n');
  document.head.appendChild(style);
}

function loadSignauxValoAlertes() {
  // 1. Remplir #page-signals via le loader existant (écrit dans #page-previsions-content)
  if (typeof renderPrevisionsPage !== 'undefined') {
    renderPrevisionsPage();
  }

  var pageSignals   = document.getElementById('page-signals');
  var pageValuation = document.getElementById('page-valuation');
  var pageAlerts    = document.getElementById('page-alerts');
  if (!pageSignals) return;

  // 2. Empilement #page-valuation (garde-fou anti-doublon)
  if (pageValuation && pageValuation.parentElement !== pageSignals) {
    pageValuation.classList.remove('page');
    pageValuation.style.display = 'block';
    pageValuation.style.padding = '0';

    var sepV = document.createElement('div');
    sepV.style.cssText = 'margin:28px 0 0;border-top:1px solid var(--border)';

    var hdrV = document.createElement('div');
    hdrV.style.cssText = 'padding:18px 0 10px;font-size:15px;font-weight:700;color:var(--text)';
    hdrV.textContent = '💰 Valorisation';

    pageSignals.appendChild(sepV);
    pageSignals.appendChild(hdrV);
    pageSignals.appendChild(pageValuation);
  }

  // 3. Empilement #page-alerts (garde-fou anti-doublon)
  if (pageAlerts && pageAlerts.parentElement !== pageSignals) {
    pageAlerts.classList.remove('page');
    pageAlerts.style.display = 'block';
    pageAlerts.style.padding = '0';

    var sepA = document.createElement('div');
    sepA.style.cssText = 'margin:28px 0 0;border-top:1px solid var(--border)';

    var hdrA = document.createElement('div');
    hdrA.style.cssText = 'padding:18px 0 10px;font-size:15px;font-weight:700;color:var(--text)';
    hdrA.textContent = '🔔 Alertes';

    pageSignals.appendChild(sepA);
    pageSignals.appendChild(hdrA);
    pageSignals.appendChild(pageAlerts);
  }

  // 4. Épuration chrome dupliqué (one-shot)
  injectEpurationSignaux();

  // 5. Loaders valorisation et alertes
  if (typeof renderTargets === 'function') renderTargets();
  if (typeof loadAlertsLocal !== 'undefined') {
    loadAlertsLocal();
    if (typeof renderAlertsPanel === 'function') renderAlertsPanel();
  }
}
