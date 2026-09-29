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
    # ROE 15 / médiane banques 14 : la jambe P/B passe de 12 080 à 12 943.
    assert alph["pb_target"] == 12943
    assert alph["avg_target"] == 12070
    assert alph["upside_pct"] == 20.7
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
    # ROE 20 / ROE médian du marché 12 : facteur 20/12, P/B 26 667.
    assert brav["pb_target"] == 26667
    assert brav["avg_target"] == 18028
    assert brav["upside_pct"] == 260.6
    assert brav["n_models"] == 3
    assert brav["target_unreliable"] is True
    assert brav["verdict"] == "incertain"
    assert brav["pe_secteur"] == 14.0
    assert brav["pb_secteur"] == 2.0

    # Cible loin sous le cours : le libellé suit l'écart, il ne dit pas « proche ».
    cher = par_ticker["CHER"]
    assert cher["epv_target"] == 7000
    assert cher["graham_target"] == 6708
    # 6 347 est sous le tiers de 20 000 : « Cible à vérifier », même si
    # l'écart (−68,3 %) ne dépasse pas 80 %.
    assert cher["pb_target"] == 5333
    assert cher["avg_target"] == 6347
    assert cher["upside_pct"] == -68.3
    assert cher["target_unreliable"] is True
    assert cher["verdict"] == "incertain"
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
    # Pas de secteur : P/B 2 et ROE médian 12. ROE 10 → facteur 10/12.
    assert row["pb_target"] == 833
    assert row["avg_target"] == 1098
    assert row["upside_pct"] == 9.8
    assert row["verdict"] == "Proche du prix cible"
    assert row["libelle_valeur"] == "Proche du prix cible"


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
