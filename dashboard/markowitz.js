// ── Optimisation Markowitz — markowitz.js ────────────────────────────────

let _mrkTickers = [];
let _mrkResult = null;

function openMarkowitz(preselected) {
  let modal = document.getElementById('mrk-modal');
  if (!modal) modal = _createMrkModal();
  if (preselected?.length) _mrkTickers = [...preselected];
  _refreshMrkSelector();
  modal.style.display = 'flex';
}

function _createMrkModal() {
  const modal = document.createElement('div');
  modal.id = 'mrk-modal';
  modal.style = 'display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.85);align-items:center;justify-content:center;padding:16px';
  modal.innerHTML = `
    <div style="background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:24px;max-width:1000px;width:100%;max-height:93vh;overflow-y:auto;position:relative">
      <button onclick="closeMrk()" style="position:absolute;top:14px;right:14px;background:var(--bg3);border:1px solid var(--border);border-radius:6px;color:var(--t2);padding:4px 12px;cursor:pointer">✕</button>
      <h2 style="font-size:18px;font-weight:700;margin-bottom:4px">📐 Optimisation Markowitz</h2>
      <p style="font-size:12px;color:var(--t2);margin-bottom:16px">Frontière efficiente & allocation optimale sur données BOC réelles BRVM</p>
      <div style="margin-bottom:12px">
        <div style="font-size:11px;color:var(--t2);margin-bottom:6px">Actions à optimiser (2-10) :</div>
        <div id="mrk-selected" style="display:flex;flex-wrap:wrap;gap:6px;min-height:36px;padding:8px;background:var(--bg3);border-radius:8px;border:1px solid var(--border)"></div>
      </div>
      <div id="mrk-picker" style="display:flex;flex-wrap:wrap;gap:4px;max-height:90px;overflow-y:auto;margin-bottom:10px"></div>
      <div style="display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap">
        <span style="font-size:11px;color:var(--t2);align-self:center">Rapide:</span>
        <button onclick="mrkGroup('Top5')" style="font-size:10px;padding:3px 8px;background:var(--bg3);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--t2)">Top5</button>
        <button onclick="mrkGroup('Top8')" style="font-size:10px;padding:3px 8px;background:var(--bg3);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--t2)">Top8</button>
        <button onclick="mrkGroup('Banques')" style="font-size:10px;padding:3px 8px;background:var(--bg3);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--t2)">Banques</button>
        <button onclick="mrkGroup('Telecom')" style="font-size:10px;padding:3px 8px;background:var(--bg3);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--t2)">Télécoms</button>
        <button onclick="mrkGroup('Effacer')" style="font-size:10px;padding:3px 8px;background:var(--bg3);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--red)">✕ Effacer</button>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px">
        <div>
          <div style="font-size:11px;color:var(--t2);margin-bottom:4px">Taux sans risque (BCEAO) :</div>
          <input id="mrk-rf" type="number" value="6" min="0" max="20" step="0.5"
            style="width:100%;padding:6px 10px;background:var(--bg3);border:1px solid var(--border);border-radius:6px;color:var(--t1);font-size:12px;box-sizing:border-box"/>
        </div>
        <div>
          <div style="font-size:11px;color:var(--t2);margin-bottom:4px">Simulations Monte Carlo :</div>
          <select id="mrk-sim" style="width:100%;padding:6px 10px;background:var(--bg3);border:1px solid var(--border);border-radius:6px;color:var(--t1);font-size:12px">
            <option value="1000">1 000 (rapide)</option>
            <option value="3000" selected>3 000 (standard)</option>
            <option value="5000">5 000 (précis)</option>
          </select>
        </div>
      </div>
      <button onclick="launchMarkowitz()"
        style="width:100%;padding:12px;background:linear-gradient(135deg,#8B5CF6,#60A5FA);border:none;border-radius:8px;color:#fff;font-weight:700;font-size:13px;cursor:pointer;margin-bottom:16px">
        📐 Calculer la frontière efficiente
      </button>
      <div id="mrk-result" style="display:none">
        <div style="border-top:1px solid var(--border);padding-top:16px">
          <div id="mrk-portfolios" style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px"></div>
          <div class="card" style="margin-bottom:12px">
            <div class="ct">📈 Frontière efficiente (Risque vs Rendement)</div>
            <div id="mrk-chart" style="width:100%;height:280px"></div>
          </div>
          <div class="card">
            <div class="ct">📊 Statistiques individuelles</div>
            <table style="width:100%;border-collapse:collapse;font-size:11px">
              <thead><tr style="border-bottom:1px solid var(--border)">
                <th style="text-align:left;padding:4px 6px;color:var(--t2)">Ticker</th>
                <th style="text-align:right;padding:4px 6px;color:var(--t2)">Ret. annuel</th>
                <th style="text-align:right;padding:4px 6px;color:var(--t2)">Volatilité</th>
                <th style="text-align:right;padding:4px 6px;color:var(--t2)">Sharpe</th>
              </tr></thead>
              <tbody id="mrk-stats-table"></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>`;
  modal.addEventListener('click', e => { if (e.target === modal) closeMrk(); });
  document.body.appendChild(modal);
  return modal;
}

function _refreshMrkSelector() {
  const all = window.scores || (typeof scores !== "undefined" ? scores : []) || [];
  const sorted = [...(all||[])].sort((a,b) => (b.composite_adj||0)-(a.composite_adj||0));
  const selEl = document.getElementById('mrk-selected');
  if (selEl) {
    selEl.innerHTML = _mrkTickers.map(t => {
      const s = all.find(x=>x.ticker===t);
      const v = s?.composite_adj||0;
      const c = v>=60?'var(--green)':v>=40?'var(--amber)':'var(--red)';
      return `<span style="display:flex;align-items:center;gap:4px;background:var(--bg2);border:1px solid ${c};border-radius:6px;padding:3px 8px;font-size:11px">
        <strong style="color:${c}">${t}</strong>
        <button onclick="mrkRemove('${t}')" style="background:none;border:none;color:var(--red);cursor:pointer;padding:0 2px">✕</button>
      </span>`;
    }).join('') || '<span style="color:var(--t3);font-size:11px">Sélectionnez 2 à 10 actions</span>';
  }
  const picker = document.getElementById('mrk-picker');
  if (picker) {
    picker.innerHTML = sorted.map(x => {
      const sel = _mrkTickers.includes(x.ticker);
      const v = x.composite_adj||0;
      const c = v>=60?'var(--green)':v>=40?'var(--amber)':'var(--red)';
      return `<button onclick="mrkToggle('${x.ticker}')"
        style="font-size:10px;padding:2px 7px;border-radius:4px;border:1px solid ${sel?c:'var(--border)'};background:${sel?c+'22':'var(--bg3)'};color:${sel?c:'var(--t2)'};cursor:pointer">
        ${x.ticker} <span style="opacity:0.6">${v.toFixed(0)}</span></button>`;
    }).join('');
  }
}

function mrkToggle(t) {
  if (_mrkTickers.includes(t)) _mrkTickers = _mrkTickers.filter(x=>x!==t);
  else { if (_mrkTickers.length >= 10) { return; } _mrkTickers.push(t); }
  _refreshMrkSelector();
}
function mrkRemove(t) { _mrkTickers = _mrkTickers.filter(x=>x!==t); _refreshMrkSelector(); }
function mrkGroup(g) {
  const all = window.scores || (typeof scores !== "undefined" ? scores : []);
  const sorted = [...(all||[])].sort((a,b)=>(b.composite_adj||0)-(a.composite_adj||0));
  if (g==='Effacer') _mrkTickers=[];
  else if (g==='Top5') _mrkTickers=sorted.slice(0,5).map(x=>x.ticker);
  else if (g==='Top8') _mrkTickers=sorted.slice(0,8).map(x=>x.ticker);
  else if (g==='Banques') _mrkTickers=sorted.filter(x=>x.sector?.includes('Banque')).slice(0,6).map(x=>x.ticker);
  else if (g==='Telecom') _mrkTickers=sorted.filter(x=>x.sector?.includes('Télécom')||x.sector?.includes('Telecom')).slice(0,4).map(x=>x.ticker);
  _refreshMrkSelector();
}
function closeMrk() { const m = document.getElementById('mrk-modal'); if (m) m.style.display='none'; }

async function launchMarkowitz() {
  if (_mrkTickers.length < 2) { return; }
  const resultDiv = document.getElementById('mrk-result');
  const portfoliosDiv = document.getElementById('mrk-portfolios');
  portfoliosDiv.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:20px;color:var(--t2)">⏳ Calcul Monte Carlo en cours...</div>';
  resultDiv.style.display = 'block';
  const rf = parseFloat(document.getElementById('mrk-rf')?.value||6)/100;
  const nsim = parseInt(document.getElementById('mrk-sim')?.value||3000);
  try {
    const res = await fetch('/api/markowitz',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tickers:_mrkTickers,n_portfolios:nsim,risk_free:rf})});
    const d = await res.json();
    if (d.error) throw new Error(d.error);
    _mrkResult = d;
    _renderMrkResult(d);
  } catch(e) {
    portfoliosDiv.innerHTML = `<div style="grid-column:1/-1;color:var(--red);padding:16px">Erreur: ${e.message}</div>`;
  }
}

function _renderMrkResult(d) {
  const portfolios = [
    {label:'🏆 Max Sharpe',subtitle:'Meilleur ratio risque/rendement',data:d.max_sharpe,color:'var(--green)'},
    {label:'🛡️ Min Volatilité',subtitle:'Portefeuille le moins risqué',data:d.min_volatility,color:'var(--blue)'},
    {label:'🚀 Max Rendement',subtitle:'Rendement potentiel maximal',data:d.max_return,color:'var(--amber)'},
  ];
  document.getElementById('mrk-portfolios').innerHTML = portfolios.map(p => {
    const w = p.data.weights;
    const top4 = Object.entries(w).sort((a,b)=>b[1]-a[1]).slice(0,4);
    return `<div style="background:var(--bg3);border:1px solid ${p.color}33;border-radius:10px;padding:14px">
      <div style="font-weight:700;font-size:12px;color:${p.color};margin-bottom:2px">${p.label}</div>
      <div style="font-size:10px;color:var(--t3);margin-bottom:10px">${p.subtitle}</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:10px">
        <div style="text-align:center"><div style="font-size:10px;color:var(--t2)">Rendement</div><div style="font-size:15px;font-weight:700;color:${p.color}">${p.data.return>=0?'+':''}${p.data.return.toFixed(1)}%</div></div>
        <div style="text-align:center"><div style="font-size:10px;color:var(--t2)">Volatilité</div><div style="font-size:15px;font-weight:700">${p.data.volatility.toFixed(1)}%</div></div>
        <div style="text-align:center"><div style="font-size:10px;color:var(--t2)">Sharpe</div><div style="font-size:15px;font-weight:700;color:${p.data.sharpe>=2?'var(--green)':p.data.sharpe>=1?'var(--amber)':'var(--red)'}">${p.data.sharpe.toFixed(2)}</div></div>
      </div>
      <div style="font-size:10px;color:var(--t2);margin-bottom:4px">Allocation :</div>
      ${top4.map(([t,wt])=>`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px">
        <span style="font-size:10px;font-weight:600;cursor:pointer" onclick="closeMrk();showStock('${t}')">${t}</span>
        <div style="display:flex;align-items:center;gap:4px;flex:1;margin:0 6px">
          <div style="flex:1;height:4px;background:var(--border);border-radius:2px"><div style="width:${(wt*100).toFixed(0)}%;height:100%;background:${p.color};border-radius:2px"></div></div>
          <span style="font-size:10px;color:${p.color};min-width:32px;text-align:right">${(wt*100).toFixed(1)}%</span>
        </div>
      </div>`).join('')}
      <div style="display:flex;gap:6px;margin-top:8px">
        <button onclick="applyMrkToBacktest(${JSON.stringify(w)})" style="flex:1;padding:5px;background:${p.color}22;border:1px solid ${p.color}44;border-radius:6px;color:${p.color};font-size:10px;cursor:pointer">📊 Tester</button>
        <button onclick="saveMrkToPortfolio(${JSON.stringify(w)},1000000)" style="flex:1;padding:5px;background:rgba(74,222,128,.12);border:1px solid rgba(74,222,128,.3);border-radius:6px;color:var(--green);font-size:10px;cursor:pointer">📦 Portefeuille</button>
      </div>
    </div>`;
  }).join('');
  _drawMrkChart(d);
  document.getElementById('mrk-stats-table').innerHTML = Object.entries(d.individual)
    .sort((a,b)=>b[1].sharpe-a[1].sharpe)
    .map(([t,s])=>{
      const rc=s.annual_return>=0?'var(--green)':'var(--red)';
      const sc=s.sharpe>=2?'var(--green)':s.sharpe>=1?'var(--amber)':'var(--red)';
      return `<tr style="border-bottom:1px solid var(--border);cursor:pointer" onclick="closeMrk();showStock('${t}')">
        <td style="padding:5px 6px;font-weight:700">${t}</td>
        <td style="padding:5px 6px;text-align:right;color:${rc}">${s.annual_return>=0?'+':''}${s.annual_return.toFixed(1)}%</td>
        <td style="padding:5px 6px;text-align:right">${s.annual_vol.toFixed(1)}%</td>
        <td style="padding:5px 6px;text-align:right;color:${sc};font-weight:700">${s.sharpe.toFixed(2)}</td>
      </tr>`;
    }).join('');
}

function applyMrkToBacktest(weights) {
  closeMrk();
  const tickers = Object.keys(weights);
  if (typeof openBacktest==='function') {
    openBacktest(tickers);
    setTimeout(()=>{
      tickers.forEach(t=>{const el=document.getElementById('w-'+t);if(el)el.value=(weights[t]*100).toFixed(1);});
      if(typeof btUpdateWeights==='function')btUpdateWeights();
    },500);
  }
}

function _drawMrkChart(d) {
  const container = document.getElementById('mrk-chart');
  if (!container) return;
  const W=container.clientWidth||700,H=280;
  const PAD={top:20,right:100,bottom:35,left:50};
  const CW=W-PAD.left-PAD.right,CH=H-PAD.top-PAD.bottom;
  const cloud=d.cloud||[];
  if(!cloud.length) return;
  const allVols=cloud.map(p=>p.volatility),allRets=cloud.map(p=>p.return);
  const minVol=Math.min(...allVols)*0.95,maxVol=Math.max(...allVols)*1.05;
  const minRet=Math.min(...allRets)*0.9,maxRet=Math.max(...allRets)*1.05;
  const xS=v=>PAD.left+((v-minVol)/(maxVol-minVol))*CW;
  const yS=r=>PAD.top+CH-((r-minRet)/(maxRet-minRet))*CH;
  let svg='';
  for(let g=0;g<=4;g++){
    const v=minVol+(maxVol-minVol)*g/4,x=xS(v);
    svg+=`<line x1="${x}" y1="${PAD.top}" x2="${x}" y2="${PAD.top+CH}" stroke="rgba(255,255,255,0.05)" stroke-width="1"/>
          <text x="${x}" y="${H-4}" text-anchor="middle" font-size="9" fill="rgba(255,255,255,0.3)">${v.toFixed(0)}%</text>`;
    const r=minRet+(maxRet-minRet)*g/4,y=yS(r);
    svg+=`<line x1="${PAD.left}" y1="${y}" x2="${PAD.left+CW}" y2="${y}" stroke="rgba(255,255,255,0.05)" stroke-width="1"/>
          <text x="${PAD.left-4}" y="${y+4}" text-anchor="end" font-size="9" fill="rgba(255,255,255,0.3)">${r.toFixed(0)}%</text>`;
  }
  const maxSharpe=Math.max(...cloud.map(p=>p.sharpe));
  cloud.forEach(p=>{
    const x=xS(p.volatility),y=yS(p.return);
    const ratio=Math.min(1,Math.max(0,p.sharpe/maxSharpe));
    const r2=Math.round(ratio<0.5?248:74),g2=Math.round(ratio<0.5?113+ratio*2*(222-113):222),b2=Math.round(ratio<0.5?113:128);
    svg+=`<circle cx="${x}" cy="${y}" r="2.5" fill="rgb(${r2},${g2},${b2})" opacity="0.5"/>`;
  });
  const eff=d.frontier||[];
  if(eff.length>=2){const pts=eff.map(p=>`${xS(p.volatility)},${yS(p.return)}`).join(' ');svg+=`<polyline points="${pts}" fill="none" stroke="rgba(255,255,255,0.6)" stroke-width="2" stroke-dasharray="4,2"/>`;}
  [{p:d.max_sharpe,label:'Max Sharpe',color:'#4ADE80',sym:'★'},{p:d.min_volatility,label:'Min Vol',color:'#60A5FA',sym:'●'},{p:d.max_return,label:'Max Ret',color:'#FBBF24',sym:'▲'}].forEach(({p,label,color,sym})=>{
    const x=xS(p.volatility),y=yS(p.return);
    svg+=`<circle cx="${x}" cy="${y}" r="7" fill="${color}" opacity="0.9"/>
          <text x="${x}" y="${y+4}" text-anchor="middle" font-size="9" fill="#000">${sym}</text>
          <text x="${x+10}" y="${y-8}" font-size="9" font-weight="700" fill="${color}">${label}</text>
          <text x="${x+10}" y="${y+4}" font-size="8" fill="${color}">${p.return.toFixed(1)}% / ${p.volatility.toFixed(1)}%</text>`;
  });
  svg+=`<defs><linearGradient id="sh-grad" x1="0" x2="1" y1="0" y2="0"><stop offset="0%" stop-color="#F87171"/><stop offset="50%" stop-color="#FBBF24"/><stop offset="100%" stop-color="#4ADE80"/></linearGradient></defs>
        <rect x="${PAD.left+CW+5}" y="${PAD.top}" width="12" height="${CH}" fill="url(#sh-grad)" rx="3"/>
        <text x="${PAD.left+CW+11}" y="${PAD.top-4}" text-anchor="middle" font-size="8" fill="rgba(255,255,255,0.5)">Sharpe</text>`;
  container.innerHTML=`<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" style="display:block;overflow:visible">${svg}</svg>`;
}

function saveMrkToPortfolio(weights, totalXOF) {
  const prices = {};
  (window.scores||[]).forEach(x=>{ if(x.ticker) prices[x.ticker]=x.price||0; });

  // Demander montant total
  const input = prompt(`Montant total à investir (XOF) ?\nAllocation Markowitz sur ${Object.keys(weights).length} actions.`, totalXOF);
  const total = parseFloat(input)||totalXOF;
  if(!total) return;

  const existing = JSON.parse(localStorage.getItem('brvm_portfolio_v2')||'[]');
  let added = 0;

  Object.entries(weights).forEach(([ticker, wt]) => {
    const alloc = total * wt;
    const price = prices[ticker];
    if(!price || price<=0) return;
    const shares = Math.floor(alloc/price);
    if(shares<=0) return;
    // Vérifier si déjà présent
    const idx = existing.findIndex(p=>(p.ticker||p.symbol)===ticker);
    if(idx>=0){
      // Mettre à jour (ajouter les actions)
      const old = existing[idx];
      const oldShares = +(old.shares||old.qty||0);
      const oldPrice = +(old.avg_price||old.buyPrice||price);
      const newShares = oldShares+shares;
      const newAvg = (oldShares*oldPrice+shares*price)/newShares;
      existing[idx] = {...old, shares:newShares, avg_price:newAvg};
    } else {
      existing.push({ ticker, shares, avg_price: price, date: new Date().toISOString().slice(0,10), source:'markowitz' });
    }
    added++;
  });

  localStorage.setItem('brvm_portfolio_v2', JSON.stringify(existing));
  closeMrk();
  if(typeof loadPortfolio==='function') loadPortfolio();
}
