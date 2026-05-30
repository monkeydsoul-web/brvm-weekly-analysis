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

function renderRankCards() {
  const sec     = document.getElementById('fSec')?.value || '';
  const srt     = document.getElementById('fSort')?.value || 'composite_adj';
  const verdict = document.getElementById('fVerdict')?.value || '';

  let d = [...(window.scores || scores || [])];
  if (sec)     d = d.filter(x => x.sector === sec);
  if (verdict) d = d.filter(x => (x.pdf_verdict || '').toLowerCase().includes(verdict.toLowerCase()));
  d.sort((a, b) => srt === 'pe_ref'
    ? (a[srt] || 999) - (b[srt] || 999)
    : (b[srt] || 0) - (a[srt] || 0));

  const cards = document.getElementById('rank-cards');
  if (!cards) return;
  cards.innerHTML = d.map((x, i) => {
      const v      = x.composite_adj || 0;
      const v10    = (v / 80 * 10).toFixed(1);
      const scoreC = v >= 60 ? 'var(--green)' : v >= 40 ? 'var(--amber)' : 'var(--red)';
      const chg    = x.change_pct || 0;
      const chgC   = chg > 0 ? 'var(--green)' : chg < 0 ? 'var(--red)' : 'var(--t2)';
      const chgStr = (chg > 0 ? '+' : '') + chg.toFixed(2) + '%';
      const verd      = x.pdf_verdict || '';
      const verdLabel = typeof fmtVerdict === 'function' ? fmtVerdict(verd) : verd || '—';
      const verdClr   = verd === 'POSITIF' ? 'var(--green)' : verd === 'NEGATIF' ? 'var(--red)' : 'var(--amber)';
      const priceStr  = x.price
        ? (typeof fmtXOF === 'function' ? fmtXOF(x.price) : x.price.toLocaleString('fr-FR') + ' XOF')
        : 'N/D';
      const divStr = (x.div_yield || 0) > 0 ? 'Div ' + x.div_yield.toFixed(1) + '%' : '—';
      const meta   = [x.name, x.sector, x.country].filter(Boolean).join(' · ');
      return `<div role="button" tabindex="0" aria-label="${x.ticker}${x.name ? ' — ' + x.name : ''}"
        onclick="_openStock('${x.ticker}')"
        onkeydown="if(event.key==='Enter')_openStock('${x.ticker}')"
        style="cursor:pointer;background:var(--bg-card);border:1px solid var(--border-1);border-radius:10px;padding:14px 16px;box-shadow:0 1px 4px rgba(0,0,0,.08)">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <div>
            <span style="color:var(--t2);font-size:11px">#${i + 1}</span>
            <strong style="font-size:15px;margin-left:6px">${x.ticker}</strong>
          </div>
          <span style="font-size:17px;font-weight:700;color:${scoreC}">${v10}<span style="font-size:10px;opacity:.6">/10</span></span>
        </div>
        <div style="font-size:11px;color:var(--t2);margin-bottom:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${meta}</div>
        <div style="border-top:1px solid var(--border-1);padding-top:8px;display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <span style="font-size:12px;font-weight:600;color:var(--t1)">${priceStr}</span>
          <span style="font-size:12px;font-weight:600;color:${chgC}">${chgStr}</span>
          <span style="font-size:12px;color:var(--amber)">${divStr}</span>
        </div>
        <div style="border-top:1px solid var(--border-1);padding-top:8px">
          <span style="font-size:12px;font-weight:600;color:${verdClr}">${verdLabel}</span>
        </div>
      </div>`;
    }).join('');
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
