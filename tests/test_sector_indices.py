# -*- coding: utf-8 -*-
"""SECTIDX-1 : /api/sector-indices sert la meme source et le meme cache que /api/market.

Plus de lecture de sector_indices.json, pas de second calcul, pas de champ
« sector », session_date de la source, 503 si la source est absente.
?force=true reste inchange (mission FORCE-1).
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ["BRVM_DISABLE_SCHEDULER"] = "1"

import market_data

PRINCIPAUX = (
    ("BRVM - COMPOSITE", 541.20, 546.78),
    ("BRVM - 30", 262.10, 264.95),
    ("BRVM - PRESTIGE", 214.00, 215.31),
    ("BRVM - PRINCIPAL", 330.40, 333.02),
)
SECTEURS = (
    ("CONSOMMATION DE BASE", 300.10, 301.50),
    ("CONSOMMATION DISCRETIONNAIRE", 150.00, 149.20),
    ("ENERGIE", 410.00, 412.30),
    ("INDUSTRIELS", 222.90, 219.19),
    ("SERVICES FINANCIERS", 246.00, 247.54),
    ("SERVICES PUBLICS", 900.00, 905.10),
    ("TELECOMMUNICATIONS", 280.00, 281.40),
)


def _ligne(nom, prev, cours, ytd_colonne):
    return {"name": nom, "prev": prev, "current": cours, "change": round((cours / prev - 1) * 100, 2), "ytd": ytd_colonne}


def charge(maintenant, age_s=10, session_date="2026-10-02"):
    """Cache /api/market tel que market_data l'ecrit. ytd = colonne figee de brvm.org (1,7)."""
    data = {
        "updated_at": (maintenant - timedelta(seconds=age_s)).isoformat(),
        "market_activity": {},
        "top5": [],
        "flop5": [],
        "indices": [_ligne(n, p, c, 1.7) for n, p, c in PRINCIPAUX],
        "sector_indices": [_ligne(n, p, c, 0.5) for n, p, c in SECTEURS],
        "total_return": {},
    }
    if session_date is not None:
        data["session_date"] = session_date
    return data


def ancien_fichier():
    """sector_indices.json comme en prod : 11/05, Composite 405,75, mauvais rattachement."""
    chemin = os.path.join(market_data.DATA_DIR, "sector_indices.json")
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump({"updated_at": "2026-05-11T16:15:15", "indices": {
            "COMPOSITE": {"current": 405.75, "change": 0.1, "ytd": 1.7, "sector": "COMPOSITE"},
            "CONSOMMATION DISCRETIONNAIRE": {"current": 120.0, "change": 0.0, "ytd": 1.0, "sector": "Industriel"},
        }}, f)
    return chemin


@pytest.fixture
def md(monkeypatch):
    for nom, val in (("_memoire", None), ("_en_cours", False), ("_dernier_essai", 0.0), ("_dernier_fil", None), ("_references_2025", None)):
        setattr(market_data, nom, val)
    if os.path.exists(market_data.CACHE_PATH):
        os.remove(market_data.CACHE_PATH)
    maintenant = datetime(2026, 10, 2, 16, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(market_data, "_maintenant", lambda: maintenant)
    monkeypatch.setattr(market_data, "fetch_market_data", lambda: (_ for _ in ()).throw(RuntimeError("pas de reseau en test")))
    ancien = ancien_fichier()
    market_data.maintenant = maintenant
    yield market_data
    fil = market_data._dernier_fil
    if fil is not None and fil.is_alive():
        fil.join(3)
    for nom, val in (("_memoire", None), ("_en_cours", False), ("_dernier_essai", 0.0), ("_dernier_fil", None), ("_references_2025", None)):
        setattr(market_data, nom, val)
    for chemin in (market_data.CACHE_PATH, ancien):
        if os.path.exists(chemin):
            os.remove(chemin)


@pytest.fixture
def client():
    import app as application
    return application.app.test_client()


def _sans_nom(item):
    return {k: v for k, v in item.items() if k != "name"}


def test_valeurs_et_date_identiques_a_api_market(md, client):
    md._ecrire(charge(md.maintenant))
    md._memoire = None
    marche = client.get("/api/market").get_json()
    r = client.get("/api/sector-indices")
    assert r.status_code == 200
    secteurs = r.get_json()
    assert set(secteurs) == {"indices", "updated_at", "session_date"}
    attendus = marche["indices"] + marche["sector_indices"]
    assert len(attendus) == 11
    assert sorted(secteurs["indices"]) == sorted(x["name"] for x in attendus)
    for item in attendus:
        assert secteurs["indices"][item["name"]] == _sans_nom(item)
    assert secteurs["session_date"] == marche["session_date"] == "2026-10-02"
    assert secteurs["updated_at"] == marche["updated_at"]
    # YTD : celui de /api/market (cloture du 31/12/2025) pour les 4 principaux, null pour les 7 secteurs.
    for nom, _p, _c in PRINCIPAUX:
        assert secteurs["indices"][nom]["ytd"] is not None
        assert secteurs["indices"][nom]["ytd"] != 1.7
    for nom, _p, _c in SECTEURS:
        assert secteurs["indices"][nom]["ytd"] is None
    # Pas de champ « sector », rien de l'ancien fichier.
    assert all("sector" not in v for v in secteurs["indices"].values())
    assert "COMPOSITE" not in secteurs["indices"]
    assert secteurs["indices"]["BRVM - COMPOSITE"]["current"] == 546.78


def test_valeur_perimee_servie_avec_sa_propre_date(md, client):
    md._ecrire(charge(md.maintenant, age_s=3 * 86400, session_date="2026-09-29"))
    md._memoire = None
    marche = client.get("/api/market").get_json()
    secteurs = client.get("/api/sector-indices").get_json()
    assert secteurs["session_date"] == marche["session_date"] == "2026-09-29"
    assert secteurs["updated_at"] == marche["updated_at"]
    assert secteurs["indices"]["BRVM - COMPOSITE"]["current"] == 546.78


def test_session_date_absente_de_la_source_reste_absente(md, client):
    md._ecrire(charge(md.maintenant, session_date=None))
    md._memoire = None
    marche = client.get("/api/market").get_json()
    secteurs = client.get("/api/sector-indices").get_json()
    assert "session_date" not in marche
    assert secteurs["session_date"] is None


def test_source_absente_503_sans_ancien_fichier(md, client, caplog):
    caplog.set_level(logging.WARNING, logger="app")
    r = client.get("/api/sector-indices")
    assert r.status_code == 503
    corps = r.get_json()
    assert set(corps) == {"error"}
    assert "405.75" not in r.get_data(as_text=True)
    assert any(m.startswith("SECTIDX-1: source marche absente") for m in caplog.messages)


def test_source_illisible_503(md, client, caplog, monkeypatch):
    monkeypatch.setattr(md, "get_market_data", lambda *a, **k: (_ for _ in ()).throw(ValueError("cache corrompu")))
    caplog.set_level(logging.WARNING, logger="app")
    r = client.get("/api/sector-indices")
    assert r.status_code == 503
    assert set(r.get_json()) == {"error"}
    assert any("SECTIDX-1: source marche illisible" in m and "cache corrompu" in m for m in caplog.messages)


def test_force_true_inchange(md, client, monkeypatch):
    """?force=true appelle toujours scrape_sector_indices et renvoie son resultat tel quel (FORCE-1)."""
    import brvm_data_scraper
    appels = []

    def scrape():
        appels.append(1)
        return {"COMPOSITE": {"current": 1.0, "change": 0.0, "ytd": 0.0, "sector": "COMPOSITE"}}

    monkeypatch.setattr(brvm_data_scraper, "scrape_sector_indices", scrape)
    md._ecrire(charge(md.maintenant))
    md._memoire = None
    corps = client.get("/api/sector-indices?force=true").get_json()
    assert appels == [1]
    assert corps == {"COMPOSITE": {"current": 1.0, "change": 0.0, "ytd": 0.0, "sector": "COMPOSITE"}}
