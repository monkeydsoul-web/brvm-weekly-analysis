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
    calculer_reperes,
    estimer_prix_cible,
    formater_multiple,
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
    """« Proche » seulement si l'écart affiché est entre -10 % et +10 %.

    Banque : P/E 9,85, P/B 1,51, ROE médian 14. Avec un ROE société
    de 14 (facteur 1), BNA 1 000 et BVPA 8 000, la moyenne vaut 11 782.
    """
    base = {"sector": "Banque", "eps": 1000, "bvpa": 8000, "roe": 14}
    cas = [
        ({**base, "price": 8000}, LIBELLE_FORT),
        ({**base, "price": 10000}, LIBELLE_MODERE),
        ({**base, "price": 12000}, LIBELLE_PROCHE),
        ({**base, "price": 20000}, LIBELLE_CHER),
        ({**base, "price": 5000}, "incertain"),
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
        "sector": "Banque", "price": 5000, "eps": 1000, "bvpa": 8000, "roe": 12,
    })
    assert estimation["prix_cible"] > 5000
    assert estimation["ecart_pct"] > 30
    assert estimation["libelle"] != LIBELLE_PROCHE


def test_cible_tres_en_dessous_dit_trop_cher():
    estimation = estimer_prix_cible({
        "sector": "Banque", "price": 20000, "eps": 1000, "bvpa": 8000, "roe": 30,
    })
    # ROE 30 / ROE médian banques 14 = 2,14, sous le plafond de 3.
    assert estimation["facteur_roe"] == 30 / 14
    assert estimation["prix_cible"] == 16384
    assert estimation["ecart_pct"] == -18.1
    assert estimation["libelle"] == LIBELLE_CHER
    assert estimation["pe_secteur"] == 9.85
    assert estimation["pb_secteur"] == 1.51
    assert estimation["roe_secteur"] == 14.0


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
    assert estimation["epv"] == 5600


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
    libelles = Counter()
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
        libelles[estimation["libelle"]] += 1
        if estimation["libelle"] == LIBELLE_PROCHE:
            assert estimation["ecart_pct"] is not None
            assert -10.0 <= estimation["ecart_pct"] <= 10.0
        row["composite_adj"] = scores["composite_adj"]
        lignes.append(row)

    assert comptes["Intéressant"] == 1
    assert comptes["À surveiller"] == 9
    assert comptes["Prudence"] == 35
    assert comptes[None] == 2

    # Libellés sur ce fixture (pas la production).
    # Avant le ROE et la règle des 5 sociétés (P/E et P/B de secteur
    # seuls) : Au-dessus 15, Proche 11, Cible à vérifier 9,
    # sans libellé 9, Forte décote 2, Décote modérée 1.
    assert libelles[LIBELLE_PROCHE] == 14
    assert libelles[LIBELLE_CHER] == 12
    assert libelles[LIBELLE_FORT] == 5
    assert libelles["incertain"] == 7
    assert libelles[None] == 9
    assert libelles[LIBELLE_MODERE] == 0

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


def test_le_roe_ajuste_le_pb_et_pas_le_benefice():
    """Consommation : P/B 2, ROE médian 16. Le P/E 18 ne bouge pas."""
    plancher = estimer_prix_cible({
        "sector": "Consommation", "eps": 1000, "bvpa": 8000, "roe": 4, "price": 10000,
    })
    neutre = estimer_prix_cible({
        "sector": "Consommation", "eps": 1000, "bvpa": 8000, "roe": 16, "price": 10000,
    })
    plafond = estimer_prix_cible({
        "sector": "Consommation", "eps": 1000, "bvpa": 8000, "roe": 79, "price": 10000,
    })
    assert plancher["epv"] == neutre["epv"] == plafond["epv"] == 18000
    assert plancher["pe_secteur"] == 18.0
    assert plancher["facteur_roe"] == 0.5
    assert plancher["pb"] == 8000
    assert neutre["facteur_roe"] == 1.0
    assert neutre["pb"] == 16000
    assert plafond["facteur_roe"] == 3.0
    assert plafond["pb"] == 48000
    assert plafond["roe_secteur"] == 16.0
    sans_roe = estimer_prix_cible({
        "sector": "Consommation", "eps": 1000, "price": 18000,
    })
    assert sans_roe["epv"] == 18000
    assert sans_roe["pb"] is None
    assert sans_roe["facteur_roe"] == 1.0


def test_jambe_pb_citee_pour_un_roe_de_79():
    """Bénéfice 36 468 et P/B 5 119, tels que mesurés sans le ROE.

    BNA 2 026 × P/E 18 = 36 468. Actif net 2 559,5 × P/B 2 = 5 119.
    Avec un ROE de 79 % contre 16 % au milieu de la consommation,
    le facteur est plafonné à 3 et la jambe P/B passe à 15 357.
    Le cours de production n'est pas dans le dépôt : ce test ne
    fige pas le libellé de STBC sur le marché réel.
    """
    avant = round(2559.5 * 2)
    assert avant == 5119
    estimation = estimer_prix_cible({
        "sector": "Consommation", "eps": 2026, "bvpa": 2559.5, "roe": 79, "price": 22000,
    })
    assert estimation["epv"] == 36468
    assert estimation["pb"] == 15357
    assert estimation["facteur_roe"] == 3.0
    faible = estimer_prix_cible({
        "sector": "Consommation", "eps": 100, "bvpa": 1000, "roe": 8.8, "price": 1000,
    })
    assert faible["facteur_roe"] == 8.8 / 16
    assert faible["pb"] == round(1000 * 2 * (8.8 / 16))


def test_reperes_sont_la_mediane_des_historiques():
    table = calculer_reperes(STOCK_FUNDAMENTALS)
    par_nom = {ligne["secteur"]: ligne for ligne in table["secteurs"].values()}
    assert par_nom["Banque"]["n_pe"] == 16
    assert par_nom["Banque"]["pe_observe"] == 9.85
    assert par_nom["Banque"]["pb_observe"] == 1.51
    assert par_nom["Banque"]["roe"] == 14.0
    assert par_nom["Banque"]["utilise_marche"] is False
    assert par_nom["Télécoms"]["pe_observe"] == 12.0
    assert par_nom["Télécoms"]["pb_observe"] == 3.5
    assert par_nom["Télécoms"]["n"] == 3
    assert par_nom["Télécoms"]["utilise_marche"] is True
    assert par_nom["Télécoms"]["pe"] == 14.0
    assert par_nom["Télécoms"]["pb"] == 2.0
    assert par_nom["Consommation"]["pe"] == 18.0
    assert par_nom["Consommation"]["roe"] == 16.0
    assert par_nom["Agriculture"]["pe_observe"] == 15.8
    assert par_nom["Agriculture"]["pb_observe"] == 1.9
    assert par_nom["Agriculture"]["n"] == 4
    assert par_nom["Agriculture"]["pe"] == 14.0
    assert par_nom["Agriculture"]["roe"] == 12.0
    assert par_nom["Énergie"]["pe_observe"] == 12.5
    assert par_nom["Énergie"]["pb_observe"] == 2.75
    assert par_nom["Énergie"]["utilise_marche"] is True
    assert par_nom["Industriel"]["pe"] == 16.0
    assert par_nom["Industriel"]["roe"] == 8.0
    assert par_nom["Utilités"]["pe_observe"] == 14.0
    assert par_nom["Utilités"]["pb_observe"] == 2.25
    assert par_nom["Utilités"]["n_pe"] == 2
    assert par_nom["Utilités"]["pe"] == 14.0
    assert par_nom["Utilités"]["pb"] == 2.0
    assert table["n"] == 47
    assert table["pe_defaut"] == 14.0
    assert table["pb_defaut"] == 2.0
    assert table["roe_defaut"] == 12.0
    assert sum(ligne["n_pe"] for ligne in par_nom.values()) == 47
    for nom in ("Télécoms", "Agriculture", "Énergie", "Utilités"):
        assert par_nom[nom]["utilise_marche"] is True
        assert par_nom[nom]["n"] < 5


def test_telecoms_sans_accent_utilise_le_meme_multiple():
    """Trois télécoms : trop peu, donc la médiane de tout le marché."""
    avec = estimer_prix_cible({"sector": "Télécoms", "eps": 100, "price": 1200})
    sans = estimer_prix_cible({"sector": "Telecoms", "eps": 100, "price": 1200})
    assert avec["epv"] == sans["epv"] == 1400
    assert avec["pe_secteur"] == 14.0
    assert avec["pb_secteur"] == 2.0


def test_cible_sous_le_tiers_du_cours_est_a_verifier():
    """SIVC en production : 653 pour un cours de 2 140, écart d'environ −69 %.

    La règle des 80 % ne voit pas cet écart. Moins du tiers du cours,
    oui. Ici, même situation avec des chiffres de banque et un ROE
    égal à la médiane (facteur 1) : 11 782 pour un cours de 36 000.
    """
    trop_bas = estimer_prix_cible({
        "sector": "Banque", "eps": 1000, "bvpa": 8000, "roe": 14, "price": 36000,
    })
    assert trop_bas["prix_cible"] == 11782
    assert trop_bas["ecart_pct"] == -67.3
    assert abs(trop_bas["ecart_pct"]) < 80
    assert trop_bas["prix_cible"] * 3 < 36000
    assert trop_bas["libelle"] == "incertain"
    encore_cher = estimer_prix_cible({
        "sector": "Banque", "eps": 1000, "bvpa": 8000, "roe": 14, "price": 35000,
    })
    assert encore_cher["ecart_pct"] == -66.3
    assert encore_cher["libelle"] == LIBELLE_CHER
    assert encore_cher["incertain"] is False


def test_methodo_affiche_les_multiples_et_protege_la_note():
    page = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    debut = page.index('id="methodo-prix-cible"')
    fin = page.index("Fréquences de mise à jour", debut)
    bloc = page[debut:fin]
    assert "n'entre pas dans la note" in bloc
    assert "ne change pas le conseil" in bloc
    assert "toujours 10" in bloc
    table = calculer_reperes(STOCK_FUNDAMENTALS)
    for ligne in table["secteurs"].values():
        assert ligne["secteur"] in bloc
        assert (formater_multiple(ligne["pe"]) + "×") in bloc
        assert (formater_multiple(ligne["pb"]) + "×") in bloc
        assert str(ligne["n_pe"]) in bloc
    assert "P/E 14×" in bloc
    assert "P/B 2×" in bloc
    assert "moins de 5" in bloc
    assert "0,5 et 3" in bloc
    assert "moins du tiers" in bloc
    assert "3 fois le cours" in bloc
    assert "Cible à vérifier" in bloc
