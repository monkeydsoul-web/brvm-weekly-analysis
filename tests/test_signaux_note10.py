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
    assert "Conseil Intéressant (≥ 7,5)" in texte
    assert "Prévisions favorables :" in texte
    assert "Prévisions neutres :" in texte
    assert "Prévisions défavorables :" in texte
    assert "À surveiller" not in texte
    assert "Prudence" not in texte
