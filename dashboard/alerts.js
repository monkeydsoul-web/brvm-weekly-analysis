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
  if (!threshold || isNaN(threshold)) { return; }
  if (!priceAlerts[ticker]) priceAlerts[ticker] = [];
  priceAlerts[ticker].push({ threshold, direction, active: true, created: Date.now() });
  saveAlertsLocal();
  updateAlertBadge();
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
    updateAlertBadge();
  }
}

function updateAlertBadge() {
  const manual = Object.values(priceAlerts).flat().filter(a => a.active).length;
  const smart  = (window._smartAlerts || []).filter(a => !a.seen).length;
  const total  = manual + smart;
  const badge  = document.getElementById('alert-badge');
  if (badge) {
    badge.textContent = total > 0 ? total : '';
    badge.style.background = total > 0 ? '#ef4444' : '';
    badge.style.color = total > 0 ? '#fff' : '';
    badge.style.animation = total > 0 ? 'pulse 1.5s infinite' : 'none';
  }
}

// ── Alertes intelligentes ───────────────────────────────────────────────────

function checkSmartAlerts() {
  const all = window.scores || (typeof scores !== 'undefined' ? scores : []);
  if (!all.length) return;

  window._smartAlerts = window._smartAlerts || [];
  const existingKeys = new Set(window._smartAlerts.map(a => a.key));
  const newAlerts = [];
  const today = new Date();

  all.forEach(s => {
    const ticker = s.ticker;
    const price  = s.price || 0;

    // ── Alerte ex-div dans 7 jours ────────────────────────────────────────
    if (s.ex_div_date && s.ex_div_date !== 'N/D') {
      const exDiv = _parseExDivDate(s.ex_div_date);
      if (exDiv) {
        const daysUntil = Math.round((exDiv - today) / 86400000);
        if (daysUntil >= 0 && daysUntil <= 7) {
          const key = `exdiv-${ticker}-${s.ex_div_date}`;
          if (!existingKeys.has(key)) {
            newAlerts.push({
              key, ticker, type: 'exdiv', seen: false,
              msg: `📅 ${ticker} — Ex-div dans ${daysUntil === 0 ? 'aujourd\'hui' : daysUntil + ' j'} (${s.ex_div_date}) · Div: ${(s.div_per_share||0).toLocaleString('fr-FR')} XOF`,
              color: 'var(--amber)',
            });
          }
        }
      }
    }

    // ── Alerte cours dépasse cible Graham ─────────────────────────────────
    if (price > 0 && s.eps && s.eps > 0) {
      // Cible Graham approx : √(22.5 × EPS × BVPA) — si BVPA dispo
      const bvpa = s.bvpa || 0;
      if (bvpa > 0) {
        const grahamTarget = Math.round(Math.sqrt(22.5 * s.eps * bvpa));
        if (price > grahamTarget * 1.05) { // 5% de marge
          const key = `graham-${ticker}-${Math.round(price/100)}`;
          if (!existingKeys.has(key)) {
            newAlerts.push({
              key, ticker, type: 'graham_over', seen: false,
              msg: `⚠️ ${ticker} (${price.toLocaleString('fr-FR')} XOF) dépasse la cible Graham (${grahamTarget.toLocaleString('fr-FR')} XOF) de +${Math.round((price/grahamTarget-1)*100)}%`,
              color: 'var(--red)',
            });
          }
        }
      }
    }

    // ── Alerte cours dépasse EPV ───────────────────────────────────────────
    if (price > 0 && s.eps && s.eps > 0 && s.pe_ref && s.pe_ref > 0) {
      const epv = Math.round((s.eps / 0.10)); // EPV = EPS normalisé / WACC
      if (price > epv * 1.10) { // 10% de marge
        const key = `epv-${ticker}-${Math.round(price/100)}`;
        if (!existingKeys.has(key)) {
          newAlerts.push({
            key, ticker, type: 'epv_over', seen: false,
            msg: `⚠️ ${ticker} (${price.toLocaleString('fr-FR')}) au-dessus EPV (${epv.toLocaleString('fr-FR')} XOF)`,
            color: 'var(--red)',
          });
        }
      }
    }
  });

  if (newAlerts.length) {
    window._smartAlerts.push(...newAlerts);
    updateAlertBadge();
  }
}

function _parseExDivDate(str) {
  if (!str || str === 'N/D') return null;
  // Format: '3-juin-25', '21-juil.-25', '23-avr.-26'
  const months = {
    'jan':0,'fév':1,'fevr':1,'mar':2,'avr':3,'mai':4,'juin':5,
    'juil':6,'aoû':7,'aout':7,'sep':8,'oct':9,'nov':10,'déc':11,'dec':11
  };
  try {
    const parts = str.replace(/\./g,'').toLowerCase().split('-');
    if (parts.length < 3) return null;
    const day   = parseInt(parts[0]);
    const mon   = Object.entries(months).find(([k]) => parts[1].startsWith(k))?.[1];
    let   year  = parseInt(parts[2]);
    if (year < 100) year += 2000;
    if (mon === undefined || isNaN(day) || isNaN(year)) return null;
    return new Date(year, mon, day);
  } catch { return null; }
}

function markSmartAlertSeen(key) {
  if (window._smartAlerts) {
    const a = window._smartAlerts.find(x => x.key === key);
    if (a) { a.seen = true; updateAlertBadge(); renderSmartAlertsPanel(); }
  }
}

function renderSmartAlertsPanel() {
  const panel = document.getElementById('smart-alerts-list');
  if (!panel) return;
  const alerts = (window._smartAlerts || []).filter(a => !a.seen);
  if (!alerts.length) {
    panel.innerHTML = '<p style="font-size:12px;color:var(--t2)">Aucune alerte intelligente active.</p>';
    return;
  }
  panel.innerHTML = alerts.map(a => `
    <div style="display:flex;justify-content:space-between;align-items:flex-start;padding:8px;background:var(--bg3);border-radius:6px;margin-bottom:6px;border-left:3px solid ${a.color}">
      <span style="font-size:12px;color:var(--t1);flex:1;line-height:1.5">${a.msg}</span>
      <button onclick="markSmartAlertSeen('${a.key}')"
        style="background:none;border:none;color:var(--t2);cursor:pointer;font-size:14px;padding:0 0 0 8px;flex-shrink:0">✕</button>
    </div>`).join('');
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
    panel.innerHTML = `<div style="text-align:center;padding:40px 20px">
      <div style="font-size:40px;margin-bottom:12px">🔔</div>
      <div style="font-size:15px;font-weight:600;color:var(--text);margin-bottom:8px">Aucune alerte configurée</div>
      <div style="font-size:13px;color:var(--t2);max-width:340px;margin:0 auto 20px;line-height:1.7">
        Créez une alerte pour être notifié quand une action atteint votre prix cible.<br>
        <span style="font-size:11px;color:var(--t3)">Ex : SIBC atteint 8 000 XOF → notification.</span>
      </div>
      <button onclick="showAddAlert()" style="background:var(--accent);color:#0d1117;font-weight:600;padding:10px 24px;border-radius:6px;border:none;cursor:pointer;font-size:13px">+ Créer ma première alerte</button>
    </div>`;
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
