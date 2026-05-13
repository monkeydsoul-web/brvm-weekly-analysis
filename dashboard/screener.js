// ── Screener avancé BRVM — screener.js ────────────────────────────────────

let _scrSort = { col: 'composite_adj', asc: false };
let _scrResults = [];

function initScreener() {
  const sectSel = document.getElementById('sc-sect');
  if (!sectSel || sectSel.options.length > 1) return;
  const all = window.scores || scores || [];
  const sects = [...new Set(all.map(x => x.sector).filter(Boolean))].sort();
  sects.forEach(s => sectSel.add(new Option(s, s)));
  runScreener();
}

function runScreener() {
  const all = window.scores || scores || [];
  const scoreMin = parseFloat(document.getElementById('sc-score')?.value) || 0;
  const peMax    = parseFloat(document.getElementById('sc-pe')?.value)    || Infinity;
  const divMin   = parseFloat(document.getElementById('sc-div')?.value)   || 0;
  const roeMin   = parseFloat(document.getElementById('sc-roe')?.value)   || 0;
  const pbMax    = parseFloat(document.getElementById('sc-pb')?.value)    || Infinity;
  const sect     = document.getElementById('sc-sect')?.value              || '';

  _scrResults = all.filter(x => {
    if ((x.composite_adj || 0) < scoreMin) return false;
    if (peMax < Infinity && (x.pe_ref || 9999) > peMax) return false;
    if ((x.div_yield || 0) < divMin) return false;
    if ((x.roe || 0) < roeMin) return false;
    if (pbMax < Infinity && (x.pb_ref || 9999) > pbMax) return false;
    if (sect && x.sector !== sect) return false;
    return true;
  });

  _scrResults.sort((a, b) => {
    const va = a[_scrSort.col] ?? -Infinity;
    const vb = b[_scrSort.col] ?? -Infinity;
    return _scrSort.asc ? va - vb : vb - va;
  });

  const count = document.getElementById('sc-count');
  if (count) count.textContent = `${_scrResults.length} résultat${_scrResults.length !== 1 ? 's' : ''}`;

  _renderScreenerTable();
}

function _renderScreenerTable() {
  const tbody = document.getElementById('screener-table');
  if (!tbody) return;

  if (!_scrResults.length) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--t2);padding:20px">Aucun résultat — ajustez les filtres.</td></tr>';
    return;
  }

  tbody.innerHTML = _scrResults.map(x => {
    const sc  = x.composite_adj || 0;
    const scC = sc >= 60 ? 'var(--green)' : sc >= 45 ? 'var(--amber)' : 'var(--red)';
    const pe  = x.pe_ref ? x.pe_ref.toFixed(1) + '×' : '—';
    const pb  = x.pb_ref ? x.pb_ref.toFixed(2) + '×' : '—';
    const dy  = (x.div_yield || 0) > 0 ? x.div_yield.toFixed(1) + '%' : '—';
    const dyC = (x.div_yield || 0) >= 6 ? 'var(--green)' : (x.div_yield || 0) >= 3 ? 'var(--amber)' : 'var(--t2)';
    const chg = x.change_pct || 0;
    const chgC = chg > 0 ? 'var(--green)' : chg < 0 ? 'var(--red)' : 'var(--t2)';
    const chgS = (chg > 0 ? '+' : '') + chg.toFixed(2) + '%';
    const roe = x.roe ? x.roe + '%' : '—';
    const verd = x.pdf_verdict || '—';
    const verdC = verd === 'POSITIF' ? 'var(--green)' : verd === 'NEGATIF' ? 'var(--red)' : 'var(--amber)';

    return `<tr onclick="showStock('${x.ticker}')" style="cursor:pointer">
      <td>
        <div style="display:flex;align-items:center;gap:6px">
          <input type="checkbox" class="sc-chk" value="${x.ticker}" onclick="event.stopPropagation()">
          <strong>${x.ticker}</strong>
        </div>
        <div style="font-size:9px;color:var(--t2)">${(x.sector || '').substring(0, 14)}</div>
      </td>
      <td style="font-size:11px;color:var(--t2)">${x.name ? x.name.substring(0, 18) : '—'}</td>
      <td style="text-align:right;font-weight:700;color:${scC}">${sc.toFixed(0)}</td>
      <td style="text-align:right;color:var(--t1)">${pe}</td>
      <td style="text-align:right;color:var(--t1)">${pb}</td>
      <td style="text-align:right;font-weight:600;color:${dyC}">${dy}</td>
      <td style="text-align:right;color:var(--t2)">${roe}</td>
      <td style="text-align:right;color:${chgC};font-weight:600">${chgS}</td>
      <td style="text-align:center">
        <span style="font-size:10px;padding:1px 5px;border-radius:3px;background:${verd==='POSITIF'?'rgba(74,222,128,0.15)':verd==='NEGATIF'?'rgba(248,113,113,0.15)':'rgba(251,191,36,0.15)'};color:${verdC}">${verd}</span>
      </td>
    </tr>`;
  }).join('');
}

function screenerSortBy(col) {
  if (_scrSort.col === col) {
    _scrSort.asc = !_scrSort.asc;
  } else {
    _scrSort = { col, asc: false };
  }
  // Update header indicators
  document.querySelectorAll('#screener-thead th[data-col]').forEach(th => {
    const c = th.getAttribute('data-col');
    th.querySelector('.sort-ind').textContent = c === col ? (_scrSort.asc ? ' ↑' : ' ↓') : '';
  });
  runScreener();
}

function screenerReset() {
  ['sc-score', 'sc-pe', 'sc-div', 'sc-roe', 'sc-pb'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const sect = document.getElementById('sc-sect');
  if (sect) sect.value = '';
  runScreener();
}

async function screenerAnalyseAI() {
  const checked = [...document.querySelectorAll('.sc-chk:checked')].map(el => el.value);
  const tickers = checked.length ? checked : _scrResults.slice(0, 6).map(x => x.ticker);
  if (!tickers.length) { showNotif('Aucune action sélectionnée', 'red'); return; }

  const btn = document.getElementById('sc-ai-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Analyse en cours...'; }

  try {
    const res = await fetch('/api/compare-analysis', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tickers })
    });
    const data = await res.json();
    const resultEl = document.getElementById('sc-ai-result');
    if (resultEl) {
      resultEl.style.display = 'block';
      resultEl.innerHTML = `
        <div class="ct" style="margin-bottom:8px">🤖 Analyse IA — ${tickers.join(', ')}</div>
        <div style="font-size:12px;color:var(--t1);line-height:1.7;white-space:pre-wrap">${data.analysis || data.error || 'Erreur'}</div>`;
    }
  } catch(e) {
    showNotif('Erreur analyse IA', 'red');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Analyser avec IA'; }
  }
}
