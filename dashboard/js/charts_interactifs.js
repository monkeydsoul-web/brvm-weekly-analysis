// CHARTS-1 — courbes de prix, SVG maison (pas de librairie).
// Inventaire :
//   fiche /societe : #stockChartDiv (ancien survol dans stock_chart.js)
//   Marché, onglet Indices : #mkt-courbe-brvm-c et #mkt-courbe-brvm-30
//   hors périmètre : courbe Composite de l'accueil, compare.js, backtest.js,
//   performance.js (base 100), markowitz.js
// La série complète est lue une fois. Un changement de période ne relance
// aucune requête et n'ajoute aucun point.

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
  hote.innerHTML = ''
    + '<p class="ci-lecture" aria-live="polite">'
    + '<span class="ci-date"></span>'
    + '<span class="ci-cours"></span>'
    + '<span class="ci-var"></span>'
    + '</p>'
    + '<svg class="ci-svg" role="img" aria-label="Historique du cours" viewBox="0 0 640 208" width="100%" height="208"></svg>'
    + '<div class="ci-periodes" role="group" aria-label="Période"></div>';
  lierPointeur(hote);
}

function lierPointeur(hote) {
  var svg = hote.querySelector(".ci-svg");
  if (!svg || svg.getAttribute("data-ci-lie")) return;
  svg.setAttribute("data-ci-lie", "1");
  var doigt = false;

  function choisir(evt) {
    var idx = indexAuPointeur(evt, hote);
    if (idx < 0) return;
    poserIndex(hote, idx);
  }

  svg.addEventListener("pointerdown", function(evt) {
    doigt = true;
    choisir(evt);
  });
  svg.addEventListener("pointermove", function(evt) {
    if (evt.pointerType === "mouse" || doigt) choisir(evt);
  });
  svg.addEventListener("pointerup", function() { doigt = false; });
  svg.addEventListener("pointercancel", function() { doigt = false; });
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
  var visible = filtrerPeriode(complet, periode);
  if (visible.length < 2) {
    hote.innerHTML = '<p class="ci-vide">Historique insuffisant</p>';
    hote._ciVisible = [];
    return;
  }
  assurerSquelette(hote);
  hote._ciVisible = visible;
  hote._ciPeriode = periode;
  hote.setAttribute("data-ci-debut", visible[0].date);
  hote.setAttribute("data-ci-fin", visible[visible.length - 1].date);
  hote.setAttribute("data-ci-n", String(visible.length));
  hote.setAttribute("data-ci-periode", periode);

  var W = 640;
  var H = 208;
  var padL = 56;
  var padR = 12;
  var padT = 16;
  var padB = 28;
  var CW = W - padL - padR;
  var CH = H - padT - padB;
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
  for (var g = 0; g < 4; g++) {
    var v = minP + range * g / 3;
    var y = yDe(v);
    var etiquette = v >= 1000
      ? Math.round(v).toLocaleString("fr-FR")
      : v.toLocaleString("fr-FR", { maximumFractionDigits: 1 });
    html += '<line class="ci-grille" x1="' + padL + '" y1="' + y.toFixed(1) + '" x2="' + (padL + CW) + '" y2="' + y.toFixed(1) + '"/>';
    html += '<text class="ci-label" x="' + (padL - 6) + '" y="' + (y + 3).toFixed(1) + '" text-anchor="end">' + etiquette + '</text>';
  }
  var marques = visible.length === 2 ? [0, 1] : [0, Math.round((visible.length - 1) / 2), visible.length - 1];
  var deja = {};
  for (i = 0; i < marques.length; i++) {
    var k = marques[i];
    if (deja[k]) continue;
    deja[k] = 1;
    var ancre = k === 0 ? "start" : (k === visible.length - 1 ? "end" : "middle");
    html += '<text class="ci-label" x="' + xDe(k).toFixed(1) + '" y="' + (H - 8) + '" text-anchor="' + ancre + '">' + fmtDateCourte(visible[k].date) + '</text>';
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
        if (hote._ciPeriode === id) return;
        redessiner(hote, id);
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

function poserSerie(hote, points, options) {
  if (!hote) return;
  options = options || {};
  hote._ciUnite = options.unite || "";
  hote._ciComplet = normaliserPoints(points);
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

function secoursPrix(ticker) {
  var local = pointsDepuisHistorique(window._priceHistory && window._priceHistory[ticker]);
  if (local.length >= 2) return Promise.resolve(local);
  if (window._ciHistoriquePrix) {
    return Promise.resolve(pointsDepuisHistorique(window._ciHistoriquePrix[ticker]));
  }
  return fetch("/api/price-history").then(function(r) { return r.json(); }).then(function(data) {
    window._ciHistoriquePrix = data && !data.error ? data : {};
    return pointsDepuisHistorique(window._ciHistoriquePrix[ticker]);
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
  var url = "/api/price-history-extended/" + encodeURIComponent(cle) + "?period=tout";
  fetch(url).then(function(r) { return r.json(); }).then(function(data) {
    if (!hote.isConnected || hote.getAttribute("data-ci-cle") !== cle) return;
    var points = normaliserPoints(data && data.points);
    if (points.length >= 2) {
      poserSerie(hote, points, { unite: "XOF" });
      hote.setAttribute("data-ci-etat", "ok");
      return;
    }
    return secoursPrix(cle).then(function(alt) {
      if (!hote.isConnected || hote.getAttribute("data-ci-cle") !== cle) return;
      poserSerie(hote, alt, { unite: "XOF" });
      hote.setAttribute("data-ci-etat", alt.length >= 2 ? "ok" : "vide");
    });
  }).catch(function() {
    if (!hote.isConnected) return;
    return secoursPrix(cle).then(function(alt) {
      if (!hote.isConnected || hote.getAttribute("data-ci-cle") !== cle) return;
      poserSerie(hote, alt, { unite: "XOF" });
      hote.setAttribute("data-ci-etat", alt.length >= 2 ? "ok" : "vide");
    });
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

if (typeof window !== "undefined") {
  window.decalerMoisIso = decalerMoisIso;
  window.normaliserPoints = normaliserPoints;
  window.filtrerPeriode = filtrerPeriode;
  window.periodesCouvertes = periodesCouvertes;
  window.peindreSerie = peindreSerie;
  window.chargerCourbeSociete = chargerCourbeSociete;
  window.brancherCourbesMarche = brancherCourbesMarche;
}
