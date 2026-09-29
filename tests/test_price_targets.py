# -*- coding: utf-8 -*-
"""Caracterisation de features.get_price_targets (comportement actuel).

Les cibles sont lues depuis un live_ranking.json de fixture, jamais depuis /var/data.
"""
import json

import features
from features import get_price_targets


def _pointer_classement(monkeypatch, dossier, payload):
    chemin = dossier / "live_ranking.json"
    chemin.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(features, "DATA_DIR", str(dossier))


def test_cibles_depuis_fixture(monkeypatch, tmp_path, fixtures_dir):
    brut = json.loads((fixtures_dir / "live_ranking.json").read_text(encoding="utf-8"))
    _pointer_classement(monkeypatch, tmp_path, brut)

    cibles = get_price_targets()
    par_ticker = {row["ticker"]: row for row in cibles}

    assert [row["ticker"] for row in cibles] == ["BRAV", "ALPH", "CHER", "EXCP"]
    assert "SANS" not in par_ticker

    # ALPH est en Banque : P/E 9,85 et P/B 1,51, pas le P/E fixe de 10.
    alph = par_ticker["ALPH"]
    assert alph["current_price"] == 10000
    assert alph["score"] == 55.0
    assert alph["epv_target"] == 9850
    assert alph["graham_target"] == 13416
    assert alph["pb_target"] == 12080
    assert alph["avg_target"] == 11782
    assert alph["upside_pct"] == 17.8
    assert alph["n_models"] == 3
    assert alph["target_unreliable"] is False
    assert alph["verdict"] == "Décote modérée"
    assert alph["div_confidence"] == "inconnue"
    assert alph["pe_secteur"] == 9.85
    assert alph["pb_secteur"] == 1.51

    # BRAV a un secteur inconnu (« Industrie ») : médiane de toutes les sociétés.
    brav = par_ticker["BRAV"]
    assert brav["epv_target"] == 14000
    assert brav["graham_target"] == 13416
    assert brav["pb_target"] == 16000
    assert brav["avg_target"] == 14472
    assert brav["upside_pct"] == 189.4
    assert brav["n_models"] == 3
    assert brav["target_unreliable"] is True
    assert brav["verdict"] == "incertain"
    assert brav["pe_secteur"] == 14.0
    assert brav["pb_secteur"] == 2.0

    # Cible loin sous le cours : le libellé suit l'écart, il ne dit pas « proche ».
    cher = par_ticker["CHER"]
    assert cher["epv_target"] == 7000
    assert cher["graham_target"] == 6708
    assert cher["pb_target"] == 8000
    assert cher["avg_target"] == 7236
    assert cher["upside_pct"] == -63.8
    assert cher["target_unreliable"] is False
    assert cher["verdict"] == "Au-dessus du prix cible"
    assert cher["prix_cible"] == cher["avg_target"]
    assert cher["ecart_pct"] == cher["upside_pct"]
    assert cher["libelle_valeur"] == cher["verdict"]

    excp = par_ticker["EXCP"]
    assert excp["epv_target"] == 5600
    assert excp["graham_target"] == 5196
    assert excp["pb_target"] == 6000
    assert excp["avg_target"] is None
    assert excp["upside_pct"] is None
    assert excp["n_models"] == 0
    assert excp["verdict"] == "exceptional_div"
    assert excp["div_is_exceptional"] is True
    assert excp["div_flag"] == "exceptionnel_non_recurrent"


def test_cibles_alias_eps_est_et_book_value(monkeypatch, tmp_path):
    payload = {
        "ranking": [{
            "ticker": "ALIAS",
            "name": "Alias",
            "price": 1000,
            "eps_est": 100,
            "book_value_per_share": 500,
            "roe": 10,
            "composite_adj": 40,
        }]
    }
    _pointer_classement(monkeypatch, tmp_path, payload)
    row = get_price_targets()[0]
    assert row["epv_target"] == 1400
    assert row["graham_target"] == 1061
    assert row["pb_target"] == 1000
    assert row["avg_target"] == 1154
    assert row["upside_pct"] == 15.4
    assert row["verdict"] == "Décote modérée"
    assert row["libelle_valeur"] == "Décote modérée"


def test_cibles_accepte_une_liste_brute(monkeypatch, tmp_path):
    payload = [{
        "ticker": "LIST",
        "name": "Liste",
        "price": 2000,
        "eps": 200,
        "bvpa": 1000,
        "roe": 10,
        "composite_adj": 42,
    }]
    _pointer_classement(monkeypatch, tmp_path, payload)
    rows = get_price_targets()
    assert len(rows) == 1
    assert rows[0]["ticker"] == "LIST"
    assert rows[0]["epv_target"] == 2800


def test_cibles_fichier_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(features, "DATA_DIR", str(tmp_path))
    assert get_price_targets() == []
