# -*- coding: utf-8 -*-
"""Bandeau et carte Composite : une seule lecture /api/market, tenue à jour en séance."""
import os
import shutil
import subprocess

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "dashboard")
ACCUEIL = os.path.join(ROOT, "welcome_v2.js")
CORE = os.path.join(ROOT, "js", "core.js")


def _lire(chemin):
    with open(chemin, encoding="utf-8") as f:
        return f.read()


def test_branchements_bandeau_et_accueil():
    accueil = _lire(ACCUEIL)
    core = _lire(CORE)
    assert "function _seanceOuverteMaintenant" in accueil
    assert "function _tickMarcheSeance" in accueil
    assert "function _auChangementDePageMarche" in accueil
    assert "var PERIODE_MARCHE_MS = 5 * 60 * 1000;" in accueil
    assert "var _PROMESSE_MARCHE_MS = PERIODE_MARCHE_MS;" in accueil
    assert accueil.count("fetch('/api/market'") == 1
    assert "fetch('/api/market'" not in core
    assert "if (typeof loadMarketWidget === 'function') loadMarketWidget(false);" in accueil
    assert "if (typeof _remplirMarcheAccueil === 'function') _remplirMarcheAccueil(d);" in core
    assert "window._dernierMarche = d;" in core
    assert "if (typeof _noterFraicheurMarche === 'function') _noterFraicheurMarche(d);" in core
    assert "if (!forcer && precedent && Array.isArray(precedent.indices) && precedent.indices.length)" in core
    assert "if (typeof _remplirMarcheAccueil === 'function') _remplirMarcheAccueil(null);" in core
    assert "function _noterFraicheurMarche" in accueil
    assert "var SEUIL_FRAICHEUR_MARCHE_MS = 90 * 1000;" in accueil
    assert "var DELAI_RELECTURE_MARCHE_MS = 10 * 1000;" in accueil
    assert "if (_promesseMarche === promesse) _promesseMarche = null;" in accueil
    assert core.count(
        "if (typeof _auChangementDePageMarche === 'function') _auChangementDePageMarche();"
    ) == 2
    assert "if (typeof _armerRafraichissementMarche === 'function') _armerRafraichissementMarche();" in core


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_seance_30_min_bandeau_egal_carte_et_hors_seance_rien():
    script = r"""
const fs = require('fs');
const vm = require('vm');
const accueil = fs.readFileSync(process.argv[1], 'utf8');
const core = fs.readFileSync(process.argv[2], 'utf8');
const debut = core.indexOf('function _escIndice');
const fin = core.indexOf('\nfunction loadSidebar');
if (debut < 0 || fin < 0) { console.error('decoupe core'); process.exit(1); }

let horloge = Date.parse('2026-10-01T10:50:00.000Z');
let etape = 0;
let dernier = null;
const appels = [];
let erreurs = 0;
const intervalles = [];

function FakeDate(a, b, c, d, e, f, g) {
  if (!(this instanceof FakeDate)) {
    return arguments.length ? new Date(a, b, c, d || 0, e || 0, f || 0, g || 0) : new Date(horloge);
  }
  if (arguments.length === 0) return new Date(horloge);
  if (arguments.length === 1) return new Date(a);
  return new Date(a, b, c, d || 0, e || 0, f || 0, g || 0);
}
FakeDate.now = function() { return horloge; };
FakeDate.parse = Date.parse;
FakeDate.UTC = Date.UTC;
FakeDate.prototype = Date.prototype;

function element() {
  const attrs = {};
  return {
    textContent: '',
    innerHTML: '',
    hidden: false,
    className: '',
    style: {},
    isConnected: true,
    classList: { toggle() {}, add() {}, remove() {} },
    setAttribute(k, v) { attrs[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(attrs, k) ? attrs[k] : null; },
    removeAttribute(k) { delete attrs[k]; },
    addEventListener() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
}
const store = {};
const document = {
  readyState: 'complete',
  documentElement: { classList: { toggle() {}, add() {}, remove() {} } },
  getElementById(id) {
    if (!store[id]) store[id] = element();
    return store[id];
  },
  querySelector() { return null; },
  querySelectorAll() { return []; },
  addEventListener() {},
};

function corpsMarche() {
  const frais = etape > 0;
  return {
    updated_at: frais ? new Date(horloge).toISOString() : '2026-10-01T09:04:00.000Z',
    market_activity: {},
    top5: [],
    flop5: [],
    indices: [
      {
        name: 'BRVM - COMPOSITE',
        prev: 548.38,
        current: frais ? 545.31 : 548.38,
        change: frais ? -0.56 : 0.06,
        ytd: 1.2,
      },
      { name: 'BRVM-30', prev: 120, current: frais ? 118.75 : 120, change: frais ? -1.04 : 0.1, ytd: 2 },
      { name: 'BRVM - PRESTIGE', prev: 90, current: frais ? 91.2 : 90, change: frais ? 1.33 : 0.2, ytd: 3 },
      { name: 'BRVM - PRINCIPAL', prev: 70, current: frais ? 69.4 : 70, change: frais ? -0.86 : 0.05, ytd: 4 },
    ],
  };
}

const context = {
  fetch(url) {
    const u = String(url);
    if (u.indexOf('/api/market') >= 0) {
      appels.push(horloge);
      dernier = corpsMarche();
      etape += 1;
      const corps = dernier;
      return Promise.resolve({ ok: true, json() { return Promise.resolve(corps); } });
    }
    return Promise.resolve({ ok: true, json() { return Promise.resolve({}); } });
  },
  setTimeout,
  clearTimeout,
  setInterval(fn, ms) {
    const id = { fn, ms };
    intervalles.push(id);
    return id;
  },
  clearInterval(id) {
    const i = intervalles.indexOf(id);
    if (i >= 0) intervalles.splice(i, 1);
  },
  AbortController,
  Promise,
  Date: FakeDate,
  document,
  scores: [],
  console: {
    error() { erreurs += 1; },
    log() {},
    warn() {},
  },
};
context.window = context;
vm.createContext(context);
vm.runInContext(accueil, context);
vm.runInContext(core.slice(debut, fin), context);
context._renderMarketWeather = function() {};
context._paintIndexCards = function() {};

function echec(msg) {
  console.error(msg);
  process.exit(1);
}
function nombre(s) {
  const t = String(s).replace(/\u202f/g, '').replace(/\u00a0/g, '').replace(/\s/g, '');
  const m = t.match(/[+\-−]?\d+(?:,\d+)?/);
  if (!m) return null;
  return Number(m[0].replace('−', '-').replace('+', '').replace(',', '.'));
}
function proche(a, b) {
  return a != null && b != null && Math.round(a * 100) === Math.round(b * 100);
}
function extraire(html, motif) {
  const re = new RegExp(motif, 'g');
  const out = [];
  let m;
  while ((m = re.exec(html))) out.push(m[1]);
  return out;
}
function settle() {
  return new Promise(function(resolve) { setTimeout(resolve, 0); });
}
function verifier(libelle) {
  const html = store['index-chips'].innerHTML;
  const vals = extraire(html, 'class="ix-val">([^<]*)<');
  const chgs = extraire(html, 'class="ix-chg [^"]*">([^<]*)<');
  const carte = store['accueil-composite-val'].textContent;
  const badge = store['accueil-composite-badge'].textContent;
  const maj = store['msb-time'].textContent;
  if (!dernier) echec(libelle + ' sans reponse');
  if (vals.length !== 4) echec(libelle + ' pastilles ' + vals.length);
  if (!proche(nombre(vals[0]), dernier.indices[0].current)) {
    echec(libelle + ' bandeau ' + vals[0] + ' != ' + dernier.indices[0].current);
  }
  if (!proche(nombre(carte), dernier.indices[0].current)) {
    echec(libelle + ' carte ' + carte + ' != ' + dernier.indices[0].current);
  }
  if (!proche(nombre(chgs[0]), dernier.indices[0].change)) {
    echec(libelle + ' variation bandeau ' + chgs[0] + ' != ' + dernier.indices[0].change);
  }
  if (!proche(nombre(badge), dernier.indices[0].change)) {
    echec(libelle + ' variation carte ' + badge + ' != ' + dernier.indices[0].change);
  }
  for (let i = 1; i < 4; i++) {
    if (!proche(nombre(vals[i]), dernier.indices[i].current)) {
      echec(libelle + ' pastille ' + i + ' ' + vals[i] + ' != ' + dernier.indices[i].current);
    }
  }
  const attendu = context._libelleMajMarche(dernier.updated_at);
  if (maj !== attendu) echec(libelle + ' maj ' + maj + ' != ' + attendu);
  if (attendu.indexOf('MàJ ') !== 0 || attendu.indexOf('différé') >= 0) {
    echec(libelle + ' maj pas du jour ' + attendu);
  }
}
function chapitre(iso) {
  horloge = Date.parse(iso);
  etape = 0;
  dernier = null;
  appels.length = 0;
  intervalles.length = 0;
  context._promesseMarche = null;
  context._promesseMarcheDepuis = 0;
  context._timerMarche = 0;
  context._accueilIndicesParti = 0;
  context._accueilLargeurParti = 0;
  context._mktGeneration = 0;
}

(async function() {
  if (context.PERIODE_MARCHE_MS !== 5 * 60 * 1000) echec('periode ' + context.PERIODE_MARCHE_MS);
  if (context._PROMESSE_MARCHE_MS !== context.PERIODE_MARCHE_MS) echec('promesse');

  const depart = horloge;
  context._remplirIndices();
  context.loadMarketWidget(false);
  await settle();
  if (appels.length !== 1) echec('chargement ' + appels.length);
  if (!intervalles.length || intervalles[intervalles.length - 1].ms !== context.PERIODE_MARCHE_MS) {
    echec('minuteur ' + intervalles.map(function(t) { return t.ms; }).join(','));
  }
  verifier('depart');
  const majDepart = store['msb-time'].textContent;
  if (majDepart.indexOf('09:04') < 0) echec('maj initiale ' + majDepart);
  if (!proche(nombre(store['accueil-composite-val'].textContent), 548.38)) echec('cloture absente');

  horloge = depart + 2 * 60 * 1000;
  const avantNav = appels.length;
  context._auChangementDePageMarche();
  await settle();
  if (appels.length !== avantNav) echec('navigation fraiche ' + appels.length);

  for (let k = 1; k <= 6; k++) {
    horloge = depart + k * context.PERIODE_MARCHE_MS;
    const avant = appels.length;
    if (k === 3) context._auChangementDePageMarche();
    context._tickMarcheSeance();
    if (k === 3) context._auChangementDePageMarche();
    await settle();
    if (appels.length !== avant + 1) echec('pas ' + k + ' appels ' + appels.length + ' avant ' + avant);
    verifier('pas ' + k);
    const maj = store['msb-time'].textContent;
    if (maj.indexOf('09:04') >= 0) echec('maj figee ' + maj);
    if (!proche(nombre(store['accueil-composite-val'].textContent), dernier.indices[0].current)) {
      echec('carte decalee');
    }
    if (proche(nombre(store['index-chips'].innerHTML), 548.38) && k > 0) {
      const vals = extraire(store['index-chips'].innerHTML, 'class="ix-val">([^<]*)<');
      if (proche(nombre(vals[0]), 548.38)) echec('bandeau reste sur la cloture');
    }
  }
  if (erreurs !== 0) echec('console seance ' + erreurs);

  chapitre('2026-10-03T11:00:00.000Z');
  if (context._seanceOuverteMaintenant()) echec('samedi ouvert');
  context._remplirIndices();
  context.loadMarketWidget(false);
  await settle();
  if (appels.length !== 1) echec('samedi chargement ' + appels.length);
  const baseSamedi = appels.length;
  for (let i = 0; i < 6; i++) {
    horloge += context.PERIODE_MARCHE_MS;
    context._tickMarcheSeance();
    context._auChangementDePageMarche();
    await settle();
  }
  if (appels.length !== baseSamedi) echec('samedi periodique ' + (appels.length - baseSamedi));

  chapitre('2026-10-01T16:00:00.000Z');
  if (context._seanceOuverteMaintenant()) echec('soir ouvert');
  context._armerRafraichissementMarche();
  for (let i = 0; i < 6; i++) {
    horloge += context.PERIODE_MARCHE_MS;
    context._tickMarcheSeance();
    await settle();
  }
  if (appels.length !== 0) echec('soir periodique ' + appels.length);

  horloge = Date.parse('2026-10-01T08:59:00.000Z');
  if (context._seanceOuverteMaintenant()) echec('avant ouverture');
  horloge = Date.parse('2026-10-01T09:00:00.000Z');
  if (!context._seanceOuverteMaintenant()) echec('ouverture');
  horloge = Date.parse('2026-10-01T15:29:00.000Z');
  if (!context._seanceOuverteMaintenant()) echec('avant cloture');
  horloge = Date.parse('2026-10-01T15:30:00.000Z');
  if (context._seanceOuverteMaintenant()) echec('cloture');
  horloge = Date.parse('2026-10-03T10:00:00.000Z');
  if (context._seanceOuverteMaintenant()) echec('week-end');

  if (erreurs !== 0) echec('console ' + erreurs);
  process.exit(0);
})().catch(function(e) {
  console.error(e && e.stack ? e.stack : e);
  process.exit(1);
});
"""
    fini = subprocess.run(
        ["node", "-e", script, ACCUEIL, CORE],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert fini.returncode == 0, fini.stderr or fini.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_echec_apres_succes_garde_les_valeurs_sans_erreur_console():
    """Un 500 en séance ne vide pas le bandeau ni la carte, et ne reste pas en cache."""
    script = r"""
const fs = require('fs');
const vm = require('vm');
const accueil = fs.readFileSync(process.argv[1], 'utf8');
const core = fs.readFileSync(process.argv[2], 'utf8');
const debut = core.indexOf('function _escIndice');
const fin = core.indexOf('\nfunction loadSidebar');
if (debut < 0 || fin < 0) { console.error('decoupe core'); process.exit(1); }

let horloge = Date.parse('2026-10-01T10:50:00.000Z');
let mode = 'ok';
let appels = 0;
let erreurs = 0;
const timers = [];
let seq = 1;

function FakeDate(a, b, c, d, e, f, g) {
  if (!(this instanceof FakeDate)) {
    return arguments.length ? new Date(a, b, c, d || 0, e || 0, f || 0, g || 0) : new Date(horloge);
  }
  if (arguments.length === 0) return new Date(horloge);
  if (arguments.length === 1) return new Date(a);
  return new Date(a, b, c, d || 0, e || 0, f || 0, g || 0);
}
FakeDate.now = function() { return horloge; };
FakeDate.parse = Date.parse;
FakeDate.UTC = Date.UTC;
FakeDate.prototype = Date.prototype;

function element() {
  const attrs = {};
  return {
    textContent: '',
    innerHTML: '',
    hidden: false,
    className: '',
    style: {},
    isConnected: true,
    classList: { toggle() {}, add() {}, remove() {}, contains() { return false; } },
    setAttribute(k, v) { attrs[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(attrs, k) ? attrs[k] : null; },
    removeAttribute(k) { delete attrs[k]; },
    addEventListener() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
}
const store = {};
const document = {
  readyState: 'complete',
  documentElement: { classList: { toggle() {}, add() {}, remove() {} } },
  getElementById(id) {
    if (!store[id]) store[id] = element();
    return store[id];
  },
  querySelector() { return null; },
  querySelectorAll() { return []; },
  addEventListener() {},
};

function corpsOk() {
  return {
    updated_at: new Date(horloge).toISOString(),
    market_activity: {},
    top5: [{ ticker: 'SNTS', change: 1.2, price: 15000 }],
    flop5: [{ ticker: 'ABJC', change: -0.8, price: 8000 }],
    indices: [
      { name: 'BRVM - COMPOSITE', prev: 548.38, current: 545.31, change: -0.56, ytd: 1.2 },
      { name: 'BRVM-30', prev: 120, current: 118.75, change: -1.04, ytd: 2 },
      { name: 'BRVM - PRESTIGE', prev: 90, current: 91.2, change: 1.33, ytd: 3 },
      { name: 'BRVM - PRINCIPAL', prev: 70, current: 69.4, change: -0.86, ytd: 4 },
    ],
  };
}

const context = {
  fetch(url) {
    const u = String(url);
    if (u.indexOf('/api/market') >= 0) {
      appels += 1;
      if (mode === 'panne') {
        return Promise.resolve({ ok: false, status: 500, json() { return Promise.resolve({}); } });
      }
      const corps = corpsOk();
      return Promise.resolve({ ok: true, json() { return Promise.resolve(corps); } });
    }
    return Promise.resolve({ ok: true, json() { return Promise.resolve({}); } });
  },
  setTimeout(fn, ms) {
    const id = seq++;
    timers.push({ id: id, fn: fn, ms: ms });
    return id;
  },
  clearTimeout(id) {
    const i = timers.findIndex(function(t) { return t.id === id; });
    if (i >= 0) timers.splice(i, 1);
  },
  setInterval() { return 0; },
  clearInterval() {},
  AbortController,
  Promise,
  Date: FakeDate,
  document,
  scores: [],
  console: {
    error() { erreurs += 1; },
    log() {},
    warn() {},
  },
};
context.window = context;
vm.createContext(context);
vm.runInContext(accueil, context);
vm.runInContext(core.slice(debut, fin), context);
context._renderMarketWeather = function() {};
context._paintIndexCards = function() {};

function echec(msg) {
  console.error(msg);
  process.exit(1);
}
function pompe() {
  return Promise.resolve().then(function() {
    return Promise.resolve();
  }).then(function() {
    return Promise.resolve();
  }).then(function() {
    return Promise.resolve();
  });
}
function tirer(ms) {
  const dus = timers.filter(function(t) { return t.ms === ms; });
  dus.forEach(function(t) {
    const i = timers.indexOf(t);
    if (i >= 0) timers.splice(i, 1);
  });
  dus.forEach(function(t) { t.fn(); });
  return dus.length;
}
async function laisserRetenter() {
  await pompe();
  const n = tirer(700);
  if (n < 1) echec('pas de nouvel essai');
  await pompe();
  await pompe();
}

(async function() {
  context._remplirIndices();
  context.loadMarketWidget(false);
  await pompe();
  if (appels !== 1) echec('chargement ' + appels);
  if (erreurs !== 0) echec('console au succes ' + erreurs);
  if (timers.some(function(t) { return t.ms === context.DELAI_RELECTURE_MARCHE_MS; })) {
    echec('relecture alors que la reponse est fraiche');
  }
  const carte = store['accueil-composite-val'].textContent;
  const bandeau = store['index-chips'].innerHTML;
  const maj = store['msb-time'].textContent;
  const grille = store['accueil-mvt-grille'].innerHTML;
  if (carte.indexOf('545,31') < 0) echec('carte ' + carte);
  if (bandeau.indexOf('545,31') < 0) echec('bandeau ' + bandeau);
  if (grille.indexOf('SNTS') < 0) echec('seance ' + grille);
  if (grille.indexOf('indisponibles') >= 0) echec('seance vide au succes');
  if (!context._dernierMarche || !context._dernierMarche.indices.length) echec('dernier absent');

  horloge += context.PERIODE_MARCHE_MS;
  mode = 'panne';
  const avantPanne = appels;
  context.loadMarketWidget(false);
  context.loadMarketWidget(false);
  await laisserRetenter();
  if (appels !== avantPanne + 2) echec('essais panne ' + (appels - avantPanne));
  if (erreurs !== 0) echec('console panne ' + erreurs);
  if (store['accueil-composite-val'].textContent !== carte) echec('carte effacee ' + store['accueil-composite-val'].textContent);
  if (store['index-chips'].innerHTML !== bandeau) echec('bandeau efface');
  if (store['msb-time'].textContent !== maj) echec('maj effacee ' + store['msb-time'].textContent);
  if (store['accueil-mvt-grille'].innerHTML !== grille) echec('seance effacee');
  if (store['accueil-mvt-grille'].innerHTML.indexOf('indisponibles') >= 0) echec('seance indisponible');
  if (context._promesseMarche !== null) echec('promesse gardee');

  const avantNav = appels;
  context._auChangementDePageMarche();
  await pompe();
  if (appels !== avantNav + 1) echec('navigation ne relit pas ' + (appels - avantNav));
  await laisserRetenter();
  if (erreurs !== 0) echec('console navigation ' + erreurs);
  if (store['accueil-composite-val'].textContent !== carte) echec('carte apres navigation');
  if (context._promesseMarche !== null) echec('promesse apres navigation');

  const avantForce = erreurs;
  context.loadMarketWidget(true);
  await laisserRetenter();
  if (erreurs !== avantForce + 1) echec('console reessayer ' + erreurs);
  if (store['accueil-composite-val'].textContent !== '—') echec('reessayer carte ' + store['accueil-composite-val'].textContent);
  if (store['index-chips'].innerHTML.indexOf('—') < 0) echec('reessayer bandeau');
  if (store['accueil-mvt-grille'].innerHTML.indexOf('indisponibles') < 0) echec('reessayer seance');
  if (context._promesseMarche !== null) echec('promesse apres reessayer');

  process.exit(0);
})().catch(function(e) {
  console.error(e && e.stack ? e.stack : e);
  process.exit(1);
});
"""
    fini = subprocess.run(
        ["node", "-e", script, ACCUEIL, CORE],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert fini.returncode == 0, fini.stderr or fini.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_relecture_unique_si_cache_a_plus_de_90s():
    """En séance, un updated_at > 90 s programme une seule relecture ~10 s plus tard."""
    script = r"""
const fs = require('fs');
const vm = require('vm');
const accueil = fs.readFileSync(process.argv[1], 'utf8');

let horloge = Date.parse('2026-10-01T10:50:00.000Z');
let appels = 0;
let dernierForcer = null;
const timers = [];
let seq = 1;

function FakeDate(a, b, c, d, e, f, g) {
  if (!(this instanceof FakeDate)) {
    return arguments.length ? new Date(a, b, c, d || 0, e || 0, f || 0, g || 0) : new Date(horloge);
  }
  if (arguments.length === 0) return new Date(horloge);
  if (arguments.length === 1) return new Date(a);
  return new Date(a, b, c, d || 0, e || 0, f || 0, g || 0);
}
FakeDate.now = function() { return horloge; };
FakeDate.parse = Date.parse;
FakeDate.UTC = Date.UTC;
FakeDate.prototype = Date.prototype;

const context = {
  fetch() { return Promise.resolve({ ok: true, json() { return Promise.resolve({}); } }); },
  setTimeout(fn, ms) {
    const id = seq++;
    timers.push({ id: id, fn: fn, ms: ms });
    return id;
  },
  clearTimeout(id) {
    const i = timers.findIndex(function(t) { return t.id === id; });
    if (i >= 0) timers.splice(i, 1);
  },
  setInterval() { return 0; },
  clearInterval() {},
  Date: FakeDate,
  console: { error() {}, log() {} },
};
context.window = context;
context.loadMarketWidget = function(forcer) {
  dernierForcer = forcer;
  appels += 1;
  context._noterFraicheurMarche(context._reponse);
};
vm.createContext(context);
vm.runInContext(accueil, context);

function echec(msg) {
  console.error(msg);
  process.exit(1);
}
function nb(ms) {
  return timers.filter(function(t) { return t.ms === ms; }).length;
}
function tirer(ms) {
  const dus = timers.filter(function(t) { return t.ms === ms; });
  dus.forEach(function(t) {
    const i = timers.indexOf(t);
    if (i >= 0) timers.splice(i, 1);
  });
  dus.forEach(function(t) { t.fn(); });
  return dus.length;
}
function charge(ageMs) {
  return { updated_at: new Date(horloge - ageMs).toISOString(), indices: [{ name: 'BRVM - COMPOSITE', current: 545.31 }] };
}

if (context.SEUIL_FRAICHEUR_MARCHE_MS !== 90000) echec('seuil');
if (context.DELAI_RELECTURE_MARCHE_MS !== 10000) echec('delai');

context._noterFraicheurMarche(charge(30 * 1000));
if (nb(10000) !== 0) echec('relecture sur cache frais');
if (appels !== 0) echec('get immediat ' + appels);

context._reponse = charge(120 * 1000);
context._noterFraicheurMarche(context._reponse);
if (nb(10000) !== 1) echec('pas de relecture ' + nb(10000));
if (appels !== 0) echec('get avant 10 s ' + appels);
context._noterFraicheurMarche(context._reponse);
if (nb(10000) !== 1) echec('deuxieme programmation ' + nb(10000));

if (tirer(10000) !== 1) echec('tir');
if (appels !== 1) echec('relecture ' + appels);
if (dernierForcer) echec('relecture forcee');
if (nb(10000) !== 0) echec('boucle ' + nb(10000));

context._reponse = charge(0);
context._noterFraicheurMarche(context._reponse);
context._reponse = charge(120 * 1000);
context._noterFraicheurMarche(context._reponse);
if (nb(10000) !== 1) echec('apres fraicheur ' + nb(10000));

horloge = Date.parse('2026-10-03T11:00:00.000Z');
timers.length = 0;
context._noterFraicheurMarche(charge(120 * 1000));
if (nb(10000) !== 0) echec('hors seance');
if (appels !== 1) echec('get hors seance ' + appels);

process.exit(0);
"""
    fini = subprocess.run(
        ["node", "-e", script, ACCUEIL],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert fini.returncode == 0, fini.stderr or fini.stdout
