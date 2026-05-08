async function fetchLiveScore(ticker){
  const el=document.getElementById('live-score-container');
  if(!el)return;
  el.innerHTML='<div style="color:var(--t2);font-size:12px;padding:6px 0"><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#00c076;animation:pulse 1s infinite;margin-right:5px"></span>Calcul score live...</div>';
  try{
    const ctrl=new AbortController();
    const tid=setTimeout(()=>ctrl.abort(),8000);
    const res=await fetch('/api/live-score/'+ticker,{signal:ctrl.signal});
    clearTimeout(tid);
    const d=await res.json();
    if(d.error){el.innerHTML='<div style="color:var(--red);font-size:11px">'+d.error+'</div>';return;}
    const sc=d.composite_adj||0;
    const col=sc>=57?'var(--green)':sc>=40?'var(--amber)':sc>=23?'var(--orange,#f97316)':'var(--red)';
    const tier=sc>=57?'FORT':sc>=40?'MODERE':sc>=23?'FAIBLE':'EVITER';
    const chg=d.live_change_pct||0;
    const chgCol=chg>=0?'var(--green)':'var(--red)';
    const chgStr=(chg>=0?'+':'')+chg.toFixed(2)+'%';
    const price=d.live_price?d.live_price.toLocaleString('fr-FR')+' XOF':'N/D';
    const badge=d.live_source!=='static'?'<span style="background:#00c07620;color:#00c076;font-size:10px;font-weight:700;padding:1px 6px;border-radius:10px">LIVE</span>':'';
    const models=[['Graham',d.score_graham],['DCF',d.score_dcf],['DDM',d.score_ddm],['EPV',d.score_epv],['Buffett',d.score_buffett],['RevDCF',d.score_rev_dcf],['Relatif',d.score_relatif],['Tech.',d.score_technique]];
    const bars=models.map(function(m){
      var l=m[0],v=m[1],sv=v||0;
      var bc=sv>=7?'var(--green)':sv>=4?'var(--amber)':'var(--red)';var det=d['detail_'+l.toLowerCase().replace('.','').replace('/','_')]||'';
      return '<div title="'+det+'" style="display:grid;grid-template-columns:52px 1fr 26px;align-items:center;gap:5px;font-size:11px"><span style="color:var(--t2)">'+l+'</span><div style="background:var(--border);border-radius:3px;height:4px"><div style="width:'+sv*10+'%;height:4px;border-radius:3px;background:'+bc+'"></div></div><span style="color:'+bc+';font-weight:600;text-align:right">'+sv.toFixed(1)+'</span></div>';
    }).join('');
    el.innerHTML='<div style="border:1px solid var(--border);border-radius:10px;padding:12px;margin-top:8px">'+
      '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">'+
      '<div><div style="font-size:11px;color:var(--t2);margin-bottom:3px">Score live '+badge+'</div>'+
      '<div style="font-size:12px">'+price+' <span style="color:'+chgCol+'">'+chgStr+'</span></div></div>'+
      '<div style="text-align:right"><div style="font-size:28px;font-weight:700;color:'+col+'">'+sc.toFixed(1)+'<span style="font-size:13px;color:var(--t2)">/80</span></div>'+
      '<div style="font-size:11px;font-weight:600;color:'+col+'">'+tier+'</div></div></div>'+
      '<div style="background:var(--border);border-radius:4px;height:5px;margin-bottom:10px">'+
      '<div style="width:'+(sc/80*100).toFixed(0)+'%;height:5px;border-radius:4px;background:'+col+';transition:width 0.6s"></div></div>'+
      '<div style="display:flex;flex-direction:column;gap:4px;margin-bottom:8px">'+bars+'</div>'+
      '<div style="display:flex;gap:8px;flex-wrap:wrap;font-size:10px;color:var(--t2);border-top:1px solid var(--border);padding-top:6px;align-items:center">'+
      '<span>P/E: '+(d.pe_ref_live||0).toFixed(1)+'x</span><span>P/B: '+(d.pb_ref_live||0).toFixed(1)+'x</span>'+
      '<span>Rdt: '+(d.div_yield_live||0).toFixed(1)+'%</span>'+
      '<button onclick="fetchLiveScore(\''+ticker+'\')" style="margin-left:auto;font-size:10px;padding:2px 7px;border:1px solid var(--border);border-radius:5px;cursor:pointer;background:none;color:var(--t2)">Actualiser</button></div></div>';
  }catch(e){var msg=e.name==='AbortError'?'Timeout — brvm.org trop lent':e.message;el.innerHTML='<div style="color:var(--red);font-size:11px">'+msg+' <button onclick="fetchLiveScore(\"'+ticker+'\")" style="margin-left:6px;font-size:10px;padding:1px 6px;border:1px solid var(--border);border-radius:4px;cursor:pointer;background:none;color:var(--t2)">Réessayer</button></div>';}
}

async function loadReports(ticker) {
  const el = document.getElementById('reports-container');
  if (!el) return;
  el.innerHTML = '<span style="color:var(--t2);font-size:11px">Chargement rapports...</span>';
  try {
    const ctrl = new AbortController();
    const tid = setTimeout(() => ctrl.abort(), 10000);
    const res = await fetch('/api/reports/' + ticker, {signal: ctrl.signal});
    clearTimeout(tid);
    const d = await res.json();
    if (!d.reports || !d.reports.length) {
      el.innerHTML = '<span style="color:var(--t2);font-size:11px">Aucun rapport disponible</span>';
      return;
    }
    const types = {'Rapport annuel':'#00c076','Etats financiers':'var(--amber)','Rapport S1':'#3b82f6','Rapport T3':'#3b82f6','Rapport RSE':'#8b5cf6','Rapport trimestriel':'#3b82f6'};
    const rows = d.reports.slice(0,12).map(function(r) {
      var col = types[r.type] || 'var(--t2)';
      return '<a href="'+r.url+'" target="_blank" style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid var(--border);text-decoration:none;color:inherit">'+
        '<span style="font-size:10px;font-weight:600;color:'+col+';min-width:115px;white-space:nowrap">'+r.type+'</span>'+
        '<span style="font-size:11px;color:var(--t2);min-width:34px">'+(r.year||'?')+'</span>'+
        '<span style="font-size:11px;color:var(--t);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+r.title+'</span>'+
        '<span style="font-size:10px;color:#3b82f6;font-weight:600">PDF</span>'+
        (r.type==='Etats financiers'||r.type==='Rapport annuel'?
          ' <button onclick="event.preventDefault();analyzePDF(\''+r.url+'\',\''+ticker+'\',\''+r.type+'\','+r.year+',this)" style="font-size:9px;padding:1px 5px;border:1px solid var(--border);border-radius:4px;cursor:pointer;background:none;color:var(--t2);margin-left:4px">Analyser</button>':'')+
        '</a>';
    }).join('');
    el.innerHTML = '<div style="border:1px solid var(--border);border-radius:8px;padding:10px;margin-top:8px">'+
      '<div style="font-size:11px;font-weight:600;color:var(--t2);margin-bottom:6px">Rapports BRVM ('+d.total+')</div>'+
      rows+'</div>';
  } catch(e) {
    el.innerHTML = '<span style="color:var(--red);font-size:11px">'+(e.name==='AbortError'?'Timeout':'Erreur: '+e.message)+'</span>';
  }
}

async function analyzePDF(url, ticker, docType, year, btn) {
  if (btn) { btn.textContent = 'Analyse en cours...'; btn.disabled = true; }
  const el = document.getElementById('pdf-analysis-container');
  if (el) el.innerHTML = '<div style="color:var(--t2);font-size:12px;padding:8px 0">Claude lit le rapport... (~20s)</div>';
  try {
    const res = await fetch('/api/analyze-report', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url, ticker, doc_type: docType, year})
    });
    const d = await res.json();
    if (d.error) { if(el) el.innerHTML='<div style="color:var(--red);font-size:11px">'+d.error+'</div>'; return; }
    const vc = d.verdict_investisseur==='POSITIF'?'var(--green)':d.verdict_investisseur==='NEGATIF'?'var(--red)':'var(--amber)';
    const kpis = d.kpis || {};
    const kpiRows = Object.entries(kpis).filter(function(e){return e[1]&&e[1].valeur!=null;}).map(function(e){
      var label=e[0].replace(/_/g,' ');
      var v=e[1];
      var chg=v.variation?'<span style="color:'+(v.variation.startsWith('+')?'var(--green)':'var(--red)')+'">'+v.variation+'</span>':'';
      return '<div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid var(--border);font-size:11px">'+
        '<span style="color:var(--t2)">'+label+'</span>'+
        '<span><strong>'+v.valeur.toLocaleString('fr-FR')+'</strong> '+v.unite+' '+chg+'</span></div>';
    }).join('');
    const pts = (d.points_cles||[]).map(function(p){return '<li style="margin-bottom:4px">'+p+'</li>';}).join('');
    if (el) el.innerHTML =
      '<div style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-top:8px">'+
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'+
      '<span style="font-size:12px;font-weight:600">Analyse IA — '+docType+' '+(year||'')+'</span>'+
      '<span style="font-size:11px;font-weight:700;color:'+vc+'">'+d.verdict_investisseur+'</span></div>'+
      '<p style="font-size:11px;color:var(--t2);margin-bottom:8px;line-height:1.5">'+d.resume+'</p>'+
      (kpiRows?'<div style="margin-bottom:8px">'+kpiRows+'</div>':'')+
      (pts?'<div style="font-size:11px;margin-top:6px"><strong>Points clés :</strong><ul style="margin:4px 0;padding-left:16px">'+pts+'</ul></div>':'')+
      (d.perspectives?'<p style="font-size:11px;color:var(--t2);margin-top:6px;font-style:italic">'+d.perspectives+'</p>':'')+
      '</div>';
    if (btn) { btn.textContent = 'Ré-analyser'; btn.disabled = false; }
  } catch(e) {
    if (el) el.innerHTML='<div style="color:var(--red);font-size:11px">Erreur: '+e.message+'</div>';
    if (btn) { btn.textContent = 'Analyser PDF'; btn.disabled = false; }
  }
}

async function loadLiveRank(ticker) {
  try {
    const res = await fetch('/api/live-ranking');
    const d = await res.json();
    if (!d.ranking) return;
    const r = d.ranking.find(x => x.ticker === ticker);
    if (!r) return;
    const el = document.getElementById('live-rank-badge');
    if (!el) return;
    const delta = r.rank_delta || 0;
    const arrow = delta > 0 ? '▲' : delta < 0 ? '▼' : '—';
    const col   = delta > 0 ? '#00c076' : delta < 0 ? 'var(--red)' : 'var(--t2)';
    el.innerHTML =
      '<span style="font-size:11px;color:var(--t2)">Rang live : </span>' +
      '<span style="font-size:13px;font-weight:700">#' + r.rank + '</span>' +
      '<span style="font-size:11px;color:' + col + ';margin-left:4px">' + arrow +
      (delta !== 0 ? Math.abs(delta) : '') + '</span>' +
      '<span style="font-size:10px;color:var(--t2);margin-left:6px">/ 47</span>';
  } catch(e) {}
}
