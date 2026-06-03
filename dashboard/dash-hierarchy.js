(function () {
  'use strict';

  function initDashHierarchy() {
    var page = document.getElementById('page-dash');
    if (!page || page.dataset.hierarchyInit) return;
    page.dataset.hierarchyInit = '1';

    // ── Niveau 1 container ──────────────────────────────────────────────────
    var n1 = document.createElement('div');
    n1.id = 'dash-n1';

    // ── Section titre + Niveau 2 container ─────────────────────────────────
    var n2Title = document.createElement('div');
    n2Title.id = 'dash-n2-title';
    n2Title.style.cssText = [
      'font-size:var(--text-body,14px)',
      'font-weight:600',
      'text-transform:uppercase',
      'letter-spacing:1px',
      'color:var(--text-3)',
      'margin:var(--space-3,24px) 0 var(--space-1,8px)',
      'padding-bottom:var(--space-1,8px)',
      'border-bottom:1px solid var(--border-1)'
    ].join(';');
    n2Title.textContent = 'Analyse & suivi';

    var n2 = document.createElement('div');
    n2.id = 'dash-n2';

    // ── N1 : ordre cible ────────────────────────────────────────────────────
    [
      'beginner-banner-dash',
      'dash-market-summary',
      'dash-ph',
      'dash-hero',
      'kpis',
      'market-weather',
      'dash-start-guide',
      'dash-port-widget'
    ].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) n1.appendChild(el);
    });

    // ── N2 : ordre cible ────────────────────────────────────────────────────
    [
      'podium',
      'opportunities-widget',
      'dividendes-venir-widget',
      'signal-widget',
      'dash-alerts-widget',
      'dash-agenda-title',
      'dash-agenda-widget',
      'annc-widget'
    ].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) n2.appendChild(el);
    });

    // ── Insertion : n1 / titre / n2 / (N3 reste en place) ──────────────────
    // À ce stade #page-dash ne contient plus que les nœuds N3 (non déplacés).
    var firstN3 = page.firstChild;
    page.insertBefore(n1, firstN3);
    page.insertBefore(n2Title, firstN3);
    page.insertBefore(n2, firstN3);
  }

  document.addEventListener('DOMContentLoaded', initDashHierarchy);
})();
