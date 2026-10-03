// Graphique de la fiche société. Le dessin et les périodes sont dans
// js/charts_interactifs.js : un seul chargement, filtre local ensuite.

function loadPriceChart(ticker, containerId) {
  var hote = document.getElementById(containerId);
  if (typeof chargerCourbeSociete !== "function") {
    if (hote) hote.textContent = "Graphique indisponible";
    return;
  }
  chargerCourbeSociete(ticker, containerId);
}

function drawPriceChart(container, labels, prices) {
  if (!container || typeof peindreSerie !== "function") return;
  var points = [];
  var i;
  for (i = 0; i < (prices || []).length; i++) {
    points.push({ date: labels && labels[i] ? labels[i] : "", value: prices[i] });
  }
  peindreSerie(container, points, { unite: "XOF" });
}
