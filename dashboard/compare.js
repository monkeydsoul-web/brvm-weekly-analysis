// ── Comparaison multi-actions — compare.js ────────────────────────────────

let compareList = [];

function toggleCompare(ticker) {
  if (compareList.includes(ticker)) {
    compareList = compareList.filter(t => t !== ticker);
  } else {
    if (compareList.length >= 4) { return; }
    compareList.push(ticker);
  }
  updateCompareBadge();
  if (compareList.length >= 2) renderCompare();
}

function updateCompareBadge() {
  const b = document.getElementById('compare-badge');
  if (b) b.textContent = compareList.length > 0 ? '(' + compareList.length + ')' : '';
}

function renderCompare() {
  const modal = document.getElementById('compare-modal') || createCompareModal();
  const all = window.scores || scores || [];
  const items = compareList.map(t => all.find(x => x.ticker === t)).filter(Boolean);
  if (items.length < 2) return;

  const metrics = [
    ['Score /10',    x => ((x.composite_adj||0)/80*10).toFixed(1),   x => x.composite_adj||0,  true],
    ['P/E',         x => x.pe_ref ? x.pe_ref.toFixed(1)+'×' : '—', x => -(x.pe_ref||999),    true],
    ['P/B',         x => x.pb_ref ? x.pb_ref.toFixed(1)+'×' : '—', x => -(x.pb_ref||999),    true],
    ['ROE %',       x => x.roe ? x.roe.toFixed(1)+'%' : '—',        x => x.roe||0,             true],
    ['Div %',       x => x.div_yield ? x.div_yield.toFixed(1)+'%':'—', x => x.div_yield||0,   true],
    ['BNA (F)',     x => x.eps ? Math.round(x.eps).toLocaleString('fr-FR'):'—', x => x.eps||0, true],
    ['Cours (XOF)', x => x.price ? x.price.toLocaleString('fr-FR'):'—', x => 0,               false],
    ['Verdict PDF', x => x.pdf_verdict||'—',                         x => 0,                   false],
    ['Secteur',     x => x.sector||'—',                              x => 0,                   false],
    ['Rang',        x => '#'+(x.rank||'?'),                          x => -(x.rank||99),        true],
  ];

  // Couleur score
  const scoreC = v => v >= 60 ? '#4ADE80' : v >= 40 ? '#FBBF24' : '#F87171';
  const verdC  = v => v === 'POSITIF' ? '#4ADE80' : v === 'NEGATIF' ? '#F87171' : '#FBBF24';

  const cols = items.map(x => `
    <th style="text-align:center;padding:8px 12px;min-width:110px">
      <div style="font-weight:700;font-size:13px">${x.ticker}</div>
      <div style="font-size:10px;color:var(--t2)">${x.name||''}</div>
      <span style="font-size:11px;font-weight:700;color:${scoreC(x.composite_adj||0)}">${((x.composite_adj||0)/80*10).toFixed(1)}/10</span>
      <button onclick="toggleCompare('${x.ticker}')" style="display:block;margin:4px auto 0;font-size:9px;padding:1px 6px;background:var(--bg3);border:1px solid var(--border);border-radius:3px;color:var(--t2);cursor:pointer">✕ Retirer</button>
    </th>`).join('');

  const rows = metrics.map(([label, fmt, sortVal, compare]) => {
    const vals = items.map(x => sortVal(x));
    const best = compare ? Math.max(...vals) : null;
    const cells = items.map((x, i) => {
      const isBest = compare && vals[i] === best && vals.filter(v => v === best).length < items.length;
      const txt = fmt(x);
      const isVerdict = label === 'Verdict PDF';
      const color = isVerdict ? verdC(x.pdf_verdict||'') : isBest ? '#4ADE80' : 'var(--t1)';
      return `<td style="text-align:center;padding:6px 12px;font-size:12px;color:${color};font-weight:${isBest?'700':'400'};border-bottom:1px solid var(--border)">${txt}${isBest?' ✓':''}</td>`;
    }).join('');
    return `<tr><td style="padding:6px 12px;font-size:11px;color:var(--t2);border-bottom:1px solid var(--border);white-space:nowrap">${label}</td>${cells}</tr>`;
  }).join('');

  // Graphique barres scores
  const W = 320, H = 80, pad = 20;
  const maxScore = 80;
  const barW = Math.floor((W - pad * (items.length+1)) / items.length);
  const bars = items.map((x, i) => {
    const v = x.composite_adj || 0;
    const bh = Math.round((v / maxScore) * (H - 20));
    const bx = pad + i * (barW + pad);
    const by = H - bh - 4;
    return `<rect x="${bx}" y="${by}" width="${barW}" height="${bh}" rx="3" fill="${scoreC(v)}"/>
            <text x="${bx + barW/2}" y="${H}" text-anchor="middle" font-size="9" fill="rgba(255,255,255,0.5)">${x.ticker}</text>
            <text x="${bx + barW/2}" y="${by - 3}" text-anchor="middle" font-size="10" font-weight="700" fill="${scoreC(v)}">${v.toFixed(0)}</text>`;
  }).join('');
  const chart = `<svg width="${W}" height="${H}" style="margin:8px auto;display:block">${bars}</svg>`;

  modal.querySelector('#compare-content').innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <div style="font-weight:700;font-size:14px">⚖️ Comparaison (${items.length} actions)</div>
      <button onclick="clearCompare()" style="font-size:10px;padding:3px 8px;background:var(--bg3);border:1px solid var(--border);border-radius:4px;color:var(--t2);cursor:pointer">Effacer tout</button>
    </div>
    ${chart}
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse">
        <thead><tr><th style="text-align:left;padding:8px 12px;font-size:11px;color:var(--t2)">Métrique</th>${cols}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div style="margin-top:12px;font-size:10px;color:var(--t2)">✓ = Meilleure valeur dans la sélection</div>`;
  modal.style.display = 'flex';
}

function createCompareModal() {
  const modal = document.createElement('div');
  modal.id = 'compare-modal';
  modal.style = 'display:none;position:fixed;inset:0;z-index:9998;background:rgba(0,0,0,0.7);align-items:center;justify-content:center;padding:16px';
  modal.innerHTML = `
    <div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:20px;max-width:700px;width:100%;max-height:90vh;overflow-y:auto;position:relative">
      <button onclick="closeCompare()" style="position:absolute;top:12px;right:12px;background:var(--bg3);border:1px solid var(--border);border-radius:6px;color:var(--t2);padding:4px 10px;cursor:pointer;font-size:12px">✕</button>
      <div id="compare-content"></div>
    </div>`;
  modal.addEventListener('click', e => { if (e.target === modal) closeCompare(); });
  document.body.appendChild(modal);
  return modal;
}

function closeCompare() {
  const m = document.getElementById('compare-modal');
  if (m) m.style.display = 'none';
}

function clearCompare() {
  compareList = [];
  updateCompareBadge();
  closeCompare();
}

function openCompare() {
  if (compareList.length < 2) { return; }
  renderCompare();
}
