// dashboard/welcome_v2.js — Accueil : résumé du marché, des conseils et des actualités.

function loadWelcomeHero() {
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

function _puceOuTiret(label, item, activite) {
  var p = (typeof _puceIndice === 'function') ? _puceIndice(label, item, activite) : null;
  if (p && p.html) return p.html;
  return '<span class="index-chip"><span class="ix-name">' + _echapAccueil(label) + '</span><span class="ix-val">—</span></span>';
}

function _htmlTroisIndices(d) {
  var indices = (d && d.indices) || [];
  var act = (d && d.market_activity) || {};
  return [
    _puceOuTiret('Composite', _trouverIndice(indices, function(n) { return n.indexOf('COMPOSITE') >= 0; }), act['BRVM-C']),
    _puceOuTiret('BRVM 30', _trouverIndice(indices, function(n) { return n.indexOf('30') >= 0 && n.indexOf('COMPOSITE') < 0; }), act['BRVM-30']),
    _puceOuTiret('Prestige', _trouverIndice(indices, function(n) { return n.indexOf('PRESTIGE') >= 0; }), act['BRVM-PRES'] || act['BRVM-PRESTIGE'])
  ].join('');
}

function _dateSeance(rows) {
  var iso = '';
  (rows || []).some(function(x) {
    if (x && x.note_calculee_le) { iso = x.note_calculee_le; return true; }
    return false;
  });
  if (!iso) return '';
  var d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
}

function _remplirStatut(rows) {
  var seance = document.getElementById('accueil-seance');
  if (seance) {
    var jour = _dateSeance(rows);
    seance.textContent = jour ? ('Dernière séance : ' + jour) : 'Dernière séance : —';
  }
  var statut = document.getElementById('accueil-statut');
  if (!statut) return;
  fetch('/api/status').then(function(r) {
    if (!r.ok) throw new Error('statut');
    return r.json();
  }).then(function(d) {
    window._accueilStatut = d || null;
    _poserSousTitreSeance();
    if (!statut.isConnected) return;
    if (!d || typeof d.market_open !== 'boolean') {
      statut.textContent = 'Marché —';
      return;
    }
    statut.textContent = d.market_open ? 'Marché ouvert' : 'Marché fermé';
    statut.classList.toggle('is-open', !!d.market_open);
    statut.classList.toggle('is-closed', !d.market_open);
  }).catch(function() {
    if (statut.isConnected && statut.textContent === 'Marché —') statut.textContent = 'Marché —';
  });
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
    + '<span class="accueil-var-pill ' + _sensVariation(x.change_pct) + '">' + _echapAccueil(_fmtVariation(x.change_pct)) + '</span>'
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
  if (sous && sous.isConnected) sous.textContent = _sousTitreSeance(window._accueilMarche, window._accueilStatut);
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
    + '<span class="accueil-var-pill ' + _sensVariation(x.change) + '">' + _echapAccueil(_fmtVariation(x.change)) + '</span>';
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

function _remplirIndices() {
  var box = document.getElementById('accueil-indices');
  fetch('/api/market').then(function(r) {
    if (!r.ok) throw new Error('marche');
    return r.json();
  }).then(function(d) {
    if (box && box.isConnected) box.innerHTML = _htmlTroisIndices(d);
    _remplirMouvements(d);
  }).catch(function() {
    if (box && box.isConnected) box.innerHTML = _htmlTroisIndices(null);
    _remplirMouvements(null);
  });
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
  var el = document.getElementById('accueil-actus');
  if (!el) return;
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

function renderAccueil() {
  var page = document.getElementById('page-welcome');
  if (!page || !page.classList.contains('on')) return;
  var rows = window.scores || (typeof scores !== 'undefined' ? scores : []) || [];
  _remplirStatut(rows);
  _remplirIndices();
  _remplirActus();
  if (!rows.length && !window._accueilRetente) {
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
