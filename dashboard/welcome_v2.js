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

function _nomSociete(ticker, rows) {
  var t = String(ticker || '').toUpperCase();
  var i;
  for (i = 0; i < (rows || []).length; i++) {
    if (rows[i] && String(rows[i].ticker || '').toUpperCase() === t) return rows[i].name || '';
  }
  return '';
}

function _ligneMouvement(x, rows, sens) {
  var ticker = String(x.ticker || '').toUpperCase();
  if (!ticker) return '';
  var nom = _nomSociete(ticker, rows);
  var variation = _fmtVariation(x.change);
  var cls = (Number(x.change) < 0 || sens === 'bas') ? 'is-down' : 'is-up';
  var nomHtml = nom ? '<span class="accueil-mvt-nom">' + _echapAccueil(nom) + '</span>' : '';
  return '<button type="button" class="accueil-mvt-ligne" data-ticker="' + _echapAccueil(ticker) + '">'
    + '<strong>' + _echapAccueil(ticker) + '</strong>'
    + nomHtml
    + '<span class="accueil-mvt-var ' + cls + '">' + _echapAccueil(variation) + '</span>'
    + '</button>';
}

function _remplirMouvements(d, rows) {
  var bloc = document.getElementById('accueil-mouvements');
  var grille = document.getElementById('accueil-mvt-grille');
  if (!bloc || !grille) return;
  var hausses = (d && d.top5) || [];
  var baisses = (d && d.flop5) || [];
  if (!hausses.length && !baisses.length) {
    bloc.hidden = true;
    grille.innerHTML = '';
    return;
  }
  var html = '';
  if (hausses.length) {
    html += '<div class="accueil-mvt"><h3>Plus fortes hausses</h3>'
      + hausses.map(function(x) { return _ligneMouvement(x, rows, 'haut'); }).join('')
      + '</div>';
  }
  if (baisses.length) {
    html += '<div class="accueil-mvt"><h3>Plus fortes baisses</h3>'
      + baisses.map(function(x) { return _ligneMouvement(x, rows, 'bas'); }).join('')
      + '</div>';
  }
  grille.innerHTML = html;
  bloc.hidden = false;
  grille.querySelectorAll('.accueil-mvt-ligne').forEach(function(btn) {
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
    _remplirMouvements(d, window.scores || (typeof scores !== 'undefined' ? scores : []));
  }).catch(function() {
    if (box && box.isConnected) box.innerHTML = _htmlTroisIndices(null);
  });
}

function _lignesTop(rows) {
  var tries = (rows || []).slice().sort(typeof triCommeClassement === 'function' ? triCommeClassement : function() { return 0; });
  var interessant = [];
  var surveiller = [];
  tries.forEach(function(x) {
    var a = (typeof conseilAffiche === 'function') ? conseilAffiche(x) : null;
    if (!a || a.suspendu) return;
    if (a.libelle === 'Intéressant') interessant.push(x);
    else if (a.libelle === 'À surveiller') surveiller.push(x);
  });
  var lignes = interessant.concat(surveiller);
  if (lignes.length > 8) lignes = lignes.slice(0, 8);
  return lignes;
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
  var lignes = _lignesTop(rows);
  if (!lignes.length) {
    el.innerHTML = '<p class="accueil-vide">Aucune société Intéressant ou À surveiller pour le moment.</p>';
    return;
  }
  var entete = '<div class="accueil-entete" aria-hidden="true">'
    + '<span>Société</span><span>Note</span><span>Conseil</span><span>Var. jour</span><span>Cours</span><span>Écart cible</span>'
    + '</div>';
  var corps = lignes.map(function(x) {
    var n = (typeof note10num === 'function') ? note10num(x) : 0;
    var note = (typeof note10txt === 'function') ? note10txt(x) : _frFixe(n, 1);
    var conseil = (typeof fmtConseil === 'function') ? fmtConseil(x) : '—';
    var cours = (x.price != null && typeof fmtXOF === 'function') ? fmtXOF(x.price) : '—';
    var ecart = (typeof fmtEcartPct === 'function') ? fmtEcartPct(x.ecart_pct) : '—';
    var variation = _fmtVariation(x.change_pct);
    return '<button type="button" class="accueil-ligne" data-ticker="' + _echapAccueil(x.ticker) + '">'
      + '<span class="accueil-id"><strong class="accueil-ticker">' + _echapAccueil(x.ticker) + '</strong>'
      + '<span class="accueil-nom">' + _echapAccueil(x.name || '') + '</span></span>'
      + '<span class="accueil-note ' + _classeConseil(x) + '">' + note + '<span>/10</span></span>'
      + '<span class="accueil-conseil">' + conseil + '</span>'
      + '<span class="accueil-var ' + _sensVariation(x.change_pct) + '">' + _echapAccueil(variation) + '</span>'
      + '<span class="accueil-cours">' + _echapAccueil(cours) + '</span>'
      + '<span class="accueil-ecart">' + _echapAccueil(ecart) + '</span>'
      + '</button>';
  }).join('');
  el.innerHTML = entete + corps;
  el.querySelectorAll('.accueil-ligne').forEach(function(btn) {
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
