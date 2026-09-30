# -*- coding: utf-8 -*-
"""Cache de /api/market : reponse immediate, un seul scrape, memes champs."""
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

import market_data


CHAMPS = {
    "updated_at",
    "market_activity",
    "top5",
    "flop5",
    "indices",
    "sector_indices",
    "total_return",
}


def _a(moment):
    return moment.isoformat()


def _payload(moment, ticker="AAAA"):
    return {
        "updated_at": _a(moment),
        "market_activity": {"Capitalisation Actions": "10 000"},
        "top5": [{"ticker": ticker, "price": 1000.0, "change": 1.5}],
        "flop5": [{"ticker": "ZZZZ", "price": 10.0, "change": -1.0}],
        "indices": [{
            "name": "BRVM - COMPOSITE",
            "prev": 200.0,
            "current": 201.0,
            "change": 0.5,
            "ytd": 3.0,
        }],
        "sector_indices": [],
        "total_return": {},
    }


def _vide(moment):
    return {
        "updated_at": _a(moment),
        "market_activity": {},
        "top5": [],
        "flop5": [],
        "indices": [],
        "sector_indices": [],
        "total_return": {},
    }


def _joindre(md):
    fil = md._dernier_fil
    if fil is not None and fil.is_alive():
        fil.join(3)
        assert not fil.is_alive()


@pytest.fixture
def md():
    market_data._memoire = None
    market_data._en_cours = False
    market_data._dernier_essai = 0.0
    market_data._dernier_fil = None
    if os.path.exists(market_data.CACHE_PATH):
        os.remove(market_data.CACHE_PATH)
    yield market_data
    _joindre(market_data)
    market_data._memoire = None
    market_data._en_cours = False
    market_data._dernier_essai = 0.0
    market_data._dernier_fil = None
    if os.path.exists(market_data.CACHE_PATH):
        os.remove(market_data.CACHE_PATH)


@pytest.fixture
def client():
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    import app as application
    return application.app.test_client()


def test_ttl_60s_en_seance_et_15min_marche_ferme(md):
    mardi_matin = datetime(2026, 9, 29, 10, 15, tzinfo=timezone.utc)
    mardi_soir = datetime(2026, 9, 29, 16, 0, tzinfo=timezone.utc)
    samedi = datetime(2026, 10, 3, 11, 0, tzinfo=timezone.utc)
    assert md._ttl_secondes(mardi_matin) == 60
    assert md._ttl_secondes(mardi_soir) == 15 * 60
    assert md._ttl_secondes(samedi) == 15 * 60


def test_cache_frais_ne_scrape_pas_et_garde_les_memes_champs(md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    payload = _payload(maintenant - timedelta(seconds=20))
    md._ecrire(payload)

    def interdit():
        raise AssertionError("scrape inattendu")

    monkeypatch.setattr(md, "fetch_market_data", interdit)
    recu = md.get_market_data()
    assert recu == payload
    assert set(recu) == CHAMPS


def test_horodatage_naif_compte_comme_utc(md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    payload = _payload(maintenant - timedelta(seconds=15))
    payload["updated_at"] = (maintenant - timedelta(seconds=15)).replace(tzinfo=None).isoformat()
    md._memoire = payload

    def interdit():
        raise AssertionError("scrape inattendu")

    monkeypatch.setattr(md, "fetch_market_data", interdit)
    assert md.get_market_data()["top5"][0]["ticker"] == "AAAA"


def test_cache_perime_repond_tout_de_suite_puis_revalide(md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    ancien = _payload(maintenant - timedelta(seconds=90), ticker="VIEUX")
    md._ecrire(ancien)
    bloque = threading.Event()
    neuf = _payload(maintenant, ticker="NEUF")

    def lent():
        bloque.wait(2)
        return neuf

    monkeypatch.setattr(md, "fetch_market_data", lent)
    debut = time.perf_counter()
    recu = md.get_market_data()
    duree = time.perf_counter() - debut
    assert duree < 0.5
    assert recu == ancien
    assert set(recu) == CHAMPS
    bloque.set()
    _joindre(md)
    assert md._lire()["top5"][0]["ticker"] == "NEUF"


def test_marche_ferme_un_cache_de_5min_reste_frais(md, monkeypatch):
    samedi = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: samedi)
    payload = _payload(samedi - timedelta(minutes=5))
    md._memoire = payload

    def interdit():
        raise AssertionError("scrape inattendu")

    monkeypatch.setattr(md, "fetch_market_data", interdit)
    assert md.get_market_data() == payload


def test_un_seul_scrape_si_plusieurs_requetes_sans_cache(md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    appels = {"n": 0}
    compte = threading.Lock()
    neuf = _payload(maintenant, ticker="NEUF")

    def lent():
        with compte:
            appels["n"] += 1
        time.sleep(0.25)
        return neuf

    monkeypatch.setattr(md, "fetch_market_data", lent)
    resultats = []
    verrou = threading.Lock()

    def travail():
        data = md.get_market_data()
        with verrou:
            resultats.append(data["top5"][0]["ticker"])

    fils = [threading.Thread(target=travail) for _ in range(4)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join(3)
        assert not fil.is_alive()
    assert appels["n"] == 1
    assert resultats == ["NEUF", "NEUF", "NEUF", "NEUF"]


def test_requetes_paralleles_sur_cache_perime_ne_scrapent_qu_une_fois(md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    md._ecrire(_payload(maintenant - timedelta(seconds=120), ticker="VIEUX"))
    appels = {"n": 0}
    compte = threading.Lock()
    bloque = threading.Event()

    def lent():
        with compte:
            appels["n"] += 1
        bloque.wait(2)
        return _payload(maintenant, ticker="NEUF")

    monkeypatch.setattr(md, "fetch_market_data", lent)
    durees = []
    verrou = threading.Lock()

    def travail():
        debut = time.perf_counter()
        data = md.get_market_data()
        with verrou:
            durees.append((time.perf_counter() - debut, data["top5"][0]["ticker"]))

    fils = [threading.Thread(target=travail) for _ in range(4)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join(2)
        assert not fil.is_alive()
    assert appels["n"] == 1
    assert all(ticker == "VIEUX" for _, ticker in durees)
    assert all(duree < 0.5 for duree, _ in durees)
    bloque.set()
    _joindre(md)


def test_scrape_vide_ne_remplace_pas_un_cache_utile(md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    ancien = _payload(maintenant - timedelta(seconds=180), ticker="VIEUX")
    md._ecrire(ancien)
    appels = {"n": 0}

    def vide():
        appels["n"] += 1
        return _vide(maintenant)

    monkeypatch.setattr(md, "fetch_market_data", vide)
    recu = md.get_market_data()
    assert recu["top5"][0]["ticker"] == "VIEUX"
    _joindre(md)
    assert appels["n"] == 1
    assert md._lire()["top5"][0]["ticker"] == "VIEUX"
    encore = md.get_market_data()
    assert encore["top5"][0]["ticker"] == "VIEUX"
    assert appels["n"] == 1


def test_synchroniser_attend_le_scrape_et_renvoie_le_meme_json(md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    attendu = _payload(maintenant, ticker="SCRP")
    monkeypatch.setattr(md, "fetch_market_data", lambda: attendu)
    recu = md.get_market_data(force_refresh=True, synchroniser=True)
    assert recu == attendu
    assert set(recu) == CHAMPS
    monkeypatch.setattr(md, "fetch_market_data", lambda: (_ for _ in ()).throw(AssertionError("second scrape")))
    assert md.get_market_data() == attendu


def test_api_market_sert_le_cache_sans_champ_en_plus(client, md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    payload = _payload(maintenant - timedelta(seconds=10))
    md._ecrire(payload)
    md._memoire = None

    def interdit():
        raise AssertionError("scrape inattendu")

    monkeypatch.setattr(md, "fetch_market_data", interdit)
    reponse = client.get("/api/market")
    assert reponse.status_code == 200
    corps = reponse.get_json()
    assert corps == payload
    assert set(corps) == CHAMPS


def test_api_market_cache_perime_reste_sous_500ms(client, md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    ancien = _payload(maintenant - timedelta(minutes=10), ticker="VIEUX")
    md._ecrire(ancien)
    md._memoire = None
    bloque = threading.Event()

    def lent():
        bloque.wait(2)
        return _payload(maintenant, ticker="NEUF")

    monkeypatch.setattr(md, "fetch_market_data", lent)
    debut = time.perf_counter()
    reponse = client.get("/api/market")
    duree = time.perf_counter() - debut
    assert duree < 0.5
    assert reponse.status_code == 200
    assert reponse.get_json() == ancien
    bloque.set()
    _joindre(md)


def test_api_top5_vide_ne_relance_pas_un_scrape_synchrone(client, md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    payload = _payload(maintenant - timedelta(seconds=5))
    payload["top5"] = []
    md._ecrire(payload)
    md._memoire = None

    def interdit():
        raise AssertionError("le top5 vide ne doit plus bloquer la requete")

    monkeypatch.setattr(md, "fetch_market_data", interdit)
    reponse = client.get("/api/market")
    assert reponse.status_code == 200
    assert reponse.get_json()["top5"] == []
    assert reponse.get_json()["indices"] == payload["indices"]


def _ecrire_brut(md, data):
    """Pose un fichier tel quel, y compris un squelette non utile."""
    dossier = os.path.dirname(md.CACHE_PATH)
    os.makedirs(dossier, exist_ok=True)
    with open(md.CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_panne_sans_cache_necrit_pas_le_disque(md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    appels = {"n": 0}

    def panne():
        appels["n"] += 1
        raise RuntimeError("brvm.org en panne")

    monkeypatch.setattr(md, "fetch_market_data", panne)
    recu = md.get_market_data(synchroniser=True)
    assert recu["indices"] == []
    assert not os.path.exists(md.CACHE_PATH)
    assert md._memoire["indices"] == []
    assert appels["n"] == 1
    encore = md.get_market_data()
    assert encore["indices"] == []
    assert appels["n"] == 1
    md._dernier_essai = time.monotonic() - md.DELAI_NOUVEL_ESSAI_S - 1
    md.get_market_data()
    _joindre(md)
    assert appels["n"] == 2
    assert not os.path.exists(md.CACHE_PATH)


def test_squelette_vide_reste_en_memoire_seulement(md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)

    def vide():
        return _vide(maintenant)

    monkeypatch.setattr(md, "fetch_market_data", vide)
    recu = md.get_market_data(synchroniser=True)
    assert recu["indices"] == []
    assert not os.path.exists(md.CACHE_PATH)
    assert not md._est_frais(recu)
    assert md.get_market_data()["indices"] == []


def test_fichier_indices_vides_est_retire(md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    _ecrire_brut(md, _vide(maintenant))
    assert os.path.exists(md.CACHE_PATH)

    def panne():
        raise RuntimeError("brvm.org en panne")

    monkeypatch.setattr(md, "fetch_market_data", panne)
    recu = md.get_market_data(synchroniser=True)
    assert recu["indices"] == []
    assert not os.path.exists(md.CACHE_PATH)


def test_activite_seule_ne_remplace_pas_les_indices(md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    ancien = _payload(maintenant - timedelta(minutes=5), ticker="VIEUX")
    ancien["sector_indices"] = [{
        "name": "Finance", "prev": 100.0, "current": 101.0, "change": 1.0, "ytd": 2.0,
    }]
    md._ecrire(ancien)
    md._memoire = None
    md._dernier_essai = 0.0

    def partiel():
        data = _vide(maintenant)
        data["market_activity"] = {"Capitalisation Actions": "99 000"}
        return data

    monkeypatch.setattr(md, "fetch_market_data", partiel)
    md.get_market_data()
    _joindre(md)
    with open(md.CACHE_PATH, encoding="utf-8") as f:
        disque = json.load(f)
    assert disque["indices"][0]["current"] == 201.0
    assert disque["top5"][0]["ticker"] == "VIEUX"
    assert disque["flop5"][0]["ticker"] == "ZZZZ"
    assert disque["sector_indices"][0]["name"] == "Finance"
    assert disque["market_activity"]["Capitalisation Actions"] == "99 000"


def test_liste_vide_ne_remplace_pas_une_liste_pleine(md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    ancien = _payload(maintenant - timedelta(minutes=5), ticker="VIEUX")
    md._ecrire(ancien)
    md._memoire = None
    md._dernier_essai = 0.0

    def partiel():
        data = _payload(maintenant, ticker="NEUF")
        data["indices"] = [{
            "name": "BRVM - COMPOSITE",
            "prev": 210.0,
            "current": 211.0,
            "change": 0.4,
            "ytd": 1.0,
        }]
        data["top5"] = []
        data["flop5"] = []
        data["sector_indices"] = []
        return data

    monkeypatch.setattr(md, "fetch_market_data", partiel)
    md.get_market_data(synchroniser=True)
    with open(md.CACHE_PATH, encoding="utf-8") as f:
        disque = json.load(f)
    assert disque["top5"][0]["ticker"] == "VIEUX"
    assert disque["flop5"][0]["ticker"] == "ZZZZ"
    assert disque["indices"][0]["current"] == 211.0
    assert set(disque) == CHAMPS


def test_indices_implausibles_ne_sont_pas_ecrits(md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)

    def mauvais():
        data = _vide(maintenant)
        data["indices"] = [{
            "name": "BRVM - COMPOSITE",
            "prev": 1.0,
            "current": 1.0,
            "change": 0.0,
            "ytd": 0.0,
        }]
        data["market_activity"] = {"BRVM-C": "1"}
        return data

    monkeypatch.setattr(md, "fetch_market_data", mauvais)
    recu = md.get_market_data(synchroniser=True)
    assert recu["indices"] == []
    assert md._memoire["indices"][0]["current"] == 1.0
    assert not os.path.exists(md.CACHE_PATH)
    assert not md._scrape_utile(recu)


def test_memoire_ne_sert_pas_un_indice_implausible(md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    payload = _payload(maintenant)
    payload["indices"].append({
        "name": "BRVM - 30",
        "prev": 1.0,
        "current": 1.0,
        "change": 0.0,
        "ytd": 0.0,
    })
    md._memoire = payload
    recu = md.get_market_data()
    assert [item["name"] for item in recu["indices"]] == ["BRVM - COMPOSITE"]
    assert md._memoire["indices"][1]["current"] == 1.0


def test_fusion_recopie_la_session_date(md, monkeypatch):
    jour29 = datetime(2026, 9, 29, 18, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: jour29)
    ancien = _payload(jour29)
    ancien["session_date"] = "2026-09-29"
    md._ecrire(ancien)
    md._memoire = None
    md._dernier_essai = 0.0

    jour30 = datetime(2026, 9, 30, 18, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: jour30)

    def scrape():
        data = _payload(jour30, ticker="NEUF")
        data["indices"][0]["current"] = 210.0
        data["session_date"] = "2026-09-30"
        return data

    monkeypatch.setattr(md, "fetch_market_data", scrape)
    recu = md.get_market_data(force_refresh=True, synchroniser=True)
    assert recu["session_date"] == "2026-09-30"
    with open(md.CACHE_PATH, encoding="utf-8") as f:
        disque = json.load(f)
    assert disque["session_date"] == "2026-09-30"


def test_indices_implausibles_gardent_le_cache_utile(md, monkeypatch):
    maintenant = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    ancien = _payload(maintenant - timedelta(minutes=5), ticker="VIEUX")
    md._ecrire(ancien)
    md._memoire = None
    md._dernier_essai = 0.0

    def mauvais():
        data = _vide(maintenant)
        data["indices"] = [{"name": "BRVM - COMPOSITE", "current": 3.0}]
        data["top5"] = []
        return data

    monkeypatch.setattr(md, "fetch_market_data", mauvais)
    md.get_market_data(synchroniser=True)
    with open(md.CACHE_PATH, encoding="utf-8") as f:
        disque = json.load(f)
    assert disque["indices"][0]["current"] == 201.0
    assert disque["top5"][0]["ticker"] == "VIEUX"


def test_widget_une_promesse_delai_et_maj_differe():
    racine = os.path.join(os.path.dirname(__file__), "..", "dashboard")
    with open(os.path.join(racine, "js", "core.js"), encoding="utf-8") as f:
        core = f.read()
    with open(os.path.join(racine, "welcome_v2.js"), encoding="utf-8") as f:
        accueil = f.read()
    assert "function demanderMarche" in accueil
    assert "var DELAI_MARCHE_MS = 20000;" in accueil
    assert accueil.count("fetch('/api/market'") == 1
    assert "if (essai < 1)" in accueil
    assert "fetch('/api/market'" not in core
    assert "demanderMarche(!!forcer)" in core
    assert "if (!abandon) console.error('[BRVM] loadMarketWidget:', e);" in core
    assert "console.error('[BRVM] loadMarketWidget:',e);" not in core
    assert "function _libelleMajMarche" in core
    assert "MàJ différé" in core
    assert "loadMarketWidget(true)" in core
    script = r"""
const fs = require('fs');
const vm = require('vm');
const accueil = fs.readFileSync(process.argv[1], 'utf8');
const core = fs.readFileSync(process.argv[2], 'utf8');
let calls = 0;
let errors = 0;
const context = {
  fetch: function() {
    calls += 1;
    return Promise.resolve({ ok: true, json: function() { return Promise.resolve({ indices: [] }); } });
  },
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  AbortController: AbortController,
  Promise: Promise,
  Date: Date,
  console: { error: function() { errors += 1; }, log: function() {} },
};
vm.createContext(context);
vm.runInContext(accueil, context);
Promise.all([
  context.demanderMarche(false),
  context.demanderMarche(false),
  context.demanderMarche(false),
  context.demanderMarche(false),
  context.demanderMarche(false),
]).then(function() {
  if (calls !== 1) { console.error('appels ' + calls); process.exit(1); }
  return context.demanderMarche(false);
}).then(function() {
  if (calls !== 1) { console.error('rejeu ' + calls); process.exit(1); }
  return context.demanderMarche(true);
}).then(function() {
  if (calls !== 2) { console.error('force ' + calls); process.exit(1); }
  context._promesseMarche = null;
  context.DELAI_MARCHE_MS = 30;
  context.fetch = function(url, opts) {
    calls += 1;
    return new Promise(function(resolve, reject) {
      if (opts && opts.signal) {
        opts.signal.addEventListener('abort', function() {
          var e = new Error('aborted');
          e.name = 'AbortError';
          reject(e);
        });
      }
    });
  };
  return context.demanderMarche(true);
}).then(function() {
  console.error('aurait du abandonner');
  process.exit(1);
}).catch(function(e) {
  if (!e || e.name !== 'AbortError') { console.error('pas abort ' + (e && e.name)); process.exit(1); }
  if (errors !== 0) { console.error('console ' + errors); process.exit(1); }
  if (calls !== 4) { console.error('essais ' + calls); process.exit(1); }
  var debut = core.indexOf('function _libelleMajMarche');
  var fin = core.indexOf('function loadMarketWidget');
  vm.runInContext(core.slice(debut, fin), context);
  var now = new Date();
  var heure = now.toLocaleTimeString('fr-FR', {hour:'2-digit', minute:'2-digit'});
  if (context._libelleMajMarche(now.toISOString()) !== 'MàJ ' + heure) {
    console.error('jour ' + context._libelleMajMarche(now.toISOString()));
    process.exit(1);
  }
  var hier = new Date(now.getTime() - 36 * 3600 * 1000);
  var jour = hier.toLocaleDateString('fr-FR', {day:'2-digit', month:'2-digit'});
  var h2 = hier.toLocaleTimeString('fr-FR', {hour:'2-digit', minute:'2-digit'});
  var lib = context._libelleMajMarche(hier.toISOString());
  if (lib !== 'MàJ différé ' + jour + ' ' + h2) {
    console.error('differe ' + lib);
    process.exit(1);
  }
  process.exit(0);
});
"""
    import subprocess
    import sys
    resultat = subprocess.run(
        [sys.executable, "-c", "import shutil,sys; sys.exit(0 if shutil.which('node') else 1)"]
    )
    if resultat.returncode != 0:
        pytest.skip("node absent")
    chemin_accueil = os.path.join(racine, "welcome_v2.js")
    chemin_core = os.path.join(racine, "js", "core.js")
    fini = subprocess.run(
        ["node", "-e", script, chemin_accueil, chemin_core],
        capture_output=True, text=True, timeout=5,
    )
    assert fini.returncode == 0, fini.stderr or fini.stdout
