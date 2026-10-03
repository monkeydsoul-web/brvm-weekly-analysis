# -*- coding: utf-8 -*-
"""CSV du Classement : les valeurs de /api/live-ranking, note /10 et conseil."""
import json

import pytest

import features
import live_ranker


def _ligne(**kwargs):
    base = {
        "ticker": "XXXX",
        "name": "Nom",
        "sector": "Secteur",
        "price": 1000.0,
        "change_pct": 0.0,
        "note10": 5.0,
        "composite_adj": 40.0,
        "conseil_libelle": "Prudence",
        "prix_cible": 1200,
        "libelle_valeur": "Décote modérée",
        "div_yield": 1.5,
    }
    base.update(kwargs)
    return base


@pytest.fixture
def classement(tmp_path, monkeypatch):
    chemin = tmp_path / "live_ranking.json"
    monkeypatch.setattr(live_ranker, "RANKING_PATH", str(chemin))
    monkeypatch.setattr(features, "DATA_DIR", str(tmp_path))
    lignes = [
        _ligne(
            ticker="UNLC", name="Unilever CI", sector="Consommation",
            price=50900.0, change_pct=-1.2, note10=4.1, composite_adj=32.8,
            conseil_libelle=None, prix_cible=930, libelle_valeur="incertain",
            div_yield=0.0,
        ),
        _ligne(
            ticker="SMBC", name="SMB CI", sector="Industriel",
            price=16450.0, change_pct=0.24, note10=8.4, composite_adj=67.0,
            conseil_libelle="Intéressant", prix_cible=25440,
            libelle_valeur="Forte décote", div_yield=4.28,
        ),
        _ligne(
            ticker="SICC", name="SICOR", sector="Industrie",
            price=8400.0, change_pct=0.0, note10=6.1, composite_adj=48.8,
            conseil_libelle=None, prix_cible=856, libelle_valeur="incertain",
        ),
    ]
    payload = {"updated_at": "2026-10-02T18:00:00+00:00", "ranking": lignes}
    chemin.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return chemin, payload


def test_csv_reprend_la_note_dix_et_vide_la_cible_douteuse(classement):
    chemin, payload = classement
    avant = chemin.read_bytes()
    texte = features.export_csv()
    assert chemin.read_bytes() == avant
    assert not texte.startswith("\ufeff")
    assert "\r" not in texte
    lignes = texte.split("\n")
    assert lignes[0] == "ticker,nom,secteur,cours,variation,note /10,conseil,prix cible,rendement"
    assert lignes[1] == "UNLC,Unilever CI,Consommation,50900,-1.2,4.1,,,0"
    assert lignes[2] == "SMBC,SMB CI,Industriel,16450,0.24,8.4,Intéressant,25440,4.28"
    assert lignes[3] == "SICC,SICOR,Industrie,8400,0,6.1,,,1.5"
    assert "67" not in texte
    assert "930" not in texte
    assert "856" not in texte
    # L'API garde le montant. Le fichier n'est pas recalculé.
    assert payload["ranking"][0]["prix_cible"] == 930
    assert payload["ranking"][1]["note10"] == 8.4
    assert payload["ranking"][1]["composite_adj"] == 67.0


def test_route_csv_alignee_sur_live_ranking(classement):
    import app as application
    client = application.app.test_client()
    api = client.get("/api/live-ranking").get_json()
    csv_texte = client.get("/api/export/csv").get_data(as_text=True)
    corps = [l for l in csv_texte.split("\n") if l]
    assert len(corps) == 1 + len(api["ranking"])
    for ligne_csv, ligne_api in zip(corps[1:], api["ranking"]):
        ticker = ligne_csv.split(",")[0]
        assert ticker == ligne_api["ticker"]
        note = ligne_csv.split(",")[5]
        assert note == features._texte_valeur_api(ligne_api["note10"])
        assert note != features._texte_valeur_api(ligne_api["composite_adj"])
    assert api["ranking"][0]["prix_cible"] == 930
    assert ",," in corps[1]
