// ── Classement Live — ranking.js ──────────────────────────────────────────

let _lastRankOrder = {};   // ticker -> rank précédent pour badges ↑↓
let _autoRefreshTimer = null;

function initRanking() {
  // Remplir filtre secteurs
  const sec = document.getElementById('fSec');
  if (sec && (window.scores || typeof scores !== "undefined")) {
    const secs = [...new Set(scores.map(x => x.sector).filter(Boolean))].sort();
    secs.forEach(s => {
      if (!sec.querySelector(`option[value="${s}"]`)) {
        const o = document.createElement('option');
        o.value = s; o.textContent = s;
        sec.appendChild(o);
      }
    });
  }

  // Filtre verdict PDF
  const fv = document.getElementById('fVerdict');
  if (fv) fv.onchange = renderRankLive;

  // Mémoriser rangs actuels
  if (window.scores || typeof scores !== "undefined") {
    (window.scores || scores || []).forEach((x, i) => { _lastRankOrder[x.ticker] = i + 1; });
  }
}

function renderRankLive() {
  const sec     = document.getElementById('fSec')?.value || '';
  const srt     = document.getElementById('fSort')?.value || 'composite_adj';
  const verdict = document.getElementById('fVerdict')?.value || '';

  let d = [...(window.scores || scores || [])];
  if (sec)     d = d.filter(x => x.sector === sec);
  if (verdict) d = d.filter(x => (x.pdf_verdict || '').toLowerCase().includes(verdict.toLowerCase()));
  d.sort((a, b) => srt === 'pe_ref'
    ? (a[srt] || 999) - (b[srt] || 999)
    : (b[srt] || 0) - (a[srt] || 0));

  const tbody = document.getElementById('rankBody');
  if (!tbody) return;

  tbody.innerHTML = d.map((x, i) => {
    const rank   = i + 1;
    const prev   = _lastRankOrder[x.ticker];
    const delta  = prev ? prev - rank : 0;
    const badge  = delta > 0
      ? `<span style="color:var(--green);font-size:9px">▲${delta}</span>`
      : delta < 0
      ? `<span style="color:var(--red);font-size:9px">▼${Math.abs(delta)}</span>`
      : `<span style="color:var(--t2);font-size:9px">—</span>`;

    const v    = x.composite_adj || 0;
    const v10  = (v / 80 * 10).toFixed(1);
    const chg  = x.change_pct || 0;
    const chgC = chg > 0 ? 'var(--green)' : chg < 0 ? 'var(--red)' : 'var(--t2)';
    const isFav = (window.favorites || []).includes(x.ticker);
    // Sparkline 30 derniers jours BOC
    const _ph = window._priceHistory || {};
    const _boc = (_ph[x.ticker]||[]).filter(p=>p.source==='boc').slice(-30);
    const _spk = _boc.length>=2 ? sparkline(_boc,80,26) : '<span style="color:var(--t3);font-size:9px">—</span>';

    // Verdict PDF badge
    const verd = x.pdf_verdict || '';
    const verdC = verd.toLowerCase().includes('achet') ? 'var(--green)'
      : verd.toLowerCase().includes('vend') ? 'var(--red)'
      : verd.toLowerCase().includes('neutr') ? 'var(--amber)'
      : 'var(--t2)';
    const verdBadge = verd
      ? `<span style="font-size:8px;color:${verdC};background:${verdC}22;padding:1px 4px;border-radius:3px;white-space:nowrap">${verd.substring(0,10)}</span>`
      : '';

    const pe  = x.pe_ref  ? x.pe_ref.toFixed(1)  + '×' : '—';
    const pb  = x.pb_ref  ? x.pb_ref.toFixed(1)  + '×' : '—';
    const roe = x.roe     ? x.roe.toFixed(1)      + '%' : '—';
    const div = x.div_yield && x.div_yield > 0 ? x.div_yield.toFixed(1) + '%' : '—';

    const scoreC = v >= 60 ? 'var(--green)' : v >= 40 ? 'var(--amber)' : 'var(--red)';
    const miniBarW = Math.round(v / 80 * 100);
    const miniBarC = v >= 60 ? 'var(--green)' : v >= 40 ? 'var(--amber)' : 'var(--red)';

    return `<tr onclick="_openStock('${x.ticker}')" style="cursor:pointer">
      <td style="color:var(--t2);white-space:nowrap">${rank} ${badge}</td>
      <td onclick="event.stopPropagation();toggleFav('${x.ticker}')">
        <span class="star ${isFav ? 'fav' : ''}">★</span></td>
      <td><strong>${x.ticker}</strong></td>
      <td style="color:var(--t2);max-width:110px;overflow:hidden;text-overflow:ellipsis;font-size:11px">${x.name || ''}</td>
      <td>${x.price ? (typeof fmtXOF==='function'?fmtXOF(x.price):x.price.toLocaleString('fr-FR')) : 'N/D'}</td>
      <td style="padding:2px 4px;vertical-align:middle">${_spk}</td>
      <td style="color:${chgC}">${chg ? chg.toFixed(1) + '%' : '—'}</td>
      <td style="color:var(--t2)">${pe}</td>
      <td style="color:var(--t2)">${pb}</td>
      <td style="color:var(--amber)">${div}</td>
      <td style="color:var(--green)">${roe}</td>
      <td>${verdBadge}</td>
      <td>
        <span style="font-weight:700;color:${scoreC}" data-tip="Score composite sur 8 modèles · /10">${v10}/10</span>
        <div style="height:3px;background:rgba(255,255,255,0.1);border-radius:2px;margin-top:2px;width:52px"><div style="height:100%;width:${miniBarW}%;background:${miniBarC};border-radius:2px;transition:width 0.3s"></div></div>
      </td>
      ${['score_graham','score_dcf','score_ddm','score_epv','score_buffett','score_rev_dcf','score_relatif','score_technique'].map(k => {
        const sv = x[k] || 0;
        const sc = sv >= 7 ? 'var(--green)' : sv >= 4 ? 'var(--amber)' : 'var(--red)';
        return `<td style="color:${sc};font-weight:600;font-size:11px">${sv.toFixed(0)}</td>`;
      }).join('')}
    </tr>`;
  }).join('');

  // Mettre à jour les rangs mémorisés
  d.forEach((x, i) => { _lastRankOrder[x.ticker] = i + 1; });

  // Timestamp dernier refresh
  const ts = document.getElementById('rankTimestamp');
  if (ts) ts.textContent = 'Mis à jour ' + new Date().toLocaleTimeString('fr-FR');
}

// ── Auto-refresh global toutes les 5min ───────────────────────────────────
function startAutoRefresh() {
  if (window._ecoMode) return; // Mode économie désactivé
  if (_autoRefreshTimer) clearInterval(_autoRefreshTimer);
  _autoRefreshTimer = setInterval(async () => {
    try {
      const res  = await fetch('/api/live-scores');
      const data = await res.json();
      const arr  = Array.isArray(data) ? data : (data.scores || data.ranking || []);
      if (arr.length > 0) {
        // Mettre à jour le cache de prix live depuis les scores frais
        const freshPrices = {};
        arr.forEach(s => { if (s.ticker && s.price) freshPrices[s.ticker] = { price: s.price, change_pct: s.change_pct }; });
        if (Object.keys(freshPrices).length > 0) window._livePrices = freshPrices;
        if (typeof onScoresRefreshed === 'function') {
          onScoresRefreshed(arr);
        } else {
          window.scores = arr; scores = arr;
          renderRankLive();
        }
        const dot = document.getElementById('liveDot');
        if (dot) { dot.style.background = 'var(--green)'; setTimeout(() => { dot.style.background = ''; }, 2000); }
        console.log('[AutoRefresh] scores mis a jour', new Date().toLocaleTimeString());
      }
    } catch(e) { console.warn('[AutoRefresh] erreur:', e); }
  }, 5 * 60 * 1000); // 5 minutes
  console.log('[AutoRefresh] démarré — interval 5min');
}
