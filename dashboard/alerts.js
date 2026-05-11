// ── Alertes prix — alerts.js ──────────────────────────────────────────────

let priceAlerts = {};

function loadAlertsLocal() {
  try { priceAlerts = JSON.parse(localStorage.getItem('brvm_alerts') || '{}'); }
  catch { priceAlerts = {}; }
}

function saveAlertsLocal() {
  try { localStorage.setItem('brvm_alerts', JSON.stringify(priceAlerts)); }
  catch {}
}

function setAlert(ticker, threshold, direction) {
  threshold = parseFloat(threshold);
  if (!threshold || isNaN(threshold)) { showNotif('Prix invalide', 'red'); return; }
  if (!priceAlerts[ticker]) priceAlerts[ticker] = [];
  priceAlerts[ticker].push({ threshold, direction, active: true, created: Date.now() });
  saveAlertsLocal();
  updateAlertBadge();
  showNotif(`Alerte ${ticker} ${direction === 'above' ? '↑' : '↓'} ${threshold.toLocaleString('fr-FR')} XOF`, 'green');
}

function deleteAlertLocal(ticker, idx) {
  if (priceAlerts[ticker]) {
    priceAlerts[ticker].splice(idx, 1);
    if (!priceAlerts[ticker].length) delete priceAlerts[ticker];
    saveAlertsLocal();
    updateAlertBadge();
    renderAlertsPanel();
  }
}

function checkAlertsWithPrices(prices) {
  if (!prices) return;
  const triggered = [];
  Object.entries(priceAlerts).forEach(([ticker, alerts]) => {
    const p = prices[ticker];
    if (!p || !p.price) return;
    alerts.forEach(a => {
      if (!a.active) return;
      if (a.direction === 'above' && p.price >= a.threshold) {
        triggered.push({ ticker, price: p.price, threshold: a.threshold, dir: '↑ AU-DESSUS' });
        a.active = false;
      }
      if (a.direction === 'below' && p.price <= a.threshold) {
        triggered.push({ ticker, price: p.price, threshold: a.threshold, dir: '↓ EN-DESSOUS' });
        a.active = false;
      }
    });
  });
  if (triggered.length) {
    saveAlertsLocal();
    triggered.forEach(t => showNotif(
      `🔔 ${t.ticker} ${t.dir} de ${t.threshold.toLocaleString('fr-FR')} — Cours: ${t.price.toLocaleString('fr-FR')} XOF`,
      t.dir.includes('↑') ? 'green' : 'red'
    ));
    updateAlertBadge();
  }
}

function updateAlertBadge() {
  const n = Object.values(priceAlerts).flat().filter(a => a.active).length;
  const badge = document.getElementById('alert-badge');
  if (badge) badge.textContent = n > 0 ? n : '';
}

function showAlertModal(ticker) {
  const existing = document.getElementById('alert-modal');
  if (existing) existing.remove();

  const stock = (window.scores || scores || []).find(x => x.ticker === ticker);
  const price = stock?.price || 0;
  const priceStr = price ? price.toLocaleString('fr-FR') : '—';

  const modal = document.createElement('div');
  modal.id = 'alert-modal';
  modal.style = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:9999;background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:20px;width:320px;box-shadow:0 8px 32px rgba(0,0,0,.6)';
  modal.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
      <div style="font-weight:700;font-size:14px">🔔 Alerte — ${ticker}</div>
      <button onclick="this.closest('#alert-modal').remove()" style="background:none;border:none;color:var(--t2);font-size:16px;cursor:pointer">✕</button>
    </div>
    <div style="font-size:11px;color:var(--t2);margin-bottom:12px">Cours actuel : <strong style="color:var(--t1)">${priceStr} XOF</strong></div>
    <div style="margin-bottom:10px">
      <label style="font-size:11px;color:var(--t2);display:block;margin-bottom:4px">Prix seuil (XOF)</label>
      <input id="alert-price" type="number" value="${price||''}" placeholder="Ex: ${price||10000}"
        style="width:100%;padding:8px;background:var(--bg3);border:1px solid var(--border);border-radius:6px;color:var(--t1);font-size:13px;box-sizing:border-box"/>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px">
      <button onclick="setAlert('${ticker}',document.getElementById('alert-price').value,'above');this.closest('#alert-modal').remove()"
        style="padding:10px;background:rgba(74,222,128,0.15);border:1px solid var(--green);border-radius:8px;color:var(--green);cursor:pointer;font-size:12px;font-weight:700">
        ↑ Au-dessus</button>
      <button onclick="setAlert('${ticker}',document.getElementById('alert-price').value,'below');this.closest('#alert-modal').remove()"
        style="padding:10px;background:rgba(248,113,113,0.15);border:1px solid var(--red);border-radius:8px;color:var(--red);cursor:pointer;font-size:12px;font-weight:700">
        ↓ En-dessous</button>
    </div>
    ${(priceAlerts[ticker]||[]).length ? `
    <div style="border-top:1px solid var(--border);padding-top:10px;margin-top:4px">
      <div style="font-size:11px;color:var(--t2);margin-bottom:6px">Alertes actives :</div>
      ${(priceAlerts[ticker]||[]).map((a,i) => `
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:11px;padding:3px 0">
          <span style="color:${a.direction==='above'?'var(--green)':'var(--red)'}">${a.direction==='above'?'↑':'↓'} ${a.threshold.toLocaleString('fr-FR')} XOF ${a.active?'🟢':'⚫'}</span>
          <button onclick="deleteAlertLocal('${ticker}',${i});this.closest('#alert-modal').remove();showAlertModal('${ticker}')"
            style="background:none;border:none;color:var(--red);cursor:pointer;font-size:11px">✕</button>
        </div>`).join('')}
    </div>` : ''}`;
  document.body.appendChild(modal);
  setTimeout(() => document.getElementById('alert-price')?.focus(), 50);
}

function renderAlertsPanel() {
  const panel = document.getElementById('alertsList');
  if (!panel) return;
  const all = window.scores || scores || [];
  const entries = Object.entries(priceAlerts).filter(([,a]) => a.length > 0);
  if (!entries.length) {
    panel.innerHTML = '<p style="color:var(--t2);font-size:12px;padding:12px 0">Aucune alerte configurée.</p>';
    return;
  }
  panel.innerHTML = entries.map(([ticker, alerts]) => {
    const stock = all.find(x => x.ticker === ticker);
    const price = stock?.price || 0;
    return `<div style="background:var(--bg3);border-radius:8px;padding:10px 12px;margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <span style="font-weight:700;cursor:pointer" onclick="showStock('${ticker}')">${ticker}</span>
        <span style="font-size:11px;color:var(--t2)">${price ? price.toLocaleString('fr-FR')+' XOF' : '—'}</span>
      </div>
      ${alerts.map((a,i) => `
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:11px;padding:2px 0">
          <span style="color:${a.direction==='above'?'var(--green)':'var(--red)'};font-weight:600">
            ${a.direction==='above'?'↑':'↓'} ${a.threshold.toLocaleString('fr-FR')} XOF
            <span style="color:var(--t2);font-weight:400">${a.active?'• Active':'• Déclenchée'}</span>
          </span>
          <button onclick="deleteAlertLocal('${ticker}',${i})"
            style="background:none;border:none;color:var(--red);cursor:pointer;font-size:12px;padding:0 4px">✕</button>
        </div>`).join('')}
    </div>`;
  }).join('');
}
