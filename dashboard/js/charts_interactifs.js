// CHARTS-1 — courbes de prix, SVG maison (pas de librairie).
// Inventaire :
//   fiche /societe : #stockChartDiv (ancien survol dans stock_chart.js)
//   Marché, onglet Indices : #mkt-courbe-brvm-c et #mkt-courbe-brvm-30
//   hors périmètre : courbe Composite de l'accueil, compare.js, backtest.js,
//   performance.js (base 100), markowitz.js
// La série complète est lue une fois. Un changement de période ne relance
// aucune requête et n'ajoute aucun point.
// CHARTS-FIX-1 : la fiche n'utilise plus l'historique étendu. Il est faux
// jusqu'au 18/05/2026 (cours arrondi, volume qui porte le vrai prix,
// séances du 18/05/2026 incorrectes, divisions non corrigées). Seul
// /api/price-history compte, et seulement à partir du 19/05/2026.

var SEUIL_COURS_FIABLE = "2026-05-19";

var PERIODES_COURBE = [
  { id: "1M", mois: 1 },
  { id: "3M", mois: 3 },
  { id: "6M", mois: 6 },
  { id: "1A", mois: 12 },
  { id: "Tout", mois: 0 }
];

var _promessesIndice = {};

function decalerMoisIso(iso, delta) {
  var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ""));
  if (!m) return "";
  var index = (+m[1]) * 12 + (+m[2] - 1) + delta;
  var annee = Math.floor(index / 12);
  var mois = index - annee * 12;
  var dernier = new Date(Date.UTC(annee, mois + 1, 0)).getUTCDate();
  var quantieme = Math.min(+m[3], dernier);
  return new Date(Date.UTC(annee, mois, quantieme)).toISOString().slice(0, 10);
}

function normaliserPoints(brut) {
  var liste = [];
  var i, entree, date, valeur, source;
  if (!brut || !brut.length) return liste;
  for (i = 0; i < brut.length; i++) {
    entree = brut[i];
    source = "";
    if (Array.isArray(entree)) {
      date = entree[0];
      valeur = entree[1];
    } else if (entree && typeof entree === "object") {
      date = entree.date;
      source = entree.source || "";
      if (entree.close != null) valeur = entree.close;
      else if (entree.price != null) valeur = entree.price;
      else valeur = entree.value;
    } else {
      continue;
    }
    if (source === "synthetic") continue;
    date = String(date || "").slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) continue;
    valeur = Number(valeur);
    if (!(valeur > 0) || !isFinite(valeur)) continue;
    liste.push({ date: date, value: valeur });
  }
  liste.sort(function(a, b) {
    if (a.date < b.date) return -1;
    if (a.date > b.date) return 1;
    return 0;
  });
  var dedup = [];
  for (i = 0; i < liste.length; i++) {
    if (dedup.length && dedup[dedup.length - 1].date === liste[i].date) {
      dedup[dedup.length - 1] = liste[i];
    } else {
      dedup.push(liste[i]);
    }
  }
  return dedup;
}

function filtrerPeriode(points, periode) {
  var serie = normaliserPoints(points);
  if (!serie.length || periode === "Tout") return serie;
  var mois = 0;
  var i;
  for (i = 0; i < PERIODES_COURBE.length; i++) {
    if (PERIODES_COURBE[i].id === periode) mois = PERIODES_COURBE[i].mois;
  }
  if (!mois) return serie;
  var seuil = decalerMoisIso(serie[serie.length - 1].date, -mois);
  var garde = [];
  for (i = 0; i < serie.length; i++) {
    if (serie[i].date >= seuil) garde.push(serie[i]);
  }
  return garde;
}

function periodesCouvertes(points) {
  var serie = normaliserPoints(points);
  if (serie.length < 2) return [];
  var debut = serie[0].date;
  var fin = serie[serie.length - 1].date;
  var ids = [];
  var i, p, seuil;
  for (i = 0; i < PERIODES_COURBE.length; i++) {
    p = PERIODES_COURBE[i];
    if (!p.mois) {
      ids.push(p.id);
      continue;
    }
    seuil = decalerMoisIso(fin, -p.mois);
    if (debut > seuil) continue;
    if (filtrerPeriode(serie, p.id).length >= 2) ids.push(p.id);
  }
  return ids;
}

function fmtDateLongue(iso) {
  var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  if (!m) return iso || "";
  var d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  try {
    return d.toLocaleDateString("fr-FR", {
      day: "numeric",
      month: "long",
      year: "numeric",
      timeZone: "UTC"
    });
  } catch (e) {
    return m[3] + "/" + m[2] + "/" + m[1];
  }
}

function fmtDateCourte(iso) {
  var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  if (!m) return "";
  return m[3] + "/" + m[2];
}

function fmtCours(valeur, unite) {
  if (unite === "XOF") {
    return Math.round(valeur).toLocaleString("fr-FR") + " XOF";
  }
  return Number(valeur).toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

function fmtVariation(pct) {
  if (pct == null || !isFinite(pct)) return "—";
  var texte = pct.toFixed(2).replace(".", ",");
  if (pct > 0) texte = "+" + texte;
  return texte + " %";
}

function variationPoint(visible, idx) {
  if (!visible || idx <= 0) return null;
  var precedent = visible[idx - 1].value;
  if (!(precedent > 0)) return null;
  return (visible[idx].value - precedent) / precedent * 100;
}

function classeVariation(pct) {
  if (pct == null || !isFinite(pct) || Math.abs(pct) < 0.005) return "is-flat";
  return pct > 0 ? "is-up" : "is-down";
}

function assurerSquelette(hote) {
  if (hote.querySelector(".ci-svg")) return;
  var svg = '<svg class="ci-svg" role="img" aria-label="Historique du cours" viewBox="0 0 640 208" width="100%" height="208"></svg>';
  var milieu = hote.id === "stockChartDiv"
    ? '<div id="stockChartDiv_svg">' + svg + '</div>'
    : svg;
  hote.innerHTML = ''
    + '<p class="ci-lecture" aria-live="polite">'
    + '<span class="ci-date"></span>'
    + '<span class="ci-cours"></span>'
    + '<span class="ci-var"></span>'
    + '</p>'
    + milieu
    + '<div class="ci-periodes" role="group" aria-label="Période"></div>';
  lierPointeur(hote);
  lierZoom(hote);
  lierMesure(hote);
}

function unitesEtiquette(largeur) {
  var base = largeur >= 80 ? largeur : 280;
  return Math.max(11, (11 * 640) / base);
}

function largeurCourbe(hote) {
  var svg = hote.querySelector(".ci-svg");
  var largeur = svg ? svg.getBoundingClientRect().width : 0;
  if (largeur < 80) largeur = hote.getBoundingClientRect().width;
  return largeur || 0;
}

function lierMesure(hote) {
  if (!hote || hote._ciObserve || typeof ResizeObserver !== "function") return;
  hote._ciObserve = true;
  var obs = new ResizeObserver(function() {
    var largeur = largeurCourbe(hote);
    if (largeur < 80) return;
    if (Math.round(largeur) === hote._ciLargeur) return;
    if (!hote._ciVisible || hote._ciVisible.length < 2) return;
    peindreVisible(hote, hote._ciVisible);
  });
  obs.observe(hote);
}

function memeFenetre(a, b) {
  if (!a || !b || !a.length || a.length !== b.length) return false;
  return a[0].date === b[0].date && a[a.length - 1].date === b[b.length - 1].date;
}

function serieZoom(points, debut, fin) {
  var serie = normaliserPoints(points);
  if (serie.length < 2 || debut == null || fin == null || debut === "" || fin === "") return serie;
  debut = Math.round(Number(debut));
  fin = Math.round(Number(fin));
  if (!isFinite(debut) || !isFinite(fin)) return serie;
  if (debut < 0) debut = 0;
  if (fin > serie.length - 1) fin = serie.length - 1;
  if (fin < debut) return serie;
  return serie.slice(debut, fin + 1);
}

function periodeDuVisible(complet, visible, preferee) {
  var base = normaliserPoints(complet);
  var vue = normaliserPoints(visible);
  if (vue.length < 2 || base.length < 2) return "";
  var filtre;
  if (preferee) {
    filtre = preferee === "Tout" ? base : filtrerPeriode(base, preferee);
    if (memeFenetre(filtre, vue)) return preferee;
  }
  var ids = periodesCouvertes(base);
  var i;
  for (i = 0; i < ids.length; i++) {
    if (ids[i] === "Tout") continue;
    if (memeFenetre(filtrerPeriode(base, ids[i]), vue)) return ids[i];
  }
  if (memeFenetre(base, vue)) return "Tout";
  return "";
}

function evenementSurCourbe(evt, hote) {
  var cible = evt.target;
  if (cible && cible.closest && cible.closest(".ci-periodes, .brvm-zoom-bar, button, a")) return false;
  var svg = hote.querySelector(".ci-svg");
  if (!svg) return false;
  var rect = svg.getBoundingClientRect();
  if (!rect.width || !rect.height) return false;
  if (evt.clientX < rect.left || evt.clientX > rect.right) return false;
  if (evt.clientY < rect.top || evt.clientY > rect.bottom) return false;
  return true;
}

function lierPointeur(hote) {
  if (!hote || hote.getAttribute("data-ci-lie")) return;
  hote.setAttribute("data-ci-lie", "1");
  var doigt = false;

  function choisir(evt) {
    if (!evenementSurCourbe(evt, hote)) return;
    var idx = indexAuPointeur(evt, hote);
    if (idx < 0) return;
    poserIndex(hote, idx);
  }

  function noterSurvol(evt) {
    hote._ciSurCourbe = evenementSurCourbe(evt, hote);
  }

  hote.addEventListener("pointerdown", function(evt) {
    noterSurvol(evt);
    if (!hote._ciSurCourbe) return;
    doigt = true;
    choisir(evt);
  });
  hote.addEventListener("pointermove", function(evt) {
    noterSurvol(evt);
    if (evt.pointerType !== "mouse" && !doigt) return;
    choisir(evt);
  });
  hote.addEventListener("pointerup", function() { doigt = false; });
  hote.addEventListener("pointercancel", function() { doigt = false; });
  hote.addEventListener("pointerleave", function() {
    hote._ciSurCourbe = false;
    if (!hote._ciZoomSousPointeur) return;
    hote._ciZoomSousPointeur = false;
    var visible = hote._ciVisible;
    if (!visible || visible.length < 2) return;
    hote._ciDate = null;
    poserIndex(hote, visible.length - 1);
  });
}

function lierZoom(hote) {
  if (!hote || hote.id !== "stockChartDiv" || hote.getAttribute("data-ci-zoom")) return;
  hote.setAttribute("data-ci-zoom", "1");
  hote.addEventListener("brvm:zoom", function(evt) {
    var detail = (evt && evt.detail) || {};
    var zoom = hote._brvmZoom;
    var visible;
    if (zoom && zoom.labels && zoom.prices) {
      var brut = [];
      var i;
      var debut = Math.round(Number(detail.debut));
      var fin = Math.round(Number(detail.fin));
      if (!isFinite(debut) || !isFinite(fin)) return;
      for (i = debut; i <= fin && i < zoom.labels.length; i++) {
        if (i < 0) continue;
        brut.push({ date: zoom.labels[i], value: zoom.prices[i] });
      }
      visible = normaliserPoints(brut);
    } else {
      visible = serieZoom(hote._ciComplet, detail.debut, detail.fin);
    }
    if (visible.length < 2) return;
    if (hote._ciSurCourbe) hote._ciZoomSousPointeur = true;
    else {
      hote._ciDate = null;
      hote._ciZoomSousPointeur = false;
    }
    peindreVisible(hote, visible);
  });
}

function indexAuPointeur(evt, hote) {
  var svg = hote.querySelector(".ci-svg");
  var geom = hote._ciGeom;
  var visible = hote._ciVisible;
  if (!svg || !geom || !visible || visible.length < 2) return -1;
  var rect = svg.getBoundingClientRect();
  if (!rect.width) return -1;
  var x = (evt.clientX - rect.left) / rect.width * geom.W;
  var ratio = (x - geom.padL) / geom.CW;
  if (ratio < 0) ratio = 0;
  if (ratio > 1) ratio = 1;
  return Math.round(ratio * (visible.length - 1));
}

function poserIndex(hote, idx) {
  var visible = hote._ciVisible;
  var geom = hote._ciGeom;
  if (!visible || !geom || idx < 0 || idx >= visible.length) return;
  var point = visible[idx];
  var pct = variationPoint(visible, idx);
  hote._ciIndex = idx;
  hote._ciDate = point.date;
  var lecture = hote.querySelector(".ci-lecture");
  if (lecture) {
    lecture.setAttribute("data-ci-date", point.date);
    lecture.setAttribute("data-ci-valeur", String(point.value));
  }
  var dateEl = hote.querySelector(".ci-date");
  var coursEl = hote.querySelector(".ci-cours");
  var varEl = hote.querySelector(".ci-var");
  if (dateEl) dateEl.textContent = fmtDateLongue(point.date);
  if (coursEl) coursEl.textContent = fmtCours(point.value, hote._ciUnite);
  if (varEl) {
    varEl.textContent = fmtVariation(pct);
    varEl.className = "ci-var " + classeVariation(pct);
  }
  var x = geom.padL + (visible.length === 1 ? 0 : (idx / (visible.length - 1)) * geom.CW);
  var y = geom.padT + geom.CH - ((point.value - geom.minP) / geom.range) * geom.CH;
  var ligne = hote.querySelector(".ci-repere");
  var pastille = hote.querySelector(".ci-point");
  if (ligne) {
    ligne.setAttribute("x1", x.toFixed(1));
    ligne.setAttribute("x2", x.toFixed(1));
  }
  if (pastille) {
    pastille.setAttribute("cx", x.toFixed(1));
    pastille.setAttribute("cy", y.toFixed(1));
  }
}

function redessiner(hote, periode) {
  var complet = hote._ciComplet || [];
  var couvertes = periodesCouvertes(complet);
  if (!couvertes.length) {
    hote.innerHTML = '<p class="ci-vide">Historique insuffisant</p>';
    hote._ciVisible = [];
    return;
  }
  if (couvertes.indexOf(periode) < 0) periode = couvertes.indexOf("Tout") >= 0 ? "Tout" : couvertes[0];
  hote._ciChoix = periode;
  var visible = filtrerPeriode(complet, periode);
  if (visible.length < 2) {
    hote.innerHTML = '<p class="ci-vide">Historique insuffisant</p>';
    hote._ciVisible = [];
    return;
  }
  if (hote.id === "stockChartDiv") {
    assurerSquelette(hote);
    publierSociete(hote, visible);
    return;
  }
  peindreVisible(hote, visible);
}

function peindreVisible(hote, visible) {
  var complet = hote._ciComplet || visible;
  var couvertes = periodesCouvertes(complet);
  if (!visible || visible.length < 2) {
    hote.innerHTML = '<p class="ci-vide">Historique insuffisant</p>';
    hote._ciVisible = [];
    return;
  }
  var periode = periodeDuVisible(complet, visible, hote._ciChoix);
  assurerSquelette(hote);
  hote._ciVisible = visible;
  hote._ciPeriode = periode;
  hote.setAttribute("data-ci-debut", visible[0].date);
  hote.setAttribute("data-ci-fin", visible[visible.length - 1].date);
  hote.setAttribute("data-ci-n", String(visible.length));
  hote.setAttribute("data-ci-periode", periode);

  var largeur = largeurCourbe(hote);
  if (largeur >= 80) hote._ciLargeur = Math.round(largeur);
  var unites = unitesEtiquette(largeur);
  var W = 640;
  var H = 208;
  var padL = 56;
  var padR = 12;
  var padT = 16;
  var padB = 28;
  var nGrad = !largeur || largeur < 480 ? 3 : 4;
  var minV = visible[0].value;
  var maxV = visible[0].value;
  var i;
  for (i = 1; i < visible.length; i++) {
    if (visible[i].value < minV) minV = visible[i].value;
    if (visible[i].value > maxV) maxV = visible[i].value;
  }
  var minP = minV;
  var maxP = maxV;
  if (maxP === minP) {
    minP = minP * 0.98;
    maxP = maxP * 1.02;
  } else {
    var marge = (maxP - minP) * 0.08;
    minP -= marge;
    maxP += marge;
  }
  var range = (maxP - minP) || 1;
  var etiquettes = [];
  var plusLong = 0;
  var g, v, texte;
  for (g = 0; g < nGrad; g++) {
    v = minP + range * g / (nGrad - 1);
    texte = v >= 1000
      ? Math.round(v).toLocaleString("fr-FR")
      : v.toLocaleString("fr-FR", { maximumFractionDigits: 1 });
    etiquettes.push(texte);
    if (texte.length > plusLong) plusLong = texte.length;
  }
  var besoin = Math.ceil(unites * 0.62 * plusLong) + 10;
  if (besoin > padL) padL = besoin;
  if (padL > 168) padL = 168;
  if (unites > 14) padB = Math.max(padB, Math.ceil(unites) + 12);
  var CW = W - padL - padR;
  var CH = H - padT - padB;
  hote._ciGeom = { W: W, H: H, padL: padL, padT: padT, CW: CW, CH: CH, minP: minP, range: range };

  function xDe(iPoint) {
    return padL + (iPoint / (visible.length - 1)) * CW;
  }
  function yDe(valeur) {
    return padT + CH - ((valeur - minP) / range) * CH;
  }

  var hausse = visible[visible.length - 1].value >= visible[0].value;
  var sens = hausse ? "is-hausse" : "is-baisse";
  var pts = [];
  for (i = 0; i < visible.length; i++) {
    pts.push(xDe(i).toFixed(1) + "," + yDe(visible[i].value).toFixed(1));
  }
  var aire = xDe(0).toFixed(1) + "," + (padT + CH).toFixed(1) + " " + pts.join(" ") + " " + xDe(visible.length - 1).toFixed(1) + "," + (padT + CH).toFixed(1);
  var html = '<rect class="ci-hit" x="0" y="0" width="' + W + '" height="' + H + '" fill="transparent"></rect>';
  var taille = unites.toFixed(1);
  for (g = 0; g < etiquettes.length; g++) {
    v = minP + range * g / (nGrad - 1);
    var y = yDe(v);
    html += '<line class="ci-grille" x1="' + padL + '" y1="' + y.toFixed(1) + '" x2="' + (padL + CW) + '" y2="' + y.toFixed(1) + '"/>';
    html += '<text class="ci-label" font-size="' + taille + '" x="' + (padL - 6) + '" y="' + (y + unites * 0.3).toFixed(1) + '" text-anchor="end">' + etiquettes[g] + '</text>';
  }
  var marques = visible.length === 2 ? [0, 1] : [0, Math.round((visible.length - 1) / 2), visible.length - 1];
  var deja = {};
  for (i = 0; i < marques.length; i++) {
    var k = marques[i];
    if (deja[k]) continue;
    deja[k] = 1;
    var ancre = k === 0 ? "start" : (k === visible.length - 1 ? "end" : "middle");
    html += '<text class="ci-label" font-size="' + taille + '" x="' + xDe(k).toFixed(1) + '" y="' + (H - 8) + '" text-anchor="' + ancre + '">' + fmtDateCourte(visible[k].date) + '</text>';
  }
  html += '<polygon class="ci-aire ' + sens + '" points="' + aire + '"/>';
  html += '<polyline class="ci-trait ' + sens + '" points="' + pts.join(" ") + '" fill="none"/>';
  html += '<line class="ci-repere" x1="' + padL + '" y1="' + padT + '" x2="' + padL + '" y2="' + (padT + CH) + '"/>';
  html += '<circle class="ci-point ' + sens + '" cx="' + padL + '" cy="' + padT + '" r="5"/>';
  hote.querySelector(".ci-svg").innerHTML = html;

  var box = hote.querySelector(".ci-periodes");
  box.innerHTML = "";
  for (i = 0; i < couvertes.length; i++) {
    (function(id) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ci-periode" + (id === periode ? " is-on" : "");
      btn.setAttribute("data-periode", id);
      btn.setAttribute("aria-pressed", id === periode ? "true" : "false");
      btn.textContent = id;
      btn.addEventListener("click", function() {
        choisirPeriode(hote, id);
      });
      box.appendChild(btn);
    })(couvertes[i]);
  }

  var idx = visible.length - 1;
  if (hote._ciDate) {
    for (i = 0; i < visible.length; i++) {
      if (visible[i].date === hote._ciDate) { idx = i; break; }
    }
  }
  poserIndex(hote, idx);
}

function choisirPeriode(hote, id) {
  var visible = filtrerPeriode(hote._ciComplet || [], id);
  if (visible.length < 2) return;
  hote._ciChoix = id;
  hote._ciDate = null;
  if (hote.id === "stockChartDiv") {
    assurerSquelette(hote);
    publierSociete(hote, visible);
    return;
  }
  peindreVisible(hote, visible);
}

function publierSociete(hote, visible) {
  var host = document.getElementById("stockChartDiv_svg");
  if (!host || typeof window.drawPriceChart !== "function" || hote._ciDansDraw) {
    peindreVisible(hote, visible);
    return;
  }
  var labels = [];
  var prices = [];
  var i;
  for (i = 0; i < visible.length; i++) {
    labels.push(visible[i].date);
    prices.push(visible[i].value);
  }
  hote._ciDansDraw = true;
  try {
    window.drawPriceChart(host, labels, prices, hote._ciTicker || "");
  } finally {
    hote._ciDansDraw = false;
  }
}

function peindreAppel(container, labels, prices, ticker) {
  var points = [];
  var i;
  for (i = 0; i < (prices || []).length; i++) {
    points.push({ date: labels && labels[i] ? labels[i] : "", value: prices[i] });
  }
  points = normaliserPoints(points);
  if (container && container.id === "stockChartDiv_svg") {
    var hote = document.getElementById("stockChartDiv");
    if (!hote) return;
    if (ticker) hote._ciTicker = ticker;
    if (!hote._ciComplet || hote._ciComplet.length < points.length) hote._ciComplet = points;
    peindreVisible(hote, points);
    return;
  }
  if (container) peindreSerie(container, points, { unite: "XOF" });
}

function poserSerie(hote, points, options) {
  if (!hote) return;
  options = options || {};
  hote._ciUnite = options.unite || "";
  hote._ciComplet = normaliserPoints(points);
  hote._ciChoix = "Tout";
  hote._ciDate = null;
  if (hote._ciComplet.length < 2) {
    hote.innerHTML = '<p class="ci-vide">Historique insuffisant</p>';
    hote._ciVisible = [];
    hote.removeAttribute("data-ci-debut");
    hote.removeAttribute("data-ci-fin");
    return;
  }
  redessiner(hote, "Tout");
}

function peindreSerie(hote, points, options) {
  poserSerie(hote, points, options);
}

function pointsDepuisHistorique(lignes) {
  return normaliserPoints(lignes);
}

function pointsFiables(lignes) {
  var serie = normaliserPoints(lignes);
  var garde = [];
  var i;
  for (i = 0; i < serie.length; i++) {
    if (serie[i].date >= SEUIL_COURS_FIABLE) garde.push(serie[i]);
  }
  return garde;
}

function seriePrixFiable(data, ticker) {
  if (!data || data.error || !ticker) return [];
  return pointsFiables(data[ticker]);
}

function lireHistoriqueFiable(ticker) {
  var deja = seriePrixFiable(window._priceHistory, ticker);
  if (deja.length >= 2) return Promise.resolve(deja);
  if (window._ciHistoriquePrix) {
    return Promise.resolve(seriePrixFiable(window._ciHistoriquePrix, ticker));
  }
  return fetch("/api/price-history").then(function(r) { return r.json(); }).then(function(data) {
    window._ciHistoriquePrix = data && !data.error ? data : {};
    return seriePrixFiable(window._ciHistoriquePrix, ticker);
  }).catch(function() { return []; });
}

function chargerCourbeSociete(ticker, containerId) {
  var hote = document.getElementById(containerId);
  if (!hote) return;
  var cle = String(ticker || "").toUpperCase();
  if (!cle) return;
  var etat = hote.getAttribute("data-ci-etat");
  if (hote.getAttribute("data-ci-cle") === cle && (etat === "ok" || etat === "vide" || etat === "charge")) return;
  hote.setAttribute("data-ci-cle", cle);
  hote.setAttribute("data-ci-etat", "charge");
  hote.innerHTML = '<p class="ci-vide">Chargement…</p>';
  lireHistoriqueFiable(cle).then(function(points) {
    if (!hote.isConnected || hote.getAttribute("data-ci-cle") !== cle) return;
    poserSerie(hote, points, { unite: "XOF" });
    hote.setAttribute("data-ci-etat", points.length >= 2 ? "ok" : "vide");
  });
}

function chargerCourbeIndice(hote) {
  var code = hote.getAttribute("data-ci-indice");
  if (!code) return;
  var etat = hote.getAttribute("data-ci-etat");
  if (etat === "ok" || etat === "vide" || etat === "charge") return;
  hote.setAttribute("data-ci-etat", "charge");
  hote.innerHTML = '<p class="ci-vide">Chargement…</p>';
  if (!_promessesIndice[code]) {
    var url = "/api/index-history?index=" + encodeURIComponent(code) + "&range=1A";
    _promessesIndice[code] = fetch(url).then(function(r) {
      if (!r.ok) return [];
      return r.json();
    }).then(function(data) {
      return normaliserPoints(data && data.points);
    }).catch(function() { return []; });
  }
  _promessesIndice[code].then(function(points) {
    if (!hote.isConnected) return;
    poserSerie(hote, points, { unite: "" });
    hote.setAttribute("data-ci-etat", points.length >= 2 ? "ok" : "vide");
  });
}

function brancherCourbesMarche() {
  var noeuds = document.querySelectorAll("[data-ci-indice]");
  var i;
  for (i = 0; i < noeuds.length; i++) chargerCourbeIndice(noeuds[i]);
}

function enchainerDrawPriceChart() {
  if (typeof window === "undefined" || typeof window.drawPriceChart !== "function") return;
  if (window.drawPriceChart._ciEnveloppe) return;
  var precedente = window.drawPriceChart;
  function enveloppe(container, labels, prices, ticker) {
    return precedente(container, labels, prices, ticker);
  }
  enveloppe._ciEnveloppe = true;
  window.drawPriceChart = enveloppe;
}

if (typeof window !== "undefined") {
  window.decalerMoisIso = decalerMoisIso;
  window.normaliserPoints = normaliserPoints;
  window.filtrerPeriode = filtrerPeriode;
  window.periodesCouvertes = periodesCouvertes;
  window.serieZoom = serieZoom;
  window.periodeDuVisible = periodeDuVisible;
  window.unitesEtiquette = unitesEtiquette;
  window.pointsFiables = pointsFiables;
  window.peindreSerie = peindreSerie;
  window.peindreAppel = peindreAppel;
  window.chargerCourbeSociete = chargerCourbeSociete;
  window.brancherCourbesMarche = brancherCourbesMarche;
  enchainerDrawPriceChart();
}
