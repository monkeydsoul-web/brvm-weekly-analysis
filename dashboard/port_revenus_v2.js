// dashboard/port_revenus_v2.js — Fusion Portefeuille + Revenus (sprint 3a)

function loadPortRevenus() {
  loadPortfolio();

  const pagePort   = document.getElementById('page-port');
  const pageIncome = document.getElementById('page-income');
  if (!pagePort || !pageIncome) return;

  // Garde-fou anti-doublon : déjà fusionné
  if (pageIncome.parentElement === pagePort) {
    renderDiv();
    return;
  }

  // Supprimer la class 'page' pour que nav() ne masque plus ce noeud
  pageIncome.classList.remove('page');
  pageIncome.style.display = 'block';
  pageIncome.style.padding = '0';

  const sep = document.createElement('div');
  sep.style.cssText = 'margin:28px 0 0;border-top:1px solid var(--border)';

  const hdr = document.createElement('div');
  hdr.style.cssText = 'padding:18px 0 10px;font-size:15px;font-weight:700;color:var(--text)';
  hdr.textContent = '💰 Revenus & dividendes';

  pagePort.appendChild(sep);
  pagePort.appendChild(hdr);
  pagePort.appendChild(pageIncome);

  renderDiv();
}
