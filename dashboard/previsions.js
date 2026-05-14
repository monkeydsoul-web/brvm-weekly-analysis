// ── Page Prévisions IA — previsions.js ────────────────────────────────────

let _prevTab = 'portfolios';
let _prevPortfolios = null;
let _prevSignaux = null;
let _prevBacktest = null;
let _sigFilter = '';

async function renderPrevisionsPage() {
  const container = document.getElementById('page-previsions-content');
  if (!container) return;

  container.innerHTML = `
    <div style="display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:14px;overflow-x:auto">
      ${[
        ['portfolios','💼 Portefeuilles IA'],
        ['signaux','📡 Signaux'],
        ['backtest','🔬 Backtesting'],
        ['rapport','📄 Rapport'],
      ].map(([id,lbl])=>`<div class="stock-tab${_prevTab===id?' active':''}" onclick="_prevSetTab('${id}')">${lbl}</div>`).join('')}
    </div>
    <div id="prev-portfolios-panel"  class="stock-tab-panel${_prevTab==='portfolios'?' active':''}"></div>
    <div id="prev-signaux-panel"     class="stock-tab-panel${_prevTab==='signaux'?' active':''}"></div>
    <div id="prev-backtest-panel"    class="stock-tab-panel${_prevTab==='backtest'?' active':''}"></div>
    <div id="prev-rapport-panel"     class="stock-tab-panel${_prevTab==='rapport'?' active':''}"></div>`;

  _prevLoadTab(_prevTab);
}

function _prevSetTab(id) {
  _prevTab = id;
  document.querySelectorAll('#page-previsions-content .stock-tab').forEach(t => {
    t.classList.toggle('active', t.textContent.includes(id === 'portfolios' ? 'Porte' : id === 'signaux' ? 'Signal' : id === 'backtest' ? 'Back' : 'Rapport'));
  });
  document.querySelectorAll('#page-previsions-content .stock-tab-panel').forEach(p => p.classList.remove('active'));
  const panel = document.getElementById(`prev-${id}-panel`);
  if (panel) panel.classList.add('active');
  _prevLoadTab(id);
}

function _prevLoadTab(id) {
  if (id === 'portfolios') _prevRenderPortfolios();
  else if (id === 'signaux') _prevRenderSignaux();
  else if (id === 'backtest') _prevRenderBacktest();
  else if (id === 'rapport') _prevRenderRapport();
}

// ── Portfolios ────────────────────────────────────────────────────────────────

async function _prevRenderPortfolios() {
  const el = document.getElementById('prev-portfolios-panel');
  if (!el) return;
  if (_prevPortfolios) { _prevDrawPortfolios(el); return; }
  el.innerHTML = '<div style="text-align:center;padding:40px;color:var(--t2)">Calcul des portefeuilles en cours...</div>';
  try {
    const res = await fetch('/api/previsions/portfolios');
    _prevPortfolios = await res.json();
    if (_prevPortfolios.error) throw new Error(_prevPortfolios.error);
    _prevDrawPortfolios(el);
  } catch(e) {
    el.innerHTML = `<p style="color:var(--red);padding:20px">Erreur: ${e.message}</p>`;
  }
}

const _riskColor = { 'Faible': 'var(--green)', 'Modéré': 'var(--amber)', 'Élevé': 'var(--red)' };
const _riskBg    = { 'Faible': 'rgba(74,222,128,.08)', 'Modéré': 'rgba(251,191,36,.08)', 'Élevé': 'rgba(248,113,113,.08)' };

function _prevDrawPortfolios(el) {
  if (!_prevPortfolios) return;
  el.innerHTML = `
    <div style="font-size:11px;color:var(--t2);margin-bottom:12px;background:var(--bg3);border-radius:8px;padding:10px 14px;border-left:3px solid var(--blue)">
      📌 <strong>Comment lire ces portefeuilles :</strong> Construits à partir des 47 sociétés cotées, des scores composites et des données historiques BOC 30 jours. Les rendements attendus combinent dividendes historiques + tendance de cours. <em>Ces prévisions sont indicatives et ne constituent pas un conseil en investissement.</em>
    </div>
    <div class="g3">
      ${_prevPortfolios.map(pf => `
        <div class="card" style="margin-bottom:0;border-top:3px solid ${_riskColor[pf.risk]||'var(--blue)'}">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
            <div>
              <div style="font-size:15px;font-weight:700;color:var(--text)">${pf.name}</div>
              <div style="font-size:10px;padding:2px 8px;border-radius:10px;display:inline-block;background:${_riskBg[pf.risk]||''};color:${_riskColor[pf.risk]||'var(--t2)'};margin-top:3px">Risque ${pf.risk}</div>
            </div>
            <div style="text-align:right">
              <div style="font-size:18px;font-weight:700;color:${_riskColor[pf.risk]||'var(--green)'}">+${pf.target_min}–${pf.target_max}%</div>
              <div style="font-size:9px;color:var(--t3)">objectif 12 mois</div>
            </div>
          </div>
          <div style="font-size:10px;color:var(--t2);margin-bottom:10px;line-height:1.5">${pf.rationale}</div>
          <div style="display:flex;gap:12px;margin-bottom:10px;flex-wrap:wrap">
            <div style="text-align:center">
              <div style="font-size:9px;color:var(--t3)">Rend. attendu</div>
              <div style="font-size:14px;font-weight:700;color:var(--green)">${pf.exp_return}%</div>
            </div>
            <div style="text-align:center">
              <div style="font-size:9px;color:var(--t3)">Volatilité</div>
              <div style="font-size:14px;font-weight:700;color:var(--amber)">${pf.volatility}%</div>
            </div>
            <div style="text-align:center">
              <div style="font-size:9px;color:var(--t3)">Sharpe</div>
              <div style="font-size:14px;font-weight:700;color:var(--blue)">${pf.sharpe}</div>
            </div>
          </div>
          <div style="margin-bottom:10px">
            ${(pf.stocks||[]).map(s => `
              <div style="display:flex;align-items:center;gap:6px;padding:5px 0;border-bottom:1px solid var(--border);cursor:pointer" onclick="showStock('${s.ticker}')">
                <div style="width:6px;height:6px;border-radius:50%;background:${_riskColor[pf.risk]||'var(--blue)'}"></div>
                <strong style="font-size:11px;min-width:44px">${s.ticker}</strong>
                <div style="flex:1">
                  <div style="background:var(--bg3);border-radius:3px;height:10px;position:relative;overflow:hidden">
                    <div style="position:absolute;left:0;top:0;height:100%;width:${s.weight}%;background:${_riskColor[pf.risk]||'var(--blue)'}33;transition:width .5s"></div>
                  </div>
                </div>
                <span style="font-size:10px;font-weight:600;min-width:34px;text-align:right">${s.weight}%</span>
                <span style="font-size:9px;color:var(--t2);min-width:52px;text-align:right">score ${s.score.toFixed(0)}</span>
                <span style="font-size:9px;color:var(--amber);min-width:36px;text-align:right">${(s.div_yield||0).toFixed(1)}%</span>
              </div>`).join('')}
          </div>
          <div style="display:flex;gap:8px">
            <button onclick="_prevAdopter(${JSON.stringify(pf).replace(/"/g,'&quot;')})" class="btn btn-g" style="flex:1;font-size:11px">✅ Adopter</button>
            <button onclick="_prevBacktestPortfolio(${JSON.stringify((pf.stocks||[]).map(s=>s.ticker)).replace(/"/g,'&quot;')})" class="btn btn-o" style="flex:1;font-size:11px">📊 Backtest</button>
          </div>
        </div>`).join('')}
    </div>`;
}

function _prevAdopter(pf) {
  if (typeof showNotif !== 'function') return;
  const total = parseInt(prompt(`Montant total à investir en XOF pour "${pf.name}" ?`, '1000000') || '0');
  if (!total || total < 1000) { showNotif('Montant invalide', 'red'); return; }
  const existing = JSON.parse(localStorage.getItem('brvm_portfolio_v2') || '[]');
  const added = [];
  (pf.stocks || []).forEach(s => {
    const alloc = total * (s.weight / 100);
    const shares = s.price > 0 ? Math.floor(alloc / s.price) : 0;
    if (shares > 0) {
      existing.push({ ticker: s.ticker, shares, buy_price: s.price, date: new Date().toISOString().slice(0, 10), note: `Portefeuille ${pf.name}` });
      added.push(s.ticker);
    }
  });
  localStorage.setItem('brvm_portfolio_v2', JSON.stringify(existing));
  showNotif(`${added.length} positions ajoutées → Portefeuille`, 'green');
  setTimeout(() => { nav('port'); if (typeof loadPortfolio === 'function') loadPortfolio(); }, 1000);
}

function _prevBacktestPortfolio(tickers) {
  if (typeof openBacktest === 'function') {
    openBacktest(tickers);
  } else {
    showNotif('Backtesting non disponible', 'amber');
  }
}

// ── Signaux ───────────────────────────────────────────────────────────────────

async function _prevRenderSignaux() {
  const el = document.getElementById('prev-signaux-panel');
  if (!el) return;
  if (_prevSignaux) { _prevDrawSignaux(el); return; }
  el.innerHTML = '<div style="text-align:center;padding:40px;color:var(--t2)">Calcul des signaux...</div>';
  try {
    const res = await fetch('/api/previsions/signaux');
    _prevSignaux = await res.json();
    _prevDrawSignaux(el);
  } catch(e) {
    el.innerHTML = `<p style="color:var(--red)">Erreur: ${e.message}</p>`;
  }
}

function _prevDrawSignaux(el) {
  if (!_prevSignaux || !Array.isArray(_prevSignaux)) return;
  const counts = {};
  _prevSignaux.forEach(s => { counts[s.signal] = (counts[s.signal] || 0) + 1; });
  const filtered = _sigFilter ? _prevSignaux.filter(s => s.signal === _sigFilter) : _prevSignaux;
  const sigCol = { ACHETER: 'var(--green)', CONSERVER: 'var(--amber)', 'ALLÉGER': 'var(--red)', ÉVITER: 'var(--t3)' };
  const sigBg  = { ACHETER: 'rgba(74,222,128,.1)', CONSERVER: 'rgba(251,191,36,.1)', 'ALLÉGER': 'rgba(248,113,113,.1)', ÉVITER: 'rgba(100,116,139,.1)' };

  el.innerHTML = `
    <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
      ${[['', 'Tous', _prevSignaux.length], ['ACHETER','🟢 Acheter', counts['ACHETER']||0], ['CONSERVER','🟡 Conserver', counts['CONSERVER']||0], ['ALLÉGER','🔴 Alléger', counts['ALLÉGER']||0], ['ÉVITER','⚫ Éviter', counts['ÉVITER']||0]].map(([v,l,n]) =>
        `<button onclick="_sigSetFilter('${v}')" style="padding:5px 12px;border-radius:20px;border:1px solid var(--border);background:${_sigFilter===v?'var(--blue)':'var(--bg3)'};color:${_sigFilter===v?'#fff':'var(--t2)'};cursor:pointer;font-size:11px">${l} <strong>${n}</strong></button>`
      ).join('')}
      <span style="margin-left:auto;font-size:10px;color:var(--t3);align-self:center">Mis à jour ${_prevSignaux[0]?.updated_at||'—'}</span>
    </div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:11px">
        <thead><tr>
          <th style="padding:8px;text-align:left;border-bottom:2px solid var(--border);color:var(--t3);font-size:9px">TICKER</th>
          <th style="padding:8px;text-align:left;border-bottom:2px solid var(--border);color:var(--t3);font-size:9px">SECTEUR</th>
          <th style="padding:8px;text-align:center;border-bottom:2px solid var(--border);color:var(--t3);font-size:9px">SIGNAL</th>
          <th style="padding:8px;text-align:right;border-bottom:2px solid var(--border);color:var(--t3);font-size:9px">SCORE</th>
          <th style="padding:8px;text-align:right;border-bottom:2px solid var(--border);color:var(--t3);font-size:9px">CONFIANCE</th>
          <th style="padding:8px;text-align:left;border-bottom:2px solid var(--border);color:var(--t3);font-size:9px">RAISON</th>
        </tr></thead>
        <tbody>
          ${filtered.map(s => `
            <tr onclick="showStock('${s.ticker}')" style="cursor:pointer;border-bottom:1px solid var(--border)" onmouseover="this.style.background='var(--bg3)'" onmouseout="this.style.background=''">
              <td style="padding:8px;font-weight:700">${s.ticker}</td>
              <td style="padding:8px;font-size:10px;color:var(--t2)">${(s.sector||'').substring(0,14)}</td>
              <td style="padding:8px;text-align:center">
                <span style="padding:3px 8px;border-radius:10px;font-size:10px;font-weight:600;background:${sigBg[s.signal]||''};color:${sigCol[s.signal]||'var(--t2)'}">${s.emoji} ${s.signal}</span>
              </td>
              <td style="padding:8px;text-align:right;font-weight:600">${s.score.toFixed(0)}/80</td>
              <td style="padding:8px;text-align:right">
                <div style="display:flex;align-items:center;gap:4px;justify-content:flex-end">
                  <div style="width:40px;background:var(--bg3);border-radius:2px;height:6px">
                    <div style="width:${s.confidence}%;height:100%;background:${sigCol[s.signal]||'var(--blue)'};border-radius:2px"></div>
                  </div>
                  <span style="font-size:10px;color:var(--t2)">${s.confidence}%</span>
                </div>
              </td>
              <td style="padding:8px;font-size:10px;color:var(--t2)">${s.raison}</td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

function _sigSetFilter(val) {
  _sigFilter = val;
  const el = document.getElementById('prev-signaux-panel');
  if (el) _prevDrawSignaux(el);
}

// ── Backtesting ───────────────────────────────────────────────────────────────

async function _prevRenderBacktest() {
  const el = document.getElementById('prev-backtest-panel');
  if (!el) return;
  if (_prevBacktest) { _prevDrawBacktest(el); return; }
  el.innerHTML = `
    <div style="background:var(--bg3);border-radius:8px;padding:16px;margin-bottom:12px;border-left:3px solid var(--blue)">
      <strong>🔬 Validation des modèles sur données historiques BOC</strong>
      <p style="font-size:11px;color:var(--t2);margin-top:4px;line-height:1.5">
        Split 60j entraînement / 20j test. Prédit la direction (hausse/baisse) par momentum, puis compare avec la réalité.
      </p>
    </div>
    <div style="text-align:center;padding:20px;color:var(--t2)">
      <button onclick="_prevRunBacktest()" class="btn btn-g" style="font-size:13px;padding:10px 24px">🚀 Lancer le backtesting</button>
    </div>`;
}

async function _prevRunBacktest() {
  const el = document.getElementById('prev-backtest-panel');
  if (!el) return;
  el.innerHTML += '<div style="text-align:center;padding:10px;color:var(--t2)">Calcul en cours... (quelques secondes)</div>';
  try {
    const res = await fetch('/api/previsions/backtest', { method: 'POST' });
    _prevBacktest = await res.json();
    _prevDrawBacktest(el);
  } catch(e) {
    el.innerHTML = `<p style="color:var(--red)">Erreur: ${e.message}</p>`;
  }
}

function _prevDrawBacktest(el) {
  if (!_prevBacktest) return;
  const bt = _prevBacktest;
  const acc = bt.directional_accuracy_recent ?? bt.directional_accuracy ?? 0;
  const accHist = bt.directional_accuracy ?? 0;
  const accC = acc >= 60 ? 'var(--green)' : acc >= 50 ? 'var(--amber)' : 'var(--red)';
  const alphaC = (bt.avg_alpha || 0) >= 0 ? 'var(--green)' : 'var(--red)';
  const sharpeC = (bt.sharpe_model || 0) >= 0.5 ? 'var(--green)' : (bt.sharpe_model || 0) >= 0 ? 'var(--amber)' : 'var(--red)';

  // Yearly bar chart
  const yearly = bt.yearly_results || {};
  const yrs = Object.keys(yearly).sort();
  let yearBars = '';
  if (yrs.length) {
    const maxRet = Math.max(...yrs.map(y => Math.abs(yearly[y].avg_return_acheter || 0)), 10);
    yearBars = `<div style="margin-top:10px">
      <div style="font-size:10px;color:var(--t3);margin-bottom:6px;text-transform:uppercase;letter-spacing:.4px">📅 Rendement simulé "ACHETER" par année</div>
      ${yrs.map(y => {
        const v = yearly[y];
        const ret = v.avg_return_acheter ?? 0;
        const pct = Math.min(100, Math.abs(ret) / maxRet * 100);
        const col = ret >= 0 ? 'var(--green)' : 'var(--red)';
        const acc = v.directional_accuracy || 0;
        return `<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
          <span style="width:30px;font-size:10px;color:var(--t2)">${y}</span>
          <div style="flex:1;background:var(--bg3);border-radius:3px;height:18px;position:relative;overflow:hidden">
            <div style="position:absolute;left:0;top:0;height:100%;width:${pct}%;background:${col}44;border-radius:3px"></div>
            <div style="position:absolute;inset:0;display:flex;align-items:center;padding:0 6px;font-size:9px;gap:8px">
              <span style="color:${col};font-weight:700">${ret >= 0 ? '+' : ''}${ret.toFixed(1)}%</span>
              <span style="color:var(--t3)">· ${v.n_acheter} ACHETER / ${v.n_tickers} · précision ${acc}%</span>
              <span style="color:${(v.alpha||0)>=0?'var(--green)':'var(--red)'}">alpha ${(v.alpha||0)>=0?'+':''}${(v.alpha||0).toFixed(1)}%</span>
            </div>
          </div>
        </div>`;
      }).join('')}
    </div>`;
  }

  // Recent split SVG chart
  const chartData = (bt.results || []).slice(0, 15).filter(r => r.actual_return != null);
  let svgChart = '';
  if (chartData.length > 3) {
    const maxAbs = Math.max(...chartData.map(r => Math.max(Math.abs(r.actual_return), Math.abs(r.predicted_return || 0))), 1);
    const W = 400, H = 120, pad = { l: 50, r: 10, t: 10, b: 20 };
    const cw = (W - pad.l - pad.r) / chartData.length;
    const yMid = pad.t + (H - pad.t - pad.b) / 2;
    const yScale = v => yMid - (v / maxAbs) * ((H - pad.t - pad.b) / 2);
    let actualLine = '', predLine = '';
    chartData.forEach((r, i) => {
      const x = pad.l + i * cw + cw / 2;
      const pred = r.predicted_return ?? 0;
      if (i === 0) { actualLine += `M${x},${yScale(r.actual_return)}`; predLine += `M${x},${yScale(pred)}`; }
      else { actualLine += ` L${x},${yScale(r.actual_return)}`; predLine += ` L${x},${yScale(pred)}`; }
    });
    svgChart = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block;margin-bottom:10px">
      <line x1="${pad.l}" y1="${yMid}" x2="${W-pad.r}" y2="${yMid}" stroke="rgba(255,255,255,0.1)" stroke-dasharray="4,3"/>
      <text x="${pad.l-4}" y="${yMid+4}" font-size="8" fill="rgba(255,255,255,0.3)" text-anchor="end">0%</text>
      <path d="${actualLine}" fill="none" stroke="#4ADE80" stroke-width="1.5" opacity="0.9"/>
      <path d="${predLine}" fill="none" stroke="#60A5FA" stroke-width="1.5" stroke-dasharray="4,2" opacity="0.7"/>
      ${chartData.map((r, i) => `<text x="${pad.l + i*cw + cw/2}" y="${H}" font-size="7" fill="rgba(255,255,255,0.3)" text-anchor="middle">${r.ticker}</text>`).join('')}
      <circle cx="${W-90}" cy="14" r="4" fill="#4ADE80"/>
      <text x="${W-83}" y="18" font-size="8" fill="#4ADE80">Réel</text>
      <line x1="${W-58}" y1="14" x2="${W-44}" y2="14" stroke="#60A5FA" stroke-dasharray="3,2" stroke-width="1.5"/>
      <text x="${W-40}" y="18" font-size="8" fill="#60A5FA">Prédit</text>
    </svg>`;
  }

  el.innerHTML = `
    <div style="background:rgba(96,165,250,0.06);border-radius:8px;padding:10px 14px;margin-bottom:12px;font-size:10px;color:var(--t3)">
      <strong style="color:var(--blue)">Modèle :</strong> ${bt.model_description || 'Composite 4 facteurs'}
      &nbsp;·&nbsp; Seuil ACHETER : score ≥ ${(bt.seuil_acheter||0.65)*100}%
      &nbsp;·&nbsp; Seuil ALLÉGER : score ≤ ${(bt.seuil_alleger||0.35)*100}%
    </div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px">
      <div class="card" style="margin-bottom:0;text-align:center">
        <div style="font-size:9px;color:var(--t3)">Précision directionnelle<br><span style="font-size:8px">(split récent)</span></div>
        <div style="font-size:26px;font-weight:700;color:${accC}">${acc}%</div>
        <div style="font-size:8px;color:var(--t2)">${acc>=60?'Bon modèle':acc>=50?'Passable':'Faible — dépasse le hasard ?'}</div>
      </div>
      <div class="card" style="margin-bottom:0;text-align:center">
        <div style="font-size:9px;color:var(--t3)">Alpha moyen<br><span style="font-size:8px">vs marché (2019-2024)</span></div>
        <div style="font-size:26px;font-weight:700;color:${alphaC}">${(bt.avg_alpha||0)>=0?'+':''}${(bt.avg_alpha||0).toFixed(1)}%</div>
        <div style="font-size:8px;color:var(--t2)">Surperformance annuelle moy.</div>
      </div>
      <div class="card" style="margin-bottom:0;text-align:center">
        <div style="font-size:9px;color:var(--t3)">Sharpe modèle<br><span style="font-size:8px">(taux sans risque 6.5%)</span></div>
        <div style="font-size:26px;font-weight:700;color:${sharpeC}">${(bt.sharpe_model||0).toFixed(2)}</div>
        <div style="font-size:8px;color:var(--t2)">${(bt.sharpe_model||0)>=0.5?'Solide':(bt.sharpe_model||0)>0?'>0 = rendement ajusté risque positif':'Risque non rémunéré'}</div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px">
      ${bt.best_year ? `<div style="background:rgba(74,222,128,0.08);border-radius:8px;padding:10px;border-left:3px solid var(--green)">
        <div style="font-size:9px;color:var(--green);text-transform:uppercase;margin-bottom:2px">🏆 Meilleure année</div>
        <div style="font-size:18px;font-weight:700;color:var(--green)">${bt.best_year} · +${(bt.best_year_return||0).toFixed(1)}%</div>
        <div style="font-size:9px;color:var(--t3)">Rendement moyen portefeuille ACHETER</div>
      </div>` : ''}
      ${bt.worst_year ? `<div style="background:rgba(248,113,113,0.08);border-radius:8px;padding:10px;border-left:3px solid var(--red)">
        <div style="font-size:9px;color:var(--red);text-transform:uppercase;margin-bottom:2px">📉 Pire année</div>
        <div style="font-size:18px;font-weight:700;color:var(--red)">${bt.worst_year} · ${(bt.worst_year_return||0).toFixed(1)}%</div>
        <div style="font-size:9px;color:var(--t3)">Rendement moyen portefeuille ACHETER</div>
      </div>` : ''}
    </div>
    <div class="card" style="margin-bottom:12px">
      <div class="ct" style="margin-bottom:4px">📅 Validation historique 2019–2024</div>
      <div style="font-size:9px;color:var(--t3);margin-bottom:8px;font-style:italic">Simule "au 1er janvier de l'année N, quels tickers auraient score ≥ 0.65 ?" et compare avec la performance réelle sur 12 mois.</div>
      ${yearBars}
    </div>
    <div class="card" style="margin-bottom:12px">
      <div class="ct" style="margin-bottom:8px">🔬 Split train/test — données BOC récentes</div>
      <div style="font-size:9px;color:var(--t3);margin-bottom:6px">Précision : <strong style="color:${accC}">${acc}%</strong> · MAE : ${bt.mae_recent ?? bt.mae}% · ${bt.total_tested} actions testées</div>
      ${svgChart}
      <div style="overflow-x:auto;max-height:250px;overflow-y:auto">
        <table style="width:100%;border-collapse:collapse;font-size:11px">
          <thead><tr>${['Ticker','Score prév.','Signal','Réel','Correct'].map(h=>`<th style="padding:5px 6px;text-align:center;border-bottom:2px solid var(--border);color:var(--t3);font-size:9px">${h}</th>`).join('')}</tr></thead>
          <tbody>${(bt.results||[]).map(r=>{
            const sp = r.score_prevision ?? 0;
            const sig = r.signal || (sp > 0.65 ? 'ACHETER' : sp < 0.35 ? 'ALLÉGER' : 'CONSERVER');
            const sigC = sig==='ACHETER'?'var(--green)':sig==='ALLÉGER'?'var(--red)':'var(--amber)';
            return `<tr style="border-bottom:1px solid var(--border)">
              <td style="padding:5px 6px;font-weight:700;cursor:pointer;color:var(--blue)" onclick="showStock('${r.ticker}')">${r.ticker}</td>
              <td style="padding:5px 6px;text-align:center;font-size:10px">${(sp*100).toFixed(0)}%</td>
              <td style="padding:5px 6px;text-align:center"><span style="color:${sigC};font-size:9px;font-weight:600">${sig}</span></td>
              <td style="padding:5px 6px;text-align:center;font-weight:600;color:${(r.actual_return||0)>=0?'var(--green)':'var(--red)'}">${(r.actual_return||0)>=0?'+':''}${(r.actual_return||0).toFixed(1)}%</td>
              <td style="padding:5px 6px;text-align:center">${r.correct?'✅':'❌'}</td>
            </tr>`;
          }).join('')}</tbody>
        </table>
      </div>
    </div>
    <button onclick="_prevBacktest=null;_prevRenderBacktest()" class="btn btn-o" style="font-size:11px">↻ Recalculer</button>`;
}

// ── Rapport ───────────────────────────────────────────────────────────────────

function _prevRenderRapport() {
  const el = document.getElementById('prev-rapport-panel');
  if (!el) return;
  const month = new Date().toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' });
  el.innerHTML = `
    <div class="card" style="max-width:520px">
      <div class="ct" style="margin-bottom:12px">📄 Rapport mensuel BRVM — ${month}</div>
      <p style="font-size:12px;color:var(--t1);line-height:1.7;margin-bottom:14px">
        Génère un rapport PDF complet contenant :
        <br>• Résumé du marché BRVM (KPIs, scores)
        <br>• Top 3 actions par score composite
        <br>• Les 3 portefeuilles prévisionnels recommandés
        <br>• Signaux d'achat actifs avec confiance et raison
      </p>
      <button onclick="_prevGenererRapport(this)" class="btn btn-g" style="font-size:13px;padding:10px 24px;width:100%">
        📥 Générer le rapport PDF
      </button>
      <div id="prev-rapport-status" style="margin-top:10px;font-size:11px;color:var(--t2);text-align:center"></div>
    </div>`;
}

async function _prevGenererRapport(btn) {
  const statusEl = document.getElementById('prev-rapport-status');
  if (btn) btn.disabled = true;
  if (statusEl) statusEl.textContent = 'Génération du PDF en cours...';
  try {
    const a = document.createElement('a');
    a.href = '/api/rapport-mensuel';
    a.download = `BRVM_Rapport_${new Date().toISOString().slice(0,7)}.pdf`;
    a.click();
    if (statusEl) statusEl.textContent = '✅ Téléchargement démarré';
  } catch(e) {
    if (statusEl) statusEl.textContent = `❌ Erreur: ${e.message}`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

window.renderPrevisionsPage = renderPrevisionsPage;
