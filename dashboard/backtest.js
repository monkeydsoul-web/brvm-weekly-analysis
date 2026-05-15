// ── Backtesting portefeuille — backtest.js ────────────────────────────────

let _btTickers = [];
let _btWeights = {};
let _btResult = null;
let _btPeriod = '1an';
let _btCapital = 1000000;

function openBacktest(preselected) {
  let modal = document.getElementById('bt-modal');
  if (!modal) modal = createBacktestModal();
  if (preselected?.length) _btTickers = [...preselected];
  _refreshBTSelector();
  modal.style.display = 'flex';
}

function createBacktestModal() {
  const modal = document.createElement('div');
  modal.id = 'bt-modal';
  modal.style = 'display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.85);align-items:center;justify-content:center;padding:16px';
  modal.innerHTML = `
    <div style="background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:24px;max-width:960px;width:100%;max-height:93vh;overflow-y:auto;position:relative">
      <button onclick="closeBT()" style="position:absolute;top:14px;right:14px;background:var(--bg3);border:1px solid var(--border);border-radius:6px;color:var(--t2);padding:4px 12px;cursor:pointer">✕</button>
      <h2 style="font-size:18px;font-weight:700;margin-bottom:4px">📊 Backtesting portefeuille BRVM</h2>
      <p style="font-size:12px;color:var(--t2);margin-bottom:16px">Simulez la performance historique d'un portefeuille sur les données BOC réelles</p>

      <!-- Sélecteur tickers -->
      <div style="margin-bottom:12px">
        <div style="font-size:11px;color:var(--t2);margin-bottom:6px">Actions sélectionnées (max 8) :</div>
        <div id="bt-selected" style="display:flex;flex-wrap:wrap;gap:6px;min-height:36px;padding:8px;background:var(--bg3);border-radius:8px;border:1px solid var(--border)"></div>
      </div>
      <div style="margin-bottom:12px">
        <div id="bt-picker" style="display:flex;flex-wrap:wrap;gap:5px;max-height:100px;overflow-y:auto"></div>
      </div>

      <!-- Sélection rapide -->
      <div style="display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap">
        <span style="font-size:11px;color:var(--t2);align-self:center">Rapide:</span>
        ${['Top5','Banques','Télécoms','Hauts div.','Effacer'].map(g=>`<button onclick="btGroup('${g}')" style="font-size:10px;padding:3px 8px;background:var(--bg3);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:${g==='Effacer'?'var(--red)':'var(--t2)'}">${g}</button>`).join('')}
      </div>

      <!-- Paramètres -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px">
        <div>
          <div style="font-size:11px;color:var(--t2);margin-bottom:4px">Période :</div>
          <div style="display:flex;gap:6px">
            ${['1an','3ans','5ans','tout'].map(p=>`<button id="btn-bt-${p}" onclick="setBTPeriod('${p}')" style="font-size:10px;padding:4px 10px;border-radius:4px;border:1px solid var(--border);background:${p==='1an'?'var(--blue)22':'var(--bg3)'};color:${p==='1an'?'var(--blue)':'var(--t2)'};cursor:pointer">${p}</button>`).join('')}
          </div>
        </div>
        <div>
          <div style="font-size:11px;color:var(--t2);margin-bottom:4px">Capital initial (FCFA) :</div>
          <input id="bt-capital" type="number" value="1000000" min="100000" step="100000"
            style="width:100%;padding:6px 10px;background:var(--bg3);border:1px solid var(--border);border-radius:6px;color:var(--t1);font-size:12px;box-sizing:border-box"
            oninput="_btCapital=parseInt(this.value)||1000000"/>
        </div>
      </div>

      <!-- Pondérations -->
      <div id="bt-weights-div" style="margin-bottom:14px;display:none">
        <div style="font-size:11px;color:var(--t2);margin-bottom:6px">Pondérations personnalisées :</div>
        <div id="bt-weights-inputs" style="display:flex;flex-wrap:wrap;gap:8px"></div>
      </div>

      <button onclick="launchBacktest()"
        style="width:100%;padding:12px;background:linear-gradient(135deg,#60A5FA,#4ADE80);border:none;border-radius:8px;color:#000;font-weight:700;font-size:13px;cursor:pointer;margin-bottom:16px">
        📊 Lancer le backtesting
      </button>

      <!-- Résultats -->
      <div id="bt-result" style="display:none">
        <div style="border-top:1px solid var(--border);padding-top:16px">
          <!-- KPIs -->
          <div id="bt-kpis" style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px"></div>
          <!-- Graphique -->
          <div class="card" style="margin-bottom:12px">
            <div class="ct">📈 Évolution du portefeuille (base 100)</div>
            <div id="bt-chart" style="width:100%;height:220px"></div>
          </div>
          <!-- Tableau détail -->
          <div class="card">
            <div class="ct">Détail par action</div>
            <table style="width:100%;border-collapse:collapse;font-size:11px">
              <thead><tr style="border-bottom:1px solid var(--border)">
                <th style="text-align:left;padding:4px 6px;color:var(--t2)">Ticker</th>
                <th style="text-align:right;padding:4px 6px;color:var(--t2)">Poids</th>
                <th style="text-align:right;padding:4px 6px;color:var(--t2)">Début</th>
                <th style="text-align:right;padding:4px 6px;color:var(--t2)">Fin</th>
                <th style="text-align:right;padding:4px 6px;color:var(--t2)">Perf.</th>
                <th style="text-align:right;padding:4px 6px;color:var(--t2)">Contribution</th>
                <th style="text-align:right;padding:4px 6px;color:var(--t2)">Points</th>
              </tr></thead>
              <tbody id="bt-table"></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>`;

  modal.addEventListener('click', e => { if (e.target === modal) closeBT(); });
  document.body.appendChild(modal);
  return modal;
}

function _refreshBTSelector() {
  const all = window.scores || scores || [];
  const sorted = [...all].sort((a,b) => (b.composite_adj||0)-(a.composite_adj||0));

  const selEl = document.getElementById('bt-selected');
  if (selEl) {
    selEl.innerHTML = _btTickers.map(t => {
      const s = all.find(x=>x.ticker===t);
      const v = s?.composite_adj||0;
      const c = v>=60?'var(--green)':v>=40?'var(--amber)':'var(--red)';
      const w = Math.round((_btWeights[t]||1/_btTickers.length)*100);
      return `<span style="display:flex;align-items:center;gap:4px;background:var(--bg2);border:1px solid ${c};border-radius:6px;padding:3px 8px;font-size:11px">
        <strong style="color:${c}">${t}</strong>
        <span style="color:var(--t3);font-size:10px">${w}%</span>
        <button onclick="btRemove('${t}')" style="background:none;border:none;color:var(--red);cursor:pointer;padding:0 2px">✕</button>
      </span>`;
    }).join('') || '<span style="color:var(--t3);font-size:11px">Sélectionnez des actions</span>';
  }

  const picker = document.getElementById('bt-picker');
  if (picker) {
    picker.innerHTML = sorted.map(x => {
      const sel = _btTickers.includes(x.ticker);
      const v = x.composite_adj||0;
      const c = v>=60?'var(--green)':v>=40?'var(--amber)':'var(--red)';
      return `<button onclick="btToggle('${x.ticker}')"
        style="font-size:10px;padding:2px 7px;border-radius:4px;border:1px solid ${sel?c:'var(--border)'};background:${sel?c+'22':'var(--bg3)'};color:${sel?c:'var(--t2)'};cursor:pointer">
        ${x.ticker} <span style="opacity:0.6">${v.toFixed(0)}</span></button>`;
    }).join('');
  }

  // Pondérations
  const wdiv = document.getElementById('bt-weights-div');
  const winputs = document.getElementById('bt-weights-inputs');
  if (wdiv && winputs && _btTickers.length > 0) {
    wdiv.style.display = 'block';
    const eqW = (100/_btTickers.length).toFixed(1);
    winputs.innerHTML = _btTickers.map(t => `
      <div style="display:flex;align-items:center;gap:4px;background:var(--bg3);padding:4px 8px;border-radius:6px">
        <span style="font-weight:700;font-size:11px;min-width:45px">${t}</span>
        <input type="number" min="1" max="100" value="${eqW}" step="5" id="w-${t}"
          style="width:55px;padding:3px 6px;background:var(--bg2);border:1px solid var(--border);border-radius:4px;color:var(--t1);font-size:11px"
          oninput="btUpdateWeights()"/>
        <span style="font-size:10px;color:var(--t2)">%</span>
      </div>`).join('');
    btUpdateWeights();
  }
}

function btUpdateWeights() {
  let total = 0;
  _btTickers.forEach(t => {
    const val = parseFloat(document.getElementById('w-'+t)?.value || 0);
    _btWeights[t] = val / 100;
    total += val;
  });
  // Normaliser
  if (total > 0 && Math.abs(total - 100) > 1) {
    _btTickers.forEach(t => { _btWeights[t] = _btWeights[t] / (total/100); });
  }
}

function btToggle(t) {
  if (_btTickers.includes(t)) _btTickers = _btTickers.filter(x=>x!==t);
  else { if (_btTickers.length >= 8) { return; } _btTickers.push(t); }
  _refreshBTSelector();
}
function btRemove(t) { _btTickers = _btTickers.filter(x=>x!==t); _refreshBTSelector(); }
function btGroup(g) {
  const all = window.scores||scores||[];
  const sorted = [...all].sort((a,b)=>(b.composite_adj||0)-(a.composite_adj||0));
  if (g==='Effacer') _btTickers=[];
  else if (g==='Top5') _btTickers=sorted.slice(0,5).map(x=>x.ticker);
  else if (g==='Banques') _btTickers=sorted.filter(x=>x.sector?.includes('Banque')).slice(0,5).map(x=>x.ticker);
  else if (g==='Télécoms') _btTickers=sorted.filter(x=>x.sector?.includes('Télécom')||x.sector?.includes('Telecom')).slice(0,4).map(x=>x.ticker);
  else if (g==='Hauts div.') _btTickers=[...all].sort((a,b)=>(b.div_yield||0)-(a.div_yield||0)).slice(0,5).map(x=>x.ticker);
  _refreshBTSelector();
}
function setBTPeriod(p) {
  _btPeriod = p;
  ['1an','3ans','5ans','tout'].forEach(x => {
    const b = document.getElementById('btn-bt-'+x);
    if (b) { b.style.background = x===p?'var(--blue)22':'var(--bg3)'; b.style.color = x===p?'var(--blue)':'var(--t2)'; b.style.borderColor = x===p?'var(--blue)':'var(--border)'; }
  });
}
function closeBT() { const m = document.getElementById('bt-modal'); if (m) m.style.display='none'; }

async function launchBacktest() {
  if (_btTickers.length < 2) { return; }
  btUpdateWeights();
  const resultDiv = document.getElementById('bt-result');
  document.getElementById('bt-kpis').innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:20px;color:var(--t2)">⏳ Calcul en cours...</div>';
  resultDiv.style.display = 'block';

  try {
    const res = await fetch('/api/backtest', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({tickers:_btTickers, weights:_btWeights, period:_btPeriod, capital:_btCapital})
    });
    const d = await res.json();
    if (d.error) throw new Error(d.error);
    _btResult = d;
    _renderBTResult(d);
  } catch(e) {
    document.getElementById('bt-kpis').innerHTML = `<div style="grid-column:1/-1;color:var(--red)">Erreur: ${e.message}</div>`;
  }
}

function _renderBTResult(d) {
  const perfColor = d.portfolio_perf_pct >= 0 ? 'var(--green)' : 'var(--red)';
  const gainSign = d.gain >= 0 ? '+' : '';
  
  // KPIs
  document.getElementById('bt-kpis').innerHTML = [
    ['Performance', `${d.portfolio_perf_pct >= 0?'+':''}${d.portfolio_perf_pct.toFixed(1)}%`, perfColor],
    ['Capital final', `${d.final_value.toLocaleString('fr-FR')} F`, perfColor],
    ['Gain/Perte', `${gainSign}${d.gain.toLocaleString('fr-FR')} F`, perfColor],
    ['Période', d.period + ` (${d.nb_tickers} titres)`, 'var(--t2)'],
  ].map(([l,v,c]) => `<div style="background:var(--bg3);border-radius:8px;padding:12px;text-align:center">
    <div style="font-size:10px;color:var(--t2);margin-bottom:4px">${l}</div>
    <div style="font-size:16px;font-weight:700;color:${c}">${v}</div>
  </div>`).join('');

  // Graphique SVG
  _drawBTChart(d);

  // Tableau
  document.getElementById('bt-table').innerHTML = d.results.map(r => {
    const pc = r.perf_pct >= 0 ? 'var(--green)' : 'var(--red)';
    const cc = r.contribution >= 0 ? 'var(--green)' : 'var(--red)';
    return `<tr onclick="showStock('${r.ticker}')" style="cursor:pointer;border-bottom:1px solid var(--border)">
      <td style="padding:5px 6px;font-weight:700">${r.ticker}</td>
      <td style="padding:5px 6px;text-align:right;color:var(--t2)">${(r.weight*100).toFixed(1)}%</td>
      <td style="padding:5px 6px;text-align:right">${r.start_price.toLocaleString('fr-FR')}</td>
      <td style="padding:5px 6px;text-align:right">${r.end_price.toLocaleString('fr-FR')}</td>
      <td style="padding:5px 6px;text-align:right;color:${pc};font-weight:700">${r.perf_pct>=0?'+':''}${r.perf_pct.toFixed(1)}%</td>
      <td style="padding:5px 6px;text-align:right;color:${cc}">${r.contribution>=0?'+':''}${r.contribution.toFixed(2)}%</td>
      <td style="padding:5px 6px;text-align:right;color:var(--t3)">${r.nb_points}</td>
    </tr>`;
  }).join('');
}

function _drawBTChart(d) {
  const container = document.getElementById('bt-chart');
  if (!container) return;
  const W = container.clientWidth || 600, H = 220;
  const PAD = {top:20, right:80, bottom:28, left:45};
  const CW = W-PAD.left-PAD.right, CH = H-PAD.top-PAD.bottom;
  const COLORS = ['#4ADE80','#60A5FA','#FBBF24','#F87171','#C084FC','#34D399','#FB923C','#A78BFA'];

  // Collecter toutes les séries
  const series = [];
  // Portefeuille global
  if (d.portfolio_series?.length >= 2) {
    series.push({label:'Portfolio', pts: d.portfolio_series, color:'#FFFFFF', width:2.5});
  }
  // Tickers individuels
  Object.entries(d.ticker_series||{}).forEach(([t,pts],i) => {
    if (pts?.length >= 2) series.push({label:t, pts, color:COLORS[i%COLORS.length], width:1.2});
  });
  if (!series.length) { container.innerHTML='<p style="color:var(--t2);text-align:center;padding:40px">Données insuffisantes</p>'; return; }

  const allVals = series.flatMap(s=>s.pts.map(p=>p.value));
  const allDates = series[0].pts.map(p=>p.date);
  const minV = Math.min(...allVals)*0.98, maxV = Math.max(...allVals)*1.02;
  const rangeV = maxV-minV||1;

  const xS = i => PAD.left+(i/(allDates.length-1||1))*CW;
  const yS = v => PAD.top+CH-((v-minV)/rangeV)*CH;

  // Grid
  let svg = '';
  for (let g=0;g<=4;g++) {
    const v = minV+rangeV*g/4, y = yS(v);
    svg += `<line x1="${PAD.left}" y1="${y}" x2="${PAD.left+CW}" y2="${y}" stroke="rgba(255,255,255,0.06)" stroke-width="1"/>
            <text x="${PAD.left-4}" y="${y+4}" text-anchor="end" font-size="9" fill="rgba(255,255,255,0.3)">${v.toFixed(0)}</text>`;
  }
  // Base 100
  const y100 = yS(100);
  svg += `<line x1="${PAD.left}" y1="${y100}" x2="${PAD.left+CW}" y2="${y100}" stroke="rgba(255,255,255,0.2)" stroke-width="1" stroke-dasharray="4,3"/>`;

  // Labels X
  const step = Math.ceil(allDates.length/5);
  allDates.forEach((d,i) => {
    if (i%step===0||i===allDates.length-1)
      svg += `<text x="${xS(i)}" y="${H-4}" text-anchor="middle" font-size="9" fill="rgba(255,255,255,0.3)">${d.slice(0,7)}</text>`;
  });

  // Courbes
  series.forEach(s => {
    const pts = s.pts.map((p,i) => `${xS(i)},${yS(p.value)}`).join(' ');
    const last = s.pts[s.pts.length-1];
    const lx = xS(s.pts.length-1), ly = yS(last.value);
    const sign = last.value>=100?'+':'';
    svg += `<polyline points="${pts}" fill="none" stroke="${s.color}" stroke-width="${s.width}" opacity="0.9"/>
            <circle cx="${lx}" cy="${ly}" r="3" fill="${s.color}"/>
            <text x="${lx+5}" y="${ly+4}" font-size="9" font-weight="700" fill="${s.color}">${s.label} ${sign}${(last.value-100).toFixed(0)}%</text>`;
  });

  container.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" style="display:block;overflow:visible">${svg}</svg>`;
}
