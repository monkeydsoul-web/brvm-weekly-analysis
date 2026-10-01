// ── Page Prévisions IA — previsions.js ────────────────────────────────────

let _prevSignaux = null;
let _sigFilter = '';

function _sigAffiche(code){
  if(code==='ACHETER') return 'Prévision favorable';
  if(code==='CONSERVER') return 'Prévision neutre';
  if(code==='ALLÉGER'||code==='ALLEGER') return 'Prévision faible';
  if(code==='ÉVITER'||code==='EVITER') return 'Prévision défavorable';
  return code||'';
}

async function renderPrevisionsPage() {
  const container = document.getElementById('page-previsions-content');
  if (!container) return;

  container.innerHTML = `
    <div style="margin:0 0 12px">
      <div style="font-size:15px;font-weight:700;color:var(--text)">Recommandations IA</div>
      <p style="font-size:12px;color:var(--t2);margin:4px 0 0;line-height:1.5">Prévision favorable, neutre ou défavorable. Distinct du conseil de la note.</p>
    </div>
    <div id="prev-signaux-panel"></div>`;

  _prevRenderSignaux();
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
      ${[['', 'Tous', _prevSignaux.length], ['ACHETER','🟢 Prévision favorable', counts['ACHETER']||0], ['CONSERVER','🟡 Prévision neutre', counts['CONSERVER']||0], ['ALLÉGER','🔴 Prévision faible', counts['ALLÉGER']||0], ['ÉVITER','⚫ Prévision défavorable', counts['ÉVITER']||0]].map(([v,l,n]) =>
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
                <span style="padding:3px 8px;border-radius:10px;font-size:10px;font-weight:600;background:${sigBg[s.signal]||''};color:${sigCol[s.signal]||'var(--t2)'}">${s.emoji} ${_sigAffiche(s.signal)}</span>
              </td>
              <td style="padding:8px;text-align:right;font-weight:600">${(typeof note10txt==='function'?note10txt(s):v10fmt(s.score))}/10</td>
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

window.renderPrevisionsPage = renderPrevisionsPage;
