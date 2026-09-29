# -*- coding: utf-8 -*-
"""TECH-1 : la note reste figee en seance, le cours live continue.

Aucun reseau, aucune ecriture sous /var/data. Le classement de test
tient dans tmp_path.
"""
import json
from datetime import datetime, timezone

import pytest

import live_ranker
from live_ranker import (
    NOTE_FORMULE,
    EmpreinteIllisible,
    compute_live_ranking,
    empreinte_faits as empreinte_reelle,
)


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


def _ecrire_faits(dossier, boc):
    chemins = []
    for nom, contenu in (
        ("boc_data.json", boc),
        ("analyses_summary.json", {"ALPH": {"verdict": "POSITIF", "analyzed_at": "2026-09-01T00:00:00+00:00"}}),
        ("external_dividends.json", {"ALPH": {"amount": 100, "paid_date": "2026-06-01", "scraped_at": "2026-09-01T19:00:00"}}),
    ):
        chemin = dossier / nom
        chemin.write_text(json.dumps(contenu), encoding="utf-8")
        chemins.append(str(chemin))
    return tuple(chemins)


def _brancher_faits(monkeypatch, chemins):
    monkeypatch.setattr(live_ranker, "empreinte_faits", empreinte_reelle)
    monkeypatch.setattr(live_ranker, "chemins_faits", lambda: chemins)


def test_empreinte_reelle_ignore_une_reecriture_identique(tmp_path):
    chemins = _ecrire_faits(tmp_path, {"last_update": "lundi", "ALPH": {"div_net": 12, "per_boc": 8}})
    avant = empreinte_reelle(chemins)
    boc, analyses, dividendes = (tmp_path / nom for nom in (
        "boc_data.json", "analyses_summary.json", "external_dividends.json",
    ))
    boc.write_text(json.dumps({"ALPH": {"per_boc": 8, "div_net": 12}, "last_update": "samedi"}), encoding="utf-8")
    brut_a = json.loads(analyses.read_text(encoding="utf-8"))
    brut_a["ALPH"]["analyzed_at"] = "2026-10-03T19:05:00+00:00"
    analyses.write_text(json.dumps(brut_a), encoding="utf-8")
    brut_d = json.loads(dividendes.read_text(encoding="utf-8"))
    brut_d["ALPH"]["scraped_at"] = "2026-10-03T19:05:00"
    dividendes.write_text(json.dumps(brut_d), encoding="utf-8")
    assert empreinte_reelle(chemins) == avant
    brut_b = json.loads(boc.read_text(encoding="utf-8"))
    brut_b["ALPH"]["div_net"] = 40
    boc.write_text(json.dumps(brut_b), encoding="utf-8")
    assert empreinte_reelle(chemins) != avant


def test_empreinte_reelle_fichier_coupé(tmp_path):
    chemins = _ecrire_faits(tmp_path, {"ALPH": {"div_net": 12}})
    (tmp_path / "boc_data.json").write_text("{", encoding="utf-8")
    with pytest.raises(EmpreinteIllisible):
        empreinte_reelle(chemins)


def test_reecriture_identique_ne_recalcule_pas_un_vrai_changement_oui(classement, tmp_path, monkeypatch):
    chemins = _ecrire_faits(tmp_path, {"last_update": "2026-09-28T19:00:00", "ALPH": {"div_net": 12}})
    _brancher_faits(monkeypatch, chemins)
    empreinte = empreinte_reelle(chemins)
    _ecrire(classement["chemin"], faits_empreinte=empreinte)
    classement["etat"]["cache"] = _prix(5000, 8.0, 90000, trend="top")

    boc = tmp_path / "boc_data.json"
    brut = json.loads(boc.read_text(encoding="utf-8"))
    brut["last_update"] = "2026-10-03T19:00:00"
    boc.write_text(json.dumps(brut), encoding="utf-8")
    calme = compute_live_ranking(trigger="scheduler", moment=SEANCE)
    assert calme["note_recalculee"] is False
    assert calme["faits_empreinte"] == empreinte
    assert _ligne(calme)["composite_adj"] == 3.3

    vu = {}

    def faux(row):
        vu["price"] = row.get("price")
        return {"composite_adj": 48.0, "composite_raw": 40.0, "score_technique": 4.0}

    monkeypatch.setattr(live_ranker, "_compute_scores", faux)
    brut["ALPH"]["div_net"] = 80
    boc.write_text(json.dumps(brut), encoding="utf-8")
    nouveau = compute_live_ranking(trigger="scheduler", moment=SEANCE)
    assert nouveau["note_recalculee"] is True
    assert nouveau["faits_empreinte"] == empreinte_reelle(chemins)
    assert nouveau["faits_empreinte"] != empreinte
    assert vu["price"] == 1000
    assert _ligne(nouveau)["price"] == 5000


def test_fichier_illisible_garde_l_empreinte_precedente(classement, tmp_path, monkeypatch):
    chemins = _ecrire_faits(tmp_path, {"last_update": "2026-09-28T19:00:00", "ALPH": {"div_net": 12}})
    _brancher_faits(monkeypatch, chemins)
    empreinte = empreinte_reelle(chemins)
    _ecrire(classement["chemin"], faits_empreinte=empreinte)
    (tmp_path / "boc_data.json").write_text("{", encoding="utf-8")
    classe = _prix(1100, 1.0, 3000, trend=None)
    classement["etat"]["cache"] = classe
    rate = compute_live_ranking(trigger="scheduler", moment=APRES_CLOTURE)
    assert rate["note_recalculee"] is False
    assert rate["faits_empreinte"] == empreinte
    assert _ligne(rate)["composite_adj"] == 3.3

    (tmp_path / "boc_data.json").write_text(
        json.dumps({"last_update": "2026-09-29T19:00:00", "ALPH": {"div_net": 99}}),
        encoding="utf-8",
    )
    repris = compute_live_ranking(trigger="scheduler", moment=APRES_CLOTURE)
    assert repris["note_recalculee"] is True
    assert repris["faits_empreinte"] == empreinte_reelle(chemins)
    assert repris["faits_empreinte"] != empreinte


def test_redemarrage_sans_classement_prend_la_derniere_cloture(classement, monkeypatch):
    vu = {}

    def faux(row):
        vu["price"] = row.get("price")
        vu["change_pct"] = row.get("change_pct")
        vu["volume"] = row.get("volume")
        return {"composite_adj": 42.0, "composite_raw": 40.0, "score_technique": 4.0}

    monkeypatch.setattr(live_ranker, "_compute_scores", faux)
    assert not classement["chemin"].exists()
    classement["hist"]["ALPH"][-1]["price"] = 1234
    classement["etat"]["cache"] = _prix(1800, 5.0, 99999, trend="top")
    resultat = compute_live_ranking(trigger="startup", moment=SEANCE)
    assert resultat["note_recalculee"] is True
    assert vu["price"] == 1234
    assert vu["change_pct"] == 0
    assert vu["volume"] == 0
    assert _ligne(resultat)["price"] == 1800
    assert _ligne(resultat)["composite_adj"] == 42.0


def test_sans_historique_en_seance_la_societe_reste_non_notee(classement, monkeypatch):
    vu = {}

    def faux(row):
        vu["price"] = row.get("price")
        return {"composite_adj": 12.0, "composite_raw": 10.0, "score_technique": 5.0}

    monkeypatch.setattr(live_ranker, "_compute_scores", faux)
    classement["hist"]["ALPH"] = []
    classement["etat"]["cache"] = _prix(1800, 5.0, 99999, trend="top")
    resultat = compute_live_ranking(trigger="startup", moment=SEANCE)
    assert vu["price"] is None
    ligne = _ligne(resultat)
    assert ligne["price"] == 1800
    assert ligne["statut"] == "non_note"
    assert ligne["conseil"] is None


def test_ligne_en_erreur_est_recalculee(classement):
    _ecrire(classement["chemin"])
    donnees = json.loads(classement["chemin"].read_text(encoding="utf-8"))
    donnees["ranking"][0]["composite_adj"] = 0
    donnees["ranking"][0]["error"] = "scoring casse"
    classement["chemin"].write_text(json.dumps(donnees), encoding="utf-8")
    classement["etat"]["cache"] = _prix(1500, 2.0, 1000, trend="top")
    resultat = compute_live_ranking(trigger="scheduler", moment=SEANCE)
    ligne = _ligne(resultat)
    assert "error" not in ligne
    assert ligne["composite_adj"] != 0
    assert ligne["note_calculee_le"] == SEANCE.isoformat()
    assert ligne["price"] == 1500
    assert resultat["faits_empreinte"] == "fixe"
