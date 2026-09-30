# -*- coding: utf-8 -*-
"""Cache de /api/market : reponse immediate, un seul scrape, memes champs."""
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


def test_widget_delai_plus_long_un_seul_essai_sans_erreur_sur_abandon():
    chemin = os.path.join(os.path.dirname(__file__), "..", "dashboard", "js", "core.js")
    with open(chemin, encoding="utf-8") as f:
        source = f.read()
    assert "var DELAI_MARCHE_MS = 20000;" in source
    assert "setTimeout(function(){ _mktAc.abort(); }, DELAI_MARCHE_MS);" in source
    assert "setTimeout(function(){ _mktAc.abort(); }, 10000)" not in source
    assert "if (essai < 1)" in source
    assert "e.name === 'AbortError'" in source
    assert "if (!abandon) console.error('[BRVM] loadMarketWidget:', e);" in source
    assert "console.error('[BRVM] loadMarketWidget:',e);" not in source
    assert "Indices en attente" in source
