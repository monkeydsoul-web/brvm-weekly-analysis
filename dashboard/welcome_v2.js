// dashboard/welcome_v2.js — Accueil : résumé du marché, des conseils et des actualités.

function _lierDepartAccueil() {
  if (window._accueilNavLie || typeof nav !== 'function') return;
  window._accueilNavLie = 1;
  var orig = nav;
  nav = function(id) {
    if (id !== 'welcome') {
      window._accueilIndicesParti = 0;
      window._accueilLargeurParti = 0;
      window._accueilActusParti = 0;
    }
    return orig.apply(this, arguments);
  };
}

function loadWelcomeHero() {
  _lierDepartAccueil();
  if (document.getElementById('page-welcome')) renderAccueil();
}

function _echapAccueil(v) {
  if (typeof _escIndice === 'function') return _escIndice(v == null ? '' : v);
  return String(v == null ? '' : v)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _frFixe(n, dec) {
  return Number(n).toLocaleString('fr-FR', {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec
  });
}

function _fmtVariation(v) {
  if (v == null || v === '' || !isFinite(Number(v))) return '—';
  var n = Number(v);
  var txt = _frFixe(n, 2);
  if (n > 0) txt = '+' + txt;
  return txt + '\u00a0%';
}

function _classeConseil(row) {
  var a = (typeof conseilAffiche === 'function') ? conseilAffiche(row) : null;
  if (!a || a.suspendu) return '';
  if (a.libelle === 'Intéressant') return 'is-interessant';
  if (a.libelle === 'À surveiller') return 'is-surveiller';
  if (a.libelle === 'Prudence') return 'is-prudence';
  return '';
}

function _sensVariation(v) {
  if (v == null || v === '' || !isFinite(Number(v))) return 'is-flat';
  var n = Number(v);
  if (n > 0) return 'is-up';
  if (n < 0) return 'is-down';
  return 'is-flat';
}

function _nombreAccueil(v) {
  if (v == null || v === '') return null;
  var n = Number(v);
  return isFinite(n) ? n : null;
}

function _frGroupe(n, dec) {
  if (n == null || !isFinite(Number(n))) return '—';
  var neg = Number(n) < 0;
  var fixe = Math.abs(Number(n)).toFixed(dec);
  var morceaux = fixe.split('.');
  var entier = morceaux[0];
  var groupes = [];
  var i = entier.length;
  while (i > 0) {
    var debut = Math.max(0, i - 3);
    groupes.unshift(entier.slice(debut, i));
    i = debut;
  }
  var out = groupes.join('\u202f');
  if (dec > 0) out += ',' + morceaux[1];
  return (neg ? '-' : '') + out;
}

function _avecSigne(n, dec) {
  var txt = _frGroupe(Math.abs(Number(n)), dec);
  if (n > 0) return '+' + txt;
  if (n < 0) return '-' + txt;
  return txt;
}

function _texteSansAccent(s) {
  return String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}

function _lireNombreFr(brut) {
  var s = String(brut).replace(/\u202f/g, '').replace(/\u00a0/g, '').replace(/ /g, '');
  s = s.replace(/[^\d,.\-]/g, '');
  if (!s || s === '-' || s === ',' || s === '.') return null;
  var neg = s.charAt(0) === '-';
  if (neg) s = s.slice(1);
  var lastComma = s.lastIndexOf(',');
  var lastDot = s.lastIndexOf('.');
  var dec = -1;
  if (lastComma >= 0 && lastDot >= 0) dec = Math.max(lastComma, lastDot);
  else if (lastComma >= 0 && (s.length - lastComma - 1) > 0 && (s.length - lastComma - 1) <= 2) dec = lastComma;
  else if (lastDot >= 0 && (s.length - lastDot - 1) > 0 && (s.length - lastDot - 1) <= 2) dec = lastDot;
  var entier = dec >= 0 ? s.slice(0, dec).replace(/[.,]/g, '') : s.replace(/[.,]/g, '');
  var frac = dec >= 0 ? s.slice(dec + 1).replace(/[.,]/g, '') : '';
  if (!/^\d+$/.test(entier) || (frac && !/^\d+$/.test(frac))) return null;
  var n = Number(entier + (frac ? '.' + frac : ''));
  if (!isFinite(n)) return null;
  return neg ? -n : n;
}

function _montantVersMd(texte) {
  if (texte == null) return null;
  var brut = String(texte).replace(/\u202f/g, ' ').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
  if (!brut || brut === '—' || brut === '-' || brut === '–') return null;
  var lib = _texteSansAccent(brut);
  var dejaMd = /milliard|\bmds?\b/.test(lib);
  var enMillions = !dejaMd && /million|\bmn\b/.test(lib);
  var nombre = _lireNombreFr(brut);
  if (nombre == null) return null;
  if (dejaMd) return nombre;
  if (enMillions) return nombre / 1000;
  if (Math.abs(nombre) >= 1000000) return nombre / 1000000000;
  return nombre;
}

function _mdFcfa(n) {
  if (n == null || !isFinite(Number(n))) return '—';
  return _frGroupe(n, 2) + ' Md FCFA';
}

function _choisirTexteActivite(act, genre) {
  var dict = act || {};
  var cles = Object.keys(dict);
  var choix = '';
  var rang = -1;
  var i;
  for (i = 0; i < cles.length; i++) {
    var valeur = dict[cles[i]];
    if (valeur == null || String(valeur).trim() === '') continue;
    var n = _texteSansAccent(cles[i]);
    if (n.indexOf('obligation') >= 0) continue;
    var ok = false;
    var r = 0;
    if (genre === 'cap') {
      ok = n.indexOf('capitalisation') >= 0 && n.indexOf('action') >= 0;
      r = 2;
    } else {
      ok = n.indexOf('valeur') >= 0 && (n.indexOf('echange') >= 0 || n.indexOf('transig') >= 0 || n.indexOf('transaction') >= 0);
      r = n.indexOf('action') >= 0 ? 2 : 1;
    }
    if (ok && r > rang) {
      rang = r;
      choix = String(valeur);
    }
  }
  return choix;
}

function _compterLargeur(prices) {
  var h = 0;
  var b = 0;
  var s = 0;
  var dict = prices || {};
  Object.keys(dict).forEach(function(k) {
    var row = dict[k];
    if (!row || row.change_pct == null || row.change_pct === '') return;
    var ch = Number(row.change_pct);
    if (!isFinite(ch)) return;
    if (row.price == null || row.price === '' || !isFinite(Number(row.price))) return;
    if (ch > 0) h += 1;
    else if (ch < 0) b += 1;
    else s += 1;
  });
  return { hausses: h, baisses: b, stables: s, total: h + b + s };
}

function _ecartPoints(item) {
  if (!item) return null;
  var courant = _nombreAccueil(item.current);
  var veille = _nombreAccueil(item.prev);
  if (courant == null || veille == null) return null;
  return courant - veille;
}

// ytd des indices : fraction renvoyée par /api/market
// (cours / clôture du 31/12/2025 − 1). L'affichage multiplie par 100 une seule fois.
function _texteYtdIndice(ratio) {
  var n = _nombreAccueil(ratio);
  if (n == null) return '—';
  return _avecSigne(n * 100, 2) + '\u00a0%';
}

function _phraseDepuisJanvier(ratio) {
  var valeur = _texteYtdIndice(ratio);
  if (valeur === '—') return 'depuis\u00a0le\u00a01er\u00a0janvier\u00a0:\u00a0—';
  return 'depuis\u00a0le\u00a01er\u00a0janvier\u00a0:\u00a0' + valeur;
}

function _compositeMarche(d) {
  var indices = (d && d.indices) || [];
  var i;
  for (i = 0; i < indices.length; i++) {
    var nom = indices[i] && indices[i].name ? String(indices[i].name).toUpperCase() : '';
    if (nom.indexOf('COMPOSITE') >= 0 && nom.indexOf('TOTAL') < 0) return indices[i];
  }
  return null;
}

function _texteMacroYtd(d) {
  var composite = _compositeMarche(d);
  if (!composite) return '—';
  return _texteYtdIndice(composite.ytd);
}

function _ligneSeanceIndice(item) {
  if (!item) return '—';
  var pts = _ecartPoints(item);
  var ytd = _nombreAccueil(item.ytd);
  if (pts == null && ytd == null) return '—';
  var gauche = pts == null ? '— pts sur la séance' : (_avecSigne(pts, 2) + ' pts sur la séance');
  return gauche + ' · ' + _phraseDepuisJanvier(ytd);
}

function _pointsHistorique(d) {
  if (!d) return null;
  var brut = d.points || d.series || d.history || d.values;
  if (!brut || brut.length < 2) return null;
  var out = [];
  var i;
  for (i = 0; i < brut.length; i++) {
    var v = brut[i];
    var n = (v != null && typeof v === 'object')
      ? _nombreAccueil(v.v != null ? v.v : (v.value != null ? v.value : v.close))
      : _nombreAccueil(v);
    if (n == null) return null;
    out.push(n);
  }
  return out;
}

function _cheminCourbe(valeurs) {
  var w = 320;
  var h = 72;
  var pad = 4;
  var min = valeurs[0];
  var max = valeurs[0];
  var i;
  for (i = 1; i < valeurs.length; i++) {
    if (valeurs[i] < min) min = valeurs[i];
    if (valeurs[i] > max) max = valeurs[i];
  }
  var span = (max - min) || 1;
  var d = '';
  for (i = 0; i < valeurs.length; i++) {
    var x = pad + (w - pad * 2) * (i / (valeurs.length - 1));
    var y = pad + (h - pad * 2) * (1 - (valeurs[i] - min) / span);
    d += (i ? ' L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
  }
  return d;
}

function _comptesConseil(rows) {
  var c = { 'Intéressant': 0, 'À surveiller': 0, 'Prudence': 0 };
  (rows || []).forEach(function(x) {
    var a = (typeof conseilAffiche === 'function') ? conseilAffiche(x) : null;
    if (a && !a.suspendu && Object.prototype.hasOwnProperty.call(c, a.libelle)) c[a.libelle] += 1;
  });
  return c;
}

function _trouverIndice(indices, pred) {
  var liste = indices || [];
  for (var i = 0; i < liste.length; i++) {
    var nom = liste[i] && liste[i].name ? String(liste[i].name).toUpperCase() : '';
    if (nom && pred(nom)) return liste[i];
  }
  return null;
}

function _motUtile(mot) {
  if (!mot) return false;
  if (/^d['’]/i.test(mot)) return false;
  return !/^(de|du|des|la|le|les|et|d)$/i.test(mot);
}

function _initialesSociete(nom, ticker) {
  var mots = String(nom || '').replace(/[()]/g, ' ').split(/[\s·/]+/).filter(_motUtile);
  var premier = mots[0] || '';
  var lettres = '';
  if (/^[A-ZÀ-Ÿ0-9]{2,4}$/.test(premier)) lettres = premier.slice(0, 2);
  else if (mots.length >= 2) lettres = mots[0].charAt(0) + mots[1].charAt(0);
  else if (mots.length === 1) lettres = mots[0].slice(0, 2);
  else lettres = String(ticker || '').slice(0, 2);
  return lettres.toLocaleUpperCase('fr-FR');
}

function _teintePastille(ticker) {
  var s = String(ticker || '');
  var h = 0;
  var i;
  for (i = 0; i < s.length; i++) h = (h + s.charCodeAt(i) * (i + 1)) % 6;
  return 'mn-' + h;
}

function _nomCourt(row) {
  var nom = row && row.name ? String(row.name) : '';
  var sec = row && row.sector ? String(row.sector) : '';
  if (nom && sec) return nom + ' · ' + sec;
  return nom || sec || '';
}

function _fmtCours(n) {
  if (n == null || n === '' || !isFinite(Number(n))) return '—';
  if (typeof fmtXOF === 'function') return fmtXOF(n);
  return '—';
}

function _libelleBadge(row) {
  var a = (typeof conseilAffiche === 'function') ? conseilAffiche(row) : null;
  if (!a) return '—';
  if (a.suspendu) return a.libelle || '—';
  if (a.libelle === 'Intéressant' || a.libelle === 'À surveiller' || a.libelle === 'Prudence') return a.libelle;
  return '—';
}

function _mieuxNotees(rows) {
  var liste = (rows || []).filter(function(x) {
    return x && x.ticker && x.statut !== 'suspendu';
  });
  liste.sort(function(a, b) {
    var na = (typeof note10num === 'function') ? note10num(a) : 0;
    var nb = (typeof note10num === 'function') ? note10num(b) : 0;
    if (na !== nb) return nb - na;
    if (typeof triCommeClassement === 'function') return triCommeClassement(a, b);
    return String(a.ticker || '').localeCompare(String(b.ticker || ''), 'fr');
  });
  return liste.slice(0, 4);
}

function _htmlAnneau(row) {
  var n = (typeof note10num === 'function') ? note10num(row) : 0;
  var note = (typeof note10txt === 'function') ? note10txt(row) : _frFixe(n, 1);
  var part = Math.max(0, Math.min(10, Number(n) || 0)) / 10;
  var tour = 2 * Math.PI * 15.5;
  var plein = (tour * part).toFixed(2);
  var reste = (tour - tour * part).toFixed(2);
  return '<span class="accueil-anneau ' + _classeConseil(row) + '">'
    + '<svg viewBox="0 0 36 36" aria-hidden="true">'
    + '<circle class="accueil-anneau-piste" cx="18" cy="18" r="15.5"></circle>'
    + '<circle class="accueil-anneau-arc" cx="18" cy="18" r="15.5" stroke-dasharray="' + plein + ' ' + reste + '"></circle>'
    + '</svg>'
    + '<span class="accueil-anneau-note">' + _echapAccueil(note) + '</span>'
    + '</span>';
}

function _htmlCarteNote(x) {
  var ticker = String(x.ticker || '').toUpperCase();
  var lib = _libelleBadge(x);
  var clsBadge = (typeof classePrincipale === 'function') ? classePrincipale(x) : 'bx';
  var note = (typeof note10txt === 'function') ? note10txt(x) : '';
  var nom = _nomCourt(x);
  var aria = ticker;
  if (nom) aria += ', ' + nom;
  if (note) aria += ', note ' + note + ' sur 10';
  if (lib && lib !== '—') aria += ', ' + lib;
  return '<button type="button" class="accueil-mieux-carte" data-ticker="' + _echapAccueil(ticker) + '" aria-label="' + _echapAccueil(aria) + '">'
    + '<span class="accueil-mieux-haut">'
    + '<span class="accueil-pastille ' + _teintePastille(ticker) + '" aria-hidden="true">' + _echapAccueil(_initialesSociete(x.name, ticker)) + '</span>'
    + '<span class="accueil-mieux-id"><strong class="accueil-mieux-ticker">' + _echapAccueil(ticker) + '</strong>'
    + '<span class="accueil-mieux-nom">' + _echapAccueil(nom) + '</span></span>'
    + _htmlAnneau(x)
    + '</span>'
    + '<span class="accueil-mieux-cours">'
    + '<span class="accueil-mieux-prix">' + _echapAccueil(_fmtCours(x.price)) + '</span>'
    + baliseVariationJour(ticker, 'accueil-var-pill ' + _sensVariation(variationJour(ticker).pct))
    + '</span>'
    + '<span class="accueil-badge ' + clsBadge + '">' + _echapAccueil(lib) + '</span>'
    + '</button>';
}

function _jourSeance(iso) {
  if (iso == null || iso === '') return '';
  var s = String(iso).trim();
  if (!/^\d{4}-\d{2}-\d{2}(?:[T\s].*)?$/.test(s)) return '';
  var d = new Date(s);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Africa/Abidjan' });
}

function _sousTitreSeance(marche, statut) {
  var jour = _jourSeance(marche && marche.session_date) || _jourSeance(statut && statut.session_date);
  return jour ? ('Plus fortes variations · ' + jour) : 'Plus fortes variations';
}

function _poserSousTitreSeance() {
  var sous = document.getElementById('accueil-seance-sous');
  if (sous && sous.isConnected) {
    var session = (_variationLive && typeof _variationLive.session_date === 'string')
      ? _variationLive.session_date : '';
    sous.textContent = _sousTitreSeance(session ? { session_date: session } : null);
  }
  _poserLibellesVariation();
}

function _classementAccueil() {
  if (window.scores && window.scores.length) return window.scores;
  if (typeof scores !== 'undefined' && scores && scores.length) return scores;
  return [];
}

function _tickerDansClassement(ticker) {
  var t = String(ticker || '').toUpperCase();
  if (!t) return false;
  return _classementAccueil().some(function(x) {
    return x && String(x.ticker || '').toUpperCase() === t;
  });
}

function _htmlLigneSeance(x) {
  var ticker = String((x && x.ticker) || '').toUpperCase();
  if (!ticker) return '';
  var corps = '<strong class="accueil-seance-ticker">' + _echapAccueil(ticker) + '</strong>'
    + '<span class="accueil-seance-cours">' + _echapAccueil(_fmtCours(x.price)) + '</span>'
    + baliseVariationJour(ticker, 'accueil-var-pill ' + _sensVariation(variationJour(ticker).pct));
  if (_tickerDansClassement(ticker)) {
    return '<button type="button" class="accueil-seance-ligne" data-ticker="' + _echapAccueil(ticker) + '">' + corps + '</button>';
  }
  return '<div class="accueil-seance-ligne is-inerte">' + corps + '</div>';
}

function _htmlColonneSeance(titre, cls, lignes) {
  var corps = (lignes || []).length
    ? lignes.slice(0, 5).map(_htmlLigneSeance).join('')
    : '<p class="accueil-vide">Aucune variation.</p>';
  return '<div class="accueil-seance-col"><h3 class="accueil-seance-h ' + cls + '">' + titre + '</h3>' + corps + '</div>';
}

function _remplirMouvements(d) {
  var bloc = document.getElementById('accueil-mouvements');
  var grille = document.getElementById('accueil-mvt-grille');
  window._accueilMarche = d || null;
  _poserSousTitreSeance();
  if (!bloc || !grille) return;
  var hausses = ((d && d.top5) || []).filter(function(x) { return x && x.ticker; }).slice(0, 5);
  var baisses = ((d && d.flop5) || []).filter(function(x) { return x && x.ticker; }).slice(0, 5);
  if (!hausses.length && !baisses.length) {
    grille.innerHTML = '<p class="accueil-vide">Variations de séance indisponibles.</p>';
    bloc.hidden = false;
    return;
  }
  grille.innerHTML = _htmlColonneSeance('▲ Hausses', 'is-up', hausses)
    + _htmlColonneSeance('▼ Baisses', 'is-down', baisses);
  bloc.hidden = false;
  grille.querySelectorAll('.accueil-seance-ligne[data-ticker]').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var t = btn.getAttribute('data-ticker');
      if (t && typeof _openStock === 'function') _openStock(t);
    });
  });
}

function _poserBadge(el, n) {
  if (!el) return;
  if (n == null || !isFinite(Number(n))) {
    el.textContent = '—';
    el.className = 'accueil-badge is-flat';
    return;
  }
  el.textContent = _avecSigne(n, 2) + '\u00a0%';
  el.className = 'accueil-badge ' + (n > 0 ? 'is-up' : n < 0 ? 'is-down' : 'is-flat');
}

function _remplirComposite(item, repliTexte) {
  var val = document.getElementById('accueil-composite-val');
  var badge = document.getElementById('accueil-composite-badge');
  var seance = document.getElementById('accueil-composite-seance');
  var courant = item ? _nombreAccueil(item.current) : null;
  if (val) {
    if (courant != null) val.textContent = _frGroupe(courant, 2);
    else val.textContent = repliTexte ? String(repliTexte) : '—';
  }
  _poserBadge(badge, courant != null && item ? _nombreAccueil(item.change) : null);
  if (seance) seance.textContent = courant != null ? _ligneSeanceIndice(item) : '—';
}

function _remplirBrvm30(item, repliTexte) {
  var val = document.getElementById('accueil-brvm30-val');
  var badge = document.getElementById('accueil-brvm30-badge');
  var courant = item ? _nombreAccueil(item.current) : null;
  if (val) {
    if (courant != null) val.textContent = _frGroupe(courant, 2);
    else val.textContent = repliTexte ? String(repliTexte) : '—';
  }
  _poserBadge(badge, courant != null && item ? _nombreAccueil(item.change) : null);
}

function _remplirLargeur(compte) {
  var nEl = document.getElementById('accueil-largeur-n');
  var barre = document.getElementById('accueil-largeur-barre');
  var sEl = document.getElementById('accueil-largeur-s');
  if (!compte || !compte.total) {
    if (nEl) nEl.textContent = '—';
    if (barre) {
      barre.hidden = true;
      barre.innerHTML = '';
      barre.removeAttribute('aria-label');
    }
    if (sEl) sEl.textContent = '';
    return;
  }
  if (nEl) {
    nEl.innerHTML = '<span class="is-up">' + compte.hausses.toLocaleString('fr-FR') + '</span>'
      + '<span class="accueil-largeur-sep"> / </span>'
      + '<span class="is-down">' + compte.baisses.toLocaleString('fr-FR') + '</span>';
  }
  if (barre) {
    barre.hidden = false;
    barre.setAttribute('role', 'img');
    barre.setAttribute('aria-label', compte.hausses + ' hausses, ' + compte.stables + ' stables, ' + compte.baisses + ' baisses');
    barre.innerHTML = '<span class="is-hausse" style="flex:' + compte.hausses + ' 1 0"></span>'
      + '<span class="is-stable" style="flex:' + compte.stables + ' 1 0"></span>'
      + '<span class="is-baisse" style="flex:' + compte.baisses + ' 1 0"></span>';
  }
  if (sEl) {
    var mot = compte.stables > 1 ? ' stables' : ' stable';
    sEl.textContent = compte.stables.toLocaleString('fr-FR') + mot;
  }
}

function _texteActiviteAccueil(v) {
  if (typeof _texteActivite === 'function') return _texteActivite(v);
  if (v == null) return '';
  var s = String(v).trim();
  if (!s || s === '—' || s === '-') return '';
  return s;
}

function _appliquerCourbe(points, reel) {
  var trait = document.getElementById('accueil-courbe-trait');
  var svg = document.querySelector('#accueil-courbe .accueil-courbe');
  var legende = document.getElementById('accueil-courbe-legende');
  if (!trait) return;
  if (!reel || !points) {
    trait.setAttribute('d', 'M0 50 C28 48 42 54 68 42 S118 18 152 28 S206 58 246 36 S286 16 320 22');
    trait.setAttribute('stroke-dasharray', '6 5');
    if (svg) {
      svg.classList.add('is-exemple');
      svg.classList.remove('is-reel');
    }
    if (legende) legende.textContent = 'Courbe illustrative · EXEMPLE · valeur et variation réelles';
    return;
  }
  trait.setAttribute('d', _cheminCourbe(points));
  trait.removeAttribute('stroke-dasharray');
  if (svg) {
    svg.classList.remove('is-exemple');
    svg.classList.add('is-reel');
  }
  if (legende) legende.textContent = 'Historique publié · valeur et variation réelles';
}

function _activerPeriodes(periodes) {
  var box = document.getElementById('accueil-periodes');
  if (!box) return;
  var liste = Array.isArray(periodes) ? periodes : [];
  box.querySelectorAll('button[data-periode]').forEach(function(btn) {
    var dispo = liste.indexOf(btn.getAttribute('data-periode')) >= 0;
    btn.disabled = !dispo;
    btn.setAttribute('aria-disabled', dispo ? 'false' : 'true');
    btn.classList.toggle('is-on', false);
    if (dispo) btn.removeAttribute('title');
    else btn.setAttribute('title', "Historique de l'indice indisponible");
  });
}

function _accueilHistoriqueIndice(nom, periode, callback) {
  var url = '/api/index-history?indice=' + encodeURIComponent(nom || 'composite')
    + '&periode=' + encodeURIComponent(periode || '');
  fetch(url).then(function(r) {
    if (!r.ok) throw new Error('absent');
    return r.json();
  }).then(function(d) {
    callback(d || null);
  }).catch(function() {
    callback(null);
  });
}

function _brancherPeriodes() {
  var box = document.getElementById('accueil-periodes');
  if (!box || box.getAttribute('data-lie')) return;
  box.setAttribute('data-lie', '1');
  box.addEventListener('click', function(e) {
    var btn = e.target && e.target.closest ? e.target.closest('button[data-periode]') : null;
    if (!btn || btn.disabled || !box.contains(btn)) return;
    box.querySelectorAll('button[data-periode]').forEach(function(b) { b.classList.remove('is-on'); });
    btn.classList.add('is-on');
    _accueilHistoriqueIndice('composite', btn.getAttribute('data-periode'), function(d) {
      var points = _pointsHistorique(d);
      if (points) _appliquerCourbe(points, true);
    });
  });
}

// Sous ce seuil, la courbe illustrative et les onglets restent masqués.
// window.BRVM_INDEX_HISTORY peut porter un décompte ou des points déjà connus.
// Il n'est pas posé aujourd'hui : aucune séance n'est comptée ici, et aucun
// appel à /api/index-history n'est fait. La courbe réelle n'est pas branchée.
var SEUIL_SEANCES_COURBE = 20;

function _seancesIndiceConnues() {
  var src = window.BRVM_INDEX_HISTORY;
  if (typeof src === 'number' && isFinite(src)) return src;
  if (Array.isArray(src)) return src.length;
  if (src && typeof src === 'object') {
    if (typeof src.seances === 'number' && isFinite(src.seances)) return src.seances;
    if (Array.isArray(src.points)) return src.points.length;
    if (Array.isArray(src.series)) return src.series.length;
  }
  return 0;
}

function _masquerCourbeComposite() {
  var zone = document.getElementById('accueil-courbe');
  var periodes = document.getElementById('accueil-periodes');
  if (zone) zone.hidden = true;
  if (periodes) periodes.hidden = true;
}

function _chargerCourbeComposite() {
  if (_seancesIndiceConnues() < SEUIL_SEANCES_COURBE) {
    _masquerCourbeComposite();
    return;
  }
  // Le seuil serait atteint, mais la série réelle n'est pas dessinée ici.
  _masquerCourbeComposite();
}

function _remplirMontants(act) {
  var echange = document.getElementById('accueil-echange');
  var cap = document.getElementById('accueil-cap');
  if (echange) echange.textContent = _mdFcfa(_montantVersMd(_choisirTexteActivite(act, 'echange')));
  if (cap) cap.textContent = _mdFcfa(_montantVersMd(_choisirTexteActivite(act, 'cap')));
}


// Une seule requête /api/market pour le bandeau et l'accueil.
// La promesse est gardée 5 min : chargement, navigation et minuteur
// de la même période partagent un seul GET. Le serveur, lui, reste
// plus court (60 s en séance) ; le front ne le relit qu'à cette cadence.
var DELAI_MARCHE_MS = 20000;
var PERIODE_MARCHE_MS = 5 * 60 * 1000;
var _PROMESSE_MARCHE_MS = PERIODE_MARCHE_MS;
var _promesseMarche = null;
var _promesseMarcheDepuis = 0;
var _timerMarche = 0;

// Même fenêtre que live_data.is_market_open_at : lun–ven, 09:00 inclus,
// 15:30 exclus, en UTC. L'horloge du navigateur décide ; pas de second
// appel /api/status pour savoir s'il faut relire /api/market.
function _seanceOuverteMaintenant() {
  var d = new Date();
  var wd = d.getUTCDay();
  if (wd === 0 || wd === 6) return false;
  var mins = d.getUTCHours() * 60 + d.getUTCMinutes();
  return mins >= 9 * 60 && mins < 15 * 60 + 30;
}

function _tickMarcheSeance() {
  if (!_seanceOuverteMaintenant()) return;
  if (_promesseMarche && (Date.now() - _promesseMarcheDepuis) < _PROMESSE_MARCHE_MS) {
    // Le minuteur peut parler quelques centaines de ms avant les 5 min
    // (il est armé au chargement, la première lecture part juste après).
    var reste = _PROMESSE_MARCHE_MS - (Date.now() - _promesseMarcheDepuis);
    if (reste > 0 && reste <= 2000) setTimeout(_tickMarcheSeance, reste);
    return;
  }
  if (typeof loadMarketWidget === 'function') loadMarketWidget(false);
}

function _armerRafraichissementMarche() {
  if (typeof setInterval !== 'function') return;
  if (_timerMarche && typeof clearInterval === 'function') clearInterval(_timerMarche);
  _timerMarche = setInterval(_tickMarcheSeance, PERIODE_MARCHE_MS);
}

function _auChangementDePageMarche() {
  if (!_seanceOuverteMaintenant()) return;
  if (_promesseMarche && (Date.now() - _promesseMarcheDepuis) < _PROMESSE_MARCHE_MS) return;
  if (typeof loadMarketWidget === 'function') loadMarketWidget(false);
}

// Le serveur rend son cache puis le rafraîchit derrière. Si ce cache a
// plus de 90 s en séance, une seule relecture part ~10 s plus tard.
// Pas une boucle : tant que la réponse suivante est encore ancienne,
// on n'en programme pas une autre.
var SEUIL_FRAICHEUR_MARCHE_MS = 90 * 1000;
var DELAI_RELECTURE_MARCHE_MS = 10 * 1000;
var _relectureMarcheArmee = 0;

function _noterFraicheurMarche(d, depuis) {
  if (!_seanceOuverteMaintenant()) {
    _relectureMarcheArmee = 0;
    return;
  }
  var brut = d && d.updated_at;
  var instant = brut ? new Date(brut).getTime() : NaN;
  // Âge au moment de l'appel réseau, pas à la reprise de la promesse :
  // un retour sur l'accueil 2 min plus tard ne vieillit pas une réponse fraîche.
  var age = depuis - instant;
  if (!(age > SEUIL_FRAICHEUR_MARCHE_MS)) {
    _relectureMarcheArmee = 0;
    return;
  }
  if (_relectureMarcheArmee) return;
  _relectureMarcheArmee = 1;
  setTimeout(function() {
    _promesseMarche = null;
    if (typeof loadMarketWidget === 'function') loadMarketWidget(false);
  }, DELAI_RELECTURE_MARCHE_MS);
}

function demanderMarche(forcer) {
  if (!forcer && _promesseMarche && (Date.now() - _promesseMarcheDepuis) < _PROMESSE_MARCHE_MS) {
    return _promesseMarche;
  }
  _promesseMarcheDepuis = Date.now();
  var depuis = _promesseMarcheDepuis;
  // Un échec ne reste pas en cache 5 min : la navigation suivante
  // et le prochain tour relisent, au lieu de rejouer la promesse rejetée.
  var promesse = _telechargerMarche(0).then(function(d) {
    _noterFraicheurMarche(d, depuis);
    return d;
  }, function(e) {
    if (_promesseMarche === promesse) _promesseMarche = null;
    throw e;
  });
  _promesseMarche = promesse;
  // Le minuteur repart avec cette lecture : le prochain tour tombe
  // quand la promesse a 5 min, pas en double avec elle.
  _armerRafraichissementMarche();
  return _promesseMarche;
}

function _telechargerMarche(essai) {
  return new Promise(function(resolve, reject) {
    var ctrl = (typeof AbortController === 'function') ? new AbortController() : null;
    var timer = setTimeout(function() { if (ctrl) ctrl.abort(); }, DELAI_MARCHE_MS);
    var opts = ctrl ? { signal: ctrl.signal } : {};
    fetch('/api/market', opts).then(function(r) {
      clearTimeout(timer);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(resolve).catch(function(e) {
      clearTimeout(timer);
      if (essai < 1) {
        setTimeout(function() {
          _telechargerMarche(essai + 1).then(resolve, reject);
        }, 700);
        return;
      }
      reject(e);
    });
  });
}


// Une seule lecture de la variation du jour pour les six vues.
// Même cache que demanderMarche : une promesse partagée pendant 60 s.
var DELAI_VARIATION_MS = 20000;
var _PROMESSE_VARIATION_MS = 60000;
var _promesseVariation = null;
var _promesseVariationDepuis = 0;
var _variationLive = null;

function demanderVariation(forcer) {
  if (!forcer && _promesseVariation && (Date.now() - _promesseVariationDepuis) < _PROMESSE_VARIATION_MS) {
    return _promesseVariation;
  }
  _promesseVariationDepuis = Date.now();
  _promesseVariation = _telechargerVariation(0);
  return _promesseVariation;
}

function _empreinteVariation(d) {
  if (!d || typeof d !== 'object') return '';
  var prices = d.prices || {};
  var cles = Object.keys(prices).sort();
  var morceaux = [String(d.session_date || ''), d.seance_ouverte ? '1' : '0'];
  var i;
  for (i = 0; i < cles.length; i++) {
    var row = prices[cles[i]] || {};
    morceaux.push(cles[i] + '=' + row.change_pct + '/' + row.price + '/' + row.volume);
  }
  return morceaux.join('|');
}

function _telechargerVariation(essai) {
  return new Promise(function(resolve, reject) {
    var ctrl = (typeof AbortController === 'function') ? new AbortController() : null;
    var timer = setTimeout(function() { if (ctrl) ctrl.abort(); }, DELAI_VARIATION_MS);
    var opts = ctrl ? { signal: ctrl.signal } : {};
    fetch('/api/live', opts).then(function(r) {
      clearTimeout(timer);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function(d) {
      var avant = _empreinteVariation(_variationLive);
      _variationLive = d || null;
      if (_empreinteVariation(d) !== avant) {
        try { redessinerVariations(); } catch (err) { /* le dessin ne casse pas la promesse */ }
      }
      resolve(d);
    }).catch(function(e) {
      clearTimeout(timer);
      if (essai < 1) {
        setTimeout(function() {
          _telechargerVariation(essai + 1).then(resolve, reject);
        }, 700);
        return;
      }
      reject(e);
    });
  });
}

function _instantVariation() {
  return new Date();
}

function _dateAbidjan(instant) {
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Africa/Abidjan',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    }).format(instant);
  } catch (e) {
    return '';
  }
}

function variationJour(ticker) {
  var t = String(ticker || '').toUpperCase();
  var live = _variationLive;
  var prices = live && live.prices ? live.prices : null;
  var row = (prices && t) ? prices[t] : null;
  var session = null;
  if (row && typeof row.session_date === 'string' && row.session_date) session = row.session_date;
  else if (live && typeof live.session_date === 'string' && live.session_date) session = live.session_date;
  var pct = null;
  if (row && row.price != null && row.price !== '' && row.source !== 'unavailable') {
    if (row.change_pct != null && row.change_pct !== '' && isFinite(Number(row.change_pct))) {
      pct = Number(row.change_pct);
    }
  }
  if (row && row.volume === 0 && pct === 0) pct = null;
  return {
    pct: pct,
    session_date: session,
    seance_ouverte: !!(live && live.seance_ouverte === true)
  };
}

function texteVariationJour(ticker) {
  return _fmtVariation(variationJour(ticker).pct);
}

function libelleSeanceVariation() {
  var live = _variationLive;
  if (!live || typeof live.session_date !== 'string') return '';
  var session = live.session_date;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(session)) return '';
  var auj = _dateAbidjan(_instantVariation());
  var pasAujourdhui = !auj || session !== auj;
  var pasDEchange = live.seance_ouverte !== true;
  if (!pasAujourdhui && !pasDEchange) return '';
  return 'séance du ' + session.slice(8, 10) + '/' + session.slice(5, 7);
}

function baliseVariationJour(ticker, classe) {
  var t = String(ticker || '').toUpperCase();
  var texte = texteVariationJour(t);
  var lib = libelleSeanceVariation();
  var attrs = ' data-var-ticker="' + _echapAccueil(t) + '" data-var-texte="' + _echapAccueil(texte) + '"';
  if (lib) attrs += ' data-var-seance="' + _echapAccueil(lib) + '"';
  var cls = classe ? (' class="' + classe + '"') : '';
  return '<span' + cls + attrs + '>' + _echapAccueil(texte) + '</span>';
}

function _poserTexteEnteteVariation(el, lib, defaut) {
  if (!el) return;
  var ind = el.querySelector ? el.querySelector('.sort-ind') : null;
  var fleche = ind ? ind.textContent : '';
  el.textContent = lib || defaut;
  if (ind && document.createElement && el.appendChild) {
    var span = document.createElement('span');
    span.className = 'sort-ind';
    span.textContent = fleche;
    el.appendChild(span);
  }
}

function _poserLibellesVariation() {
  var lib = libelleSeanceVariation();
  var titre = document.getElementById('accueil-seance-titre');
  if (titre) titre.textContent = lib || 'Séance du jour';
  var ids = ['accueil-mieux-seance', 'rank-seance-libelle', 'heatmap-seance-libelle'];
  var i;
  for (i = 0; i < ids.length; i++) {
    var el = document.getElementById(ids[i]);
    if (!el) continue;
    el.textContent = lib;
    el.hidden = !lib;
  }
  _poserTexteEnteteVariation(document.getElementById('rank-col-var'), lib, '+/- aujourd\'hui');
  _poserTexteEnteteVariation(document.getElementById('screener-col-var'), lib, 'Var. j.');
}

function _dessinVariation(fn) {
  try { fn(); } catch (e) { /* une vue en échec n'empêche pas les autres */ }
}

function redessinerVariations() {
  _dessinVariation(_poserSousTitreSeance);
  var rows = (window.scores && window.scores.length) ? window.scores : [];
  if (document.getElementById('accueil-top')) _dessinVariation(function() { _remplirTop(rows); });
  if (document.getElementById('accueil-mvt-grille') && window._accueilMarche) {
    _dessinVariation(function() { _remplirMouvements(window._accueilMarche); });
  }
  if (document.getElementById('rankBody') && typeof renderRankLive === 'function') {
    _dessinVariation(renderRankLive);
  }
  if (document.getElementById('mkt-heatmap-grid') && typeof renderHeatmap === 'function') {
    _dessinVariation(function() { renderHeatmap('mkt-heatmap-grid'); });
  }
  if (document.getElementById('screener-table') && typeof runScreener === 'function') {
    _dessinVariation(runScreener);
  }
  var modal = document.getElementById('cmp-modal');
  if (modal && modal.classList && modal.classList.contains('show') && typeof openCompareModal === 'function') {
    _dessinVariation(openCompareModal);
  }
  var pageStock = document.getElementById('page-stock');
  if (pageStock && pageStock.classList && pageStock.classList.contains('on')
      && window._openTicker && typeof _htmlVariationFiche === 'function') {
    _dessinVariation(function() {
      var marque = _htmlVariationFiche(window._openTicker);
      var els = pageStock.querySelectorAll('[data-var-ticker]');
      var i;
      for (i = 0; i < els.length; i++) els[i].outerHTML = marque;
    });
  }
}


function _texteEtatComposite() {
  var statut = window._accueilStatut;
  if (statut && statut.market_open === true) return 'Marché ouvert · Séance en cours';
  var jour = _jourSeance(window._accueilMarche && window._accueilMarche.session_date);
  return jour ? ('Dernière séance : ' + jour) : '';
}

function _poserEtatComposite() {
  var el = document.getElementById('accueil-composite-etat');
  if (!el || !el.isConnected) return;
  var txt = _texteEtatComposite();
  el.textContent = txt;
  el.hidden = !txt;
}

function _noterStatutLive(d) {
  if (!d || typeof d.market_open !== 'boolean') return;
  var statut = window._accueilStatut ? window._accueilStatut : {};
  statut.market_open = d.market_open;
  if (d.session_date) statut.session_date = d.session_date;
  window._accueilStatut = statut;
  _poserSousTitreSeance();
  _poserEtatComposite();
}

function _remplirMarcheAccueil(d) {
  var indices = (d && d.indices) || [];
  var act = (d && d.market_activity) || {};
  var composite = _trouverIndice(indices, function(n) { return n.indexOf('COMPOSITE') >= 0; });
  var b30 = _trouverIndice(indices, function(n) { return n.indexOf('30') >= 0 && n.indexOf('COMPOSITE') < 0; });
  _remplirComposite(composite, _texteActiviteAccueil(act['BRVM-C']));
  _remplirBrvm30(b30, _texteActiviteAccueil(act['BRVM-30']));
  _remplirMontants(act);
  _remplirMouvements(d);
  _chargerCourbeComposite();
  _poserEtatComposite();
}

function _remplirLargeurLive() {
  if (window._accueilLargeurParti) return;
  window._accueilLargeurParti = 1;
  demanderVariation(false).then(function(d) {
    _noterStatutLive(d);
    var el = document.getElementById('accueil-largeur-n');
    if (!el || !el.isConnected) return;
    _remplirLargeur(_compterLargeur((d && d.prices) || {}));
  }).catch(function() {
    var el = document.getElementById('accueil-largeur-n');
    if (el && el.isConnected) _remplirLargeur(null);
  });
}

function _remplirIndices() {
  if (window._accueilIndicesParti) return;
  window._accueilIndicesParti = 1;
  // Le bandeau et la carte passent par le même peintre : une navigation
  // qui relit l'accueil ne laisse plus le bandeau sur l'ancienne réponse.
  if (typeof loadMarketWidget === 'function') loadMarketWidget(false);
  else {
    demanderMarche(false).then(_remplirMarcheAccueil).catch(function() {
      _remplirMarcheAccueil(null);
    });
  }
  _remplirLargeurLive();
}

function _remplirCartes(rows) {
  var el = document.getElementById('accueil-cartes');
  if (!el) return;
  var c = _comptesConseil(rows);
  var specs = [
    ['Intéressant', 'is-interessant'],
    ['À surveiller', 'is-surveiller'],
    ['Prudence', 'is-prudence']
  ];
  el.innerHTML = specs.map(function(spec) {
    var lib = spec[0];
    var n = c[lib];
    return '<button type="button" class="accueil-carte" data-conseil="' + _echapAccueil(lib) + '" title="Voir dans le classement">'
      + '<span class="accueil-carte-n ' + spec[1] + '">' + n.toLocaleString('fr-FR') + '</span>'
      + '<span class="accueil-carte-l">' + _echapAccueil(lib) + '</span>'
      + '<span class="accueil-carte-s">Voir dans le classement</span>'
      + '</button>';
  }).join('');
  el.querySelectorAll('.accueil-carte').forEach(function(btn) {
    btn.addEventListener('click', function() {
      ouvrirClassementConseil(btn.getAttribute('data-conseil'));
    });
  });
}

function _remplirTop(rows) {
  var el = document.getElementById('accueil-top');
  if (!el) return;
  var lignes = _mieuxNotees(rows);
  if (!lignes.length) {
    el.innerHTML = '<p class="accueil-vide">Aucune note disponible pour le moment.</p>';
    return;
  }
  el.innerHTML = lignes.map(_htmlCarteNote).join('');
  el.querySelectorAll('.accueil-mieux-carte').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var t = btn.getAttribute('data-ticker');
      if (t && typeof _openStock === 'function') _openStock(t);
    });
  });
}

function _titreActu(item) {
  if (item && item._type && typeof _anncTitle === 'function') return _anncTitle(item, item._type);
  return (item && (item.titre || item.title)) || '';
}

function _remplirActus() {
  if (window._accueilActusParti) return;
  var el = document.getElementById('accueil-actus');
  if (!el) return;
  window._accueilActusParti = 1;
  el.innerHTML = '<p class="accueil-vide">Chargement…</p>';
  Promise.all([
    fetch('/api/announcements?limit=8').then(function(r) { return r.ok ? r.json() : { data: [] }; }).catch(function() { return { data: [] }; }),
    fetch('/api/news?limit=8').then(function(r) { return r.ok ? r.json() : { data: [] }; }).catch(function() { return { data: [] }; })
  ]).then(function(pair) {
    if (!el.isConnected) return;
    var items = [];
    ((pair[0] && pair[0].data) || []).forEach(function(a) {
      var titre = _titreActu(a);
      if (!titre) return;
      items.push({
        date: a.date || '',
        titre: titre,
        href: a.source_url || '',
        meta: a.ticker || 'Annonce'
      });
    });
    ((pair[1] && pair[1].data) || []).forEach(function(a) {
      if (!a || !a.titre) return;
      items.push({
        date: a.date || '',
        titre: a.titre,
        href: a.lien || '',
        meta: a.ticker || (a.source || 'Presse')
      });
    });
    items.sort(function(a, b) { return String(b.date).localeCompare(String(a.date)); });
    if (items.length > 5) items = items.slice(0, 5);
    if (!items.length) {
      el.innerHTML = '<p class="accueil-vide">Aucune actualité disponible.</p>';
      return;
    }
    el.innerHTML = items.map(function(a) {
      return '<button type="button" class="accueil-actu" data-href="' + _echapAccueil(a.href) + '">'
        + '<span class="accueil-actu-meta">' + _echapAccueil([a.meta, a.date].filter(Boolean).join(' · ')) + '</span>'
        + '<span class="accueil-actu-titre">' + _echapAccueil(a.titre) + '</span>'
        + '</button>';
    }).join('');
    el.querySelectorAll('.accueil-actu').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var href = btn.getAttribute('data-href');
        if (href && /^https?:\/\//i.test(href)) window.open(href, '_blank', 'noopener');
        else if (typeof nav === 'function') nav('news');
      });
    });
  });
}

function _scoresConnus() {
  var brut = window.scores;
  if (!Array.isArray(brut) && typeof scores !== 'undefined') brut = scores;
  return Array.isArray(brut) ? brut : null;
}

function _remplirChapo(rows) {
  var el = document.getElementById('accueil-chapo');
  if (!el) return;
  var liste = Array.isArray(rows) ? rows : [];
  var n = 0;
  liste.forEach(function(x) {
    if (x && x.ticker) n += 1;
  });
  var nombre = n > 0 ? n.toLocaleString('fr-FR') : '—';
  el.textContent = nombre + ' sociétés notées avec 8 modèles de valorisation publics. Une méthode transparente pour les investisseurs débutants — pas un conseil en investissement.';
}

function renderAccueil() {
  var page = document.getElementById('page-welcome');
  if (!page || !page.classList.contains('on')) return;
  var connus = _scoresConnus();
  var rows = connus || [];
  _remplirChapo(rows);
  _remplirIndices();
  _poserEtatComposite();
  _remplirActus();
  if (!connus && !window._accueilRetente) {
    window._accueilRetente = 1;
    var cartes = document.getElementById('accueil-cartes');
    var top = document.getElementById('accueil-top');
    if (cartes) cartes.innerHTML = '<p class="accueil-vide">Chargement…</p>';
    if (top) top.innerHTML = '<p class="accueil-vide">Chargement…</p>';
    setTimeout(function() { renderAccueil(); }, 700);
    return;
  }
  _remplirCartes(rows);
  _remplirTop(rows);
}

function ouvrirClassementConseil(libelle) {
  var sec = document.getElementById('fSec');
  var verd = document.getElementById('fVerdict');
  var tri = document.getElementById('fSort');
  var conseil = document.getElementById('fConseil');
  if (sec) sec.value = '';
  if (verd) verd.value = '';
  if (tri) tri.value = 'composite_adj';
  if (conseil) conseil.value = libelle || '';
  window._favOnly = false;
  var fav = document.getElementById('fFav');
  if (fav) {
    fav.style.borderColor = '';
    fav.style.color = '';
  }
  if (typeof nav === 'function') nav('rank');
  if (typeof renderRankLive === 'function') renderRankLive();
}

function allerCommentInvestir() {
  if (typeof navTo === 'function') navTo('glossaire');
  else if (typeof nav === 'function') nav('glossaire');
  var cible = document.getElementById('glossaire-investir');
  if (!cible) return;
  cible.setAttribute('tabindex', '-1');
  window.requestAnimationFrame(function() {
    cible.scrollIntoView({ block: 'start' });
    if (typeof cible.focus === 'function') cible.focus({ preventScroll: true });
  });
}
