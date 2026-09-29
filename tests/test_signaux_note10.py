# -*- coding: utf-8 -*-
"""Page Signaux et PDF mensuel : note sur 10, virgule, trois libelles.

Les codes internes ACHETER / CONSERVER / ALLÉGER / ÉVITER restent.
Le champ score reste le composite. Seul le texte affiche change.
"""
import io
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _scores():
    return [
        {
            "ticker": "HAUT", "name": "Haut", "sector": "Banque",
            "composite_adj": 80, "div_yield": 6, "pe_ref": 8, "price": 1000,
            "statut": "cote",
            "score_graham": 8, "score_dcf": 8, "score_ddm": 8,
            "score_epv": 8, "score_buffett": 8,
        },
        {
            "ticker": "MID", "name": "Milieu", "sector": "Banque",
            "composite_adj": 54, "div_yield": 5, "pe_ref": 12, "price": 1000,
            "statut": "cote",
        },
        {
            "ticker": "BAS", "name": "Bas", "sector": "Banque",
            "composite_adj": 40, "div_yield": 5, "pe_ref": 12, "price": 1000,
            "statut": "cote",
        },
        {
            "ticker": "FAIBLE", "name": "Faible", "sector": "Banque",
            "composite_adj": 7, "div_yield": 5, "pe_ref": 12, "price": 1000,
            "statut": "cote",
        },
    ]


def test_source_sans_slash_80_visible():
    src = (ROOT / "backtest_previsionnel.py").read_text(encoding="utf-8")
    assert "/80" not in src
    assert " / 80" in src


def test_raisons_note10_virgule_et_libelles():
    import backtest_previsionnel as bp
    sigs = bp.compute_signals(_scores(), {})
    by = dict((s["ticker"], s) for s in sigs)
    assert by["HAUT"]["signal"] == "ACHETER"
    assert by["HAUT"]["score"] == 80
    assert "Prévision favorable" in by["HAUT"]["raison"]
    assert "10,0/10" in by["HAUT"]["raison"]
    assert by["MID"]["signal"] == "CONSERVER"
    assert by["MID"]["score"] == 54
    assert "Prévision neutre" in by["MID"]["raison"]
    assert "6,8/10" in by["MID"]["raison"]
    assert by["BAS"]["signal"] == "ALLÉGER"
    assert "Prévision défavorable" in by["BAS"]["raison"]
    assert "5,0/10" in by["BAS"]["raison"]
    assert by["FAIBLE"]["signal"] == "ÉVITER"
    assert "Prévision défavorable" in by["FAIBLE"]["raison"]
    assert "0,9/10" in by["FAIBLE"]["raison"]
    for s in sigs:
        assert "/80" not in s["raison"]
        assert "ACHAT" not in s["raison"]
        assert "Intéressant" not in s["raison"]
        assert "À surveiller" not in s["raison"]
        assert "Prudence" not in s["raison"]


def test_pdf_mensuel_note10_et_trois_libelles():
    pytest.importorskip("reportlab")
    import backtest_previsionnel as bp
    from pypdf import PdfReader
    pdf = bp.generate_rapport_pdf(_scores(), {})
    texte = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    assert "/80" not in texte
    assert "Score/80" not in texte
    assert "ACHAT" not in texte
    assert "10,0" in texte
    assert "Conseil Intéressant" in texte
    assert "(≥ 7,5)" not in texte
    assert "Une société déjà Intéressante le reste dès 7,2/10." in texte
    assert "Prévisions favorables :" in texte
    assert "Prévisions neutres :" in texte
    assert "Prévisions défavorables :" in texte
    assert "À surveiller" not in texte
    assert "Prudence" not in texte


def test_pdf_compte_le_conseil_reel_avec_amortisseur():
    """ETIT reste Intéressant à 7,3 : le PDF ne compte pas le seuil brut 7,5."""
    pytest.importorskip("reportlab")
    import backtest_previsionnel as bp
    from pypdf import PdfReader
    from verdict import note10

    etit = {
        "ticker": "ETIT", "name": "Ecobank", "sector": "Banque",
        "composite_adj": 58.4, "note10": 7.3,
        "conseil": "Intéressant", "conseil_libelle": "Intéressant",
        "statut": "cote", "div_yield": 5, "pe_ref": 8, "price": 20,
    }
    assert note10(etit["composite_adj"]) == 7.3
    assert note10(etit["composite_adj"]) < 7.5
    scores = [
        {
            "ticker": "HAUT", "name": "Haut", "sector": "Banque",
            "composite_adj": 64, "note10": 8.0,
            "conseil": "Intéressant", "conseil_libelle": "Intéressant",
            "statut": "cote", "div_yield": 5, "pe_ref": 8, "price": 1000,
        },
        {
            "ticker": "MID", "name": "Milieu", "sector": "Banque",
            "composite_adj": 60, "note10": 7.5,
            "conseil": "Intéressant", "conseil_libelle": "Intéressant",
            "statut": "cote", "div_yield": 5, "pe_ref": 8, "price": 1000,
        },
        etit,
        {
            "ticker": "BAS", "name": "Bas", "sector": "Banque",
            "composite_adj": 58.4, "note10": 7.3,
            "conseil": "À surveiller", "conseil_libelle": "À surveiller",
            "statut": "cote", "div_yield": 5, "pe_ref": 8, "price": 1000,
        },
        {
            "ticker": "FAIBLE", "name": "Faible", "sector": "Banque",
            "composite_adj": 30, "note10": 3.8,
            "conseil": "Prudence", "conseil_libelle": "Prudence",
            "statut": "cote", "div_yield": 5, "pe_ref": 8, "price": 1000,
        },
    ]
    assert bp._libelle_conseil_ligne(etit) == "Intéressant"
    assert sum(
        1 for s in scores if bp._libelle_conseil_ligne(s) == "Intéressant"
    ) == 3
    assert sum(
        1 for s in scores if (note10(s["composite_adj"]) or 0) >= 7.5
    ) == 2
    pdf = bp.generate_rapport_pdf(scores, {})
    texte = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    assert "Conseil Intéressant" in texte
    assert "(≥ 7,5)" not in texte
    assert "Une société déjà Intéressante le reste dès 7,2/10." in texte
    assert "Conseil Intéressant 3" in texte.replace("\n", " ")
