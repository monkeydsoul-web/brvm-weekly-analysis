# -*- coding: utf-8 -*-
"""TECH-1 : la note reste figee en seance, le cours live continue.

Aucun reseau, aucune ecriture sous /var/data. Le classement de test
tient dans tmp_path.
"""
import json
from datetime import datetime, timezone

import pytest

import live_ranker
from live_ranker import NOTE_FORMULE, compute_live_ranking


SEANCE = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
APRES_CLOTURE = datetime(2026, 9, 29, 15, 35, tzinfo=timezone.utc)
SAMEDI = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
NOTE_VEILLE = "2026-09-28T16:00:00+00:00"

FOND = {
    "ALPH": {
        "name": "Emetteur Alpha",
        "sector": "Banque",
        "country": "Côte d'Ivoire",
        "shares": 1000,
        "pe_hist": 8.0,
        "pb_hist": 1.2,
        "roe": 20,
        "div_hist": 100,
        "debt": "Faible",
        "stable": True,
    },
}


def _prix(prix, change, volume, trend="top"):
    return {
        "updated_at": "2026-09-29T10:00:00+00:00",
        "market_open": True,
        "prices": {
            "ALPH": {
                "price": prix,
                "open": prix - 10,
                "change_pct": change,
                "volume": volume,
                "trend": trend,
                "source": "brvm.org",
            },
        },
    }


def _historique():
    return {
        "ALPH": [
            {"date": "2026-08-%02d" % (i + 1), "price": 1000, "volume": 2000}
            for i in range(20)
        ],
    }


@pytest.fixture
def classement(tmp_path, monkeypatch):
    chemin = tmp_path / "live_ranking.json"
    historique = tmp_path / "ranking_history.json"
    monkeypatch.setattr(live_ranker, "RANKING_PATH", str(chemin))
    monkeypatch.setattr(live_ranker, "HISTORY_PATH", str(historique))
    monkeypatch.setattr(live_ranker, "_last_prices", {})
    monkeypatch.setattr(live_ranker, "_last_ranking", None)
    monkeypatch.setattr("scraper.STOCK_FUNDAMENTALS", FOND)
    monkeypatch.setattr(live_ranker, "empreinte_faits", lambda chemins=None: "fixe")
    monkeypatch.setattr(live_ranker, "get_reference_prices", lambda ttl=300: {})
    hist = _historique()
    monkeypatch.setattr(
        "price_history_builder.load_history", lambda: hist,
    )

    etat = {"cache": _prix(1000, 0, 0, trend=None)}

    def lire(force_refresh=False):
        return etat["cache"]

    monkeypatch.setattr("live_data.get_live_data", lire)
    return {"chemin": chemin, "etat": etat, "hist": hist}


def _ecrire(chemin, **extra):
    payload = {
        "updated_at": NOTE_VEILLE,
        "note_calculee_le": NOTE_VEILLE,
        "note_formule": NOTE_FORMULE,
        "faits_empreinte": "fixe",
        "trigger": "fixture",
        "market_open": False,
        "ranking": [{
            "ticker": "ALPH",
            "name": "Emetteur Alpha",
            "composite_adj": 3.3,
            "composite_raw": 3.0,
            "note10": 0.4,
            "conseil": "Prudence",
            "conseil_libelle": "Prudence",
            "conseil_couleur": "rouge",
            "statut": "cote",
            "score_technique": 9.9,
            "detail_technique": "note figee de test",
            "note_calculee_le": NOTE_VEILLE,
            "price": 1000,
        }],
    }
    payload.update(extra)
    chemin.write_text(json.dumps(payload), encoding="utf-8")


def _ligne(payload):
    return payload["ranking"][0]


def test_prix_live_bouge_note_figee_en_seance(classement):
    _ecrire(classement["chemin"])
    classement["etat"]["cache"] = _prix(1500, 6.0, 80000, trend="top")
    resultat = compute_live_ranking(trigger="scheduler", moment=SEANCE)
    ligne = _ligne(resultat)
    assert resultat["note_recalculee"] is False
    assert ligne["price"] == 1500
    assert ligne["change_pct"] == 6.0
    assert ligne["volume"] == 80000
    assert ligne["trend"] == "top"
    assert ligne["composite_adj"] == 3.3
    assert ligne["note10"] == 0.4
    assert ligne["conseil"] == "Prudence"
    assert ligne["score_technique"] == 9.9
    assert ligne["note_calculee_le"] == NOTE_VEILLE
    assert resultat["note_calculee_le"] == NOTE_VEILLE
    assert resultat["updated_at"] != NOTE_VEILLE


def test_redemarrage_en_seance_garde_la_note(classement):
    _ecrire(classement["chemin"])
    classement["etat"]["cache"] = _prix(1510, 1.0, 10)
    resultat = compute_live_ranking(trigger="startup", moment=SEANCE)
    ligne = _ligne(resultat)
    assert resultat["note_recalculee"] is False
    assert ligne["composite_adj"] == 3.3
    assert ligne["conseil"] == "Prudence"
    assert ligne["note_calculee_le"] == NOTE_VEILLE
    assert ligne["price"] == 1510


def test_note_recalculee_apres_la_cloture(classement):
    _ecrire(classement["chemin"])
    classement["etat"]["cache"] = _prix(1100, 1.0, 3000, trend=None)
    resultat = compute_live_ranking(trigger="scheduler", moment=APRES_CLOTURE)
    ligne = _ligne(resultat)
    assert resultat["note_recalculee"] is True
    assert ligne["composite_adj"] != 3.3
    assert ligne["score_technique"] != 9.9
    assert ligne["note_calculee_le"] == APRES_CLOTURE.isoformat()
    assert ligne["price"] == 1100
    assert resultat["note_formule"] == NOTE_FORMULE


def test_deuxieme_passage_apres_cloture_ne_recalcule_pas(classement):
    _ecrire(classement["chemin"])
    classement["etat"]["cache"] = _prix(1100, 1.0, 3000, trend=None)
    premier = compute_live_ranking(trigger="scheduler", moment=APRES_CLOTURE)
    note = _ligne(premier)["composite_adj"]
    conseil = _ligne(premier)["conseil"]
    classement["etat"]["cache"] = _prix(1105, 0.4, 100, trend=None)
    second = compute_live_ranking(trigger="scheduler", moment=APRES_CLOTURE.replace(minute=40))
    assert second["note_recalculee"] is False
    assert _ligne(second)["composite_adj"] == note
    assert _ligne(second)["conseil"] == conseil
    assert _ligne(second)["note_calculee_le"] == APRES_CLOTURE.isoformat()
    assert _ligne(second)["price"] == 1105


def test_fait_nouveau_recalcule_sur_la_cloture_pas_le_tick(classement, monkeypatch):
    vu = {}

    def faux(row):
        vu["price"] = row.get("price")
        vu["change_pct"] = row.get("change_pct")
        vu["volume"] = row.get("volume")
        vu["trend"] = row.get("trend")
        return {
            "composite_adj": 48.0,
            "composite_raw": 40.0,
            "score_technique": 4.0,
        }

    monkeypatch.setattr(live_ranker, "_compute_scores", faux)
    _ecrire(classement["chemin"])
    classement["etat"]["cache"] = _prix(5000, 8.0, 90000, trend="top")
    monkeypatch.setattr(live_ranker, "empreinte_faits", lambda chemins=None: "boc-neuf")
    resultat = compute_live_ranking(trigger="scheduler", moment=SEANCE)
    assert resultat["note_recalculee"] is True
    assert vu["price"] == 1000
    assert vu["change_pct"] == 0
    assert vu["volume"] == 0
    assert not vu["trend"]
    assert _ligne(resultat)["price"] == 5000
    assert _ligne(resultat)["composite_adj"] == 48.0
    assert _ligne(resultat)["note_calculee_le"] == SEANCE.isoformat()


def test_hysteresis_appliquee_au_recalcul(classement, monkeypatch):
    def faux(row):
        return {"composite_adj": 57.6, "composite_raw": 50.0, "score_technique": 1.0}

    monkeypatch.setattr(live_ranker, "_compute_scores", faux)
    _ecrire(classement["chemin"])
    # Le fichier fige disait Prudence ; 57,6 sans amortisseur serait
    # À surveiller (7,2/10). Avec le precedent Intéressant, on reste dessus.
    payload = json.loads(classement["chemin"].read_text(encoding="utf-8"))
    payload["ranking"][0]["conseil"] = "Intéressant"
    payload["ranking"][0]["conseil_libelle"] = "Intéressant"
    classement["chemin"].write_text(json.dumps(payload), encoding="utf-8")
    resultat = compute_live_ranking(trigger="scheduler", moment=APRES_CLOTURE)
    assert _ligne(resultat)["composite_adj"] == 57.6
    assert _ligne(resultat)["note10"] == 7.2
    assert _ligne(resultat)["conseil"] == "Intéressant"


def test_week_end_ne_recalcule_pas(classement):
    vendredi_soir = "2026-10-02T16:00:00+00:00"
    _ecrire(
        classement["chemin"],
        note_calculee_le=vendredi_soir,
        updated_at=vendredi_soir,
    )
    donnees = json.loads(classement["chemin"].read_text(encoding="utf-8"))
    donnees["ranking"][0]["note_calculee_le"] = vendredi_soir
    classement["chemin"].write_text(json.dumps(donnees), encoding="utf-8")
    classement["etat"]["cache"] = _prix(1400, 0, 0, trend=None)
    resultat = compute_live_ranking(trigger="scheduler", moment=SAMEDI)
    assert resultat["note_recalculee"] is False
    assert resultat["market_open"] is False
    assert _ligne(resultat)["composite_adj"] == 3.3
    assert _ligne(resultat)["note_calculee_le"] == vendredi_soir
    assert _ligne(resultat)["price"] == 1400


def test_premiere_formule_hors_seance_recalcule(classement):
    """Premier deploiement apres la cloture : la nouvelle formule s'applique une fois."""
    _ecrire(classement["chemin"], note_formule=None)
    classement["etat"]["cache"] = _prix(1100, 0.5, 2000, trend=None)
    resultat = compute_live_ranking(trigger="startup", moment=APRES_CLOTURE)
    assert resultat["note_recalculee"] is True
    assert resultat["note_formule"] == NOTE_FORMULE
    assert _ligne(resultat)["composite_adj"] != 3.3
    assert _ligne(resultat)["note_calculee_le"] == APRES_CLOTURE.isoformat()


def test_premiere_formule_en_seance_garde_l_ancienne_note(classement):
    """Premier deploiement en seance : pas de note intraday toute neuve."""
    _ecrire(classement["chemin"], note_formule=None, faits_empreinte=None)
    classement["etat"]["cache"] = _prix(1800, 4.0, 1000, trend="top")
    resultat = compute_live_ranking(trigger="startup", moment=SEANCE)
    assert resultat["note_recalculee"] is False
    assert _ligne(resultat)["composite_adj"] == 3.3
    assert _ligne(resultat)["score_technique"] == 9.9
    assert resultat["note_formule"] != NOTE_FORMULE
