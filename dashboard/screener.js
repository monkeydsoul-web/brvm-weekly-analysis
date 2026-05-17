// ── Screener avancé BRVM — screener.js ────────────────────────────────────

let _scrSort = { col: 'composite_adj', asc: false };
let _scrResults = [];

function initScreener() {
  const sectSel = document.getElementById('sc-sect');
  if (!sectSel || sectSel.options.length > 1) return;
  const all = window.scores || scores || [];
  const sects = [...new Set(all.map(x => x.sector).filter(Boolean))].sort();
  sects.forEach(s => sectSel.add(new Option(s, s)));
  _screenerLoadFilters();
  runScreener();
}

function runScreener() {
  _screenerSaveFilters();
  const all = window.scores || scores || [];
  const scoreMin = (parseFloat(document.getElementById('sc-score')?.value) || 0) * 8;
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
  if (count) {
    const numSpan = count.querySelector('span:first-child');
    if (numSpan) numSpan.textContent = _scrResults.length;
    else count.innerHTML = `<span style="font-size:15px;font-weight:700;color:var(--accent)">${_scrResults.length}</span> <span style="font-size:12px;color:var(--text-2)">sociétés correspondent à vos critères</span>`;
  }

  _renderScreenerTable();
}

function _renderScreenerTable() {
  const tbody = document.getElementById('screener-table');
  if (!tbody) return;

  if (!_scrResults.length) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--t2);padding:20px">Aucun résultat — ajustez les filtres.</td></tr>';
    return;
  }

  const showSector = !document.getElementById('sc-sect')?.value;

  tbody.innerHTML = _scrResults.map(x => {
    const sc  = x.composite_adj || 0;
    const sc10 = (sc / 80 * 10).toFixed(1);
    const scC = sc >= 60 ? 'var(--green)' : sc >= 45 ? 'var(--amber)' : 'var(--red)';
    const scBarW = Math.round(sc / 80 * 100);
    const pe  = x.pe_ref ? x.pe_ref.toFixed(1) + '×' : '—';
    const pb  = x.pb_ref ? x.pb_ref.toFixed(2) + '×' : '—';
    const dy  = (x.div_yield || 0) > 0 ? x.div_yield.toFixed(1) + '%' : '—';
    const dyC = (x.div_yield || 0) >= 6 ? 'var(--green)' : (x.div_yield || 0) >= 3 ? 'var(--amber)' : 'var(--t2)';
    const chg = x.change_pct || 0;
    const chgC = chg > 0 ? 'var(--green)' : chg < 0 ? 'var(--red)' : 'var(--t2)';
    const chgS = (chg > 0 ? '+' : '') + chg.toFixed(2) + '%';
    const verd = x.pdf_verdict || '';
    const verdLabel = typeof fmtVerdict === 'function' ? fmtVerdict(verd) : verd || '—';
    const verdC = verd === 'POSITIF' ? 'var(--green)' : verd === 'NEGATIF' ? 'var(--red)' : 'var(--amber)';
    // Prix cible Graham ou EPV
    const eps = x.eps || 0; const bvpa = x.bvpa || 0;
    const grahamT = (eps > 0 && bvpa > 0) ? Math.round(Math.sqrt(22.5 * eps * bvpa)) : 0;
    const epvT = eps > 0 ? Math.round(eps / 0.10) : 0;
    const target = grahamT || epvT;
    const price = x.price || 0;
    const targetStr = target > 0 ? target.toLocaleString('fr-FR') + ' XOF' : '—';
    const targetC = target > 0 && price > 0 ? (price < target ? 'var(--bull)' : 'var(--bear)') : 'var(--text-2)';
    const targetArrow = target > 0 && price > 0 ? (price < target ? ' ↑' : ' ↓') : '';

    return `<tr onclick="showStock('${x.ticker}')" style="cursor:pointer">
      <td style="padding:8px 12px">
        <strong style="font-size:12px">${x.ticker}</strong>
        ${showSector ? `<div style="font-size:9px;color:var(--t2)">${(x.sector || '').substring(0, 14)}</div>` : ''}
      </td>
      <td style="padding:8px 12px;font-size:11px;color:var(--t2)">${x.name ? x.name.substring(0, 20) : '—'}</td>
      <td style="padding:8px 12px;text-align:right">
        <span style="font-weight:700;color:${scC}">${sc10}/10</span>
        <div style="height:3px;background:rgba(255,255,255,0.1);border-radius:2px;margin-top:2px"><div style="height:100%;width:${scBarW}%;background:${scC};border-radius:2px"></div></div>
      </td>
      <td style="padding:8px 12px;text-align:right;font-size:11px;color:${targetC};font-weight:${target>0?'600':'400'}">${targetStr}${targetArrow}</td>
      <td style="padding:8px 12px;text-align:right;color:var(--t1)">${pe}</td>
      <td style="padding:8px 12px;text-align:right;font-weight:600;color:${dyC}">${dy}</td>
      <td style="padding:8px 12px;text-align:right;color:${chgC};font-weight:600">${chgS}</td>
      <td style="padding:8px 12px;text-align:center;white-space:nowrap">
        <span style="font-size:10px;padding:1px 5px;border-radius:3px;background:${verd==='POSITIF'?'rgba(74,222,128,0.15)':verd==='NEGATIF'?'rgba(248,113,113,0.15)':'rgba(251,191,36,0.15)'};color:${verdC}">${verdLabel}</span>
        <button onclick="event.stopPropagation();showStock('${x.ticker}')" style="background:none;border:1px solid var(--border-1);color:var(--text-2);font-size:11px;padding:2px 7px;border-radius:var(--radius-sm);cursor:pointer;margin-left:4px">Fiche →</button>
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

const _LS_SCREENER = 'brvm_screener_filters_v1';

function _screenerSaveFilters(){
  const f = {};
  ['sc-score','sc-pe','sc-div','sc-roe','sc-pb'].forEach(id=>{
    const el = document.getElementById(id);
    if(el) f[id] = el.value;
  });
  const sect = document.getElementById('sc-sect');
  if(sect) f['sc-sect'] = sect.value;
  localStorage.setItem(_LS_SCREENER, JSON.stringify(f));
}

function _screenerLoadFilters(){
  try{
    const f = JSON.parse(localStorage.getItem(_LS_SCREENER)||'{}');
    Object.entries(f).forEach(([id,val])=>{
      const el = document.getElementById(id);
      if(el) el.value = val;
    });
  }catch{}
}

function screenerPreset(name){
  screenerReset();
  const presets = {
    value:      { 'sc-score': 5.5, 'sc-pe': 15, 'sc-pb': 1.5 },
    croissance: { 'sc-score': 6.5, 'sc-roe': 15 },
    revenus:    { 'sc-score': 5, 'sc-div': 5 },
    defensif:   { 'sc-score': 5, 'sc-pe': 20, 'sc-div': 3, 'sc-roe': 10 },
  };
  const p = presets[name] || {};
  Object.entries(p).forEach(([id,val])=>{
    const el = document.getElementById(id);
    if(el) el.value = val;
  });
  // Highlight active chip
  document.querySelectorAll('.chat-chip[onclick*="screenerPreset"]').forEach(btn=>{
    btn.style.background = btn.getAttribute('onclick').includes(`'${name}'`) ? 'var(--blue)' : '';
    btn.style.color = btn.getAttribute('onclick').includes(`'${name}'`) ? '#fff' : '';
  });
  runScreener();
  _screenerSaveFilters();
}

function screenerReset() {
  ['sc-score', 'sc-pe', 'sc-div', 'sc-roe', 'sc-pb'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const sect = document.getElementById('sc-sect');
  if (sect) sect.value = '';
  // Reset chip highlights
  document.querySelectorAll('.chat-chip[onclick*="screenerPreset"]').forEach(btn=>{
    btn.style.background = '';
    btn.style.color = '';
  });
  localStorage.removeItem(_LS_SCREENER);
  runScreener();
}

function screenerExportCSV() {
  if (!_scrResults.length) { return; }
  const cols = ['Ticker','Nom','Secteur','Score/10','P/E','P/B','Div%','ROE%','Var%','Cours XOF','Verdict IA','Graham/10','DCF/10','DDM/10','EPV/10','Buffett/10'];
  const rows = _scrResults.map(x => [
    x.ticker,
    (x.name||'').replace(/,/g,''),
    (x.sector||'').replace(/,/g,''),
    ((x.composite_adj||0)/80*10).toFixed(2),
    x.pe_ref ? x.pe_ref.toFixed(2) : '',
    x.pb_ref ? x.pb_ref.toFixed(2) : '',
    x.div_yield ? x.div_yield.toFixed(2) : '',
    x.roe ? x.roe.toFixed(1) : '',
    x.change_pct != null ? x.change_pct.toFixed(2) : '',
    x.price ? Math.round(x.price) : '',
    x.pdf_verdict||'',
    (x.score_graham||0).toFixed(1),
    (x.score_dcf||0).toFixed(1),
    (x.score_ddm||0).toFixed(1),
    (x.score_epv||0).toFixed(1),
    (x.score_buffett||0).toFixed(1),
  ]);
  const csv = [cols, ...rows].map(r => r.join(',')).join('\n');
  const blob = new Blob(['﻿'+csv], { type: 'text/csv;charset=utf-8' }); // BOM pour Excel
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `BRVM_Screener_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

async function screenerAnalyseAI() {
  const checked = [...document.querySelectorAll('.sc-chk:checked')].map(el => el.value);
  const tickers = checked.length ? checked : _scrResults.slice(0, 6).map(x => x.ticker);
  if (!tickers.length) { return; }

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
    console.error('Erreur analyse IA', e);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Analyser avec IA'; }
  }
}
