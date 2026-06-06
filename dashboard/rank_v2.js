// dashboard/rank_v2.js — Fusion Classement + 4 KPIs Tableau de bord (sprint 5)

function loadRankDash() {
  renderRankLive();

  var pageRank = document.getElementById('page-rank');
  var kpis = document.getElementById('kpis');
  if (!pageRank || !kpis) return;

  // Garde-fou anti-doublon
  if (kpis.parentElement === pageRank) {
    if (typeof renderDash === 'function') renderDash({});
    return;
  }

  // Insérer #kpis avant le premier <details> de #page-rank (après le .ph header)
  var firstDetails = pageRank.querySelector(':scope > details');
  if (firstDetails) {
    pageRank.insertBefore(kpis, firstDetails);
  } else {
    pageRank.appendChild(kpis);
  }

  kpis.style.margin = '0 0 12px';

  // Peupler les 4 cartes KPI
  if (typeof renderDash === 'function') renderDash({});
}
