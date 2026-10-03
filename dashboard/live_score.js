async function fetchLiveScore(ticker){
  // Lire depuis le ranking live (scores enrichis PDF)
  try {
    const rRes = await fetch('/api/live-ranking');
    const rData = await rRes.json();
    if (rData.ranking) {
      const r = rData.ranking.find(x => x.ticker === ticker);
      if (r && r.composite_adj > 0) {
        _renderLiveScore(ticker, {
          composite_adj:   r.composite_adj,
          live_price:      r.price,
          live_change_pct: r.change_pct,
          live_source:     'brvm.org',
          market_open:     rData.market_open,
          score_graham:    r.score_graham,
          score_dcf:       r.score_dcf,
          score_ddm:       r.score_ddm,
          score_epv:       r.score_epv,
          score_buffett:   r.score_buffett,
          score_rev_dcf:   r.score_rev_dcf,
          score_relatif:   r.score_relatif,
          score_technique: r.score_technique,
          detail_graham:   r.detail_graham,
          detail_dcf:      r.detail_dcf,
          detail_ddm:      r.detail_ddm,
          detail_epv:      r.detail_epv,
          detail_buffett:  r.detail_buffett,
          detail_rev_dcf:  r.detail_rev_dcf,
          detail_relatif:  r.detail_relatif,
          detail_technique:r.detail_technique,
          note10:          r.note10,
          statut:          r.statut,
          pe_ref_live:     r.pe_ref,
          pb_ref_live:     r.pb_ref,
          div_yield_live:  r.div_yield,
        });
        return;
      }
    }
  } catch(e) {}
  // Fallback: ancienne route
  _fetchLiveScoreFallback(ticker);
}

function _palierScoreLive(n10, statut){
  if (statut === 'suspendu') return { tier: 'Cotation suspendue', col: 'var(--note-muted)' };
  var haut = Number(window.SEUIL_NOTE_HAUT);
  var bas = Number(window.SEUIL_NOTE_BAS);
  if (n10 >= haut) return { tier: 'Fort', col: 'var(--note-green)' };
  if (n10 >= bas) return { tier: 'Modéré', col: 'var(--note-amber)' };
  return { tier: 'Très faible', col: 'var(--note-red)' };
}

function _renderLiveScore(ticker, d){
  // D.14d : extrait de _fetchLiveScoreFallback pour etre partage avec le chemin rapide (live-ranking) -- fix du bug _renderLiveScore manquante
  const el=document.getElementById('live-score-container');
  if(!el)return;
  const sc=d.composite_adj||0;
  const n10=(typeof note10num==='function')?note10num(d):(Math.round(sc/8*10)/10);
  const palier=_palierScoreLive(n10, d.statut);
  const col=palier.col;
  const tier=palier.tier;
  const chg=d.live_change_pct||0;
  const chgCol=chg>=0?'var(--green)':'var(--red)';
  const chgStr=(chg>=0?'+':'')+chg.toFixed(2)+'%';
  const price=d.live_price?(typeof fmtXOF==='function'?fmtXOF(d.live_price):d.live_price.toLocaleString('fr-FR')+' XOF'):'N/D';
  const badge=d.live_source!=='static'?'<span style="background:#00c07620;color:#00c076;font-size:10px;font-weight:700;padding:1px 6px;border-radius:10px">LIVE</span>':'';
  const models=[['Graham',d.score_graham],['DCF',d.score_dcf],['DDM',d.score_ddm],['EPV',d.score_epv],['Buffett',d.score_buffett],['RevDCF',d.score_rev_dcf],['Relatif',d.score_relatif],['Tech.',d.score_technique]];
  const bars=models.map(function(m){
    var l=m[0],v=m[1],sv=v||0;
    var hautBar=Number(window.SEUIL_NOTE_HAUT), basBar=Number(window.SEUIL_NOTE_BAS);
    var bc=(typeof couleurNote==='function')?couleurNote(sv):(sv>=hautBar?'var(--note-green)':sv>=basBar?'var(--note-amber)':'var(--note-red)');var det=d['detail_'+l.toLowerCase().replace('.','').replace('/','_')]||'';
    return '<div title="'+det+'" style="display:grid;grid-template-columns:52px 1fr 26px;align-items:center;gap:5px;font-size:11px"><span style="color:var(--t2)">'+l+'</span><div style="background:var(--border);border-radius:3px;height:4px"><div style="width:'+sv*10+'%;height:4px;border-radius:3px;background:'+bc+'"></div></div><span style="color:'+bc+';font-weight:600;text-align:right">'+sv.toFixed(1)+'</span></div>';
  }).join('');
  el.innerHTML='<div style="border:1px solid var(--border);border-radius:10px;padding:12px;margin-top:8px">'+
    '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">'+
    '<div><div style="font-size:11px;color:var(--t2);margin-bottom:3px">Score live '+badge+'</div>'+
    '<div style="font-size:12px">'+price+' <span style="color:'+chgCol+'">'+chgStr+'</span></div></div>'+
    '<div style="text-align:right"><div style="font-size:28px;font-weight:700;color:'+col+'">'+((typeof note10txt==='function')?note10txt(d):v10fmt(sc).replace('.',','))+'<span style="font-size:13px;color:var(--t2)">/10</span></div>'+
    '<div style="font-size:11px;font-weight:600;color:'+col+'">'+tier+'</div></div></div>'+
    '<div style="background:var(--border);border-radius:4px;height:5px;margin-bottom:10px">'+
    '<div style="width:'+(Math.max(0, Math.min(100, n10*10))).toFixed(0)+'%;height:5px;border-radius:4px;background:'+col+';transition:width 0.6s"></div></div>'+
    '<div style="display:flex;flex-direction:column;gap:4px;margin-bottom:8px">'+bars+'</div>'+
    '<div style="display:flex;gap:8px;flex-wrap:wrap;font-size:10px;color:var(--t2);border-top:1px solid var(--border);padding-top:6px;align-items:center">'+
    (function(){
      var ligne=(window.scores||[]).find(function(x){return x.ticker===ticker;})||{};
      var marq=function(cle){return (typeof marqueExercice==='function')?marqueExercice(anneeDuChiffre(ligne,cle)):'';};
      return '<span>P/E: '+(d.pe_ref_live||d.pe_ref||0).toFixed(1)+'x '+marq('pe')+'</span><span>P/B: '+(d.pb_ref_live||d.pb_ref||0).toFixed(1)+'x '+marq('pb')+'</span>'+
        '<span>Rdt: '+(d.div_yield_live||d.div_yield||0).toFixed(1)+'% '+marq('rendement')+'</span>';
    })()+
    '<button onclick="fetchLiveScore(\''+ticker+'\')" style="margin-left:auto;font-size:10px;padding:2px 7px;border:1px solid var(--border);border-radius:5px;cursor:pointer;background:none;color:var(--t2)">Actualiser</button></div></div>';
}

async function _fetchLiveScoreFallback(ticker){
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
    _renderLiveScore(ticker, d);
  }catch(e){var msg=e.name==='AbortError'?'Timeout — brvm.org trop lent':e.message;el.innerHTML='<div style="color:var(--red);font-size:11px">'+msg+' <button onclick="fetchLiveScore(\"'+ticker+'\")" style="margin-left:6px;font-size:10px;padding:1px 6px;border:1px solid var(--border);border-radius:4px;cursor:pointer;background:none;color:var(--t2)">Réessayer</button></div>';}
}

async function loadLiveRank(ticker) {
  try {
    const res = await fetch('/api/live-ranking');
    const d = await res.json();
    if (!d.ranking) return;
    const r = d.ranking.find(x => x.ticker === ticker);
    if (!r) return;
    if (r.statut === 'suspendu') return;
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
