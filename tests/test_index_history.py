# -*- coding: utf-8 -*-
"""Clôture des indices : une séance, pas de week-end, plages de lecture."""
import json
import os
from datetime import date, datetime, timezone

import pytest

import index_history

MARDI_18H = datetime(2026, 9, 29, 18, 10, tzinfo=timezone.utc)
MARDI_15H29 = datetime(2026, 9, 29, 15, 29, tzinfo=timezone.utc)
MARDI_15H30 = datetime(2026, 9, 29, 15, 30, tzinfo=timezone.utc)
SAMEDI = datetime(2026, 9, 26, 18, 10, tzinfo=timezone.utc)
DIMANCHE = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def historique(tmp_path, monkeypatch):
    chemin = tmp_path / "index_history.json"
    monkeypatch.setattr(index_history, "HISTORY_PATH", str(chemin))
    index_history.invalider_cache()
    yield chemin
    index_history.invalider_cache()


def _marche(updated="2026-09-29T18:05:00+00:00", courant=245.2):
    return {
        "updated_at": updated,
        "indices": [
            {"name": "BRVM - COMPOSITE", "prev": 244.0, "current": courant, "change": 0.4},
            {"name": "BRVM - 30", "prev": 140.0, "current": 140.2, "change": 0.1},
            {"name": "BRVM – PRESTIGE", "prev": 154.0, "current": 155.0, "change": 0.6},
            {"name": "BRVM - PRINCIPAL", "prev": 128.0, "current": 128.5, "change": 0.3},
        ],
    }


def _cours(prix=1510, volume=12, updated="2026-09-29T15:25:00+00:00"):
    return {
        "updated_at": updated,
        "prices": {"ALPH": {"price": prix, "volume": volume}},
    }


def _hist(prix=1500, volume=10, jour="2026-09-28"):
    return {
        "ALPH": [{"date": jour, "price": prix, "volume": volume, "source": "live"}],
    }


def _classement(note_snts=7.3):
    return {
        "ranking": [
            {
                "ticker": "beta",
                "rank": 2,
                "note10": 5.5,
                "composite_adj": 44.0,
                "conseil": "ATTENDRE",
                "prix_cible": 900,
            },
            {
                "ticker": "SNTS",
                "rank": 1,
                "note10": note_snts,
                "composite_adj": 58.4,
                "conseil": "INTERESSANT",
                "prix_cible": 18000,
            },
            {"ticker": "SANS", "composite_adj": 10, "note10": 1.0},
        ],
    }


def _enregistrer(moment=MARDI_18H, **kwargs):
    params = {
        "marche": _marche(),
        "cours": _cours(),
        "historique_prix": _hist(),
        "classement": _classement(),
    }
    params.update(kwargs)
    return index_history.enregistrer_cloture(moment=moment, **params)


def _lire(chemin):
    return json.loads(chemin.read_text(encoding="utf-8"))


def test_enregistre_la_cloture_et_le_rang_sans_recalculer(historique, monkeypatch):
    def interdit(*_a, **_k):
        raise AssertionError("calcul interdit")

    monkeypatch.setattr("verdict.note10", interdit)
    monkeypatch.setattr("live_ranker.compute_live_ranking", interdit)

    resultat = _enregistrer()
    assert resultat == {"statut": "enregistre", "date": "2026-09-29"}
    seance = _lire(historique)["seances"]
    assert len(seance) == 1
    assert seance[0]["date"] == "2026-09-29"
    assert seance[0]["indices"] == {
        "BRVM-C": 245.2,
        "BRVM-30": 140.2,
        "Prestige": 155.0,
        "Principal": 128.5,
    }
    assert seance[0]["societes"] == [
        {"ticker": "SNTS", "rang": 1, "note": 7.3},
        {"ticker": "BETA", "rang": 2, "note": 5.5},
    ]
    brut = historique.read_text(encoding="utf-8")
    assert "conseil" not in brut
    assert "composite_adj" not in brut
    assert "prix_cible" not in brut


def test_idempotent_ne_reesit_pas_et_ne_change_pas_la_cloture(historique):
    assert _enregistrer()["statut"] == "enregistre"
    inode = os.stat(historique).st_ino
    contenu = historique.read_text(encoding="utf-8")

    second = _enregistrer(
        marche=_marche(courant=999.9),
        classement=_classement(note_snts=1.0),
    )
    assert second == {"statut": "deja_enregistre", "date": "2026-09-29"}
    assert os.stat(historique).st_ino == inode
    assert historique.read_text(encoding="utf-8") == contenu
    assert _lire(historique)["seances"][0]["indices"]["BRVM-C"] == 245.2
    assert _lire(historique)["seances"][0]["societes"][0]["note"] == 7.3
    assert [s["date"] for s in _lire(historique)["seances"]] == ["2026-09-29"]


def test_complete_les_societes_sans_toucher_aux_indices(historique):
    assert _enregistrer(classement={"ranking": []})["statut"] == "enregistre"
    assert _lire(historique)["seances"][0]["societes"] == []
    assert _enregistrer()["statut"] == "societes_completees"
    seance = _lire(historique)["seances"]
    assert len(seance) == 1
    assert seance[0]["indices"]["BRVM-C"] == 245.2
    assert seance[0]["societes"][0]["ticker"] == "SNTS"
    assert _enregistrer(classement=_classement(note_snts=9.9))["statut"] == "deja_enregistre"
    assert _lire(historique)["seances"][0]["societes"][0]["note"] == 7.3


def test_week_end_n_ecrit_rien(historique):
    assert _enregistrer(moment=SAMEDI) == {"statut": "week-end", "date": "2026-09-26"}
    assert _enregistrer(moment=DIMANCHE) == {"statut": "week-end", "date": "2026-09-27"}
    assert not historique.exists()


def test_avant_15h30_n_ecrit_rien(historique):
    assert _enregistrer(moment=MARDI_15H29) == {"statut": "avant_cloture", "date": "2026-09-29"}
    assert not historique.exists()


def test_15h30_est_la_cloture(historique):
    resultat = _enregistrer(
        moment=MARDI_15H30,
        marche=_marche(updated="2026-09-29T15:30:00+00:00"),
    )
    assert resultat["statut"] == "enregistre"
    assert _lire(historique)["seances"][0]["date"] == "2026-09-29"


def test_jour_sans_seance_si_cours_et_volumes_identiques(historique):
    resultat = _enregistrer(cours=_cours(prix=1500, volume=10))
    assert resultat == {"statut": "sans_seance", "date": "2026-09-29"}
    assert not historique.exists()


def test_volume_different_compte_comme_une_seance(historique):
    resultat = _enregistrer(cours=_cours(prix=1500, volume=12))
    assert resultat["statut"] == "enregistre"


def test_cache_cours_d_un_autre_jour_nest_pas_une_seance(historique):
    resultat = _enregistrer(cours=_cours(updated="2026-09-28T15:25:00+00:00"))
    assert resultat["statut"] == "sans_seance"
    assert not historique.exists()


def test_cache_marche_avant_la_cloture_nest_pas_enregistre(historique):
    resultat = _enregistrer(marche=_marche(updated="2026-09-29T15:29:00+00:00"))
    assert resultat == {"statut": "marche_perime", "date": "2026-09-29"}
    assert not historique.exists()


def test_fichier_illisible_n_est_pas_ecrase(historique):
    historique.write_text("{", encoding="utf-8")
    assert _enregistrer()["statut"] == "fichier_illisible"
    assert historique.read_text(encoding="utf-8") == "{"


def test_remplacement_rate_garde_l_ancien_fichier(historique, monkeypatch):
    assert _enregistrer()["statut"] == "enregistre"
    avant = historique.read_text(encoding="utf-8")

    def casse(_src, _dst):
        raise OSError("disque plein")

    monkeypatch.setattr(index_history.os, "replace", casse)
    with pytest.raises(OSError):
        _enregistrer(moment=datetime(2026, 9, 30, 18, 10, tzinfo=timezone.utc),
                     marche=_marche(updated="2026-09-30T18:05:00+00:00"),
                     cours=_cours(updated="2026-09-30T15:25:00+00:00"))
    assert historique.read_text(encoding="utf-8") == avant
    assert [p.name for p in historique.parent.iterdir()] == ["index_history.json"]


def test_lit_le_cache_qui_alimente_api_market(historique, tmp_path, monkeypatch):
    import market_data
    cache = tmp_path / "market_cache.json"
    cache.write_text(json.dumps(_marche()), encoding="utf-8")
    monkeypatch.setattr(market_data, "CACHE_PATH", str(cache))
    resultat = index_history.enregistrer_cloture(
        moment=MARDI_18H,
        cours=_cours(),
        historique_prix=_hist(),
        classement=_classement(),
    )
    assert resultat["statut"] == "enregistre"
    assert _lire(historique)["seances"][0]["indices"]["Principal"] == 128.5


def test_indice_partiel_n_invente_pas_le_manquant(historique):
    marche = _marche()
    marche["indices"] = [i for i in marche["indices"] if "PRINCIPAL" not in i["name"].upper()]
    assert _enregistrer(marche=marche)["statut"] == "enregistre"
    indices = _lire(historique)["seances"][0]["indices"]
    assert "Principal" not in indices
    assert indices["BRVM-C"] == 245.2


def test_valeur_indice_borne_et_arrondie():
    assert index_history.valeur_indice(200.126) == 200.13
    assert index_history.valeur_indice(50) == 50.0
    assert index_history.valeur_indice(5000) == 5000.0
    assert index_history.valeur_indice(49.99) is None
    assert index_history.valeur_indice(100000) is None
    assert index_history.valeur_indice(True) is None
    assert index_history.valeur_indice(float("nan")) is None


def test_noms_d_indices():
    assert index_history.code_indice("BRVM-COMPOSITE") == "BRVM-C"
    assert index_history.code_indice("BRVM 30") == "BRVM-30"
    assert index_history.code_indice("BRVM – PRESTIGE") == "Prestige"
    assert index_history.code_indice("Indice Principal") == "Principal"
    assert index_history.code_indice("BRVM INDUSTRIE") is None


def _serie():
    valeurs = {
        "2025-09-29": 100,
        "2025-09-30": 101,
        "2025-12-31": 102,
        "2026-01-01": 103,
        "2026-08-29": 104,
        "2026-08-30": 105,
        "2026-09-23": 106,
        "2026-09-24": 107,
        "2026-09-30": 108,
        "2026-10-01": 109,
    }
    seances = []
    for jour, valeur in valeurs.items():
        seances.append({
            "date": jour,
            "indices": {"BRVM-C": valeur, "Prestige": valeur + 1000},
            "societes": [{"ticker": "SNTS", "rang": 1, "note": 7.3}],
        })
    return {"seances": seances}


@pytest.fixture
def client(historique):
    historique.write_text(json.dumps(_serie()), encoding="utf-8")
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    import app as application
    application_client = application.app.test_client()
    return application_client


def _points(client, plage, index="BRVM-C"):
    reponse = client.get("/api/index-history?index=%s&range=%s" % (index, plage))
    assert reponse.status_code == 200
    corps = reponse.get_json()
    assert set(corps) == {"index", "range", "points"}
    assert "societes" not in json.dumps(corps)
    assert reponse.headers.get("Cache-Control") == "public, max-age=300"
    return corps


def test_plages(client, monkeypatch):
    monkeypatch.setattr(index_history, "_aujourdhui", lambda: date(2026, 9, 30))
    assert _points(client, "1S") == {
        "index": "BRVM-C",
        "range": "1S",
        "points": [["2026-09-24", 107], ["2026-09-30", 108]],
    }
    assert _points(client, "1M")["points"] == [
        ["2026-08-30", 105],
        ["2026-09-23", 106],
        ["2026-09-24", 107],
        ["2026-09-30", 108],
    ]
    assert _points(client, "YTD")["points"] == [
        ["2026-01-01", 103],
        ["2026-08-29", 104],
        ["2026-08-30", 105],
        ["2026-09-23", 106],
        ["2026-09-24", 107],
        ["2026-09-30", 108],
    ]
    assert _points(client, "1A")["points"] == [
        ["2025-09-30", 101],
        ["2025-12-31", 102],
        ["2026-01-01", 103],
        ["2026-08-29", 104],
        ["2026-08-30", 105],
        ["2026-09-23", 106],
        ["2026-09-24", 107],
        ["2026-09-30", 108],
    ]
    prestige = _points(client, "1S", index="Prestige")
    assert prestige["index"] == "Prestige"
    assert prestige["points"] == [["2026-09-24", 1107], ["2026-09-30", 1108]]


def test_plage_vide_et_alias(client, monkeypatch):
    monkeypatch.setattr(index_history, "_aujourdhui", lambda: date(2026, 9, 30))
    principal = client.get("/api/index-history?index=Principal&range=1A")
    assert principal.status_code == 200
    assert principal.get_json()["points"] == []
    alias = client.get("/api/index-history?index=brvm-composite&range=1S")
    assert alias.get_json()["index"] == "BRVM-C"
    assert alias.get_json()["points"][0] == ["2026-09-24", 107]


def test_index_ou_range_inconnu(client):
    inconnu = client.get("/api/index-history?index=CAC40&range=1S")
    assert inconnu.status_code == 400
    assert inconnu.headers.get("Cache-Control") == "no-store"
    assert inconnu.get_json()["index"] == ["BRVM-C", "BRVM-30", "Prestige", "Principal"]
    plage = client.get("/api/index-history?index=BRVM-C&range=5A")
    assert plage.status_code == 400
    assert plage.get_json()["range"] == ["1S", "1M", "YTD", "1A"]


def test_get_fichier_absent_ne_le_cree_pas(tmp_path, monkeypatch):
    chemin = tmp_path / "index_history.json"
    monkeypatch.setattr(index_history, "HISTORY_PATH", str(chemin))
    index_history.invalider_cache()
    monkeypatch.setattr(index_history, "_aujourdhui", lambda: date(2026, 9, 30))
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    import app as application
    reponse = application.app.test_client().get("/api/index-history?index=BRVM-C&range=1A")
    assert reponse.status_code == 200
    assert reponse.get_json()["points"] == []
    assert not chemin.exists()


def test_cache_memoire_voit_une_reecriture(client, historique, monkeypatch):
    monkeypatch.setattr(index_history, "_aujourdhui", lambda: date(2026, 9, 30))
    assert _points(client, "1S")["points"][-1] == ["2026-09-30", 108]
    data = _lire(historique)
    for seance in data["seances"]:
        if seance["date"] == "2026-09-30":
            seance["indices"]["BRVM-C"] = 111
    tmp = historique.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(str(tmp), str(historique))
    assert _points(client, "1S")["points"][-1] == ["2026-09-30", 111]


def test_doublon_deja_present_ne_sert_que_la_premiere_valeur(client, historique, monkeypatch):
    monkeypatch.setattr(index_history, "_aujourdhui", lambda: date(2026, 9, 30))
    data = _lire(historique)
    data["seances"].append({
        "date": "2026-09-30",
        "indices": {"BRVM-C": 999},
        "societes": [],
    })
    historique.write_text(json.dumps(data), encoding="utf-8")
    index_history.invalider_cache()
    points = _points(client, "1S")["points"]
    assert points.count(["2026-09-30", 108]) == 1
    assert ["2026-09-30", 999] not in points


def test_bornes_de_calendrier():
    assert index_history.debut_plage(date(2026, 9, 30), "1S") == date(2026, 9, 24)
    assert index_history.debut_plage(date(2026, 9, 30), "1M") == date(2026, 8, 30)
    assert index_history.debut_plage(date(2026, 3, 31), "1M") == date(2026, 2, 28)
    assert index_history.debut_plage(date(2026, 9, 30), "YTD") == date(2026, 1, 1)
    assert index_history.debut_plage(date(2026, 9, 30), "1A") == date(2025, 9, 30)
    assert index_history._decaler_annees(date(2024, 2, 29), -1) == date(2023, 2, 28)


def test_job_n_appelle_pas_le_marche_avant_la_cloture(monkeypatch):
    import auto_scheduler

    monkeypatch.setattr(index_history, "pret_pour_cloture", lambda moment=None: False)

    def interdit(*_a, **_k):
        raise AssertionError("marche rafraichi hors cloture")

    monkeypatch.setattr("market_data.get_market_data", interdit)
    auto_scheduler.job_index_history()


def test_job_rafraichit_puis_enregistre(monkeypatch):
    import auto_scheduler

    ordre = []
    monkeypatch.setattr(index_history, "pret_pour_cloture", lambda moment=None: True)

    def marche(force_refresh=False):
        ordre.append(("marche", force_refresh))
        return {}

    def enregistre():
        ordre.append("enregistre")
        return {"statut": "enregistre", "date": "2026-09-29"}

    monkeypatch.setattr("market_data.get_market_data", marche)
    monkeypatch.setattr(index_history, "enregistrer_cloture", enregistre)
    auto_scheduler.job_index_history()
    assert ordre == [("marche", True), "enregistre"]


def test_cron_18h10_lun_ven():
    import inspect
    import auto_scheduler
    source = inspect.getsource(auto_scheduler.start_scheduler)
    assert "index_history" in source
    assert "day_of_week='mon-fri'" in source
    assert "hour=18, minute=10" in source
