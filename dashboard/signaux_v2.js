// dashboard/signaux_v2.js — Signaux n'affiche que ses propres blocs.
// Les anciennes pages Valorisation et Alertes ne sont plus empilées ici.
// Les adresses #valuation et #alerts sont redirigées vers Signaux dans core.js.

function loadSignauxValoAlertes() {
  if (typeof renderPrevisionsPage === 'function') {
    renderPrevisionsPage();
  }
}
