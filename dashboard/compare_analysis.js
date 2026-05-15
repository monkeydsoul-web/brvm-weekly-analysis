// ── Analyse comparative IA — compare_analysis.js ──────────────────────────

let _compareAnalysisTickers = [];
let _compareAnalysisResult = null;

function openCompareAnalysis(preselected) {
  // Créer/afficher le modal d'analyse comparative
  let modal = document.getElementById('ca-modal');
  if (!modal) modal = createCompareAnalysisModal();
  
  // Pré-sélectionner si fourni
  if (preselected && preselected.length) {
    _compareAnalysisTickers = [...preselected];
  }
  
  refreshCASelector();
  modal.style.display = 'flex';
}

function createCompareAnalysisModal() {
  const modal = document.createElement('div');
  modal.id = 'ca-modal';
  modal.style = 'display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.8);align-items:center;justify-content:center;padding:16px';
  modal.innerHTML = `
    <div style="background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:24px;max-width:900px;width:100%;max-height:92vh;overflow-y:auto;position:relative">
      <button onclick="closeCompareAnalysis()" style="position:absolute;top:14px;right:14px;background:var(--bg3);border:1px solid var(--border);border-radius:6px;color:var(--t2);padding:4px 12px;cursor:pointer;font-size:13px">✕</button>
      
      <div style="margin-bottom:16px">
        <h2 style="font-size:18px;font-weight:700;margin-bottom:4px">🤖 Analyse comparative IA</h2>
        <p style="font-size:12px;color:var(--t2)">Sélectionnez 2 à 6 sociétés pour une analyse approfondie par Claude</p>
      </div>

      <!-- Sélecteur -->
      <div style="margin-bottom:14px">
        <div style="font-size:11px;color:var(--t2);margin-bottom:6px">Sociétés sélectionnées (${_compareAnalysisTickers.length}/6) :</div>
        <div id="ca-selected" style="display:flex;flex-wrap:wrap;gap:6px;min-height:36px;padding:8px;background:var(--bg3);border-radius:8px;border:1px solid var(--border)"></div>
      </div>
      
      <!-- Recherche rapide -->
      <div style="margin-bottom:10px">
        <div style="font-size:11px;color:var(--t2);margin-bottom:6px">Ajouter une société :</div>
        <div id="ca-picker" style="display:flex;flex-wrap:wrap;gap:5px;max-height:120px;overflow-y:auto"></div>
      </div>

      <!-- Filtres rapides -->
      <div style="display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap">
        <span style="font-size:11px;color:var(--t2);align-self:center">Sélection rapide:</span>
        <button onclick="caSelectGroup('top5')" style="font-size:10px;padding:3px 8px;background:var(--bg3);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--t2)">Top 5</button>
        <button onclick="caSelectGroup('banque')" style="font-size:10px;padding:3px 8px;background:var(--bg3);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--t2)">Banques top</button>
        <button onclick="caSelectGroup('telecom')" style="font-size:10px;padding:3px 8px;background:var(--bg3);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--t2)">Télécoms</button>
        <button onclick="caSelectGroup('div')" style="font-size:10px;padding:3px 8px;background:var(--bg3);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--t2)">Hauts dividendes</button>
        <button onclick="caSelectGroup('clear')" style="font-size:10px;padding:3px 8px;background:var(--bg3);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--red)">✕ Effacer</button>
      </div>

      <!-- Question optionnelle -->
      <div style="margin-bottom:14px">
        <div style="font-size:11px;color:var(--t2);margin-bottom:6px">Question spécifique (optionnel) :</div>
        <input id="ca-question" type="text" placeholder="Ex: Laquelle offre le meilleur rapport risque/rendement pour 2026 ?"
          style="width:100%;padding:8px 12px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;color:var(--t1);font-size:12px;box-sizing:border-box"/>
      </div>

      <!-- Bouton lancer -->
      <button id="ca-launch-btn" onclick="launchCompareAnalysis()"
        style="width:100%;padding:12px;background:linear-gradient(135deg,#4ADE80,#22D3EE);border:none;border-radius:8px;color:#000;font-weight:700;font-size:13px;cursor:pointer;margin-bottom:16px">
        🤖 Lancer l'analyse comparative
      </button>

      <!-- Résultat -->
      <div id="ca-result" style="display:none">
        <div style="border-top:1px solid var(--border);padding-top:16px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
            <div style="font-size:13px;font-weight:700">📊 Analyse Claude</div>
            <button onclick="caExportText()" style="font-size:10px;padding:3px 8px;background:var(--bg3);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--t2)">📋 Copier</button>
          </div>
          <div id="ca-text" style="font-size:12px;color:var(--t1);line-height:1.8;white-space:pre-wrap;background:var(--bg3);border-radius:8px;padding:14px;max-height:400px;overflow-y:auto"></div>
          <div id="ca-meta" style="font-size:10px;color:var(--t3);margin-top:8px"></div>
        </div>
      </div>
    </div>`;
  
  modal.addEventListener('click', e => { if (e.target === modal) closeCompareAnalysis(); });
  document.body.appendChild(modal);
  return modal;
}

function refreshCASelector() {
  const all = window.scores || scores || [];
  const sorted = [...all].sort((a,b) => (b.composite_adj||0)-(a.composite_adj||0));
  
  // Sélectionnés
  const selEl = document.getElementById('ca-selected');
  if (selEl) {
    selEl.innerHTML = _compareAnalysisTickers.map(t => {
      const s = all.find(x=>x.ticker===t);
      const v = s?.composite_adj||0;
      const c = v>=60?'var(--green)':v>=40?'var(--amber)':'var(--red)';
      return `<span style="display:flex;align-items:center;gap:4px;background:var(--bg2);border:1px solid ${c};border-radius:6px;padding:3px 8px;font-size:11px">
        <strong style="color:${c}">${t}</strong>
        <span style="color:var(--t2);font-size:10px">${v.toFixed(0)}/80</span>
        <button onclick="caRemoveTicker('${t}')" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:11px;padding:0 2px">✕</button>
      </span>`;
    }).join('') || '<span style="color:var(--t3);font-size:11px">Aucune société sélectionnée</span>';
  }
  
  // Picker
  const picker = document.getElementById('ca-picker');
  if (picker) {
    picker.innerHTML = sorted.map(x => {
      const selected = _compareAnalysisTickers.includes(x.ticker);
      const v = x.composite_adj||0;
      const c = v>=60?'var(--green)':v>=40?'var(--amber)':'var(--red)';
      return `<button onclick="caToggleTicker('${x.ticker}')"
        style="font-size:10px;padding:3px 8px;border-radius:4px;border:1px solid ${selected?c:'var(--border)'};background:${selected?c+'22':'var(--bg3)'};color:${selected?c:'var(--t2)'};cursor:pointer;font-weight:${selected?'700':'400'}">
        ${x.ticker} <span style="opacity:0.7">${v.toFixed(0)}</span></button>`;
    }).join('');
  }
}

function caToggleTicker(ticker) {
  if (_compareAnalysisTickers.includes(ticker)) {
    _compareAnalysisTickers = _compareAnalysisTickers.filter(t=>t!==ticker);
  } else {
    if (_compareAnalysisTickers.length >= 6) { return; }
    _compareAnalysisTickers.push(ticker);
  }
  refreshCASelector();
}

function caRemoveTicker(ticker) {
  _compareAnalysisTickers = _compareAnalysisTickers.filter(t=>t!==ticker);
  refreshCASelector();
}

function caSelectGroup(group) {
  const all = window.scores || scores || [];
  const sorted = [...all].sort((a,b)=>(b.composite_adj||0)-(a.composite_adj||0));
  if (group === 'clear') { _compareAnalysisTickers = []; }
  else if (group === 'top5') { _compareAnalysisTickers = sorted.slice(0,5).map(x=>x.ticker); }
  else if (group === 'banque') { _compareAnalysisTickers = sorted.filter(x=>x.sector?.includes('Banque')).slice(0,5).map(x=>x.ticker); }
  else if (group === 'telecom') { _compareAnalysisTickers = sorted.filter(x=>x.sector?.includes('Télécom')||x.sector?.includes('Telecom')).slice(0,4).map(x=>x.ticker); }
  else if (group === 'div') { _compareAnalysisTickers = [...all].sort((a,b)=>(b.div_yield||0)-(a.div_yield||0)).slice(0,5).map(x=>x.ticker); }
  refreshCASelector();
}

async function launchCompareAnalysis() {
  if (_compareAnalysisTickers.length < 2) { return; }
  
  const btn = document.getElementById('ca-launch-btn');
  const resultDiv = document.getElementById('ca-result');
  const textDiv = document.getElementById('ca-text');
  const metaDiv = document.getElementById('ca-meta');
  
  btn.disabled = true;
  btn.textContent = '⏳ Analyse en cours...';
  resultDiv.style.display = 'none';
  
  const question = document.getElementById('ca-question')?.value || '';
  
  try {
    const res = await fetch('/api/compare-analysis', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ tickers: _compareAnalysisTickers, question })
    });
    const data = await res.json();
    
    if (data.error) throw new Error(data.error);
    
    // Formater le markdown en HTML
    let text = data.analysis || '';
    // Tableaux markdown -> HTML
    const lines = text.split('\n');
    let html = '';
    let inTable = false;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (line.startsWith('|')) {
        if (!inTable) { html += '<table style="width:100%;border-collapse:collapse;margin:8px 0;font-size:11px">'; inTable = true; }
        if (line.includes('---')) continue;
        const cells = line.split('|').filter(c=>c.trim());
        const isHeader = i < lines.length-1 && lines[i+1]?.includes('---');
        const tag = isHeader ? 'th' : 'td';
        html += '<tr>' + cells.map(c=>`<${tag} style="border:1px solid var(--border);padding:4px 8px;text-align:left">${c.trim().replace(/\*\*(.*?)\*\*/g,'<strong>$1</strong>')}</${tag}>`).join('') + '</tr>';
      } else {
        if (inTable) { html += '</table>'; inTable = false; }
        let l = line
          .replace(/^### (.*)/,'<h4 style="font-size:12px;font-weight:700;color:var(--blue);margin:10px 0 4px">$1</h4>')
          .replace(/^## (.*)/,'<h3 style="font-size:13px;font-weight:700;color:var(--t1);margin:12px 0 6px;border-bottom:1px solid var(--border);padding-bottom:4px">$1</h3>')
          .replace(/^# (.*)/,'<h2 style="font-size:14px;font-weight:700;color:var(--green);margin:14px 0 8px">$1</h2>')
          .replace(/^---$/,'<hr style="border-color:var(--border);margin:10px 0">')
          .replace(/\*\*(.*?)\*\*/g,'<strong>$1</strong>')
          .replace(/^- (.*)/,'<li style="margin:2px 0;padding-left:8px">$1</li>')
          .replace(/^> (.*)/,'<blockquote style="border-left:3px solid var(--blue);padding-left:8px;color:var(--t2);margin:4px 0">$1</blockquote>');
        if (l === line && line.trim()) l = `<p style="margin:3px 0">${line}</p>`;
        html += l;
      }
    }
    if (inTable) html += '</table>';
    textDiv.innerHTML = html;
    metaDiv.textContent = `Analyse générée le ${new Date(data.generated_at).toLocaleString('fr-FR')} pour ${data.tickers.join(', ')}`;
    resultDiv.style.display = 'block';
    resultDiv.scrollIntoView({behavior:'smooth'});
    
    _compareAnalysisResult = data;
  } catch(e) {
    textDiv.textContent = 'Erreur: ' + e.message;
    resultDiv.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = '🤖 Lancer l\'analyse comparative';
  }
}

function caExportText() {
  if (!_compareAnalysisResult) return;
  navigator.clipboard.writeText(_compareAnalysisResult.analysis).catch(()=>{});
}

function closeCompareAnalysis() {
  const m = document.getElementById('ca-modal');
  if (m) m.style.display = 'none';
}
