/* Preuve navigateur : une variation, une date, cinq tickers, six vues. */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const racine = path.join(__dirname, '..', 'dashboard');
const erreurs = [];

function element(id) {
  const node = {
    id: id || '',
    innerHTML: '',
    textContent: '',
    value: '',
    hidden: false,
    isConnected: true,
    className: '',
    style: {},
    dataset: {},
    options: { length: 1 },
    childNodes: [],
    parentNode: null,
    appendChild(enfant) { this.childNodes.push(enfant); enfant.parentNode = this; return enfant; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    addEventListener() {},
    setAttribute(cle, valeur) { this[cle] = valeur; },
    getAttribute(cle) { return this[cle] == null ? null : this[cle]; },
    remove() {},
    closest() { return null; },
    contains() { return false; },
    focus() {}
  };
  node.classList = {
    add(c) { node._classes[c] = 1; },
    remove(c) { delete node._classes[c]; },
    toggle(c, on) {
      if (on === false) delete node._classes[c];
      else node._classes[c] = 1;
    },
    contains(c) { return !!node._classes[c]; }
  };
  node._classes = {};
  return node;
}

const noeuds = {};
function parId(id) {
  if (!noeuds[id]) noeuds[id] = element(id);
  return noeuds[id];
}

const document = {
  getElementById: parId,
  querySelector() { return null; },
  querySelectorAll() { return []; },
  addEventListener() {},
  createElement() { return element(''); },
  documentElement: element('html'),
  body: element('body'),
  readyState: 'complete'
};

const stockage = {
  getItem() { return null; },
  setItem() {},
  removeItem() {}
};

const context = {
  document: document,
  localStorage: stockage,
  sessionStorage: stockage,
  location: { hash: '', pathname: '/', search: '' },
  navigator: {},
  console: {
    error() { erreurs.push(Array.prototype.join.call(arguments, ' ')); },
    log() {},
    warn() {},
    info() {}
  },
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  setInterval: function() { return 0; },
  clearInterval: function() {},
  requestAnimationFrame(fn) { fn(); },
  getComputedStyle() { return { display: 'none' }; },
  MutationObserver: function MutationObserver() {},
  AbortController: AbortController,
  Promise: Promise,
  Date: Date,
  Intl: Intl,
  fetch: function() {
    return Promise.resolve({ ok: true, json: function() { return Promise.resolve({}); } });
  },
  isFinite: isFinite,
  isNaN: isNaN,
  Number: Number,
  String: String,
  Object: Object,
  Array: Array,
  Math: Math,
  JSON: JSON,
  RegExp: RegExp,
  parseFloat: parseFloat,
  parseInt: parseInt,
  Set: Set
};
context.MutationObserver.prototype.observe = function() {};
context.MutationObserver.prototype.disconnect = function() {};
context.addEventListener = function() {};
context.removeEventListener = function() {};
context.window = context;
context.global = context;
vm.createContext(context);

function charger(nom) {
  let source = fs.readFileSync(path.join(racine, nom), 'utf8');
  if (nom === 'js/core.js') source = source.replace('\ninit();\n', '\n/* init non lance */\n');
  vm.runInContext(source, context, { filename: nom });
}

charger('welcome_v2.js');
charger('screener.js');
charger('ranking.js');
charger('badges.js');
charger('js/core.js');

function echec(msg) {
  console.error(msg);
  process.exit(1);
}

const TICKERS = ['SNTS', 'BICC', 'BOAB', 'CABC', 'TTLS'];

function ligne(ticker, note, rang, changeScore) {
  return {
    ticker: ticker,
    name: ticker + ' Societe',
    sector: 'Banque',
    note10: note,
    composite_adj: note * 8,
    rank: rang,
    price: 1000 + rang,
    change_pct: changeScore,
    conseil: 'acheter',
    conseil_libelle: 'Intéressant',
    conseil_couleur: 'vert',
    statut: 'cote',
    pe_ref: 8,
    div_yield: 1,
    pdf_verdict: 'POSITIF',
    shares: 1000
  };
}

const scoresIdentite = [
  ligne('SNTS', 9.1, 1, 9.99),
  ligne('BICC', 8.4, 2, -1),
  ligne('BOAB', 7.7, 3, 0.2),
  ligne('CABC', 7.3, 4, 3),
  ligne('TTLS', 6.6, 5, -6.56)
];

function liveIdentite() {
  return {
    session_date: '2026-09-30',
    seance_ouverte: true,
    market_open: false,
    prices: {
      SNTS: { price: 44995, change_pct: 4.65, volume: 80, source: 'brvm.org', session_date: '2026-09-30' },
      BICC: { price: 32510, change_pct: -6.56, volume: 40, source: 'brvm.org', session_date: '2026-09-30' },
      BOAB: { price: 9800, change_pct: 1.2, volume: 12, source: 'brvm.org', session_date: '2026-09-30' },
      CABC: { price: 500, change_pct: 0, volume: 4, source: 'brvm.org', session_date: '2026-09-30' }
    }
  };
}

function installer(live, scores) {
  context._variationLive = live;
  context.window.scores = scores;
  context.window._maintenantVariation = function() { return new Date('2026-10-01T09:04:00Z'); };
  context.window._accueilMarche = {
    session_date: '2026-09-29',
    top5: scores.map(function(x) { return { ticker: x.ticker, price: x.price, change: 8.88 }; }),
    flop5: []
  };
  context._cmpSelected.clear();
  TICKERS.forEach(function(t) { context._cmpSelected.add(t); });
  parId('sc-score').value = '0';
  parId('sc-pe').value = '';
  parId('sc-div').value = '';
  parId('sc-pb').value = '';
  parId('sc-sect').value = '';
  parId('fSec').value = '';
  parId('fSort').value = 'composite_adj';
  parId('fVerdict').value = '';
  parId('fConseil').value = '';
  parId('cmp-modal').classList.add('show');
}

function textes(html, ticker) {
  const trouves = [];
  const motif = new RegExp('data-var-ticker="' + ticker + '" data-var-texte="([^"]*)"', 'g');
  let m;
  while ((m = motif.exec(html))) trouves.push(m[1]);
  return trouves;
}

function htmlVues() {
  context.redessinerVariations();
  return {
    accueil: parId('accueil-top').innerHTML + parId('accueil-mvt-grille').innerHTML
      + parId('accueil-seance-titre').textContent + parId('accueil-mieux-seance').textContent,
    classement: parId('rankBody').innerHTML + parId('rank-cards').innerHTML
      + parId('rank-col-var').textContent + parId('rank-seance-libelle').textContent,
    screener: parId('screener-table').innerHTML + parId('screener-col-var').textContent,
    chaleur: parId('mkt-heatmap-grid').innerHTML + parId('heatmap-seance-libelle').textContent,
    comparer: parId('cmp-modal-content').innerHTML
  };
}

function exigerIdentiques(vues, live) {
  context._variationLive = live;
  TICKERS.forEach(function(ticker) {
    const attendu = context.texteVariationJour(ticker);
    Object.keys(vues).forEach(function(nom) {
      const trouves = textes(vues[nom], ticker);
      if (!trouves.length) echec(nom + ' sans ' + ticker);
      trouves.forEach(function(texte) {
        if (texte !== attendu) echec(nom + ' ' + ticker + ' « ' + texte + ' » ≠ « ' + attendu + ' »');
      });
    });
  });
}

installer(liveIdentite(), scoresIdentite);
const vues = htmlVues();
exigerIdentiques(vues, liveIdentite());

const libelle = 'séance du 30/09';
Object.keys(vues).forEach(function(nom) {
  if (vues[nom].indexOf(libelle) < 0) echec(nom + ' sans date de séance');
  if (vues[nom].indexOf('séance du 01/10') >= 0) echec(nom + ' date du jour inventée');
  if (vues[nom].indexOf('9,99') >= 0 || vues[nom].indexOf('9.99') >= 0) echec(nom + ' variation des scores');
  if (vues[nom].indexOf('8,88') >= 0 || vues[nom].indexOf('8.88') >= 0) echec(nom + ' variation du marché');
});
if (parId('accueil-seance-titre').textContent !== libelle) echec('titre séance ' + parId('accueil-seance-titre').textContent);

const avant = context.texteVariationJour('SNTS');
const liveSuivant = liveIdentite();
liveSuivant.prices.SNTS = { price: 45000, change_pct: 2.5, volume: 90, source: 'brvm.org', session_date: '2026-09-30' };
context._variationLive = liveSuivant;
context.redessinerVariations();
const apres = htmlVues();
if (context.texteVariationJour('SNTS') === avant) echec('variation inchangée');
exigerIdentiques(apres, liveSuivant);

function matin(session) {
  const live = {
    session_date: session,
    seance_ouverte: false,
    market_open: true,
    prices: {}
  };
  TICKERS.forEach(function(t) {
    live.prices[t] = { price: 1000, change_pct: 0, volume: 0, source: 'brvm.org', session_date: session };
  });
  const scores = [
    ligne('SNTS', 9.1, 1, 4.65),
    ligne('BICC', 8.4, 2, -6.56),
    ligne('BOAB', 7.7, 3, 1.2),
    ligne('CABC', 7.3, 4, 0),
    ligne('TTLS', 6.6, 5, -6.56)
  ];
  installer(live, scores);
  const rendu = htmlVues();
  const jj = session.slice(8, 10) + '/' + session.slice(5, 7);
  Object.keys(rendu).forEach(function(nom) {
    const html = rendu[nom];
    if (html.indexOf('6,56') >= 0 || html.indexOf('6.56') >= 0) echec(nom + ' mélange la veille');
    if (/0[,.]0+\s*%|0[,.]0+&nbsp;%|0[,.]0+\u00a0%/.test(html)) echec(nom + ' affiche zéro');
    if (html.indexOf('séance du ' + jj) < 0) echec(nom + ' sans séance du ' + jj);
    TICKERS.forEach(function(ticker) {
      textes(html, ticker).forEach(function(texte) {
        if (texte !== '—') echec(nom + ' ' + ticker + ' « ' + texte + ' »');
      });
    });
  });
}

matin('2026-09-30');
matin('2026-10-01');

let liveFetch = 0;
let marketFetch = 0;
context.fetch = function(url) {
  const u = String(url);
  if (u.indexOf('/api/live') >= 0) liveFetch += 1;
  if (u.indexOf('/api/market') >= 0) marketFetch += 1;
  return Promise.resolve({
    ok: true,
    json: function() {
      return Promise.resolve({ prices: {}, indices: [], session_date: '2026-09-30', seance_ouverte: false });
    }
  });
};

setTimeout(function() {
  liveFetch = 0;
  marketFetch = 0;
  context._promesseVariation = null;
  context._promesseMarche = null;
  Promise.all([
    context.demanderVariation(false),
    context.demanderVariation(false),
    context.demanderVariation(false),
    context.demanderVariation(false),
    context.demanderVariation(false)
  ]).then(function() {
    if (liveFetch !== 1) echec('GET /api/live ' + liveFetch);
    return Promise.all([
      context.demanderMarche(false),
      context.demanderMarche(false),
      context.demanderMarche(false),
      context.demanderMarche(false),
      context.demanderMarche(false)
    ]);
  }).then(function() {
    if (marketFetch !== 1) echec('GET /api/market ' + marketFetch);
    if (erreurs.length) echec('console ' + erreurs.join(' | '));
    process.exit(0);
  }).catch(function(e) {
    echec(e && e.stack ? e.stack : String(e));
  });
}, 0);
