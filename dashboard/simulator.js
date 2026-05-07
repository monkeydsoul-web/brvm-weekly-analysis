var simData = {};

function simInit() {
  fetch('/api/scores').then(function(r){ return r.json(); }).then(function(data) {
    if (!window.scores) window.scores = data;
    var top = data.slice(0, 4);
    simData = {};
    top.forEach(function(s, i) {
      var w = i===0?40:i===1?30:i===2?20:10;
      simData[s.ticker] = { weight: w };
    });
    simRender();
  }).catch(function() {
    simData = { CBIBF:{weight:40}, SNTS:{weight:30}, SGBC:{weight:20}, NSBC:{weight:10} };
    simRender();
  });
}

function simAddTicker() {
  var t = prompt('Ticker BRVM (ex: ORAC, BOAB, NTLC)');
  if (!t) return;
  t = t.toUpperCase().trim();
  if (simData[t]) { showNotif(t + ' deja dans le simulateur', 'red'); return; }
  if (Object.keys(simData).length >= 8) { showNotif('Maximum 8 actions', 'red'); return; }
  var n = Object.keys(simData).length + 1;
  var base = Math.floor(100 / n);
  var rem = 100 - base * n;
  Object.keys(simData).forEach(function(k) { simData[k].weight = base; });
  simData[t] = { weight: base + rem };
  simRender();
}

function simRemove(ticker) {
  delete simData[ticker];
  var keys = Object.keys(simData);
  if (!keys.length) { simRender(); return; }
  var total = keys.reduce(function(s,k){ return s + simData[k].weight; }, 0);
  if (total !== 100) simData[keys[0]].weight += 100 - total;
  simRender();
}

function simUpdate(ticker, val) {
  simData[ticker].weight = parseInt(val);
  simRecalc();
}

function simNormalize(changed) {
  var keys = Object.keys(simData);
  var changedVal = simData[changed].weight;
  var others = keys.filter(function(k) { return k !== changed; });
  if (!others.length) { simData[changed].weight = 100; simRender(); return; }
  var remaining = Math.max(0, 100 - changedVal);
  var total = others.reduce(function(s,k){ return s + simData[k].weight; }, 0);
  if (total === 0) {
    var each = Math.floor(remaining / others.length);
    others.forEach(function(k,i){ simData[k].weight = each + (i===0 ? remaining - each*others.length : 0); });
  } else {
    others.forEach(function(k){ simData[k].weight = Math.round(simData[k].weight / total * remaining); });
  }
  simRender();
}

function simRender() {
  var container = document.getElementById('simSliders');
  if (!container) return;
  var tickers = Object.keys(simData);
  var COLORS = ['#4ADE80','#60A5FA','#FBBF24','#F87171','#A78BFA','#34D399','#FB923C','#E879F9'];
  var html = '';
  tickers.forEach(function(t, i) {
    var w = simData[t].weight || 0;
    var sc = window.scores ? window.scores.find(function(x){ return x.ticker===t; }) : null;
    var price = sc && sc.price ? Math.round(sc.price).toLocaleString('fr-FR') + ' XOF' : '---';
    var score = sc ? Math.round(sc.composite_adj||0) : 0;
    var color = COLORS[i % COLORS.length];
    html += '<div style="margin-bottom:10px">';
    html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">';
    html += '<div style="display:flex;align-items:center;gap:8px">';
    html += '<span style="width:10px;height:10px;border-radius:50%;background:' + color + ';display:inline-block"></span>';
    html += '<span style="font-weight:600;font-size:12px;cursor:pointer" onclick="showStock(\'' + t + '\')">' + t + '</span>';
    html += '<span style="font-size:10px;color:var(--t3)">' + price + '</span>';
    if (score) html += '<span style="font-size:10px;padding:1px 6px;border-radius:8px;background:rgba(255,255,255,.07)">' + score + '/80</span>';
    html += '</div>';
    html += '<div style="display:flex;align-items:center;gap:8px">';
    html += '<span style="font-size:12px;font-weight:700;color:' + color + ';min-width:36px;text-align:right" id="sim-pct-' + t + '">' + w + '%</span>';
    html += '<button onclick="simRemove(\'' + t + '\')" style="font-size:10px;padding:1px 6px;background:var(--bg3);border:1px solid var(--border);border-radius:4px;color:var(--red);cursor:pointer">x</button>';
    html += '</div></div>';
    html += '<input type="range" min="0" max="100" value="' + w + '" style="width:100%;accent-color:' + color + '"';
    html += ' oninput="simUpdate(\'' + t + '\',this.value);document.getElementById(\'sim-pct-' + t + '\').textContent=this.value+\'%\'"';
    html += ' onchange="simNormalize(\'' + t + '\')">';
    html += '</div>';
  });
  container.innerHTML = html;
  simRecalc();
}

function simRecalc() {
  var keys = Object.keys(simData);
  var total = keys.reduce(function(s,k){ return s + (simData[k].weight||0); }, 0);
  var warn = document.getElementById('sim-warning');
  if (warn) warn.style.display = Math.abs(total-100) > 1 ? 'block' : 'none';
  var invest = 1000000;
  var simDiv = 0, simYield = 0;
  var avgScore = 0;
  keys.forEach(function(t) {
    var w = (simData[t].weight||0) / 100;
    var sc = window.scores ? window.scores.find(function(x){ return x.ticker===t; }) : null;
    if (sc) {
      simDiv += invest * w * (sc.div_yield||0) / 100;
      simYield += w * (sc.div_yield||0);
      avgScore += w * (sc.composite_adj||0);
    }
  });
  var sharpe = (avgScore / 80 * 2).toFixed(2);
  var vEl = document.getElementById('sim-value');
  var yEl = document.getElementById('sim-yield');
  var sEl = document.getElementById('sim-sharpe');
  var dEl = document.getElementById('sim-div');
  if (vEl) vEl.textContent = invest.toLocaleString('fr-FR') + ' XOF';
  if (yEl) { yEl.textContent = simYield.toFixed(2) + '%'; yEl.style.color = simYield>5?'var(--green)':'var(--amber)'; }
  if (sEl) { sEl.textContent = sharpe; sEl.style.color = parseFloat(sharpe)>1?'var(--green)':'var(--amber)'; }
  if (dEl) dEl.textContent = Math.round(simDiv).toLocaleString('fr-FR') + ' XOF';
  simDrawPie();
}

function simDrawPie() {
  var el = document.getElementById('sim-chart');
  if (!el) return;
  var keys = Object.keys(simData);
  var COLORS = ['#4ADE80','#60A5FA','#FBBF24','#F87171','#A78BFA','#34D399','#FB923C','#E879F9'];
  var W=400, H=110, cx=80, cy=55, r=48;
  var total = keys.reduce(function(s,k){ return s+(simData[k].weight||0); },0)||1;
  var svg = '<svg width="100%" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '">';
  var startAngle = -Math.PI/2;
  keys.forEach(function(t,i) {
    var w = (simData[t].weight||0)/total;
    var endAngle = startAngle + w*2*Math.PI;
    var x1=cx+r*Math.cos(startAngle), y1=cy+r*Math.sin(startAngle);
    var x2=cx+r*Math.cos(endAngle),   y2=cy+r*Math.sin(endAngle);
    var large = w>0.5?1:0;
    if (w>0.001) svg += '<path d="M'+cx+','+cy+' L'+x1+','+y1+' A'+r+','+r+' 0 '+large+',1 '+x2+','+y2+' Z" fill="'+COLORS[i%COLORS.length]+'" opacity="0.85"/>';
    startAngle = endAngle;
  });
  keys.forEach(function(t,i) {
    var y = 14+i*18;
    if (y>H-10) return;
    svg += '<rect x="175" y="'+(y-8)+'" width="10" height="10" rx="2" fill="'+COLORS[i%COLORS.length]+'"/>';
    svg += '<text x="190" y="'+y+'" font-size="11" fill="#94A3B8">'+t+' '+(simData[t].weight||0)+'%</text>';
  });
  svg += '</svg>';
  el.innerHTML = svg;
}

function simReset() { simInit(); }
