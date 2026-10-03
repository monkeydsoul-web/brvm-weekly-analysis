/* CHARTS-3 — zoom et glissement de la courbe de prix de la fiche société.
   Inventaire : pas de librairie (ni Chart.js, ni autre). La courbe de
   /societe/<TICKER> est le SVG dessiné par drawPriceChart dans
   stock_chart.js. Un plugin de zoom n'a donc rien à accrocher : en
   charger un, même en local, remplacerait le tracé et gênerait les
   modules voisins (point touché, comparaison base 100). Le zoom est
   du JS vanilla, limité à #stockChartDiv.

   Accueil, Comparer et Backtest ne passent pas par drawPriceChart.
   Pas d'infobulle au survol : les attributs onmousemove / onmouseleave
   posés par le tracé sont retirés. Le doigt vertical ne fait pas
   preventDefault (touch-action: pan-y) pour laisser défiler la page.
*/
(function () {
  if (window.__BRVM_ZOOM_PRET) return;
  window.__BRVM_ZOOM_PRET = 1;

  var HOTE = 'stockChartDiv';
  var original = null;

  function racineDe(el) {
    var n = el;
    while (n) {
      if (n.id === HOTE) return n;
      n = n.parentElement;
    }
    return null;
  }

  function hote() {
    return document.getElementById(HOTE + '_svg');
  }

  function injecterStyle() {
    if (document.getElementById('brvm-zoom-style')) return;
    var style = document.createElement('style');
    style.id = 'brvm-zoom-style';
    style.textContent = [
      '.brvm-zoom-bar{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:0 0 8px}',
      '.brvm-zoom-bar button{font-family:inherit;font-size:12px;font-weight:600;line-height:1;min-height:36px;min-width:36px;padding:6px 10px;border-radius:6px;cursor:pointer;border:1px solid var(--border);background:var(--bg3);color:var(--text)}',
      '.brvm-zoom-bar button[data-brvm-zoom="reset"]{min-width:0;padding:6px 12px}',
      '.brvm-zoom-bar button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}',
      '.brvm-zoom-plage{font-size:11px;color:var(--t2);font-variant-numeric:tabular-nums}',
      '.brvm-zoom-cadre{position:relative}',
      '.brvm-zoom-surface{position:absolute;left:0;top:0;right:0;bottom:0;touch-action:pan-y;cursor:grab;background:transparent}',
      '.brvm-zoom-surface.is-drag{cursor:grabbing}',
      '#stockChartDiv svg{touch-action:pan-y;-webkit-user-select:none;user-select:none}'
    ].join('');
    (document.head || document.documentElement).appendChild(style);
  }

  function normaliser(labels, prices) {
    var libs = [];
    var prix = [];
    var i, n;
    n = prices && prices.length ? prices.length : 0;
    for (i = 0; i < n; i++) {
      var v = Number(prices[i]);
      if (!isFinite(v)) continue;
      libs.push(labels && labels[i] != null ? String(labels[i]) : '');
      prix.push(v);
    }
    return { labels: libs, prices: prix };
  }

  function largeurMin(n) {
    var max = n - 1;
    if (max < 1) return 1;
    return max < 8 ? max : 8;
  }

  function poserFenetre(etat, debut, largeur) {
    var max = etat.prices.length - 1;
    if (max < 1) {
      etat.debut = 0;
      etat.fin = max > 0 ? max : 0;
      return;
    }
    var minL = largeurMin(etat.prices.length);
    largeur = Math.round(largeur);
    if (largeur < minL) largeur = minL;
    if (largeur > max) largeur = max;
    debut = Math.round(debut);
    if (debut < 0) debut = 0;
    if (debut + largeur > max) debut = max - largeur;
    etat.debut = debut;
    etat.fin = debut + largeur;
  }

  function zoomerAutour(etat, ratio, facteur) {
    if (!(facteur > 0) || !isFinite(facteur)) return;
    if (ratio < 0) ratio = 0;
    if (ratio > 1) ratio = 1;
    var largeur = etat.fin - etat.debut;
    var centre = etat.debut + largeur * ratio;
    poserFenetre(etat, centre - (largeur / facteur) * ratio, largeur / facteur);
  }

  function ratioClient(el, clientX) {
    var rect = el.getBoundingClientRect();
    if (!rect.width) return 0.5;
    var r = (clientX - rect.left) / rect.width;
    if (r < 0) return 0;
    if (r > 1) return 1;
    return r;
  }

  function distance(a, b) {
    var dx = a.clientX - b.clientX;
    var dy = a.clientY - b.clientY;
    return Math.sqrt(dx * dx + dy * dy);
  }

  function nettoyerInfobulle(svg) {
    svg.removeAttribute('onmousemove');
    svg.removeAttribute('onmouseleave');
    svg.onmousemove = null;
    svg.onmouseleave = null;
    var noeuds = svg.querySelectorAll('[id$="_vline"],[id$="_dot"],[id$="_bg"],[id$="_price"],[id$="_date"]');
    var i;
    for (i = 0; i < noeuds.length; i++) noeuds[i].setAttribute('opacity', '0');
  }

  function lisibilite(svg) {
    svg.style.color = 'var(--t2)';
    var noeuds = svg.querySelectorAll('text, line');
    var i, el, fill, stroke;
    for (i = 0; i < noeuds.length; i++) {
      el = noeuds[i];
      if (el.id && /_(price|date)$/.test(el.id)) continue;
      fill = el.getAttribute('fill') || '';
      stroke = el.getAttribute('stroke') || '';
      if (fill.indexOf('255,255,255') !== -1 || fill === 'white') el.setAttribute('fill', 'currentColor');
      if (stroke.indexOf('255,255,255') !== -1) {
        el.setAttribute('stroke', 'currentColor');
        el.setAttribute('stroke-opacity', '0.35');
      }
    }
  }

  function majPlage(racine) {
    var el = racine.querySelector('.brvm-zoom-plage');
    var etat = racine._brvmZoom;
    if (!el || !etat) return;
    var a = String(etat.labels[etat.debut] || '').slice(0, 10);
    var b = String(etat.labels[etat.fin] || '').slice(0, 10);
    el.textContent = a + ' \u2192 ' + b;
  }

  function marquer(racine) {
    var host = hote();
    var etat = racine._brvmZoom;
    if (!host || !etat) return;
    host.setAttribute('data-zoom-debut', String(etat.debut));
    host.setAttribute('data-zoom-fin', String(etat.fin));
    host.setAttribute('data-zoom-total', String(etat.prices.length));
  }

  function onClickBarre(e) {
    var btn = e.target.closest ? e.target.closest('[data-brvm-zoom]') : null;
    if (!btn) return;
    var racine = racineDe(btn);
    var etat = racine && racine._brvmZoom;
    if (!etat) return;
    var action = btn.getAttribute('data-brvm-zoom');
    if (action === 'plus') zoomerAutour(etat, 0.5, 1.8);
    else if (action === 'moins') zoomerAutour(etat, 0.5, 1 / 1.8);
    else if (action === 'reset') poserFenetre(etat, 0, etat.prices.length - 1);
    else return;
    redessiner(racine);
  }

  function relayerClic(surface, x, y) {
    surface.style.pointerEvents = 'none';
    var dessous = document.elementFromPoint(x, y);
    surface.style.pointerEvents = '';
    if (!dessous || dessous === surface) return;
    dessous.dispatchEvent(new MouseEvent('click', {
      bubbles: true,
      cancelable: true,
      clientX: x,
      clientY: y,
      view: window
    }));
  }

  function assurerBarre(racine) {
    var barre = racine.querySelector('.brvm-zoom-bar');
    if (barre) return barre;
    barre = document.createElement('div');
    barre.className = 'brvm-zoom-bar';
    barre.setAttribute('role', 'group');
    barre.setAttribute('aria-label', 'Zoom du cours');
    barre.innerHTML =
      '<button type="button" data-brvm-zoom="moins" aria-label="Zoom arrière">\u2212</button>' +
      '<button type="button" data-brvm-zoom="plus" aria-label="Zoom avant">+</button>' +
      '<button type="button" data-brvm-zoom="reset">Réinitialiser</button>' +
      '<span class="brvm-zoom-plage"></span>';
    barre.addEventListener('click', onClickBarre);
    var cadre = racine.querySelector('.brvm-zoom-cadre');
    if (cadre) racine.insertBefore(barre, cadre);
    else racine.appendChild(barre);
    return barre;
  }

  function assurerCadre(host) {
    var parent = host.parentElement;
    var cadre = parent && parent.classList.contains('brvm-zoom-cadre') ? parent : null;
    if (!cadre) {
      cadre = document.createElement('div');
      cadre.className = 'brvm-zoom-cadre';
      host.parentNode.insertBefore(cadre, host);
      cadre.appendChild(host);
    }
    var surface = cadre.querySelector('.brvm-zoom-surface');
    if (!surface) {
      surface = document.createElement('div');
      surface.className = 'brvm-zoom-surface';
      surface.setAttribute('aria-hidden', 'true');
      cadre.appendChild(surface);
      brancherSurface(surface);
    }
    var racine = racineDe(host);
    if (racine && racine._brvmGlisse) surface.classList.add('is-drag');
    else surface.classList.remove('is-drag');
    return cadre;
  }

  function habiller(container) {
    var racine = racineDe(container);
    var svg = container.querySelector('svg');
    if (svg) {
      nettoyerInfobulle(svg);
      lisibilite(svg);
      svg.style.touchAction = 'pan-y';
    }
    if (!racine || !racine._brvmZoom) return;
    injecterStyle();
    assurerCadre(container);
    assurerBarre(racine);
    majPlage(racine);
    marquer(racine);
  }

  function redessiner(racine) {
    var etat = racine._brvmZoom;
    var host = hote();
    if (!etat || !host || typeof window.drawPriceChart !== 'function') return;
    var labels = etat.labels.slice(etat.debut, etat.fin + 1);
    var prices = etat.prices.slice(etat.debut, etat.fin + 1);
    racine._brvmZoomInterne = true;
    try {
      window.drawPriceChart(host, labels, prices, etat.ticker);
    } finally {
      racine._brvmZoomInterne = false;
    }
  }

  function onWheel(e) {
    if (!e.ctrlKey) return;
    var surface = e.currentTarget;
    var racine = racineDe(surface);
    var etat = racine && racine._brvmZoom;
    if (!etat) return;
    e.preventDefault();
    var pas = Math.abs(e.deltaY) / 100;
    if (pas < 0.25) pas = 0.25;
    if (pas > 4) pas = 4;
    var facteur = Math.pow(1.25, pas);
    if (e.deltaY > 0) facteur = 1 / facteur;
    zoomerAutour(etat, ratioClient(surface, e.clientX), facteur);
    redessiner(racine);
  }

  function onMouseDown(e) {
    if (e.button !== 0) return;
    var surface = e.currentTarget;
    var racine = racineDe(surface);
    var etat = racine && racine._brvmZoom;
    if (!etat) return;
    e.preventDefault();
    var startX = e.clientX;
    var startY = e.clientY;
    var debut0 = etat.debut;
    var largeur = etat.fin - etat.debut;
    var bouge = false;
    function bouger(ev) {
      if (Math.abs(ev.clientX - startX) + Math.abs(ev.clientY - startY) > 4) bouge = true;
      var rect = surface.getBoundingClientRect();
      var delta = Math.round(-(ev.clientX - startX) / Math.max(rect.width, 1) * largeur);
      poserFenetre(etat, debut0 + delta, largeur);
      racine._brvmGlisse = true;
      redessiner(racine);
    }
    function lacher(ev) {
      document.removeEventListener('mousemove', bouger);
      document.removeEventListener('mouseup', lacher);
      racine._brvmGlisse = false;
      var courant = racine.querySelector('.brvm-zoom-surface');
      if (courant) courant.classList.remove('is-drag');
      if (!bouge) relayerClic(surface, ev.clientX, ev.clientY);
    }
    document.addEventListener('mousemove', bouger);
    document.addEventListener('mouseup', lacher);
  }

  function preparerPinch(racine, touches, surface) {
    var p = racine._brvmPointeur;
    var etat = racine._brvmZoom;
    p.mode = 'pinch';
    p.dist = distance(touches[0], touches[1]);
    p.debut = etat.debut;
    p.largeur = etat.fin - etat.debut;
    var milieu = (touches[0].clientX + touches[1].clientX) / 2;
    p.ratio = ratioClient(surface, milieu);
  }

  function onTouchStart(e) {
    var surface = e.currentTarget;
    var racine = racineDe(surface);
    if (!racine || !racine._brvmZoom) return;
    var p = racine._brvmPointeur || (racine._brvmPointeur = {});
    if (e.touches.length >= 2) preparerPinch(racine, e.touches, surface);
    else {
      p.mode = '';
      p.x = e.touches[0].clientX;
      p.y = e.touches[0].clientY;
      p.debut = racine._brvmZoom.debut;
      p.largeur = racine._brvmZoom.fin - racine._brvmZoom.debut;
    }
  }

  function onTouchMove(e) {
    var surface = e.currentTarget;
    var racine = racineDe(surface);
    var etat = racine && racine._brvmZoom;
    var p = racine && racine._brvmPointeur;
    if (!etat || !p) return;
    if (e.touches.length >= 2) {
      if (p.mode !== 'pinch') preparerPinch(racine, e.touches, surface);
      if (e.cancelable) e.preventDefault();
      var dist = distance(e.touches[0], e.touches[1]);
      if (!(p.dist > 0)) return;
      var facteur = dist / p.dist;
      if (facteur < 0.2) facteur = 0.2;
      if (facteur > 5) facteur = 5;
      var centre = p.debut + p.largeur * p.ratio;
      poserFenetre(etat, centre - (p.largeur / facteur) * p.ratio, p.largeur / facteur);
      redessiner(racine);
      return;
    }
    if (e.touches.length !== 1 || p.mode === 'pinch') return;
    var dx = e.touches[0].clientX - p.x;
    var dy = e.touches[0].clientY - p.y;
    if (!p.mode) {
      if (Math.abs(dx) < 10 && Math.abs(dy) < 10) return;
      if (Math.abs(dy) >= Math.abs(dx)) {
        p.mode = 'scroll';
        return;
      }
      p.mode = 'pan';
      p.x = e.touches[0].clientX;
      p.debut = etat.debut;
      p.largeur = etat.fin - etat.debut;
    }
    if (p.mode !== 'pan') return;
    if (e.cancelable) e.preventDefault();
    var rect = surface.getBoundingClientRect();
    var delta = Math.round(-(e.touches[0].clientX - p.x) / Math.max(rect.width, 1) * p.largeur);
    poserFenetre(etat, p.debut + delta, p.largeur);
    redessiner(racine);
  }

  function onTouchEnd(e) {
    var surface = e.currentTarget;
    var racine = racineDe(surface);
    var p = racine && racine._brvmPointeur;
    if (e.touches && e.touches.length > 0) return;
    if (p && !p.mode && e.changedTouches && e.changedTouches[0]) {
      var t = e.changedTouches[0];
      if (Math.abs(t.clientX - p.x) < 10 && Math.abs(t.clientY - p.y) < 10) relayerClic(surface, t.clientX, t.clientY);
    }
    if (p) p.mode = '';
  }

  function brancherSurface(surface) {
    surface.addEventListener('wheel', onWheel, { passive: false });
    surface.addEventListener('mousedown', onMouseDown);
    surface.addEventListener('touchstart', onTouchStart, { passive: true });
    surface.addEventListener('touchmove', onTouchMove, { passive: false });
    surface.addEventListener('touchend', onTouchEnd);
    surface.addEventListener('touchcancel', onTouchEnd);
  }

  function memoriser(racine, labels, prices, ticker) {
    var serie = normaliser(labels, prices);
    racine._brvmZoom = {
      labels: serie.labels,
      prices: serie.prices,
      ticker: ticker,
      debut: 0,
      fin: serie.prices.length - 1
    };
  }

  function enveloppe(container, labels, prices, ticker) {
    if (!container || container.id !== HOTE + '_svg') {
      if (original) return original(container, labels, prices, ticker);
      return;
    }
    var racine = racineDe(container);
    if (racine && racine._brvmZoomInterne) {
      if (original) original(container, labels, prices, ticker);
      habiller(container);
      return;
    }
    var serie = normaliser(labels, prices);
    if (serie.prices.length < 2) {
      if (original) original(container, labels, prices, ticker);
      return;
    }
    if (racine) memoriser(racine, serie.labels, serie.prices, ticker);
    if (original) original(container, serie.labels, serie.prices, ticker);
    habiller(container);
  }
  enveloppe._brvmZoom = true;

  window.brvmZoomCourbe = enveloppe;

  function brancher() {
    if (typeof window.drawPriceChart !== 'function') return false;
    if (window.drawPriceChart._brvmZoom) return true;
    original = window.drawPriceChart;
    window.drawPriceChart = enveloppe;
    return true;
  }

  injecterStyle();
  if (!brancher()) {
    var essais = 0;
    var timer = setInterval(function () {
      essais += 1;
      if (brancher() || essais > 40) clearInterval(timer);
    }, 100);
  }
})();
