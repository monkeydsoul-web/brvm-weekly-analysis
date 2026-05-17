// ── Badges de rang et harmonisation dashboard — badges.js ─────────────────

// Historique des rangs (persisté en sessionStorage)
let _rankHistory = {};

function initRankHistory() {
  try {
    const saved = sessionStorage.getItem('brvm_rank_history');
    if (saved) _rankHistory = JSON.parse(saved);
  } catch(e) { _rankHistory = {}; }
}

function saveRankHistory() {
  try { sessionStorage.setItem('brvm_rank_history', JSON.stringify(_rankHistory)); }
  catch(e) {}
}

function updateRankHistory(ranking) {
  if (!Array.isArray(ranking)) return;
  ranking.forEach(x => {
    const t = x.ticker;
    if (!_rankHistory[t]) _rankHistory[t] = [];
    const last = _rankHistory[t][_rankHistory[t].length - 1];
    const rank = x.rank || 0;
    if (!last || last.rank !== rank) {
      _rankHistory[t].push({ rank, ts: Date.now() });
      if (_rankHistory[t].length > 20) _rankHistory[t].shift();
    }
  });
  saveRankHistory();
}

function getRankBadge(ticker, currentRank) {
  const hist = _rankHistory[ticker];
  if (!hist || hist.length < 2) return '';
  const prev = hist[hist.length - 2].rank;
  const delta = prev - currentRank;
  if (delta > 0) return `<span style="color:var(--green);font-size:10px;font-weight:700">▲${delta}</span>`;
  if (delta < 0) return `<span style="color:var(--red);font-size:10px;font-weight:700">▼${Math.abs(delta)}</span>`;
  return '';
}

// ── Badge rang dans la fiche société ─────────────────────────────────────
function renderLiveRankBadge(ticker) {
  const el = document.getElementById('live-rank-badge');
  if (!el) return;
  const entry = (window.scores || scores || []).find(x => x.ticker === ticker);
  if (!entry) return;
  const rank = entry.rank || '?';
  const total = (window.scores || scores || []).length;
  const badge = getRankBadge(ticker, rank);
  const scoreC = (entry.composite_adj||0) >= 60 ? 'var(--green)' : (entry.composite_adj||0) >= 40 ? 'var(--amber)' : 'var(--red)';
  const verdict = entry.pdf_verdict || '';
  const verdC = verdict.toLowerCase().includes('achet') || verdict === 'POSITIF' ? 'var(--green)'
    : verdict.toLowerCase().includes('vend') || verdict === 'NEGATIF' ? 'var(--red)'
    : 'var(--amber)';
  el.innerHTML = `
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:4px">
      <span style="font-size:11px;background:var(--bg3);padding:2px 8px;border-radius:4px">
        🏆 Rang <strong style="color:${scoreC}">#${rank}</strong>/${total} ${badge}
      </span>
      <span style="font-size:11px;background:var(--bg3);padding:2px 8px;border-radius:4px">
        Note <strong style="color:${scoreC}">${((entry.composite_adj||0)/80*10).toFixed(1)}/10</strong>
      </span>
      ${verdict ? `<span style="font-size:10px;padding:2px 8px;border-radius:4px;background:${verdC}22;color:${verdC};font-weight:700">${verdict}</span>` : ''}
      ${entry.eps ? `<span class="tt" data-tt="Bénéfice Net par Action · bénéfice annuel divisé par le nombre d'actions" style="font-size:10px;color:var(--t2);padding:2px 8px;border-radius:4px;background:var(--bg3);cursor:help">BNA <strong>${entry.eps.toLocaleString('fr-FR')} XOF</strong></span>` : ''}
      ${entry.bvpa ? `<span class="tt" data-tt="Book Value Per Action · valeur comptable par action — actif net / nombre d'actions" style="font-size:10px;color:var(--t2);padding:2px 8px;border-radius:4px;background:var(--bg3);cursor:help">BVPA <strong>${Math.round(entry.bvpa).toLocaleString('fr-FR')} XOF</strong></span>` : ''}
    </div>`;
}

// ── Harmonisation sidebar scores ──────────────────────────────────────────
function renderSidebarScores(ranking) {
  const sidebar = document.getElementById('sidebarList');
  if (!sidebar) return;
  const arr = ranking || window.scores || scores || [];
  const sorted = [...arr].sort((a,b) => (b.composite_adj||0) - (a.composite_adj||0));
  sidebar.innerHTML = sorted.map(x => {
    const v = x.composite_adj || 0;
    const c = v >= 60 ? 'var(--green)' : v >= 40 ? 'var(--amber)' : 'var(--red)';
    const badge = getRankBadge(x.ticker, x.rank || 0);
    return `<div class="si" onclick="showStock('${x.ticker}')">
      <span style="flex:1;cursor:pointer;font-size:12px">${x.ticker}</span>
      ${badge}
      <span style="color:${c};font-weight:700;font-size:12px;min-width:24px;text-align:right">${v.toFixed(0)}</span>
    </div>`;
  }).join('');
}

// ── KPI cards harmonisés pour fiche société ───────────────────────────────
function buildKpiCards(s) {
  const entry = (window.scores || scores || []).find(x => x.ticker === s.ticker) || s;
  const pe  = entry.pe_ref  || s.pe_ref;
  const pb  = entry.pb_ref  || s.pb_ref;
  const roe = entry.roe     || s.roe;
  const eps = entry.eps     || s.eps_est;
  const bvpa = entry.bvpa;
  const div = entry.div_yield || s.div_yield;
  const ca  = entry.pdf_ca_mfcfa;
  const rn  = entry.pdf_rn_mfcfa;

  const _fmtXOF = typeof fmtXOF === 'function' ? fmtXOF : (n => n != null ? Number(n).toLocaleString('fr-FR') + ' XOF' : '—');
  const kpis = [
    ['P/E', pe ? pe.toFixed(1)+'×' : '—', pe && pe < 15 ? 'var(--green)' : pe && pe < 25 ? 'var(--amber)' : 'var(--red)',
      'Price/Earnings (cours ÷ BNA). Seuil Graham : ≤ 15. Un P/E élevé = action chère par rapport aux bénéfices.'],
    ['P/B', pb ? pb.toFixed(1)+'×' : '—', pb && pb < 1.5 ? 'var(--green)' : pb && pb < 3 ? 'var(--amber)' : 'var(--red)',
      'Price/Book (cours ÷ valeur comptable). Seuil Graham : ≤ 1.5. P/B < 1 = l\'action se traite sous sa valeur comptable.'],
    ['ROE', roe ? roe.toFixed(1)+'%' : '—', roe && roe > 15 ? 'var(--green)' : roe && roe > 8 ? 'var(--amber)' : 'var(--red)',
      'Return On Equity = Résultat net ÷ Capitaux propres. Mesure la rentabilité. ≥ 15% = excellent, ≥ 8% = correct.'],
    ['Div%', div && div > 0 ? div.toFixed(1)+'%' : '—', div && div > 5 ? 'var(--green)' : div && div > 2 ? 'var(--amber)' : 'var(--t2)',
      'Rendement du dividende = dividende annuel ÷ cours actuel. Un rendement élevé peut signaler une sous-évaluation ou un risque de coupe.'],
    ['BNA', eps ? _fmtXOF(Math.round(eps)) : '—', 'var(--blue)',
      'Bénéfice Net par Action (EPS) — BNA issu des données BOC ou PDF. Utilisé pour calculer P/E, Graham et EPV.'],
    ['BVPA', bvpa ? _fmtXOF(Math.round(bvpa)) : '—', 'var(--blue)',
      'Book Value par Action (valeur comptable / nombre d\'actions). Utilisé pour P/B et la cible Graham = √(22.5 × BNA × BVPA).'],
    ['CA', ca ? (ca/1000).toFixed(0)+' Mrd' : '—', 'var(--t2)',
      'Chiffre d\'Affaires annuel en milliards de FCFA (source : rapports PDF analysés par IA).'],
    ['RN', rn ? (rn/1000).toFixed(0)+' Mrd' : '—', 'var(--t2)',
      'Résultat Net annuel en milliards de FCFA (source : rapports PDF analysés par IA).'],
  ];

  return `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px">
    ${kpis.map(([l,v,c,tip]) => `
      <div class="kpi tt" data-tt="${tip}">
        <div class="kl">${l}</div>
        <div class="kv" style="color:${c};font-size:14px">${v}</div>
      </div>`).join('')}
  </div>`;
}

// ── Auto-refresh harmonisé : met à jour scores + badges + sidebar ─────────
function onScoresRefreshed(newScores) {
  const prev = window.scores || scores || [];
  // Sauvegarder anciens rangs avant mise à jour
  if (prev.length > 0) updateRankHistory(prev);
  // Mettre à jour
  window.scores = newScores;
  if (typeof scores !== 'undefined') scores = newScores;
  // Rafraîchir composants
  if (typeof renderRankLive === 'function') renderRankLive();
  if (typeof renderSidebarScores === 'function') renderSidebarScores(newScores);
  if (typeof renderDash === 'function' && window._lastMarket) renderDash(window._lastMarket);
  // Badge rang fiche ouverte
  const openTicker = window._openTicker;
  if (openTicker) renderLiveRankBadge(openTicker);
}

// Init au chargement
document.addEventListener('DOMContentLoaded', initRankHistory);
