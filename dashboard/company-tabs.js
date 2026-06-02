// Sprint 11 — Onglets fiche société (Comprendre / Chiffres / Documents)

let _ctabReportsLoaded = false;

function initCompanyTabs(ticker) {
  _ctabReportsLoaded = false;

  const btns   = document.querySelectorAll('.ctab-btn');
  const panels = document.querySelectorAll('.ctab-panel');

  btns.forEach(function(btn) {
    btn.addEventListener('click', function() {
      const tab = btn.dataset.ctab;

      btns.forEach(function(b) {
        b.classList.toggle('active', b.dataset.ctab === tab);
      });
      panels.forEach(function(p) {
        p.classList.toggle('active', p.dataset.ctab === tab);
      });

      if (tab === 'documents' && !_ctabReportsLoaded) {
        _ctabReportsLoaded = true;
        if (typeof loadStockReports === 'function') loadStockReports(ticker);
      }
    });
  });
}
