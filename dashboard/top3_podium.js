// dashboard/top3_podium.js — D.17b : podium de constance Top 3 sur l'Accueil

function initTop3Podium() {
  var el = document.getElementById('top3-podium');
  if (!el) return;
  fetch('/api/top3-constance', { cache: 'no-store' })
    .then(r => r.json())
    .then(data => {
      if (!data || !data.days || !data.podium || !data.podium.length) return;
      _renderTop3Podium(el, data);
    })
    .catch(() => {});
}

const _T3P_MEDALS = ['🥇', '🥈', '🥉'];
const _T3P_MONTHS_FR = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];

function _fmtDateFR(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
  if (!m) return iso;
  const day = parseInt(m[3], 10);
  const month = _T3P_MONTHS_FR[parseInt(m[2], 10) - 1];
  return `${day} ${month} ${m[1]}`;
}

function _renderTop3Podium(el, data) {
  if (!document.getElementById('t3p-style')) {
    const style = document.createElement('style');
    style.id = 't3p-style';
    style.textContent =
      '.t3p-row:hover{background:var(--bg-elevated)}' +
      '@media(max-width:420px){#top3-podium .t3p-row{flex:1 1 100%}}';
    document.head.appendChild(style);
  }

  const dayLabel = data.days > 1 ? 'jours' : 'jour';
  const rows = data.podium.map((p, i) => `
    <div class="t3p-row" role="button" tabindex="0" aria-label="${p.ticker}${p.name ? ' — ' + p.name : ''}"
      onclick="_openStock('${p.ticker}')"
      onkeydown="if(event.key==='Enter')_openStock('${p.ticker}')"
      style="display:flex;align-items:center;gap:10px;padding:8px 12px;min-height:40px;cursor:pointer;border-radius:var(--radius-md);flex:1 1 150px">
      <span style="font-size:20px">${_T3P_MEDALS[i] || ''}</span>
      <div style="min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">
        <strong style="color:var(--text-1)">${p.ticker}</strong>
        <span style="color:var(--text-2);font-size:12px">${p.name || ''}</span>
      </div>
      <span style="margin-left:auto;font-size:11px;color:var(--gold);background:var(--gold-dim);padding:2px 8px;border-radius:20px;white-space:nowrap">${p.pct} % du temps</span>
    </div>`).join('');

  el.innerHTML = `
    <div style="background:var(--bg-surface);border:1px solid var(--border-1);border-radius:var(--radius-md);padding:14px 16px;margin-bottom:20px">
      <div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:8px">
        <span style="font-weight:700;color:var(--gold)">🏆 Top 3 constance</span>
        <span style="font-size:12px;color:var(--text-2)">dans le Top 3 depuis le ${_fmtDateFR(data.since)} · ${data.days} ${dayLabel}</span>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:8px">${rows}</div>
    </div>`;
  el.hidden = false;
}
