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
    assert "if (typeof _remplirMarcheAccueil === 'function') _remplirMarcheAccueil(null);" in core
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
