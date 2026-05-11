// ── Page Performances historiques — performance.js ────────────────────────

let _perfData = {};
let _perfSelected = [];
const PERF_COLORS = ['#4ADE80','#60A5FA','#FBBF24','#F87171','#C084FC','#34D399','#FB923C','#A78BFA'];

async function renderPerfPage() {
  const container = document.getElementById('perfPageContent');
  if (!container) return;
  container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--t2)">Chargement historique...</div>';

  const all = window.scores || scores || [];
  if (!all.length) return;

  // Charger historique depuis API
  try {
    const res = await fetch('/api/price-history');
    _perfData = await res.json();
  } catch(e) {
    container.innerHTML = '<div style="color:var(--red);padding:20px">Erreur chargement historique</div>';
    return;
  }

  // Top performers depuis historique
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

  // Sélection par défaut: Top 5
  if (_perfSelected.length === 0) {
    _perfSelected = performers.slice(0,5).map(p=>p.ticker);
  }

  container.innerHTML = `
    <div class="card" style="margin-bottom:12px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <div class="ct">📈 Évolution des cours (2019–2026)</div>
        <div style="display:flex;gap:6px;flex-wrap:wrap" id="perf-period-btns">
          ${['1an','3ans','5ans','Tout'].map(p=>`
            <button onclick="setPerfPeriod('${p}')" id="btn-period-${p}"
              style="font-size:10px;padding:3px 8px;border-radius:4px;border:1px solid var(--border);background:var(--bg3);color:var(--t2);cursor:pointer">${p}</button>`).join('')}
        </div>
      </div>
      <div id="perf-chart" style="width:100%;height:280px"></div>
    </div>
    <div class="g2" style="margin-bottom:12px">
      <div class="card" style="margin-bottom:0">
        <div class="ct">🏆 Meilleures performances</div>
        <div id="perf-top-list"></div>
      </div>
      <div class="card" style="margin-bottom:0">
        <div class="ct">📉 Moins bonnes performances</div>
        <div id="perf-flop-list"></div>
      </div>
    </div>
    <div class="card">
      <div class="ct">Sélectionner actions à comparer (max 8)</div>
      <div id="perf-selector" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px"></div>
      <div id="perf-chart2" style="width:100%;height:220px"></div>
    </div>`;

  // Remplir top/flop
  _renderPerfList('perf-top-list', performers.slice(0,8), true);
  _renderPerfList('perf-flop-list', [...performers].sort((a,b)=>a.perf-b.perf).slice(0,8), false);

  // Sélecteur
  _renderPerfSelector(all, performers);

  // Graphique principal
  _drawPerfChart('perf-chart', _perfSelected);
  _drawPerfChart('perf-chart2', _perfSelected);

  // Activer bouton "Tout"
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
  el.innerHTML = performers.map((p,i) => {
    const c = p.perf >= 0 ? 'var(--green)' : 'var(--red)';
    const sign = p.perf >= 0 ? '+' : '';
    const p1y = p.perf1y != null ? `<span style="font-size:9px;color:var(--t2);margin-left:4px">1an: ${p.perf1y>=0?'+':''}${p.perf1y.toFixed(0)}%</span>` : '';
    return `<div onclick="togglePerfTicker('${p.ticker}')" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid var(--border)">
      <div>
        <span style="font-weight:700;font-size:12px">${p.ticker}</span>
        <span style="font-size:10px;color:var(--t2);margin-left:4px">${p.name.substring(0,20)}</span>
        ${p1y}
      </div>
      <span style="color:${c};font-weight:700;font-size:12px">${sign}${p.perf.toFixed(1)}%</span>
    </div>`;
  }).join('');
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
    if (_perfSelected.length >= 8) { showNotif('Maximum 8 actions', 'red'); return; }
    _perfSelected.push(ticker);
  }
  // Mettre à jour bouton
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

let _perfPeriod = 'Tout';
function setPerfPeriod(period) {
  _perfPeriod = period;
  document.querySelectorAll('[id^="btn-period-"]').forEach(b => {
    b.style.background = 'var(--bg3)'; b.style.color = 'var(--t2)'; b.style.borderColor = 'var(--border)';
  });
  const btn = document.getElementById(`btn-period-${period}`);
  if (btn) { btn.style.background = 'var(--blue)22'; btn.style.color = 'var(--blue)'; btn.style.borderColor = 'var(--blue)'; }
  _drawPerfChart('perf-chart', _perfSelected);
}

function _filterByPeriod(pts) {
  if (_perfPeriod === 'Tout') return pts;
  const years = {'1an':1,'3ans':3,'5ans':5}[_perfPeriod]||10;
  const now = new Date();
  const cutoff = new Date(now); cutoff.setFullYear(now.getFullYear()-years);
  const cutStr = cutoff.toISOString().slice(0,10);
  return pts.filter(p=>p.date>=cutStr);
}

function _drawPerfChart(containerId, tickers) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const datasets = tickers.map((ticker,i) => {
    const pts = _filterByPeriod((_perfData[ticker]||[]).sort((a,b)=>a.date.localeCompare(b.date)));
    return {ticker, pts, color: PERF_COLORS[i % PERF_COLORS.length]};
  }).filter(d=>d.pts.length>1);

  if (!datasets.length) { container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--t2)">Sélectionnez des actions</div>'; return; }

  // Normaliser à base 100
  const W = container.clientWidth || 600;
  const H = containerId === 'perf-chart' ? 280 : 220;
  const PAD = {top:20, right:80, bottom:30, left:45};
  const CW = W-PAD.left-PAD.right, CH = H-PAD.top-PAD.bottom;

  // Toutes les dates uniques
  const allDates = [...new Set(datasets.flatMap(d=>d.pts.map(p=>p.date)))].sort();
  if (allDates.length < 2) return;

  // Normaliser base 100
  const normalized = datasets.map(d => {
    const base = d.pts[0].price;
    const byDate = Object.fromEntries(d.pts.map(p=>[p.date,p.price]));
    return {
      ...d,
      values: allDates.map(date => {
        // Interpoler si date manquante
        const p = byDate[date];
        if (p) return (p/base)*100;
        const prev = d.pts.filter(x=>x.date<=date).pop();
        return prev ? (prev.price/base)*100 : null;
      }).filter(v=>v!==null)
    };
  });

  const allValues = normalized.flatMap(d=>d.values).filter(Boolean);
  const minV = Math.min(...allValues)*0.98, maxV = Math.max(...allValues)*1.02;
  const rangeV = maxV-minV||1;

  const xScale = i => PAD.left + (i/(allDates.length-1))*CW;
  const yScale = v => PAD.top + CH - ((v-minV)/rangeV)*CH;

  // Lignes grille
  const gridLines = [0,1,2,3,4].map(i=>{
    const v = minV + rangeV*i/4;
    const y = yScale(v);
    return `<line x1="${PAD.left}" y1="${y}" x2="${PAD.left+CW}" y2="${y}" stroke="rgba(255,255,255,0.05)" stroke-width="1"/>
            <text x="${PAD.left-4}" y="${y+4}" text-anchor="end" font-size="9" fill="rgba(255,255,255,0.3)">${v.toFixed(0)}</text>`;
  }).join('');

  // Ligne base 100
  const base100Y = yScale(100);
  const baseLine = `<line x1="${PAD.left}" y1="${base100Y}" x2="${PAD.left+CW}" y2="${base100Y}" stroke="rgba(255,255,255,0.15)" stroke-width="1" stroke-dasharray="4,3"/>
                    <text x="${PAD.left-4}" y="${base100Y+4}" text-anchor="end" font-size="9" fill="rgba(255,255,255,0.4)">100</text>`;

  // Labels X (6 max)
  const step = Math.ceil(allDates.length/6);
  const xLabels = allDates.map((d,i)=>{
    if(i%step!==0&&i!==allDates.length-1) return '';
    return `<text x="${xScale(i)}" y="${H-4}" text-anchor="middle" font-size="9" fill="rgba(255,255,255,0.3)">${d.slice(0,7)}</text>`;
  }).join('');

  // Courbes
  const lines = normalized.map(d=>{
    const pts = d.values.map((v,i)=>`${xScale(i)},${yScale(v)}`).join(' ');
    const lastV = d.values[d.values.length-1];
    const lastX = xScale(d.values.length-1), lastY = yScale(lastV);
    const sign = lastV>=100?'+':'';
    return `<polyline points="${pts}" fill="none" stroke="${d.color}" stroke-width="1.8" stroke-linejoin="round" opacity="0.9"/>
            <circle cx="${lastX}" cy="${lastY}" r="3" fill="${d.color}"/>
            <text x="${lastX+5}" y="${lastY+4}" font-size="9" font-weight="700" fill="${d.color}">${d.ticker} ${sign}${(lastV-100).toFixed(0)}%</text>`;
  }).join('');

  container.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" style="display:block;overflow:visible">
    ${gridLines}${baseLine}${xLabels}${lines}
  </svg>`;
}
