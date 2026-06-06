// dashboard/port_revenus_v2.js — Fusion Portefeuille + Revenus (sprints 3a + 3b)

function injectEpuration() {
  if (document.getElementById('epuration-port-revenus')) return;
  var style = document.createElement('style');
  style.id = 'epuration-port-revenus';
  style.textContent = [
    // A) Chrome duplique de #page-income : bouton retour, titre, bandeaux aide
    '#page-port #page-income .brvm-back-btn { display:none !important; }',
    '#page-port #page-income .ph { display:none !important; }',
    '#page-port #income-tab-dividendes > details { display:none !important; }',
    '#page-port #income-tab-simulateur > details { display:none !important; }',

    // B) Simulateur portefeuille-live : replie visuellement + badge Avance
    '#simPortCard { max-height:52px; overflow:hidden; opacity:0.5; transition:max-height .3s ease,opacity .3s ease; position:relative; cursor:pointer; }',
    '#simPortCard:hover { max-height:1400px; opacity:1; }',
    '#simPortCard::before { content:"Avance"; position:absolute; top:13px; right:14px; font-size:9px; font-weight:700; padding:2px 8px; border-radius:10px; background:rgba(96,165,250,.15); color:var(--blue); border:1px solid rgba(96,165,250,.3); pointer-events:none; }',

    // C) Prochains detachements : liste scrollable au lieu d une page interminable
    '#page-port #divCal { max-height:600px; overflow-y:auto; }',
  ].join('\n');
  document.head.appendChild(style);
}

function loadPortRevenus() {
  loadPortfolio();

  var pagePort   = document.getElementById('page-port');
  var pageIncome = document.getElementById('page-income');
  if (!pagePort || !pageIncome) return;

  // Garde-fou anti-doublon : deja fusionne
  if (pageIncome.parentElement === pagePort) {
    injectEpuration();
    renderDiv();
    return;
  }

  // Supprimer la class 'page' pour que nav() ne masque plus ce noeud
  pageIncome.classList.remove('page');
  pageIncome.style.display = 'block';
  pageIncome.style.padding = '0';

  var sep = document.createElement('div');
  sep.style.cssText = 'margin:28px 0 0;border-top:1px solid var(--border)';

  var hdr = document.createElement('div');
  hdr.style.cssText = 'padding:18px 0 10px;font-size:15px;font-weight:700;color:var(--text)';
  hdr.textContent = '💰 Revenus & dividendes';

  pagePort.appendChild(sep);
  pagePort.appendChild(hdr);
  pagePort.appendChild(pageIncome);

  injectEpuration();
  renderDiv();
}
