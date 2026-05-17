// ── Page Performances historiques — performance.js ────────────────────────

let _perfData = {};
let _perfSelected = [];
let _perfPeriod = 'Tout';
let _perfZoom = null; // {startDate, endDate}
const PERF_COLORS = ['#4ADE80','#60A5FA','#FBBF24','#F87171','#C084FC','#34D399','#FB923C','#A78BFA'];
const _perfChartStates = {};
const _perfVisible = {}; // containerId -> Set of visible tickers

async function renderPerfPage() {
  const container = document.getElementById('perfPageContent');
  if (!container) return;
  container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--t2)">Chargement historique...</div>';

  const all = window.scores || scores || [];
  if (!all.length) return;

  try {
    const res = await fetch('/api/price-history');
    _perfData = await res.json();
  } catch(e) {
    container.innerHTML = '<div style="color:var(--red);padding:20px">Erreur chargement historique</div>';
    return;
  }

  const performers = [];
  for (const [ticker, pts] of Object.entries(_perfData)) {
    if (!pts || pts.length < 2) continue;
    const sorted = [...pts].sort((a,b) => a.date.localeCompare(b.date));
    const first = sorted[0].price, last = sorted[sorted.length-1].price;
    if (first > 0) {
      performers.push({
        ticker,
        perf: ((last - first) / first * 100),
        perf1y: _perf1y(sorted),
        perf3y: _perfNy(sorted, 3),
        first, last,
        pts: sorted.length,
        name: (all.find(x=>x.ticker===ticker)||{}).name || ''
      });
    }
  }
  performers.sort((a,b) => b.perf - a.perf);

  const scoreMap = Object.fromEntries((all).map(x=>[x.ticker,x]));
  performers.forEach(p => {
    const sc = scoreMap[p.ticker];
    const divAnnuel = (sc?.div_per_share || 0);
    const yearsApprox = p.pts > 200 ? 5 : p.pts > 100 ? 3 : p.pts > 50 ? 2 : 1;
    const totalDivs = divAnnuel * yearsApprox;
    const totalReturn = p.first > 0 ? ((p.last + totalDivs - p.first) / p.first * 100) : p.perf;
    p.totalReturn = totalReturn;
    p.totalDivsXof = totalDivs;
  });

  // Always reselect top 5 performers on fresh page load
  _perfSelected = performers.slice(0,5).map(p=>p.ticker);

  container.innerHTML = `
    <div class="card" style="margin-bottom:12px">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;flex-wrap:wrap;gap:8px">
        <div>
          <div class="ct">📈 Évolution des cours</div>
          <p class="help-text">Base 100 depuis la première date disponible · survolez pour les valeurs · glissez pour zoomer · double-clic pour réinitialiser</p>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap" id="perf-period-btns">
          ${['6m','1an','3ans','5ans','Tout'].map(p=>`
            <button onclick="setPerfPeriod('${p}')" id="btn-period-${p}"
              style="font-size:10px;padding:3px 8px;border-radius:4px;border:1px solid var(--border);background:var(--bg3);color:var(--t2);cursor:pointer">${p}</button>`).join('')}
        </div>
      </div>
      <div id="perf-chart" style="width:100%;height:280px"></div>
      <div id="perf-legend" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px"></div>
    </div>
    <div class="g2" style="margin-bottom:12px">
      <div class="card" style="margin-bottom:0">
        <div class="ct">🏆 Meilleures performances (Total Return)</div>
        <div id="perf-top-list"></div>
      </div>
      <div class="card" style="margin-bottom:0">
        <div class="ct">📉 Moins bonnes performances</div>
        <div id="perf-flop-list"></div>
      </div>
    </div>
    <div class="card" style="margin-bottom:12px">
      <div class="ct" style="margin-bottom:10px">🏅 Palmarès annuel — Top 3 / Flop 3 par année</div>
      <div id="perf-palmares" style="overflow-x:auto"></div>
    </div>
    <div class="card">
      <div class="ct">Sélectionner actions à comparer (max 8)</div>
      <div id="perf-selector" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px"></div>
      <div id="perf-chart2" style="width:100%;height:220px"></div>
    </div>`;

  _renderPerfList('perf-top-list', performers.slice(0,8), true);
  _renderPerfList('perf-flop-list', [...performers].sort((a,b)=>a.perf-b.perf).slice(0,8), false);
  _renderPalmaresAnnuel(performers);
  _renderPerfSelector(all, performers);
  _drawPerfChart('perf-chart', _perfSelected);
  _drawPerfChart('perf-chart2', _perfSelected);
  document.getElementById('btn-period-Tout')?.click();
}

function _perf1y(sorted) {
  const now = new Date();
  const oneYearAgo = new Date(now); oneYearAgo.setFullYear(now.getFullYear()-1);
  const cutoff = oneYearAgo.toISOString().slice(0,10);
  const base = sorted.find(p=>p.date>=cutoff);
  if (!base) return null;
  return ((sorted[sorted.length-1].price - base.price) / base.price * 100);
}

function _perfNy(sorted, n) {
  const now = new Date();
  const cutoff = new Date(now); cutoff.setFullYear(now.getFullYear()-n);
  const cutStr = cutoff.toISOString().slice(0,10);
  const base = sorted.find(p=>p.date>=cutStr);
  if (!base) return null;
  return ((sorted[sorted.length-1].price - base.price) / base.price * 100);
}

function _renderPerfList(id, performers, isTop) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = performers.map(p => {
    const tr = p.totalReturn != null ? p.totalReturn : p.perf;
    const c = tr >= 0 ? 'var(--green)' : 'var(--red)';
    const trSign = tr >= 0 ? '+' : '';
    const pSign = p.perf >= 0 ? '+' : '';
    const trDiff = p.totalReturn != null && p.totalDivsXof > 0
      ? `<span style="font-size:9px;color:var(--amber)"> +div</span>` : '';
    return `<div onclick="showStock('${p.ticker}')" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border)">
      <div>
        <span style="font-weight:700;font-size:12px">${p.ticker}</span>
        <span style="font-size:10px;color:var(--t2);margin-left:4px">${p.name.substring(0,18)}</span>
      </div>
      <div style="text-align:right">
        <div style="color:${c};font-weight:700;font-size:13px">${trSign}${tr.toFixed(1)}%${trDiff}</div>
        <div style="font-size:9px;color:var(--t3)">cours: ${pSign}${p.perf.toFixed(1)}%</div>
      </div>
    </div>`;
  }).join('');
}

function _renderPalmaresAnnuel(performers) {
  const el = document.getElementById('perf-palmares');
  if (!el) return;

  const currentYear = new Date().getFullYear();
  const years = [];
  for (let y = currentYear - 1; y >= currentYear - 5; y--) years.push(y);

  const yearlyPerf = years.map(year => {
    const startCut = `${year}-01-01`, endCut = `${year}-12-31`;
    const results = performers.map(p => {
      const pts = (_perfData[p.ticker]||[]).sort((a,b)=>a.date.localeCompare(b.date));
      const yearPts = pts.filter(x=>x.date>=startCut && x.date<=endCut);
      if (yearPts.length < 2) return null;
      const first = yearPts[0].price, last = yearPts[yearPts.length-1].price;
      const perf = first > 0 ? ((last-first)/first*100) : 0;
      return {ticker:p.ticker, name:p.name, perf};
    }).filter(Boolean);
    results.sort((a,b)=>b.perf-a.perf);
    return {year, top3: results.slice(0,3), flop3: results.slice(-3).reverse()};
  }).filter(y => y.top3.length > 0);

  if (!yearlyPerf.length) { el.innerHTML = '<p style="color:var(--t2);font-size:11px">Historique annuel insuffisant.</p>'; return; }

  let html = `<div style="display:flex;gap:10px;overflow-x:auto;padding-bottom:4px">`;
  yearlyPerf.forEach(({year, top3, flop3}) => {
    html += `<div style="min-width:160px;background:var(--bg3);border-radius:8px;padding:10px;flex-shrink:0">
      <div style="font-size:13px;font-weight:700;color:var(--text);margin-bottom:8px;text-align:center">${year}</div>
      ${top3.map((p,i)=>`<div onclick="showStock('${p.ticker}')" style="display:flex;justify-content:space-between;padding:3px 0;cursor:pointer;border-bottom:1px solid var(--border)">
        <span style="font-size:11px;font-weight:600;color:var(--green)">${['🥇','🥈','🥉'][i]} ${p.ticker}</span>
        <span style="font-size:10px;color:var(--green)">+${p.perf.toFixed(0)}%</span>
      </div>`).join('')}
      <div style="margin:6px 0 2px;font-size:9px;color:var(--t3);text-transform:uppercase">Flop</div>
      ${flop3.map(p=>`<div onclick="showStock('${p.ticker}')" style="display:flex;justify-content:space-between;padding:3px 0;cursor:pointer">
        <span style="font-size:10px;color:var(--red)">${p.ticker}</span>
        <span style="font-size:10px;color:var(--red)">${p.perf.toFixed(0)}%</span>
      </div>`).join('')}
    </div>`;
  });
  html += '</div>';
  el.innerHTML = html;
}

function _renderPerfSelector(all, performers) {
  const el = document.getElementById('perf-selector');
  if (!el) return;
  el.innerHTML = performers.map((p,i) => {
    const selected = _perfSelected.includes(p.ticker);
    const color = PERF_COLORS[performers.findIndex(x=>x.ticker===p.ticker) % PERF_COLORS.length];
    return `<button id="perf-btn-${p.ticker}" onclick="togglePerfTicker('${p.ticker}')"
      style="font-size:10px;padding:3px 8px;border-radius:4px;border:2px solid ${selected?color:'var(--border)'};background:${selected?color+'22':'var(--bg3)'};color:${selected?color:'var(--t2)'};cursor:pointer;font-weight:${selected?'700':'400'}">
      ${p.ticker}</button>`;
  }).join('');
}

function togglePerfTicker(ticker) {
  if (_perfSelected.includes(ticker)) {
    _perfSelected = _perfSelected.filter(t => t !== ticker);
  } else {
    if (_perfSelected.length >= 8) { return; }
    _perfSelected.push(ticker);
  }
  const all = window.scores || scores || [];
  const performers = Object.keys(_perfData).map(t => {
    const pts = (_perfData[t]||[]).sort((a,b)=>a.date.localeCompare(b.date));
    const first = pts[0]?.price||0, last = pts[pts.length-1]?.price||0;
    return {ticker:t, perf: first>0?((last-first)/first*100):0};
  }).sort((a,b)=>b.perf-a.perf);
  _renderPerfSelector(all, performers);
  _drawPerfChart('perf-chart', _perfSelected);
  _drawPerfChart('perf-chart2', _perfSelected);
}

function setPerfPeriod(period) {
  _perfPeriod = period;
  _perfZoom = null;
  document.querySelectorAll('[id^="btn-period-"]').forEach(b => {
    b.style.background = 'var(--bg3)'; b.style.color = 'var(--t2)'; b.style.borderColor = 'var(--border)';
  });
  const btn = document.getElementById(`btn-period-${period}`);
  if (btn) { btn.style.background = 'var(--blue)22'; btn.style.color = 'var(--blue)'; btn.style.borderColor = 'var(--blue)'; }

  // Recompute top 5 performers for this period
  const top5ForPeriod = Object.entries(_perfData)
    .map(([ticker, rawPts]) => {
      const pts = _filterByPeriod([...rawPts].sort((a,b)=>a.date.localeCompare(b.date)));
      if (pts.length < 2) return null;
      const first = pts[0].price, last = pts[pts.length-1].price;
      return first > 0 ? {ticker, perf:(last-first)/first*100} : null;
    })
    .filter(Boolean)
    .sort((a,b) => b.perf - a.perf)
    .slice(0,5)
    .map(p=>p.ticker);
  if (top5ForPeriod.length >= 2) _perfSelected = top5ForPeriod;

  _drawPerfChart('perf-chart', _perfSelected);
}

function _filterByPeriod(pts) {
  if (_perfPeriod === 'Tout') return pts;
  const months = {'6m':6,'1an':12,'3ans':36,'5ans':60}[_perfPeriod];
  if (!months) return pts;
  const now = new Date();
  const cutoff = new Date(now); cutoff.setMonth(now.getMonth() - months);
  const cutStr = cutoff.toISOString().slice(0,10);
  return pts.filter(p => p.date >= cutStr);
}

function _drawPerfChart(containerId, tickers) {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (!_perfVisible[containerId]) {
    _perfVisible[containerId] = new Set(tickers);
  }
  const visible = _perfVisible[containerId];
  tickers.forEach(t => { if (!visible.has(t)) visible.add(t); });

  const datasets = tickers.map((ticker,i) => {
    const pts = _filterByPeriod((_perfData[ticker]||[]).sort((a,b)=>a.date.localeCompare(b.date)));
    return {ticker, pts, color: PERF_COLORS[i % PERF_COLORS.length], visible: visible.has(ticker)};
  }).filter(d => d.pts.length > 1);

  if (!datasets.length) {
    container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--t2);font-size:12px">Sélectionnez des actions</div>';
    return;
  }

  const W = container.clientWidth || 600;
  const H = containerId === 'perf-chart' ? 280 : 220;
  const PAD = {top:20, right:80, bottom:30, left:45};
  const CW = W - PAD.left - PAD.right, CH = H - PAD.top - PAD.bottom;

  let allDates = [...new Set(datasets.flatMap(d => d.pts.map(p => p.date)))].sort();
  if (allDates.length < 2) return;

  // Apply zoom
  if (_perfZoom) {
    const zoomed = allDates.filter(d => d >= _perfZoom.startDate && d <= _perfZoom.endDate);
    if (zoomed.length >= 2) allDates = zoomed;
  }

  const normalized = datasets.map(d => {
    const base = d.pts[0].price;
    const byDate = Object.fromEntries(d.pts.map(p => [p.date, p.price]));
    return {
      ...d,
      values: allDates.map(date => {
        const p = byDate[date];
        if (p !== undefined) return (p / base) * 100;
        const prev = d.pts.filter(x => x.date <= date).pop();
        return prev ? (prev.price / base) * 100 : null;
      })
    };
  });

  const allValues = normalized.flatMap(d => d.visible ? d.values.filter(v => v !== null) : []);
  if (!allValues.length) { container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--t2);font-size:12px">Aucune donnée</div>'; return; }

  const minV = Math.min(...allValues) * 0.98, maxV = Math.max(...allValues) * 1.02;
  const rangeV = maxV - minV || 1;

  const xScale = i => PAD.left + (i / (allDates.length - 1 || 1)) * CW;
  const yScale = v => PAD.top + CH - ((v - minV) / rangeV) * CH;

  // Grid lines
  const gridLines = [0,1,2,3,4].map(i => {
    const v = minV + rangeV * i / 4;
    const y = yScale(v);
    return `<line x1="${PAD.left}" y1="${y}" x2="${PAD.left+CW}" y2="${y}" stroke="rgba(255,255,255,0.05)" stroke-width="1"/>
            <text x="${PAD.left-4}" y="${y+4}" text-anchor="end" font-size="9" fill="rgba(255,255,255,0.3)">${v.toFixed(0)}</text>`;
  }).join('');

  const base100Y = yScale(100);
  const baseLine = `<line x1="${PAD.left}" y1="${base100Y}" x2="${PAD.left+CW}" y2="${base100Y}" stroke="rgba(255,255,255,0.15)" stroke-width="1" stroke-dasharray="4,3"/>
                    <text x="${PAD.left-4}" y="${base100Y+4}" text-anchor="end" font-size="9" fill="rgba(255,255,255,0.4)">100</text>`;

  const step = Math.ceil(allDates.length / 6);
  const xLabels = allDates.map((d,i) => {
    if (i % step !== 0 && i !== allDates.length - 1) return '';
    return `<text x="${xScale(i)}" y="${H-4}" text-anchor="middle" font-size="9" fill="rgba(255,255,255,0.3)">${d.slice(0,7)}</text>`;
  }).join('');

  // Chart lines (handle null gaps)
  const lines = normalized.map(d => {
    if (!d.visible) return '';
    let segments = [], cur = [];
    d.values.forEach((v, i) => {
      if (v !== null) cur.push(`${xScale(i)},${yScale(v)}`);
      else if (cur.length) { segments.push(cur); cur = []; }
    });
    if (cur.length) segments.push(cur);

    const lastValidPair = d.values.map((v,i) => [v,i]).filter(([v]) => v !== null).pop();
    if (!lastValidPair) return '';
    const [lastV, lastI] = lastValidPair;
    const lastX = xScale(lastI), lastY = yScale(lastV);
    const sign = lastV >= 100 ? '+' : '';

    return segments.map(seg =>
      `<polyline points="${seg.join(' ')}" fill="none" stroke="${d.color}" stroke-width="1.8" stroke-linejoin="round" opacity="0.9"/>`
    ).join('') +
    `<circle cx="${lastX}" cy="${lastY}" r="3" fill="${d.color}"/>
     <text x="${lastX+5}" y="${lastY+4}" font-size="9" font-weight="700" fill="${d.color}">${d.ticker} ${sign}${(lastV-100).toFixed(0)}%</text>`;
  }).join('');

  // Interactive elements
  const crosshair = `<line id="perf-ch-${containerId}" x1="0" y1="${PAD.top}" x2="0" y2="${PAD.top+CH}" stroke="rgba(255,255,255,0.4)" stroke-width="1" stroke-dasharray="3,3" style="pointer-events:none" opacity="0"/>`;
  const zoomRect = `<rect id="perf-zr-${containerId}" x="0" y="${PAD.top}" width="0" height="${CH}" fill="rgba(99,102,241,0.12)" stroke="rgba(99,102,241,0.5)" stroke-width="1" style="pointer-events:none" opacity="0"/>`;
  const zoomResetBtn = _perfZoom
    ? `<button onclick="_resetPerfZoom('${containerId}')" style="position:absolute;top:2px;left:${PAD.left+4}px;font-size:9px;padding:2px 6px;background:rgba(99,102,241,0.2);border:1px solid rgba(99,102,241,0.5);border-radius:4px;cursor:pointer;color:#a5b4fc">↩ Réinitialiser zoom</button>`
    : '';

  container.innerHTML = `
    <div style="position:relative;user-select:none">
      <svg id="perf-svg-${containerId}" viewBox="0 0 ${W} ${H}" width="100%" height="${H}" style="display:block;overflow:visible;cursor:crosshair">
        ${gridLines}${baseLine}${xLabels}${lines}${crosshair}${zoomRect}
      </svg>
      <div id="perf-tooltip-${containerId}" style="display:none;position:absolute;background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:10px;line-height:1.6;pointer-events:none;z-index:10;box-shadow:0 2px 8px rgba(0,0,0,.3);min-width:100px"></div>
      ${zoomResetBtn}
    </div>`;

  _perfChartStates[containerId] = {W, H, PAD, CW, CH, allDates, normalized, minV, maxV, rangeV, tickers};
  _attachPerfInteractivity(containerId);

  if (containerId === 'perf-chart') _renderPerfLegend(containerId, normalized);
}

function _attachPerfInteractivity(containerId) {
  const svg = document.getElementById(`perf-svg-${containerId}`);
  if (!svg) return;
  const state = _perfChartStates[containerId];
  if (!state) return;
  const {W, H, PAD, CW, CH, allDates, normalized} = state;

  const ch = document.getElementById(`perf-ch-${containerId}`);
  const tt = document.getElementById(`perf-tooltip-${containerId}`);
  const zr = document.getElementById(`perf-zr-${containerId}`);

  let dragStartX = null, isDragging = false;

  const svgX = (clientX) => {
    const rect = svg.getBoundingClientRect();
    return (clientX - rect.left) * (W / rect.width);
  };

  const idxFromX = (x) => Math.max(0, Math.min(allDates.length - 1,
    Math.round((x - PAD.left) / CW * (allDates.length - 1))));

  svg.addEventListener('mousemove', e => {
    const x = svgX(e.clientX);
    if (x < PAD.left || x > PAD.left + CW) {
      if (ch) ch.setAttribute('opacity', '0');
      if (tt) tt.style.display = 'none';
      return;
    }
    const idx = idxFromX(x);
    const date = allDates[idx];
    const cx = PAD.left + (idx / (allDates.length - 1 || 1)) * CW;

    if (ch) { ch.setAttribute('x1', cx); ch.setAttribute('x2', cx); ch.setAttribute('opacity', '1'); }

    if (tt) {
      const items = normalized
        .filter(d => d.visible && d.values[idx] !== null && d.values[idx] !== undefined)
        .map(d => {
          const v = d.values[idx];
          const sign = v >= 100 ? '+' : '';
          return `<div><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${d.color};margin-right:4px;vertical-align:middle"></span><span style="color:${d.color};font-weight:700">${d.ticker}</span> <span style="${v>=100?'color:var(--green)':'color:var(--red)'}">${sign}${(v-100).toFixed(1)}%</span></div>`;
        });
      if (items.length) {
        tt.innerHTML = `<div style="color:var(--t3);margin-bottom:3px;font-size:9px">${date}</div>${items.join('')}`;
        const svgRect = svg.getBoundingClientRect();
        const ttX = (cx / W) * svgRect.width;
        const flip = ttX > svgRect.width * 0.6;
        tt.style.left = (flip ? ttX - 140 : ttX + 8) + 'px';
        tt.style.top = PAD.top + 'px';
        tt.style.display = 'block';
      }
    }

    if (isDragging && dragStartX !== null && zr) {
      const dx = x - dragStartX;
      if (dx > 0) { zr.setAttribute('x', dragStartX); zr.setAttribute('width', dx); }
      else { zr.setAttribute('x', x); zr.setAttribute('width', -dx); }
      zr.setAttribute('opacity', '1');
    }
  });

  svg.addEventListener('mouseleave', () => {
    if (ch) ch.setAttribute('opacity', '0');
    if (tt) tt.style.display = 'none';
    if (!isDragging && zr) zr.setAttribute('opacity', '0');
  });

  svg.addEventListener('mousedown', e => {
    const x = svgX(e.clientX);
    if (x >= PAD.left && x <= PAD.left + CW) {
      isDragging = true;
      dragStartX = x;
      if (zr) { zr.setAttribute('x', x); zr.setAttribute('width', '0'); zr.setAttribute('opacity', '0'); }
    }
  });

  svg.addEventListener('mouseup', e => {
    if (!isDragging) return;
    isDragging = false;
    const x = svgX(e.clientX);
    const startX = Math.min(dragStartX, x);
    const endX = Math.max(dragStartX, x);
    dragStartX = null;
    if (endX - startX > 12) {
      const startIdx = idxFromX(startX);
      const endIdx = idxFromX(endX);
      if (endIdx > startIdx + 1) {
        _perfZoom = {startDate: allDates[startIdx], endDate: allDates[endIdx]};
        _drawPerfChart(containerId, state.tickers);
        return;
      }
    }
    if (zr) zr.setAttribute('opacity', '0');
  });

  svg.addEventListener('dblclick', () => {
    _perfZoom = null;
    _drawPerfChart(containerId, state.tickers);
  });
}

function _resetPerfZoom(containerId) {
  _perfZoom = null;
  const state = _perfChartStates[containerId];
  if (state) _drawPerfChart(containerId, state.tickers);
}

function _renderPerfLegend(containerId, normalized) {
  const legendEl = document.getElementById('perf-legend');
  if (!legendEl) return;
  legendEl.innerHTML = normalized.map(d => {
    const op = d.visible ? '1' : '0.4';
    return `<button onclick="_togglePerfLegend('${containerId}','${d.ticker}')"
      title="${d.visible ? 'Cliquez pour masquer' : 'Cliquez pour afficher'}"
      style="font-size:10px;padding:3px 8px;border-radius:4px;border:1px solid ${d.color};background:${d.color}22;color:${d.color};cursor:pointer;opacity:${op};transition:opacity .2s">
      <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${d.color};margin-right:3px;vertical-align:middle"></span>${d.ticker}</button>`;
  }).join('');
}

function _togglePerfLegend(containerId, ticker) {
  if (!_perfVisible[containerId]) _perfVisible[containerId] = new Set();
  const vis = _perfVisible[containerId];
  const visCount = [...vis].filter(t => vis.has(t)).length;
  if (vis.has(ticker)) {
    if (visCount <= 1) return;
    vis.delete(ticker);
  } else {
    vis.add(ticker);
  }
  const state = _perfChartStates[containerId];
  if (state) _drawPerfChart(containerId, state.tickers);
}
