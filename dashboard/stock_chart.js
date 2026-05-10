// ── Graphiques de prix interactifs — stock_chart.js ───────────────────────

function drawPriceChart(container, labels, prices, ticker) {
  if (!container || !prices || prices.length < 2) return;

  const W = container.clientWidth || 500;
  const H = 200;
  const PAD = { top: 16, right: 12, bottom: 32, left: 52 };
  const CW = W - PAD.left - PAD.right;
  const CH = H - PAD.top - PAD.bottom;

  const minP = Math.min(...prices) * 0.98;
  const maxP = Math.max(...prices) * 1.02;
  const range = maxP - minP || 1;

  const xScale = i => PAD.left + (i / (prices.length - 1)) * CW;
  const yScale = v => PAD.top + CH - ((v - minP) / range) * CH;

  // Couleur courbe selon performance
  const isUp = prices[prices.length - 1] >= prices[0];
  const lineColor = isUp ? '#4ADE80' : '#F87171';
  const fillColor = isUp ? '#4ADE8022' : '#F8717122';

  // Points SVG
  const pts = prices.map((p, i) => `${xScale(i)},${yScale(p)}`).join(' ');
  const fillPts = `${xScale(0)},${yScale(minP)} ` + pts + ` ${xScale(prices.length-1)},${yScale(minP)}`;

  // Lignes de grille Y (4 niveaux)
  const gridLines = [0,1,2,3].map(i => {
    const v = minP + (range * i / 3);
    const y = yScale(v);
    const label = v >= 1000 ? Math.round(v/1000)+'k' : Math.round(v).toString();
    return `<line x1="${PAD.left}" y1="${y}" x2="${PAD.left+CW}" y2="${y}" stroke="rgba(255,255,255,0.06)" stroke-width="1"/>
            <text x="${PAD.left-4}" y="${y+4}" text-anchor="end" font-size="9" fill="rgba(255,255,255,0.35)">${label}</text>`;
  }).join('');

  // Labels X (max 6 labels)
  const step = Math.ceil(labels.length / 6);
  const xLabels = labels.map((l, i) => {
    if (i % step !== 0 && i !== labels.length - 1) return '';
    const short = l.length > 7 ? l.substring(2, 7) : l;
    return `<text x="${xScale(i)}" y="${H - 4}" text-anchor="middle" font-size="9" fill="rgba(255,255,255,0.35)">${short}</text>`;
  }).join('');

  // Tooltip interactif
  const tooltipId = `tt_${ticker}_${Math.random().toString(36).substr(2,5)}`;

  const svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" style="display:block;overflow:visible"
    onmousemove="chartHover(event,'${tooltipId}',${JSON.stringify(prices)},${JSON.stringify(labels)},${PAD.left},${CW},${PAD.top},${CH},${minP},${range})"
    onmouseleave="chartLeave('${tooltipId}')">
    <defs>
      <linearGradient id="grad_${tooltipId}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${lineColor}" stop-opacity="0.3"/>
        <stop offset="100%" stop-color="${lineColor}" stop-opacity="0"/>
      </linearGradient>
    </defs>
    ${gridLines}
    ${xLabels}
    <polygon points="${fillPts}" fill="url(#grad_${tooltipId})"/>
    <polyline points="${pts}" fill="none" stroke="${lineColor}" stroke-width="2" stroke-linejoin="round"/>
    <!-- Dernier point -->
    <circle cx="${xScale(prices.length-1)}" cy="${yScale(prices[prices.length-1])}" r="3" fill="${lineColor}"/>
    <!-- Tooltip elements -->
    <line id="${tooltipId}_vline" x1="0" y1="${PAD.top}" x2="0" y2="${PAD.top+CH}" stroke="rgba(255,255,255,0.2)" stroke-width="1" stroke-dasharray="4,3" opacity="0"/>
    <circle id="${tooltipId}_dot" cx="0" cy="0" r="4" fill="${lineColor}" stroke="white" stroke-width="1.5" opacity="0"/>
    <rect id="${tooltipId}_bg" x="0" y="${PAD.top+4}" width="80" height="28" rx="4" fill="rgba(15,23,42,0.92)" opacity="0"/>
    <text id="${tooltipId}_price" x="0" y="${PAD.top+14}" font-size="10" font-weight="700" fill="white" opacity="0"></text>
    <text id="${tooltipId}_date" x="0" y="${PAD.top+24}" font-size="9" fill="rgba(255,255,255,0.55)" opacity="0"></text>
  </svg>`;

  container.innerHTML = svg;
}

function chartHover(evt, id, prices, labels, padL, CW, padT, CH, minP, range) {
  const svg = evt.currentTarget;
  const rect = svg.getBoundingClientRect();
  const mx = evt.clientX - rect.left;
  const ratio = Math.max(0, Math.min(1, (mx - padL) / CW));
  const idx = Math.round(ratio * (prices.length - 1));
  if (idx < 0 || idx >= prices.length) return;

  const price = prices[idx];
  const label = labels[idx] || '';
  const x = padL + (idx / (prices.length - 1)) * CW;
  const y = padT + CH - ((price - minP) / (range || 1)) * CH;

  const priceStr = price >= 1000 ? price.toLocaleString('fr-FR') : price.toString();
  const dateStr = label.length > 10 ? label.substring(0,10) : label;

  // Positionner tooltip à gauche ou droite selon position
  const tipX = x + 85 > padL + CW ? x - 84 : x + 4;

  _setAttr(id+'_vline', {x1:x, x2:x, opacity:1});
  _setAttr(id+'_dot', {cx:x, cy:y, opacity:1});
  _setAttr(id+'_bg', {x:tipX, opacity:1});
  _setAttr(id+'_price', {x:tipX+6, opacity:1, textContent: priceStr+' XOF'});
  _setAttr(id+'_date', {x:tipX+6, opacity:1, textContent: dateStr});
}

function chartLeave(id) {
  [id+'_vline', id+'_dot', id+'_bg', id+'_price', id+'_date'].forEach(eid => {
    const el = document.getElementById(eid);
    if (el) el.setAttribute('opacity', '0');
  });
}

function _setAttr(id, attrs) {
  const el = document.getElementById(id);
  if (!el) return;
  Object.entries(attrs).forEach(([k, v]) => {
    if (k === 'textContent') el.textContent = v;
    else el.setAttribute(k, v);
  });
}

// ── Chargement et affichage du graphique dans showStock ───────────────────
async function loadPriceChart(ticker, containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = '<div style="height:200px;display:flex;align-items:center;justify-content:center;color:var(--t2);font-size:11px">Chargement...</div>';
  try {
    const res = await fetch(`/api/stock/${ticker}`);
    const data = await res.json();
    const history = data.price_history || [];
    if (history.length < 2) {
      container.innerHTML = '<div style="height:200px;display:flex;align-items:center;justify-content:center;color:var(--t2);font-size:11px">Historique insuffisant</div>';
      return;
    }
    const labels = history.map(p => p.date || p.week || '');
    const prices = history.map(p => p.price);
    const first = prices[0], last = prices[prices.length-1];
    const perf = ((last - first) / first * 100).toFixed(1);
    const perfColor = last >= first ? '#4ADE80' : '#F87171';
    const perfSign = last >= first ? '+' : '';

    // Header performance
    container.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <span style="font-size:11px;color:var(--t2)">${history.length} points · ${labels[0].substring(0,4)}→${labels[labels.length-1].substring(0,10)}</span>
        <span style="font-size:12px;font-weight:700;color:${perfColor}">${perfSign}${perf}%</span>
      </div>
      <div id="${containerId}_svg"></div>`;
    drawPriceChart(document.getElementById(containerId+'_svg'), labels, prices, ticker);
  } catch(e) {
    container.innerHTML = '<div style="height:200px;display:flex;align-items:center;justify-content:center;color:var(--t2);font-size:11px">Erreur chargement</div>';
  }
}
