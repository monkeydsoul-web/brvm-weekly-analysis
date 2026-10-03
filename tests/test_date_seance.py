# -*- coding: utf-8 -*-
"""Date de séance affichée : réponse HTTP seulement.

Le scrape écrit l'horloge du site dans market_cache.json. /api/market
recule samedi et dimanche au vendredi, et laisse un jour ouvré tel quel.
Aucun historique n'est réécrit.
"""
import json
import os
from datetime import datetime, timezone

import pytest

import live_data
import market_data
import price_history_builder
import rank_history_builder
import index_history

VENDREDI_SEANCE = datetime(2026, 10, 2, 11, 0, tzinfo=timezone.utc)
VENDREDI_APRES = datetime(2026, 10, 2, 16, 0, tzinfo=timezone.utc)
VENDREDI_18H = datetime(2026, 10, 2, 18, 10, tzinfo=timezone.utc)
SAMEDI = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
DIMANCHE = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


class _Horloge:
    """Remplace datetime.now, laisse fromisoformat et le reste intacts."""

    def __init__(self, moment):
        self._moment = moment

    def now(self, tz=None):
        if tz is None:
            return self._moment.replace(tzinfo=None)
        return self._moment.astimezone(tz)

    def __getattr__(self, nom):
        return getattr(datetime, nom)


def _geler(monkeypatch, moment):
    monkeypatch.setattr(market_data, "_maintenant", lambda: moment)
    horloge = _Horloge(moment)
    monkeypatch.setattr(live_data, "datetime", horloge)
    monkeypatch.setattr(price_history_builder, "datetime", horloge)
    monkeypatch.setattr(rank_history_builder, "datetime", horloge)


def _marche(moment, session_date):
    data = {
        "updated_at": moment.isoformat(),
        "market_activity": {"Capitalisation Actions": "10 000"},
        "top5": [],
        "flop5": [],
        "indices": [
            {"name": "BRVM - COMPOSITE", "prev": 540.0, "current": 546.78, "change": 1.2},
            {"name": "BRVM - 30", "prev": 260.0, "current": 264.57, "change": 1.7},
            {"name": "BRVM - PRESTIGE", "prev": 210.0, "current": 215.31, "change": 2.5},
            {"name": "BRVM - PRINCIPAL", "prev": 330.0, "current": 333.02, "change": 0.9},
        ],
        "sector_indices": [],
        "total_return": {},
    }
    if session_date is not None:
        data["session_date"] = session_date
    return data


def _ecrire(chemin, data):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _lire(chemin):
    with open(chemin, encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def client(monkeypatch):
    import app as application
    market_data._memoire = None
    market_data._en_cours = False
    market_data._dernier_essai = 0.0
    monkeypatch.setattr(
        market_data, "fetch_market_data",
        lambda: (_ for _ in ()).throw(RuntimeError("pas de reseau")),
    )
    yield application.app.test_client()
    market_data._memoire = None


@pytest.fixture
def isole(tmp_path, monkeypatch):
    """Fichiers du test, hors du répertoire partagé des autres tests."""
    marche = tmp_path / "market_cache.json"
    macro = tmp_path / "macro_cache.json"
    cours = tmp_path / "live_cache.json"
    prix = tmp_path / "price_history.json"
    rangs = tmp_path / "rank_history.json"
    classement = tmp_path / "live_ranking.json"
    indices = tmp_path / "index_history.json"
    monkeypatch.setattr(market_data, "CACHE_PATH", str(marche))
    monkeypatch.setattr(live_data, "CACHE_PATH", str(cours))
    monkeypatch.setattr(price_history_builder, "HISTORY_PATH", str(prix))
    monkeypatch.setattr(rank_history_builder, "RANK_HISTORY_PATH", str(rangs))
    monkeypatch.setattr(rank_history_builder, "LIVE_RANKING_PATH", str(classement))
    monkeypatch.setattr(index_history, "HISTORY_PATH", str(indices))
    index_history.invalider_cache()
    # /api/macro lit DATA_DIR, pas un chemin de module.
    import app as application
    monkeypatch.setattr(application, "DATA_DIR", str(tmp_path))
    yield {
        "dir": tmp_path,
        "marche": marche,
        "macro": macro,
        "cours": cours,
        "prix": prix,
        "rangs": rangs,
        "classement": classement,
        "indices": indices,
    }
    index_history.invalider_cache()


def test_samedi_et_dimanche_renvoient_la_derniere_seance(client, isole, monkeypatch):
    # Cache des cours volontairement à jeudi : un jour ouvré ne doit pas
    # être choisi à la place du vendredi, et le week-end non plus.
    _ecrire(str(isole["cours"]), {
        "updated_at": "2026-10-01T15:00:00+00:00",
        "session_date": "2026-10-01",
        "prices": {"ALPH": {"price": 1000, "session_date": "2026-10-01"}},
    })
    _ecrire(str(isole["prix"]), {
        "ALPH": [{"date": "2026-10-01", "price": 1000, "source": "live"}],
    })
    for moment, horloge_site in ((SAMEDI, "2026-10-03"), (DIMANCHE, "2026-10-04")):
        _geler(monkeypatch, moment)
        _ecrire(str(isole["marche"]), _marche(moment, horloge_site))
        avant = _lire(str(isole["marche"]))
        market_data._memoire = None
        corps = client.get("/api/market").get_json()
        assert corps["session_date"] == "2026-10-02"
        assert isinstance(corps["session_date"], str)
        assert _lire(str(isole["marche"])) == avant
        assert json.loads(avant)["session_date"] == horloge_site
        secteurs = client.get("/api/sector-indices").get_json()
        assert secteurs["session_date"] == horloge_site


def test_jour_ouvre_en_seance_et_apres_cloture_garde_la_date_du_jour(client, isole, monkeypatch):
    _ecrire(str(isole["cours"]), {
        "updated_at": "2026-10-01T18:00:00+00:00",
        "session_date": "2026-10-01",
        "prices": {"ALPH": {"price": 1000, "session_date": "2026-10-01"}},
    })
    for moment in (VENDREDI_SEANCE, VENDREDI_APRES):
        _geler(monkeypatch, moment)
        jour = moment.date().isoformat()
        _ecrire(str(isole["marche"]), _marche(moment, jour))
        avant = _lire(str(isole["marche"]))
        market_data._memoire = None
        corps = client.get("/api/market").get_json()
        assert corps["session_date"] == jour
        assert set(corps) == set(json.loads(avant)) | set(corps)
        assert "session_date" in json.loads(avant)
        assert _lire(str(isole["marche"])) == avant


def test_cles_et_types_de_la_reponse_market_inchanges(client, isole, monkeypatch):
    _geler(monkeypatch, SAMEDI)
    brut = _marche(SAMEDI, "2026-10-03")
    _ecrire(str(isole["marche"]), brut)
    market_data._memoire = None
    corps = client.get("/api/market").get_json()
    assert set(corps) == set(brut)
    for cle, valeur in brut.items():
        if cle == "session_date":
            assert type(corps[cle]) is type(valeur)
            continue
        if cle in ("indices", "sector_indices"):
            assert type(corps[cle]) is list
            continue
        assert corps[cle] == valeur


def test_session_date_absente_n_est_pas_ajoutee(client, isole, monkeypatch):
    _geler(monkeypatch, SAMEDI)
    _ecrire(str(isole["marche"]), _marche(SAMEDI, None))
    market_data._memoire = None
    corps = client.get("/api/market").get_json()
    assert "session_date" not in corps


def test_macro_semaine_iso_sans_rewrire_le_fichier(client, isole, monkeypatch):
    _geler(monkeypatch, SAMEDI)
    _ecrire(str(isole["macro"]), {
        "date": "2026-10-03",
        "week": "Semaine 39/2026",
        "BRVM_30": 264.57,
        "BRVM_COMPOSITE": 546.78,
    })
    avant = _lire(str(isole["macro"]))
    corps = client.get("/api/macro").get_json()
    assert corps["date"] == "2026-10-02"
    assert corps["week"] == "Semaine 40/2026"
    assert corps["BRVM_30"] == 264.57
    assert _lire(str(isole["macro"])) == avant

    _geler(monkeypatch, VENDREDI_SEANCE)
    _ecrire(str(isole["macro"]), {
        "date": "2026-10-02",
        "week": "Semaine 39/2026",
        "FCFA_per_USD": 580.49,
    })
    avant = _lire(str(isole["macro"]))
    corps = client.get("/api/macro").get_json()
    assert corps["date"] == "2026-10-02"
    assert corps["week"] == "Semaine 40/2026"
    assert _lire(str(isole["macro"])) == avant

    # Fixture sans clé week (devises) : rien n'est réécrit.
    brut = {"date": "2026-10-03T12:00:00+00:00", "FCFA_per_EUR": 655.957}
    _ecrire(str(isole["macro"]), brut)
    assert client.get("/api/macro").get_json() == brut


def test_historiques_ecrivent_la_meme_date_qu_avant(client, isole, monkeypatch):
    """Jour ouvré : les trois jobs de 18h écrivent la date du jour, comme avant."""
    _geler(monkeypatch, VENDREDI_18H)
    jour = "2026-10-02"
    _ecrire(str(isole["marche"]), _marche(VENDREDI_18H, jour))
    _ecrire(str(isole["cours"]), {
        "updated_at": VENDREDI_18H.isoformat(),
        "session_date": "2026-10-01",
        "prices": {"ALPH": {"price": 1510, "volume": 12, "source": "brvm.org"}},
    })
    _ecrire(str(isole["prix"]), {
        "ALPH": [{"date": "2026-10-01", "price": 1400, "volume": 10, "source": "live"}],
    })
    _ecrire(str(isole["classement"]), {
        "ranking": [{"ticker": "ALPH", "rank": 1, "note": 8.4, "note10": 8.4}],
    })
    avant_marche = _lire(str(isole["marche"]))
    market_data._memoire = None
    assert client.get("/api/market").get_json()["session_date"] == jour
    assert _lire(str(isole["marche"])) == avant_marche

    assert price_history_builder.append_live_prices() == 1
    points = json.loads(isole["prix"].read_text(encoding="utf-8"))["ALPH"]
    assert points[-1]["date"] == jour
    assert all(p["date"] != "2026-10-03" for p in points)

    rank_history_builder.append_daily_top3()
    rangs = json.loads(isole["rangs"].read_text(encoding="utf-8"))
    assert [e["date"] for e in rangs] == [jour]

    resultat = index_history.enregistrer_cloture()
    assert resultat["date"] == jour
    assert resultat["statut"] == "enregistre"
    seances = json.loads(isole["indices"].read_text(encoding="utf-8"))["seances"]
    assert [s["date"] for s in seances] == [jour]
    assert _lire(str(isole["marche"])) == avant_marche


def test_week_end_aucun_point_dans_price_history(isole, monkeypatch):
    _geler(monkeypatch, SAMEDI)
    _ecrire(str(isole["prix"]), {
        "ALPH": [{"date": "2026-10-02", "price": 1510, "volume": 12, "source": "live"}],
    })
    avant = _lire(str(isole["prix"]))
    assert price_history_builder.append_live_prices() == 0
    assert _lire(str(isole["prix"])) == avant
