// ── Analyse sectorielle — sectors.js ─────────────────────────────────────

function renderSectorPage() {
  const container = document.getElementById('sectorContent');
  if (!container) return;
  const all = window.scores || scores || [];
  if (!all.length) return;

  // Grouper par secteur
  const sectorMap = {};
  all.forEach(x => {
    const s = x.sector || 'Autre';
    if (!sectorMap[s]) sectorMap[s] = [];
    sectorMap[s].push(x);
  });

  const sectors = Object.entries(sectorMap).sort((a,b) => b[1].length - a[1].length);

  // Couleurs secteurs
  const sectorColors = {
    'Banque': '#60A5FA', 'Finance': '#60A5FA',
    'Télécoms': '#4ADE80', 'Telecommunications': '#4ADE80',
    'Industrie': '#FBBF24', 'Industriel': '#FBBF24',
    'Consommation': '#F87171', 'Agriculture': '#34D399',
    'Energie': '#FB923C', 'Utilities': '#A78BFA',
    'Distribution': '#F472B6', 'Autre': '#94A3B8'
  };
  const getColor = s => {
    for (const [k,v] of Object.entries(sectorColors))
      if (s.toLowerCase().includes(k.toLowerCase())) return v;
    return '#94A3B8';
  };

  // SVG donut global
  const total = all.length;
  const donutData = sectors.map(([s, items]) => ({
    label: s, count: items.length,
    pct: items.length/total,
    avgScore: items.reduce((a,x) => a+(x.composite_adj||0),0)/items.length,
    color: getColor(s)
  }));

  let angle = 0;
  const cx = 80, cy = 80, R = 65, r = 38;
  const slices = donutData.map(d => {
    const a1 = angle, a2 = angle + d.pct * 2 * Math.PI;
    angle = a2;
    const x1 = cx + R*Math.cos(a1), y1 = cy + R*Math.sin(a1);
    const x2 = cx + R*Math.cos(a2), y2 = cy + R*Math.sin(a2);
    const xi1 = cx + r*Math.cos(a1), yi1 = cy + r*Math.sin(a1);
    const xi2 = cx + r*Math.cos(a2), yi2 = cy + r*Math.sin(a2);
    const large = d.pct > 0.5 ? 1 : 0;
    return `<path d="M${xi1},${yi1} L${x1},${y1} A${R},${R} 0 ${large},1 ${x2},${y2} L${xi2},${yi2} A${r},${r} 0 ${large},0 ${xi1},${yi1}"
      fill="${d.color}" opacity="0.85" stroke="var(--bg1)" stroke-width="1.5">
      <title>${d.label}: ${d.count} sociétés (${(d.pct*100).toFixed(0)}%)</title></path>`;
  }).join('');
  const donutSvg = `<svg viewBox="0 0 160 160" width="160" height="160">
    ${slices}
    <text x="${cx}" y="${cy-6}" text-anchor="middle" font-size="11" fill="var(--t1)" font-weight="700">${total}</text>
    <text x="${cx}" y="${cy+8}" text-anchor="middle" font-size="9" fill="var(--t2)">sociétés</text>
  </svg>`;

  // Légende
  const legend = donutData.map(d =>
    `<div style="display:flex;align-items:center;gap:6px;font-size:11px;margin-bottom:3px">
      <span style="width:10px;height:10px;border-radius:2px;background:${d.color};flex-shrink:0"></span>
      <span style="color:var(--t2);flex:1">${d.label}</span>
      <span style="font-weight:600">${d.count}</span>
      <span style="color:${d.avgScore>=55?'var(--green)':d.avgScore>=40?'var(--amber)':'var(--red)'};min-width:36px;text-align:right">${d.avgScore.toFixed(0)}/80</span>
    </div>`).join('');

  // Cards secteurs détaillées
  const sectorCards = sectors.map(([s, items]) => {
    const color = getColor(s);
    const sorted = [...items].sort((a,b) => (b.composite_adj||0)-(a.composite_adj||0));
    const avgScore = items.reduce((a,x) => a+(x.composite_adj||0),0)/items.length;
    const avgPE = items.filter(x=>x.pe_ref&&x.pe_ref<200).reduce((a,x,_,arr) => a+x.pe_ref/arr.length, 0);
    const avgDiv = items.filter(x=>x.div_yield>0).reduce((a,x,_,arr) => a+x.div_yield/arr.length, 0);
    const positifs = items.filter(x=>(x.pdf_verdict||'').includes('POSITIF')).length;

    return `<div class="card" style="border-left:3px solid ${color};margin-bottom:12px">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px">
        <div>
          <div style="font-weight:700;font-size:13px;color:${color}">${s}</div>
          <div style="font-size:10px;color:var(--t2);margin-top:2px">${items.length} sociétés · Score moy. ${avgScore.toFixed(0)}/80</div>
        </div>
        <div style="display:flex;gap:8px;font-size:10px">
          ${avgPE>0?`<span style="background:var(--bg3);padding:2px 6px;border-radius:4px">P/E moy. ${avgPE.toFixed(1)}×</span>`:''}
          ${avgDiv>0?`<span style="background:var(--bg3);padding:2px 6px;border-radius:4px">Div ${avgDiv.toFixed(1)}%</span>`:''}
          ${positifs>0?`<span style="background:rgba(74,222,128,0.1);color:var(--green);padding:2px 6px;border-radius:4px">${positifs} POSITIF</span>`:''}
        </div>
      </div>
      <!-- Barre score moyen -->
      <div style="background:var(--bg3);border-radius:4px;height:4px;margin-bottom:10px">
        <div style="background:${color};height:4px;border-radius:4px;width:${Math.min(100,avgScore/80*100).toFixed(0)}%"></div>
      </div>
      <!-- Liste sociétés -->
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:6px">
        ${sorted.map(x => {
          const sc = x.composite_adj||0;
          const vc = sc>=60?'var(--green)':sc>=40?'var(--amber)':'var(--red)';
          return `<div onclick="showStock('${x.ticker}')" style="cursor:pointer;background:var(--bg3);border-radius:6px;padding:7px 10px;display:flex;justify-content:space-between;align-items:center;border:1px solid transparent;transition:border-color 0.2s" onmouseover="this.style.borderColor='${color}'" onmouseout="this.style.borderColor='transparent'">
            <div>
              <div style="font-weight:700;font-size:12px">${x.ticker}</div>
              <div style="font-size:9px;color:var(--t2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:80px">${x.name||''}</div>
            </div>
            <span style="font-weight:700;font-size:12px;color:${vc}">${sc.toFixed(0)}</span>
          </div>`;
        }).join('')}
      </div>
    </div>`;
  }).join('');

  container.innerHTML = `
    <div class="g2" style="margin-bottom:16px">
      <div class="card" style="margin-bottom:0">
        <div class="ct">Répartition sectorielle</div>
        <div style="display:flex;gap:16px;align-items:center">
          ${donutSvg}
          <div style="flex:1">${legend}</div>
        </div>
      </div>
      <div class="card" style="margin-bottom:0">
        <div class="ct">Classement des secteurs par score moyen</div>
        ${donutData.sort((a,b)=>b.avgScore-a.avgScore).map((d,i) => `
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
            <span style="font-size:10px;color:var(--t2);min-width:14px">${i+1}</span>
            <span style="font-size:11px;color:${d.color};flex:1">${d.label}</span>
            <div style="width:120px;background:var(--bg3);border-radius:3px;height:6px">
              <div style="background:${d.color};height:6px;border-radius:3px;width:${(d.avgScore/80*100).toFixed(0)}%"></div>
            </div>
            <span style="font-size:11px;font-weight:700;color:${d.avgScore>=55?'var(--green)':d.avgScore>=40?'var(--amber)':'var(--red)'};min-width:36px;text-align:right">${d.avgScore.toFixed(0)}/80</span>
          </div>`).join('')}
      </div>
    </div>
    ${sectorCards}`;
}
