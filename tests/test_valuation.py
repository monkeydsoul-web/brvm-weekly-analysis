# -*- coding: utf-8 -*-
"""Caracterisation des 7 modeles de valuation.py (comportement actuel)."""
import pandas as pd

from valuation import (
    score_buffett,
    score_dcf,
    score_ddm,
    score_epv,
    score_graham,
    score_relative,
    score_reverse_dcf,
    compute_all_scores,
    tier_label,
)

# Ligne fictive : banque stable, Cote d'Ivoire, ratios bas.
ROW = {
    "ticker": "ALPH",
    "name": "Emetteur Alpha",
    "sector": "Banque",
    "country": "Côte d'Ivoire",
    "price": 10000,
    "change_pct": 1.5,
    "pe_ref": 8.0,
    "pb_ref": 1.2,
    "roe": 20,
    "div_per_share": 800,
    "div_yield": 8.0,
    "debt_level": "Faible",
    "earnings_stable": True,
    "market_cap_xof": 500000000000,
}

# Ligne fictive : industriel, Burkina Faso, pas de dividende.
FAIB = {
    "ticker": "FAIB",
    "name": "Emetteur Faible",
    "sector": "Industriel",
    "country": "Burkina Faso",
    "price": 5000,
    "pe_ref": 40.0,
    "pb_ref": 4.0,
    "roe": 5,
    "div_per_share": 0,
    "div_yield": 0,
    "debt_level": "Élevée",
    "earnings_stable": False,
}


def test_sept_modeles_libelles():
    fonctions = [
        score_graham, score_dcf, score_ddm, score_epv,
        score_buffett, score_reverse_dcf, score_relative,
    ]
    assert [fn(ROW)["label"] for fn in fonctions] == [
        "Graham", "DCF/FCF", "DDM", "EPV", "Buffett", "Rev.DCF", "Relatif",
    ]


def test_graham_banque_stable():
    assert score_graham(ROW)["score"] == 9.0


def test_graham_dette_synonymes():
    assert score_graham(dict(ROW, debt_level="low"))["score"] == 9.0
    assert score_graham(dict(ROW, debt_level="faible"))["score"] == 9.0
    assert score_graham(dict(ROW, debt_level="medium"))["score"] == 8.3
    assert score_graham(dict(ROW, debt_level="Modérée"))["score"] == 8.3
    assert score_graham(dict(ROW, debt_level="high"))["score"] == 8.0
    assert score_graham(dict(ROW, debt_level="Élevée"))["score"] == 8.0


def test_graham_sans_donnees():
    assert score_graham({})["score"] == 0.0


def test_graham_faible():
    assert score_graham(FAIB)["score"] == 0.0


def test_dcf_banque_et_faible():
    assert score_dcf(ROW)["score"] == 7.0
    assert score_dcf(FAIB)["score"] == 0.0


def test_ddm_banque():
    assert score_ddm(ROW)["score"] == 9.0


def test_ddm_sans_dividende():
    resultat = score_ddm({"price": 10000, "div_per_share": 0, "div_yield": 5})
    assert resultat["score"] == 0.0
    assert resultat["label"] == "DDM"
    assert "non applicable" in resultat["details"]


def test_epv_banque():
    assert score_epv(ROW)["score"] == 8.5


def test_epv_donnees_insuffisantes():
    assert score_epv({"pe_ref": 8}) == {
        "score": 0.0, "label": "EPV", "details": "Données insuffisantes",
    }
    assert score_epv({"price": 1000, "pe_ref": 0})["score"] == 0.0


def test_epv_faible():
    assert score_epv(FAIB)["score"] == 0.5


def test_buffett_plafond_dix():
    # La somme depassee 10 (ROE, moat, dividende, dette, P/E) est bornee.
    assert score_buffett(ROW)["score"] == 10.0


def test_buffett_faible():
    assert score_buffett(FAIB)["score"] == 0.0


def test_reverse_dcf_banque_et_faible():
    assert score_reverse_dcf(ROW)["score"] == 10.0
    assert score_reverse_dcf(FAIB)["score"] == 0.5


def test_reverse_dcf_donnees_insuffisantes():
    assert score_reverse_dcf({})["score"] == 0.0
    assert score_reverse_dcf({})["details"] == "Données insuffisantes"


def test_relatif_banque_et_faible():
    assert score_relative(ROW)["score"] == 6.5
    assert score_relative(FAIB)["score"] == 0.0


def test_compute_all_scores_composite_geo_et_rang():
    niger = dict(ROW, ticker="NGER", country="Niger")
    df = pd.DataFrame([FAIB, niger, ROW])
    out = compute_all_scores(df)
    par_ticker = {row["ticker"]: row for _, row in out.iterrows()}

    assert par_ticker["ALPH"]["composite_raw"] == 60.0
    assert par_ticker["ALPH"]["geo_penalty"] == 0
    assert par_ticker["ALPH"]["composite_adj"] == 60.0

    # Niger : -2.0 * 7/10 = -1.4, ramene sur le composite /70.
    assert par_ticker["NGER"]["geo_penalty"] == -2.0
    assert par_ticker["NGER"]["composite_adj"] == 58.6

    # Burkina : -1.5 * 7/10, plancher a 0.
    assert par_ticker["FAIB"]["composite_raw"] == 1.0
    assert par_ticker["FAIB"]["geo_penalty"] == -1.5
    assert par_ticker["FAIB"]["composite_adj"] == 0.0

    assert list(out["ticker"]) == ["ALPH", "NGER", "FAIB"]
    assert list(out["rank"]) == [1, 2, 3]


def test_tier_label_seuils():
    assert tier_label(50) == "★★★ FORT"
    assert tier_label(49.9) == "★★ MODÉRÉ"
    assert tier_label(35) == "★★ MODÉRÉ"
    assert tier_label(34.9) == "★ FAIBLE"
    assert tier_label(20) == "★ FAIBLE"
    assert tier_label(19.9) == "✗ ÉVITER"
    assert tier_label(0) == "✗ ÉVITER"
