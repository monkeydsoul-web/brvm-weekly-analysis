// dashboard/signaux_v2.js — Fusion Signaux + Valorisation + Alertes (sprint 4a)

function loadSignauxValoAlertes() {
  // 1. Remplir #page-signals via le loader existant (écrit dans #page-previsions-content)
  if (typeof renderPrevisionsPage !== 'undefined') {
    renderPrevisionsPage();
  }

  var pageSignals  = document.getElementById('page-signals');
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

  // 4. Loaders valorisation et alertes
  if (typeof renderTargets === 'function') renderTargets();
  if (typeof loadAlertsLocal !== 'undefined') {
    loadAlertsLocal();
    if (typeof renderAlertsPanel === 'function') renderAlertsPanel();
  }
}
