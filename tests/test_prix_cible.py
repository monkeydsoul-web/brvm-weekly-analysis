# -*- coding: utf-8 -*-
"""PR-07 : le prix cible, l'écart et le libellé sortent du même calcul.

Mesure sur tests/fixtures/bna_univers.json. Les cours de production
ne sont pas dans le dépôt.
"""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pytest

import live_ranker
from features import get_price_targets
from live_ranker import _build_enriched_row, _compute_scores, _poser_prix_cible
from prix_cible import (
    LIBELLE_CHER,
    LIBELLE_FORT,
    LIBELLE_MODERE,
    LIBELLE_PROCHE,
    estimer_prix_cible,
)
from scraper import STOCK_FUNDAMENTALS


SEANCE = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def cours_live_non_filtre(monkeypatch):
    monkeypatch.setattr(live_ranker, "get_reference_prices", lambda ttl=300: {})


def _ligne(base, prix, pdf, boc, ticker):
    return _build_enriched_row(
        ticker,
        base,
        {"price": prix, "change_pct": 0, "volume": 0},
        pdf,
        boc_snapshot={ticker: boc} if boc else {},
        moment=SEANCE,
    )


def _univers():
    return json.loads((ROOT / "tests" / "fixtures" / "bna_univers.json").read_text(encoding="utf-8"))


def test_libelle_colle_a_lecart_affiche():
    """« Proche » seulement si l'écart affiché est entre -10 % et +10 %."""
    cas = [
        ({"price": 1000, "eps": 180, "bvpa": 700, "roe": 18}, LIBELLE_FORT),
        ({"price": 10000, "eps": 1000, "bvpa": 8000, "roe": 15}, LIBELLE_MODERE),
        ({"price": 11805, "eps": 1000, "bvpa": 8000, "roe": 15}, LIBELLE_PROCHE),
        ({"price": 20000, "eps": 500, "bvpa": 4000, "roe": 8}, LIBELLE_CHER),
        ({"price": 5000, "eps": 1000, "bvpa": 8000, "roe": 20}, "incertain"),
        ({"price": 8000}, None),
    ]
    for ligne, attendu in cas:
        estimation = estimer_prix_cible(ligne)
        assert estimation["libelle"] == attendu
        ecart = estimation["ecart_pct"]
        if estimation["libelle"] == LIBELLE_PROCHE:
            assert ecart is not None
            assert -10.0 <= ecart <= 10.0
        if ecart is not None and abs(ecart) > 10 and not estimation["incertain"]:
            assert estimation["libelle"] != LIBELLE_PROCHE
        assert estimation["prix_cible"] == estimation["prix_cible"]
        if estimation["prix_cible"] and ligne.get("price"):
            brut = round((estimation["prix_cible"] / float(ligne["price"]) - 1) * 100, 1)
            assert estimation["ecart_pct"] == brut


def test_cible_tres_au_dessus_n_est_pas_proche():
    """Un prix cible très au-dessus du cours ne peut pas dire « proche »."""
    estimation = estimer_prix_cible({
        "price": 5000, "eps": 1000, "bvpa": 8000, "roe": 12,
    })
    assert estimation["prix_cible"] > 5000
    assert estimation["ecart_pct"] > 30
    assert estimation["libelle"] != LIBELLE_PROCHE


def test_cible_tres_en_dessous_dit_trop_cher():
    estimation = estimer_prix_cible({
        "price": 20000, "eps": 500, "bvpa": 4000, "roe": 8,
    })
    assert estimation["prix_cible"] == 4969
    assert estimation["ecart_pct"] == -75.2
    assert estimation["libelle"] == LIBELLE_CHER


def test_sans_donnees_ne_dit_pas_proche():
    estimation = estimer_prix_cible({"price": 5000, "roe": 10})
    assert estimation["prix_cible"] is None
    assert estimation["ecart_pct"] is None
    assert estimation["libelle"] is None


def test_dividende_exceptionnel_sans_prix():
    estimation = estimer_prix_cible({
        "price": 8000, "eps": 400, "bvpa": 3000, "roe": 12,
        "div_is_exceptional": True,
    })
    assert estimation["prix_cible"] is None
    assert estimation["ecart_pct"] is None
    assert estimation["libelle"] == "exceptional_div"
    assert estimation["epv"] == 4000


def test_estimer_ne_change_ni_la_ligne_ni_le_conseil():
    ligne = {
        "price": 12000, "eps": 1000, "bvpa": 5000, "roe": 18,
        "conseil": "Prudence", "composite_adj": 36.0, "note10": 4.5,
    }
    avant = dict(ligne)
    estimation = estimer_prix_cible(ligne)
    assert ligne == avant
    assert "conseil" not in estimation
    assert "composite_adj" not in estimation


def test_poser_prix_cible_laisse_le_conseil(fixtures_dir):
    univers = _univers()
    ticker = "SGBC"
    row = _ligne(
        STOCK_FUNDAMENTALS[ticker],
        univers["prix"][ticker],
        univers["pdf"].get(ticker),
        univers["boc"].get(ticker),
        ticker,
    )
    row["ticker"] = ticker
    scores = _compute_scores(row)
    avant = (scores["conseil"], scores["composite_adj"], scores["note10"])
    resultat = dict(scores)
    _poser_prix_cible(resultat, row)
    assert (scores["conseil"], scores["composite_adj"], scores["note10"]) == avant
    assert resultat["conseil"] == avant[0]
    assert resultat["prix_cible"] == estimer_prix_cible(row)["prix_cible"]
    assert resultat["ecart_pct"] == estimer_prix_cible(row)["ecart_pct"]
    assert resultat["libelle_valeur"] == estimer_prix_cible(row)["libelle"]


def test_univers_conseils_inchanges_et_libelles_coherents(monkeypatch, tmp_path):
    """Les 47 sociétés du fixture. Pas les données de production.

    Sur ce fixture : 1 Intéressant, 9 À surveiller, 35 Prudence,
    2 sans conseil (suspendues). Le décompte de production
    (3 / 13 / 29 + 2) n'est pas reproductible ici.
    """
    univers = _univers()
    lignes = []
    comptes = Counter()
    for ticker, base in STOCK_FUNDAMENTALS.items():
        row = _ligne(
            base,
            univers["prix"][ticker],
            univers["pdf"].get(ticker),
            univers["boc"].get(ticker),
            ticker,
        )
        row["ticker"] = ticker
        row["name"] = base.get("name", "")
        scores = _compute_scores(row)
        avant = (scores["conseil"], scores["composite_adj"], scores["note10"])
        estimation = estimer_prix_cible(row)
        scores_apres = _compute_scores(row)
        assert (scores_apres["conseil"], scores_apres["composite_adj"], scores_apres["note10"]) == avant
        comptes[avant[0]] += 1
        if estimation["libelle"] == LIBELLE_PROCHE:
            assert estimation["ecart_pct"] is not None
            assert -10.0 <= estimation["ecart_pct"] <= 10.0
        row["composite_adj"] = scores["composite_adj"]
        lignes.append(row)

    assert comptes["Intéressant"] == 1
    assert comptes["À surveiller"] == 9
    assert comptes["Prudence"] == 35
    assert comptes[None] == 2

    monkeypatch.setattr("features.DATA_DIR", str(tmp_path))
    (tmp_path / "live_ranking.json").write_text(
        json.dumps({"ranking": lignes}, default=str),
        encoding="utf-8",
    )
    for cible in get_price_targets():
        source = next(x for x in lignes if x["ticker"] == cible["ticker"])
        estimation = estimer_prix_cible(source)
        assert cible["avg_target"] == estimation["prix_cible"]
        assert cible["upside_pct"] == estimation["ecart_pct"]
        assert cible["verdict"] == estimation["libelle"]
        assert cible["prix_cible"] == estimation["prix_cible"]
        assert cible["libelle_valeur"] == estimation["libelle"]


def test_les_pages_ne_recalculent_plus_graham_ou_epv():
    screener = (ROOT / "dashboard" / "screener.js").read_text(encoding="utf-8")
    alertes = (ROOT / "dashboard" / "alerts.js").read_text(encoding="utf-8")
    assert "22.5" not in screener
    assert "0.10" not in screener
    assert "prix_cible" in screener
    assert "libelle_valeur" in screener
    assert "22.5" not in alertes
    assert "eps / 0.10" not in alertes
    assert "libelle_valeur === 'Au-dessus du prix cible'" in alertes
    assert "Trop cher" not in alertes
    assert "Bonne affaire" not in alertes
    page = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    bloc = page[page.index("function fmtLibelleValeur"):page.index("async function renderTargets")]
    assert "Forte décote" in bloc
    assert "Décote modérée" in bloc
    assert "Proche du prix cible" in bloc
    assert "Au-dessus du prix cible" in bloc
    assert "Cible à vérifier" in bloc
    for mot in ("Bonne affaire", "Trop cher", "À surveiller"):
        assert mot not in bloc
        assert mot not in (ROOT / "prix_cible.py").read_text(encoding="utf-8")
    assert "function fmtLibelleValeur" in page
    assert "fmtLibelleValeur(t.verdict)" in page
    assert "fmtLibelleValeur(s.libelle_valeur)" in page
