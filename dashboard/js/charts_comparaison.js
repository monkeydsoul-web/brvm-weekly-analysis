/* CHARTS-2 — Fiche société : superposer la société, le BRVM-COMPOSITE
   et jusqu'à deux autres sociétés, en base 100 au premier jour commun
   de données réelles. Pas de légende au survol : le nom et la performance
   sont écrits à côté de chaque courbe.

   Sources lues, rien d'autre :
   - /api/price-history (déjà chargé par l'init dans window._priceHistory)
   - /api/index-history?index=BRVM-COMPOSITE&range=1A
*/
(function (factory) {
  var api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window === "undefined") return;
  window.brvmComparaison = api;
  if (document.body) brvmInstallerComparaison(api);
  else document.addEventListener("DOMContentLoaded", function () { brvmInstallerComparaison(api); });
})(function () {
  var SEUIL = 20;
  var MAX_AUTRES = 2;
  var MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"];

  function jourValide(iso) {
    if (typeof iso !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return false;
    var p = iso.split("-");
    var annee = +p[0];
    var mois = +p[1];
    var jour = +p[2];
    var dt = new Date(Date.UTC(annee, mois - 1, jour));
    if (dt.getUTCFullYear() !== annee || dt.getUTCMonth() !== mois - 1 || dt.getUTCDate() !== jour) return false;
    var wd = dt.getUTCDay();
    return wd !== 0 && wd !== 6;
  }

  function prixNombre(p) {
    if (!p || typeof p !== "object") return null;
    var brut = p.price != null ? p.price : p.prix;
    if (typeof brut === "boolean") return null;
    var n = typeof brut === "number" ? brut : Number(brut);
    if (!isFinite(n) || n <= 0) return null;
    return n;
  }

  function pointsReels(points) {
    var par = {};
    var i;
    for (i = 0; i < (points || []).length; i++) {
      var p = points[i];
      if (!p || typeof p !== "object" || p.source === "synthetic") continue;
      var date = typeof p.date === "string" ? p.date.slice(0, 10) : "";
      if (!jourValide(date)) continue;
      var prix = prixNombre(p);
      if (prix == null) continue;
      par[date] = prix;
    }
    return Object.keys(par).sort().map(function (d) { return { date: d, price: par[d] }; });
  }

  function serieBase100(entrees, seuil) {
    if (seuil == null) seuil = SEUIL;
    var series = (entrees || []).map(function (e) {
      var pts = pointsReels(e && e.points);
      var parDate = {};
      pts.forEach(function (p) { parDate[p.date] = p.price; });
      return { id: e && e.id, nom: e && e.nom, parDate: parDate };
    });
    var dates = null;
    series.forEach(function (s) {
      var cles = Object.keys(s.parDate);
      if (dates === null) dates = cles;
      else dates = dates.filter(function (d) { return s.parDate[d] != null; });
    });
    dates = (dates || []).slice().sort();
    var base = dates.length ? dates[0] : null;
    var sortie = series.map(function (s) {
      var basePrix = base ? s.parDate[base] : null;
      var valeurs = [];
      if (basePrix) {
        dates.forEach(function (d) {
          valeurs.push({ date: d, base100: s.parDate[d] / basePrix * 100 });
        });
      }
      var perf = valeurs.length ? valeurs[valeurs.length - 1].base100 - 100 : null;
      return { id: s.id, nom: s.nom, valeurs: valeurs, perf: perf };
    });
    return {
      ok: series.length >= 2 && dates.length >= seuil,
      n: dates.length,
      base: base,
      series: sortie
    };
  }

  function textePerf(perf) {
    if (perf == null || !isFinite(perf)) return "";
    var arrondi = Math.round(perf * 10) / 10;
    if (Object.is(arrondi, -0)) arrondi = 0;
    var abs = Math.abs(arrondi).toFixed(1).replace(".", ",");
    if (arrondi < 0) return "-" + abs + " %";
    if (arrondi > 0) return "+" + abs + " %";
    return "0,0 %";
  }

  function dateFr(iso) {
    var p = String(iso || "").split("-");
    if (p.length !== 3) return iso || "";
    return Number(p[2]) + " " + MOIS[Number(p[1]) - 1] + " " + p[0];
  }

  return {
    SEUIL: SEUIL,
    MAX_AUTRES: MAX_AUTRES,
    pointsReels: pointsReels,
    serieBase100: serieBase100,
    textePerf: textePerf,
    dateFr: dateFr
  };
});

function brvmInstallerComparaison(api) {
  if (window.__BRVM_CMP_INSTALLE) return;
  window.__BRVM_CMP_INSTALLE = 1;
  var cacheIndice = null;
  var seq = 0;

  function ech(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function tickerFiche() {
    var m = /\/societe\/([A-Za-z0-9]{2,12})$/i.exec(location.pathname || "");
    if (m) return m[1].toUpperCase();
    if (window._openTicker) return String(window._openTicker).toUpperCase();
    return "";
  }

  function nomDe(ticker, repli) {
    var liste = window.scores || [];
    var i;
    for (i = 0; i < liste.length; i++) {
      if (liste[i] && liste[i].ticker === ticker && liste[i].name) return String(liste[i].name);
    }
    return repli || ticker;
  }

  function palette() {
    var clair = document.documentElement.classList.contains("light");
    if (clair) return ["#0550ae", "#9a6700", "#1a7f37", "#9d174d"];
    return ["#7dd3fc", "#fbbf24", "#4ade80", "#f9a8d4"];
  }

  function encreAxe() {
    var clair = document.documentElement.classList.contains("light");
    return clair ? "#57606a" : "#8b949e";
  }

  function traitGrille() {
    var clair = document.documentElement.classList.contains("light");
    return clair ? "rgba(36,41,47,0.16)" : "rgba(230,237,243,0.16)";
  }

  function mesure(texte) {
    var c = mesure._c || (mesure._c = document.createElement("canvas"));
    var ctx = c.getContext("2d");
    ctx.font = "700 12px sans-serif";
    return Math.ceil(ctx.measureText(String(texte || "")).width);
  }

  var DELAI_LECTURE_MS = 10000;
  var promessePrix = null;
  var promesseIndice = null;

  function pretPrix() {
    return window._priceHistory && Object.keys(window._priceHistory).length;
  }

  function lireJson(url, contexte) {
    return new Promise(function (resolve, reject) {
      var ctrl = (typeof AbortController === "function") ? new AbortController() : null;
      var timer = setTimeout(function () { if (ctrl) ctrl.abort(); }, DELAI_LECTURE_MS);
      var opts = ctrl ? { signal: ctrl.signal } : {};
      fetch(url, opts).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      }).then(function (data) {
        clearTimeout(timer);
        resolve(data);
      }).catch(function (e) {
        clearTimeout(timer);
        console.error("[BRVM] " + contexte, e);
        reject(e);
      });
    });
  }

  function exigerObjet(data, contexte) {
    if (!data || typeof data !== "object" || Array.isArray(data) || data.error) {
      var e = new Error("réponse inutilisable");
      console.error("[BRVM] " + contexte, e);
      throw e;
    }
    return data;
  }

  function lirePrix() {
    if (pretPrix()) return Promise.resolve(window._priceHistory);
    if (promessePrix) return promessePrix;
    promessePrix = lireJson("/api/price-history", "cours pour la comparaison").then(function (d) {
      exigerObjet(d, "cours pour la comparaison");
      window._priceHistory = d;
      return d;
    });
    promessePrix.catch(function () { promessePrix = null; });
    return promessePrix;
  }

  function attendrePrix() {
    if (pretPrix()) return Promise.resolve(window._priceHistory);
    return new Promise(function (resolve, reject) {
      var essais = 0;
      var t = setInterval(function () {
        essais += 1;
        if (pretPrix()) {
          clearInterval(t);
          resolve(window._priceHistory);
        } else if (essais >= 40) {
          clearInterval(t);
          var e = new Error("historique absent");
          console.error("[BRVM] cours pour la comparaison", e);
          reject(e);
        }
      }, 100);
    });
  }

  function historiqueComposite() {
    if (cacheIndice) return Promise.resolve(cacheIndice);
    if (promesseIndice) return promesseIndice;
    promesseIndice = lireJson("/api/index-history?index=BRVM-COMPOSITE&range=1A", "indice BRVM-COMPOSITE").then(function (data) {
      exigerObjet(data, "indice BRVM-COMPOSITE");
      cacheIndice = data;
      return cacheIndice;
    });
    promesseIndice.catch(function () { promesseIndice = null; });
    return promesseIndice;
  }

  function afficherPanneComparer(carte) {
    carte.setAttribute("data-cmp-etat", "panne");
    carte.innerHTML = '<div class="ct" id="cmp-courbes-titre">Comparer</div>'
      + '<p class="cmp-message" role="status">Données indisponibles</p>'
      + '<button type="button" class="ci-reessayer">Réessayer</button>';
    carte.querySelector(".ci-reessayer").addEventListener("click", function () {
      if (carte.getAttribute("data-cmp-etat") !== "panne") return;
      carte.setAttribute("data-cmp-etat", "charge");
      relancerComparer(carte);
    });
  }

  function relancerComparer(carte) {
    var etat = carte._cmp;
    if (!etat) return;
    var manquant = !etat.hist ? "prix" : (!etat.indice ? "indice" : "");
    if (!manquant) {
      carte.setAttribute("data-cmp-etat", "ok");
      peindre(carte);
      return;
    }
    var job = manquant === "prix" ? lirePrix() : historiqueComposite();
    job.then(function (val) {
      if (!carte.isConnected) return;
      if (manquant === "prix") etat.hist = val;
      else etat.indice = val;
      if (etat.hist && etat.indice) {
        carte.setAttribute("data-cmp-etat", "ok");
        peindre(carte);
      } else {
        afficherPanneComparer(carte);
      }
    }, function () {
      if (!carte.isConnected) return;
      afficherPanneComparer(carte);
    });
  }

  function pointsIndice(body) {
    var brut = (body && body.points) || [];
    var sortie = [];
    var i;
    for (i = 0; i < brut.length; i++) {
      var p = brut[i];
      if (Array.isArray(p)) sortie.push({ date: p[0], price: p[1] });
      else if (p && typeof p === "object") sortie.push({ date: p.date, price: p.price != null ? p.price : p[1] });
    }
    return sortie;
  }

  function pointsTicker(hist, ticker) {
    var brut = (hist && hist[ticker]) || [];
    return Array.isArray(brut) ? brut : [];
  }

  function entrees(hist, indice, ticker, autres) {
    var liste = [{
      id: ticker,
      nom: nomDe(ticker, ticker),
      points: pointsTicker(hist, ticker)
    }, {
      id: "BRVM-COMPOSITE",
      nom: "BRVM-COMPOSITE",
      points: pointsIndice(indice)
    }];
    (autres || []).forEach(function (t) {
      liste.push({ id: t, nom: nomDe(t, t), points: pointsTicker(hist, t) });
    });
    return liste;
  }

  function monter(ticker) {
    var ancre = document.getElementById("stockChartDiv");
    if (!ancre) return;
    var deja = document.getElementById("cmp-courbes");
    if (deja && deja.getAttribute("data-ticker") === ticker && document.body.contains(deja)) return;
    if (deja) deja.remove();
    var carteCours = ancre.closest ? ancre.closest(".card") : ancre.parentNode;
    var grille = carteCours && carteCours.closest ? carteCours.closest(".g2") : null;
    var ref = grille || carteCours;
    if (!ref || !ref.parentNode) return;
    var carte = document.createElement("div");
    carte.className = "card";
    carte.id = "cmp-courbes";
    carte.setAttribute("data-ticker", ticker);
    ref.parentNode.insertBefore(carte, ref.nextSibling);
    var n = ++seq;
    carte._cmp = { ticker: ticker, autres: [], note: "" };
    carte.innerHTML = '<div class="ct" id="cmp-courbes-titre">Comparer</div>'
      + '<p class="cmp-intro">Chargement des historiques…</p>';
    Promise.all([
      attendrePrix().then(function (h) { return { ok: true, v: h }; }, function () { return { ok: false }; }),
      historiqueComposite().then(function (d) { return { ok: true, v: d }; }, function () { return { ok: false }; })
    ]).then(function (res) {
      if (n !== seq) return;
      var hote = document.getElementById("cmp-courbes");
      if (!hote || hote.getAttribute("data-ticker") !== ticker) return;
      if (res[0].ok) hote._cmp.hist = res[0].v;
      if (res[1].ok) hote._cmp.indice = res[1].v;
      if (hote._cmp.hist && hote._cmp.indice) {
        hote.setAttribute("data-cmp-etat", "ok");
        peindre(hote);
      } else {
        afficherPanneComparer(hote);
      }
    });
  }

  function peindre(carte) {
    var etat = carte._cmp;
    if (!etat || !etat.hist) return;
    var calcul = api.serieBase100(entrees(etat.hist, etat.indice, etat.ticker, etat.autres));
    var seul = api.serieBase100(entrees(etat.hist, etat.indice, etat.ticker, []));
    etat.calcul = calcul;
    etat.seul = seul;
    var html = '<div class="ct" id="cmp-courbes-titre">Comparer</div>';
    if (!seul.ok) {
      var nom = nomDe(etat.ticker, etat.ticker);
      html += '<p class="cmp-message" role="status" data-cmp-message="court" data-cmp-n="' + seul.n + '">'
        + 'Trop peu de séances en commun entre ' + ech(nom) + ' et le BRVM-COMPOSITE : '
        + seul.n + ', il en faut au moins ' + api.SEUIL + '. Aucune courbe n\'est tracée.</p>';
      carte.innerHTML = html;
      return;
    }
    html += '<p class="cmp-intro" data-cmp-base="' + ech(calcul.base) + '">Base 100 au '
      + ech(api.dateFr(calcul.base))
      + ', premier jour commun.</p>';
    html += choixHtml(etat);
    if (etat.note) html += '<p class="cmp-note" role="status" data-cmp-note="1">' + ech(etat.note) + '</p>';
    html += '<div id="cmp-courbes-dessin"></div>';
    carte.innerHTML = html;
    brancherChoix(carte);
    tracer(carte, calcul);
  }

  function choixHtml(etat) {
    var liste = window.scores || [];
    var pris = {};
    pris[etat.ticker] = 1;
    etat.autres.forEach(function (t) { pris[t] = 1; });
    var options = liste.filter(function (s) { return s && s.ticker && !pris[s.ticker]; });
    var plein = etat.autres.length >= api.MAX_AUTRES;
    var html = '<div class="cmp-choix">';
    html += '<label for="cmp-courbes-ajout">Ajouter une société</label>';
    html += '<select id="cmp-courbes-ajout"' + (plein || !options.length ? " disabled" : "") + '>';
    html += '<option value="">Choisir…</option>';
    options.forEach(function (s) {
      html += '<option value="' + ech(s.ticker) + '">' + ech(s.ticker) + ' — ' + ech(s.name || "") + '</option>';
    });
    html += '</select>';
    html += '<button type="button" class="btn btn-o" id="cmp-courbes-btn"' + (plein ? " disabled" : "") + '>Ajouter</button>';
    html += '</div>';
    if (etat.autres.length) {
      html += '<div class="cmp-puces">';
      etat.autres.forEach(function (t) {
        html += '<span class="cmp-puce">' + ech(nomDe(t, t))
          + ' <button type="button" class="cmp-retirer" data-cmp-retirer="' + ech(t) + '">Retirer</button></span>';
      });
      html += '</div>';
    }
    if (plein) {
      html += '<p class="cmp-note">Deux sociétés en plus du BRVM-COMPOSITE, c\'est le maximum.</p>';
    }
    return html;
  }

  function brancherChoix(carte) {
    var btn = carte.querySelector("#cmp-courbes-btn");
    var sel = carte.querySelector("#cmp-courbes-ajout");
    if (btn && sel) {
      btn.addEventListener("click", function () {
        var t = sel.value;
        if (!t) return;
        var etat = carte._cmp;
        if (etat.autres.length >= api.MAX_AUTRES) return;
        if (etat.autres.indexOf(t) >= 0 || t === etat.ticker) return;
        var essai = etat.autres.concat([t]);
        var calcul = api.serieBase100(entrees(etat.hist, etat.indice, etat.ticker, essai));
        if (!calcul.ok) {
          etat.note = nomDe(t, t) + " n'a que " + calcul.n
            + " séances en commun. Il en faut " + api.SEUIL + " pour tracer sa courbe.";
          peindre(carte);
          return;
        }
        etat.autres = essai;
        etat.note = "";
        peindre(carte);
      });
    }
    carte.querySelectorAll("[data-cmp-retirer]").forEach(function (b) {
      b.addEventListener("click", function () {
        var t = b.getAttribute("data-cmp-retirer");
        var etat = carte._cmp;
        etat.autres = etat.autres.filter(function (x) { return x !== t; });
        etat.note = "";
        peindre(carte);
      });
    });
  }

  function tracer(carte, calcul) {
    var hote = carte.querySelector("#cmp-courbes-dessin");
    if (!hote) return;
    var largeur = hote.getBoundingClientRect().width;
    if (largeur < 40) {
      if (hote.getAttribute("data-cmp-attente") !== "1") {
        hote.innerHTML = "";
        hote.setAttribute("data-cmp-attente", "1");
      }
      return;
    }
    hote.removeAttribute("data-cmp-attente");
    var couleurs = palette();
    var labels = calcul.series.map(function (s, i) {
      var fin = s.valeurs[s.valeurs.length - 1];
      return {
        i: i,
        nom: s.nom,
        perf: api.textePerf(s.perf),
        fin: fin.base100,
        couleur: couleurs[i % couleurs.length]
      };
    });
    var plusLarge = 72;
    labels.forEach(function (lb) {
      plusLarge = Math.max(plusLarge, mesure(lb.nom), mesure(lb.perf));
    });
    var W = Math.floor(largeur);
    var CH = 168;
    var PAD = { top: 18, right: plusLarge + 24, bottom: 28, left: 36 };
    if (PAD.left + PAD.right + 80 > W) {
      PAD.right = Math.max(88, W - PAD.left - 80);
    }
    var CW = Math.max(40, W - PAD.left - PAD.right);
    var valeurs = [];
    calcul.series.forEach(function (s) {
      s.valeurs.forEach(function (v) { valeurs.push(v.base100); });
    });
    var minV = Math.min.apply(null, valeurs.concat([100]));
    var maxV = Math.max.apply(null, valeurs.concat([100]));
    var marge = (maxV - minV) * 0.08 || 4;
    minV -= marge;
    maxV += marge;
    var range = maxV - minV || 1;
    var n = calcul.series[0].valeurs.length;
    function xScale(i) { return PAD.left + (n <= 1 ? CW / 2 : (i / (n - 1)) * CW); }
    function yScale(v) { return PAD.top + CH - ((v - minV) / range) * CH; }

    labels.forEach(function (lb) {
      lb.y = yScale(lb.fin);
    });
    labels.sort(function (a, b) { return a.y - b.y; });
    var ecart = 28;
    if (labels.length && labels[0].y < PAD.top + 8) {
      var decal = PAD.top + 8 - labels[0].y;
      labels.forEach(function (lb) { lb.y += decal; });
    }
    var k;
    for (k = 1; k < labels.length; k++) {
      if (labels[k].y < labels[k - 1].y + ecart) labels[k].y = labels[k - 1].y + ecart;
    }
    var basLabel = labels.length ? labels[labels.length - 1].y + 16 : PAD.top + CH;
    var extra = Math.max(0, basLabel - (PAD.top + CH));
    var H = PAD.top + CH + extra + PAD.bottom;

    var axe = encreAxe();
    var grille = traitGrille();
    var lignesY = [0, 1, 2, 3].map(function (i) {
      var v = minV + range * i / 3;
      var y = yScale(v);
      return '<line x1="' + PAD.left + '" y1="' + y + '" x2="' + (PAD.left + CW) + '" y2="' + y + '" stroke="' + grille + '" stroke-width="1"/>'
        + '<text x="' + (PAD.left - 6) + '" y="' + (y + 4) + '" text-anchor="end" font-size="11" fill="' + axe + '">' + Math.round(v) + '</text>';
    }).join("");
    var y100 = yScale(100);
    var baseLigne = '<line x1="' + PAD.left + '" y1="' + y100 + '" x2="' + (PAD.left + CW) + '" y2="' + y100 + '" stroke="' + axe + '" stroke-width="1" stroke-dasharray="4 3"/>';

    var dates = calcul.series[0].valeurs.map(function (v) { return v.date; });
    var marques = [0, Math.floor((dates.length - 1) / 2), dates.length - 1];
    var vusX = {};
    var xLabels = marques.filter(function (i) {
      if (vusX[i]) return false;
      vusX[i] = 1;
      return true;
    }).map(function (i) {
      var d = dates[i] || "";
      var court = d.length >= 10 ? d.slice(8, 10) + "/" + d.slice(5, 7) : d;
      return '<text x="' + xScale(i) + '" y="' + (PAD.top + CH + extra + 18) + '" text-anchor="middle" font-size="11" fill="' + axe + '">' + ech(court) + '</text>';
    }).join("");

    var courbes = calcul.series.map(function (s, i) {
      var couleur = couleurs[i % couleurs.length];
      var pts = s.valeurs.map(function (v, j) { return xScale(j) + "," + yScale(v.base100); }).join(" ");
      var fin = s.valeurs[s.valeurs.length - 1];
      return '<polyline points="' + pts + '" fill="none" stroke="' + couleur + '" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>'
        + '<circle cx="' + xScale(s.valeurs.length - 1) + '" cy="' + yScale(fin.base100) + '" r="3.5" fill="' + couleur + '"/>';
    }).join("");

    var etiquettes = labels.map(function (lb) {
      var x = PAD.left + CW + 8;
      return '<text class="cmp-label" data-cmp-id="' + ech(calcul.series[lb.i].id) + '" data-cmp-role="nom" x="' + x + '" y="' + (lb.y - 2) + '" font-size="12" font-weight="700" fill="' + lb.couleur + '">' + ech(lb.nom) + '</text>'
        + '<text class="cmp-label" data-cmp-id="' + ech(calcul.series[lb.i].id) + '" data-cmp-role="perf" x="' + x + '" y="' + (lb.y + 12) + '" font-size="12" font-weight="700" fill="' + lb.couleur + '">' + ech(lb.perf) + '</text>';
    }).join("");

    hote.innerHTML = '<svg data-cmp-graphique="1" viewBox="0 0 ' + W + ' ' + H + '" width="100%" role="img" aria-label="Comparaison en base 100" style="font-family:sans-serif">'
      + lignesY + baseLigne + xLabels + courbes + etiquettes
      + '</svg>';
  }

  function redessiner() {
    var carte = document.getElementById("cmp-courbes");
    if (!carte || !carte._cmp || !carte._cmp.calcul || !carte._cmp.calcul.ok) return;
    if (!carte.querySelector("#cmp-courbes-dessin") && carte._cmp.hist) {
      peindre(carte);
      return;
    }
    tracer(carte, carte._cmp.calcul);
  }

  var timer = 0;
  function planifier() {
    if (timer) return;
    timer = setTimeout(function () {
      timer = 0;
      var ticker = tickerFiche();
      var ancre = document.getElementById("stockChartDiv");
      if (!ticker || !ancre) return;
      var carte = document.getElementById("cmp-courbes");
      if (carte && carte.getAttribute("data-ticker") === ticker && document.body.contains(carte)) {
        if (carte.getAttribute("data-cmp-attente") === "1" || (carte.querySelector("[data-cmp-attente]"))) redessiner();
        return;
      }
      monter(ticker);
    }, 40);
  }

  var fiche = document.getElementById("page-stock");
  var volet = document.getElementById("stock-slideover");
  if (fiche) new MutationObserver(planifier).observe(fiche, { childList: true, subtree: true });
  if (volet) new MutationObserver(planifier).observe(volet, { childList: true, subtree: true });
  window.addEventListener("resize", redessiner);
  document.addEventListener("click", function (e) {
    var cible = e.target && e.target.closest ? e.target : null;
    if (!cible || !cible.closest) return;
    if (cible.closest("[data-theme-btn]")) {
      redessiner();
      return;
    }
    if (cible.closest(".ctab-btn, .stock-tab")) setTimeout(redessiner, 30);
  });
  planifier();
}
