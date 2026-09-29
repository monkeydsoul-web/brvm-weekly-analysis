# -*- coding: utf-8 -*-
"""BNA-1 : le bénéfice par action ne suit plus le cours de la séance.

Le BNA vient du rapport, sinon du BOC (cours de clôture du jour du BOC / PER),
sinon d'un chiffre statique. Le P/E, lui, vaut cours actuel / BNA.
"""
import json
from datetime import datetime, timezone

import pytest

import live_ranker
from features import get_price_targets
from live_ranker import (
    NOTE_FORMULE,
    _build_enriched_row,
    _compute_scores,
    compute_live_ranking,
)
from scraper import STOCK_FUNDAMENTALS
from valuation import score_epv


SEANCE = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
APRES_NOTE_DU_JOUR = datetime(2026, 9, 29, 16, 0, tzinfo=timezone.utc)
SAMEDI = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
NOTE_VEILLE = "2026-09-28T16:00:00+00:00"
NOTE_DEJA_DU_JOUR = "2026-09-29T15:35:00+00:00"
ANCIENNE_FORMULE = "cloture-v1"


@pytest.fixture(autouse=True)
def cours_live_non_filtre(monkeypatch):
    """Pas de référence historique : le cours passé au test reste le cours utilisé."""
    monkeypatch.setattr(live_ranker, "get_reference_prices", lambda ttl=300: {})


def _cas(fixtures_dir):
    return json.loads((fixtures_dir / "bna_cas.json").read_text(encoding="utf-8"))


def _univers(fixtures_dir):
    return json.loads((fixtures_dir / "bna_univers.json").read_text(encoding="utf-8"))


def _ligne(base, prix, pdf, boc, ticker="TEST", moment=SEANCE):
    return _build_enriched_row(
        ticker,
        base,
        {"price": prix, "change_pct": 0, "volume": 0},
        pdf,
        boc_snapshot={ticker: boc} if boc else {},
        moment=moment,
    )


def _proche(produit, prix):
    return abs(produit - prix) / prix <= 0.01


def test_bna_identique_si_seul_le_cours_change(fixtures_dir):
    cas = _cas(fixtures_dir)
    bas = _ligne(cas["base"], 12000, cas["rapport_2024"], cas["boc"])
    haut = _ligne(cas["base"], 15000, cas["rapport_2024"], cas["boc"])

    assert bas["bna"] == haut["bna"] == 1000.0
    assert bas["eps"] == haut["eps"] == 1000.0
    assert bas["bvpa"] == haut["bvpa"] == 5000.0
    assert bas["bna_source"] == haut["bna_source"] == "rapport"
    assert bas["bna_exercice"] == 2025
    assert bas["bna_date"] is None
    assert bas["bna_ecart_boc"] == round(1000.0 / 900.0, 2)
    assert bas["bvpa_source"] == "rapport"
    assert bas["pe_ref"] != haut["pe_ref"]
    assert _proche(bas["pe_ref"] * bas["bna"], 12000)
    assert _proche(haut["pe_ref"] * haut["bna"], 15000)
    assert _proche(bas["pb_ref"] * bas["bvpa"], 12000)
    assert _proche(haut["pb_ref"] * haut["bvpa"], 15000)


def test_bna_boc_ne_suit_pas_le_cours(fixtures_dir):
    """Sans rapport, le BNA reste cours de clôture du BOC / PER."""
    cas = _cas(fixtures_dir)
    bas = _ligne(cas["base"], 12000, None, cas["boc"])
    haut = _ligne(cas["base"], 15000, None, cas["boc"])
    assert bas["bna"] == haut["bna"] == 900.0
    assert bas["bna_source"] == "boc"
    assert bas["bna_date"] == "2026-09-25"
    assert bas["bna_exercice"] is None
    assert bas["bna_ecart_boc"] is None
    assert bas["bvpa"] is None
    assert bas["bvpa_source"] is None
    assert _proche(bas["pe_ref"] * bas["bna"], 12000)
    assert _proche(haut["pe_ref"] * haut["bna"], 15000)


def test_bna_change_avec_un_nouveau_boc(fixtures_dir):
    cas = _cas(fixtures_dir)
    avant = _ligne(cas["base"], 12000, None, cas["boc"])
    apres = _ligne(cas["base"], 12000, None, cas["boc_nouveau"])
    assert avant["bna"] == 900.0
    assert apres["bna"] == 1100.0
    assert apres["bna_source"] == "boc"
    assert apres["bna_date"] == "2026-09-26"
    assert avant["bna"] != apres["bna"]


def test_bna_change_avec_un_nouveau_rapport(fixtures_dir):
    cas = _cas(fixtures_dir)
    avant = _ligne(cas["base"], 12000, cas["rapport_2024"], cas["boc"])
    apres = _ligne(cas["base"], 12000, cas["rapport_2025"], cas["boc"])
    assert avant["bna"] == 1000.0
    assert avant["bna_exercice"] == 2025
    assert apres["bna"] == 1080.0
    assert apres["bna_source"] == "rapport"
    assert apres["bna_exercice"] == 2025
    assert avant["bvpa"] == apres["bvpa"] == 5000.0


def test_priorite_rapport_boc_statique(fixtures_dir):
    cas = _cas(fixtures_dir)
    statique = dict(cas["base"], bna=320, eps=320, bvpa=2100)
    trois = _ligne(statique, 12000, cas["rapport_2024"], cas["boc"])
    assert trois["bna"] == 1000.0
    assert trois["bna_source"] == "rapport"
    assert trois["bvpa_source"] == "rapport"

    sans_rapport = _ligne(statique, 12000, None, cas["boc"])
    assert sans_rapport["bna"] == 900.0
    assert sans_rapport["bna_source"] == "boc"
    assert sans_rapport["bvpa"] == 2100
    assert sans_rapport["bvpa_source"] == "statique"

    seul = _ligne(statique, 12000, None, None)
    assert seul["bna"] == 320
    assert seul["eps"] == 320
    assert seul["bna_source"] == "statique"
    assert seul["bna_exercice"] is None
    assert seul["bna_date"] is None
    assert _proche(seul["pe_ref"] * seul["bna"], 12000)
    assert _proche(seul["pb_ref"] * seul["bvpa"], 12000)


def test_estimation_prix_sur_pe_nest_pas_un_bna(fixtures_dir):
    """eps_est = cours / PE dans le scraper : ce n'est pas un bénéfice publié."""
    cas = _cas(fixtures_dir)
    base = dict(cas["base"], eps_est=9999)
    row = _ligne(base, 12000, None, None)
    assert row["bna"] is None
    assert row["bna_source"] is None


def test_ratio_hors_bande_garde_le_rapport(fixtures_dir, caplog):
    """Rapport 1 000 et BOC 100 : l'écart est noté, le rapport reste."""
    import logging
    caplog.set_level(logging.WARNING, logger="live_ranker")
    cas = _cas(fixtures_dir)
    row = _ligne(cas["base"], 12000, cas["rapport_2024"], cas["boc_incoherent"], ticker="TEST")
    assert row["bna"] == 1000.0
    assert row["bna_source"] == "rapport"
    assert row["bna_date"] is None
    assert row["bna_exercice"] == 2025
    assert row["bna_ecart_boc"] == 10.0
    assert _proche(row["pe_ref"] * row["bna"], 12000)
    assert "TEST" in caplog.text
    assert "conservé" in caplog.text


def _rapport(doc_type, rn, cap, annee=2025, year=2026, unite="MFCFA"):
    return {
        "status": "ok",
        "doc_type": doc_type,
        "annee": annee,
        "year": year,
        "kpis": {
            "resultat_net": {"valeur": rn, "unite": unite},
            "capitaux_propres": {"valeur": cap, "unite": unite},
        },
    }


def test_donnees_enrichies_sgbc_ignorees():
    """SGBC : 71 272 MFCFA d'une note enrichie ne doit pas remplacer le BOC.

    71 272 / 31 111 110 actions = 2 291. Le BOC, lui, vaut 3 299.
    """
    from scraper import STOCK_FUNDAMENTALS as fond
    base = dict(fond["SGBC"])
    pdf = _rapport("Données financières enrichies", 71272.0, 200000.0)
    boc = {"date": "2026-09-25", "cours_clot": 32990.0, "per_boc": 10.0}
    row = _ligne(base, 34000, pdf, boc, ticker="SGBC")
    assert round(71272.0 * 1000000.0 / base["shares"], 0) == 2291.0
    assert row["bna"] == 3299.0
    assert row["bna"] != 2291.0
    assert row["bna_source"] == "boc"
    assert row["bvpa_source"] == "estime"
    assert row["bvpa"] == round(200000.0 * 1000000.0 / base["shares"], 1)
    for doc in ("Données publiques", "Rapport trimestriel"):
        autre = _ligne(base, 34000, _rapport(doc, 71272.0, 200000.0), boc, ticker="SGBC")
        assert autre["bna_source"] == "boc"
        assert autre["bna"] == 3299.0


def test_etats_financiers_accepte_avec_ou_sans_accent():
    cas_base = {
        "name": "Test", "shares": 1000000, "sector": "Banque",
        "country": "Côte d'Ivoire", "roe": 10, "div_hist": 0,
        "debt": "Faible", "stable": True, "pe_hist": 10, "pb_hist": 1,
    }
    boc = {"date": "2026-09-25", "cours_clot": 10000, "per_boc": 10}
    for doc in ("Etats financiers", "États financiers", "RAPPORT ANNUEL", "Rapport annuel"):
        row = _ligne(cas_base, 11000, _rapport(doc, 1000.0, 4000.0), boc)
        assert row["bna_source"] == "rapport", doc
        assert row["bna"] == 1000.0
        assert row["bvpa_source"] == "rapport"


def test_unite_autre_que_mfcfa_ignoree():
    cas_base = {
        "name": "Test", "shares": 1000000, "sector": "Banque",
        "country": "Côte d'Ivoire", "roe": 10, "div_hist": 0,
        "debt": "Faible", "stable": True, "pe_hist": 10, "pb_hist": 1,
    }
    boc = {"date": "2026-09-25", "cours_clot": 10000, "per_boc": 10}
    pdf = _rapport("Etats financiers", 1000.0, 4000.0, unite="FCFA")
    row = _ligne(cas_base, 11000, pdf, boc)
    assert row["bna_source"] == "boc"
    assert row["bna"] == 1000.0
    assert row["bvpa"] is None


def test_ntlc_ratio_06_prend_le_boc(caplog):
    """Nombre d'actions trop haut : le rapport vaut 0,6 du BOC, le BOC reste.

    Le BOC est plus grand, pas un effondrement. On ne garde le rapport
    que lorsque le bulletin est beaucoup plus petit (moins de 70 %).
    """
    import logging
    caplog.set_level(logging.WARNING, logger="live_ranker")
    base = dict(STOCK_FUNDAMENTALS["NTLC"])
    # BNA rapport volontairement à 60 % du BOC, quelles que soient les actions.
    boc_bna = 1000.0
    rn = 0.6 * boc_bna * base["shares"] / 1000000.0
    pdf = _rapport("Etats financiers", rn, rn, annee=2025, year=2026)
    boc = {"date": "2026-09-25", "cours_clot": 10000.0, "per_boc": 10.0}
    row = _ligne(base, 12000, pdf, boc, ticker="NTLC")
    assert row["bna_ecart_boc"] == 0.6
    assert row["bna"] == 1000.0
    assert row["bna_source"] == "boc"
    assert row["bna_exercice"] is None
    assert "NTLC" in caplog.text


def test_snts_ratio_1_garde_le_rapport():
    base = dict(STOCK_FUNDAMENTALS["SNTS"])
    boc_bna = 4000.0
    rn = boc_bna * base["shares"] / 1000000.0
    pdf = _rapport("Rapport annuel", rn, rn * 3, annee=2025, year=2026)
    boc = {"date": "2026-09-25", "cours_clot": boc_bna * 8, "per_boc": 8.0}
    row = _ligne(base, 33000, pdf, boc, ticker="SNTS")
    assert row["bna_ecart_boc"] == 1.0
    assert row["bna"] == 4000.0
    assert row["bna_source"] == "rapport"
    assert row["bna_exercice"] == 2025
    assert row["bna_date"] is None


def test_exercice_fiscal_pas_annee_de_publication(fixtures_dir):
    cas = _cas(fixtures_dir)
    pdf = dict(cas["rapport_2024"], annee=2025, year=2026)
    row = _ligne(cas["base"], 12000, pdf, cas["boc"])
    assert row["bna_source"] == "rapport"
    assert row["bna_exercice"] == 2025


def test_bvpa_estime_puis_statique_sans_document_comptable():
    """Sans état financier, les capitaux propres d'une note donnent un BVPA estimé.

    Le chiffre statique ne sert qu'en dernier. Un état financier, lui, reste
    « rapport » et ne passe pas par l'estimation.
    """
    base = {
        "name": "Test", "shares": 1000000, "sector": "Banque",
        "country": "Côte d'Ivoire", "roe": 10, "div_hist": 0,
        "debt": "Faible", "stable": True, "pe_hist": 10, "pb_hist": 1.5,
        "bvpa": 2100,
    }
    note = _rapport("Données financières enrichies", 500.0, 4000.0, annee=2025, year=2026)
    estime = _ligne(base, 12000, note, {"date": "2026-09-25", "cours_clot": 10000, "per_boc": 10})
    assert estime["bna_source"] == "boc"
    assert estime["bvpa"] == 4000.0
    assert estime["bvpa_source"] == "estime"
    assert _proche(estime["pb_ref"] * estime["bvpa"], 12000)

    sans_capitaux = _rapport("Données publiques", 500.0, None, annee=2025, year=2026)
    sans_capitaux["kpis"]["capitaux_propres"] = {"valeur": None, "unite": "MFCFA"}
    statique = _ligne(base, 12000, sans_capitaux, None)
    assert statique["bvpa"] == 2100
    assert statique["bvpa_source"] == "statique"

    officiel = _rapport("Etats financiers", 1000.0, 5000.0, annee=2025, year=2026)
    rapport = _ligne(base, 12000, officiel, {"date": "2026-09-25", "cours_clot": 10000, "per_boc": 10})
    assert rapport["bvpa_source"] == "rapport"
    assert rapport["bvpa"] == 5000.0


def test_garde_fou_ne_remplace_pas_un_rapport_par_un_boc_trop_petit(caplog):
    """1,25 reste au rapport. 1,39 (PALC) bascule : le BOC vaut encore 70 %.

    1,85, comme BICC, ne bascule pas : le bulletin est trop petit.
    """
    import logging
    caplog.set_level(logging.WARNING, logger="live_ranker")
    base = {
        "name": "Test", "shares": 1000000, "sector": "Industrie",
        "country": "Côte d'Ivoire", "roe": 10, "div_hist": 0,
        "debt": "Faible", "stable": True, "pe_hist": 10, "pb_hist": 1,
    }
    boc = {"date": "2026-09-25", "cours_clot": 10000.0, "per_boc": 10.0}

    def ligne(rn, ticker):
        return _ligne(base, 12000, _rapport("Etats financiers", rn, rn * 3), boc, ticker=ticker)

    dedans = ligne(1250.0, "HAUT")
    assert dedans["bna"] == 1250.0
    assert dedans["bna_source"] == "rapport"
    assert dedans["bna_ecart_boc"] == 1.25

    palc = ligne(1390.0, "PALC")
    assert palc["bna"] == 1000.0
    assert palc["bna_source"] == "boc"
    assert palc["bna_ecart_boc"] == 1.39

    # 1 850 / 1 000 = 1,85. 1 000 < 70 % de 1 850. Le rapport reste (BICC).
    bicc = ligne(1850.0, "BICC")
    assert bicc["bna"] == 1850.0
    assert bicc["bna_source"] == "rapport"
    assert bicc["bna_ecart_boc"] == 1.85
    assert "conservé" in caplog.text

    plancher = ligne(800.0, "BAS")
    assert plancher["bna_source"] == "rapport"
    assert plancher["bna_ecart_boc"] == 0.8

    sous_plancher = ligne(790.0, "SOUS")
    assert sous_plancher["bna"] == 1000.0
    assert sous_plancher["bna_source"] == "boc"
    assert sous_plancher["bna_ecart_boc"] == 0.79


def _base_exercice():
    return {
        "name": "Test", "shares": 1000000, "sector": "Banque",
        "country": "Côte d'Ivoire", "roe": 10, "div_hist": 0,
        "debt": "Faible", "stable": True, "pe_hist": 10, "pb_hist": 1,
    }


def test_exercice_trop_ancien_apres_le_1er_juillet(caplog):
    """Le 29 septembre 2026, un exercice avant 2025 est ignoré.

    Ça écarte BOAC 2024, CFAC 2023, UNLC 2023 et SEMC 2023. 2025 reste.
    """
    import logging
    caplog.set_level(logging.WARNING, logger="live_ranker")
    base = _base_exercice()
    boc = {"date": "2026-09-25", "cours_clot": 10000.0, "per_boc": 10.0}
    jour = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
    for ticker, annee in (("BOAC", 2024), ("CFAC", 2023), ("UNLC", 2023), ("SEMC", 2023)):
        pdf = _rapport("Etats financiers", 1000.0, 4000.0, annee=annee, year=annee + 1)
        row = _ligne(base, 12000, pdf, boc, ticker=ticker, moment=jour)
        assert row["bna_source"] == "boc", ticker
        assert row["bna"] == 1000.0
        assert row["bna_exercice"] is None
        assert row["bvpa_source"] == "estime"
        assert row["bvpa"] == 4000.0
        assert ticker in caplog.text
        assert str(annee) in caplog.text

    garde = _ligne(
        base, 12000,
        _rapport("Etats financiers", 1000.0, 4000.0, annee=2025, year=2026),
        boc, ticker="SNTS", moment=jour,
    )
    assert garde["bna_source"] == "rapport"
    assert garde["bna_exercice"] == 2025


def test_vieux_rapport_garde_le_bvpa_estime():
    """Un état trop ancien ne donne plus de BNA, mais ses capitaux restent un BVPA estimé.

    Le chiffre statique ne passe qu'après. Une note sans exercice fiscal, dont
    `year` est une année de publication ancienne, n'est pas jetée non plus.
    """
    base = _base_exercice()
    base["bvpa"] = 2100
    boc = {"date": "2026-09-25", "cours_clot": 10000.0, "per_boc": 10.0}
    jour = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
    vieux = _rapport("Etats financiers", 1000.0, 4000.0, annee=2023, year=2024)
    row = _ligne(base, 12000, vieux, boc, ticker="UNLC", moment=jour)
    assert row["bna_source"] == "boc"
    assert row["bna_exercice"] is None
    assert row["bvpa_source"] == "estime"
    assert row["bvpa"] == 4000.0
    assert row["bvpa"] != 2100
    assert _proche(row["pb_ref"] * row["bvpa"], 12000)

    note = _rapport("Données financières enrichies", 500.0, 3500.0, annee=2023, year=2023)
    note.pop("annee")
    autre = _ligne(base, 12000, note, boc, ticker="SAFC", moment=jour)
    assert autre["bna_source"] == "boc"
    assert autre["bvpa_source"] == "estime"
    assert autre["bvpa"] == 3500.0


def test_grace_avant_le_1er_juillet():
    """Avant le 1er juillet, l'exercice N-2 est encore accepté. N-3 ne l'est pas."""
    base = _base_exercice()
    boc = {"date": "2026-06-15", "cours_clot": 10000.0, "per_boc": 10.0}
    juin = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    juillet = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
    pdf_2024 = _rapport("Etats financiers", 1000.0, 4000.0, annee=2024, year=2025)
    assert _ligne(base, 12000, pdf_2024, boc, moment=juin)["bna_source"] == "rapport"
    assert _ligne(base, 12000, pdf_2024, boc, ticker="BOAC", moment=juillet)["bna_source"] == "boc"
    pdf_2023 = _rapport("Rapport annuel", 1000.0, 4000.0, annee=2023, year=2024)
    assert _ligne(base, 12000, pdf_2023, boc, ticker="CFAC", moment=juin)["bna_source"] == "boc"


def test_catalogue_annee_de_publication_ne_jette_pas_lexercice(tmp_path, monkeypatch):
    """2026 dans le catalogue est une année de publication. L'exercice 2025 reste."""
    monkeypatch.setattr("paths.DATA_DIR", str(tmp_path))
    (tmp_path / "reports_full.json").write_text(json.dumps([
        {
            "ticker": "SNTS",
            "type": "Etats financiers",
            "annee": 2026,
            "titre": "20260221 - etats financiers - exercice 2025",
        },
    ]), encoding="utf-8")
    (tmp_path / "reports_cache.json").write_text(json.dumps({
        "reports": {
            "SNTS": [{"type": "Rapport annuel", "annee": 2026, "title": "Rapport 2026"}],
        },
    }), encoding="utf-8")
    base = _base_exercice()
    boc = {"date": "2026-09-25", "cours_clot": 10000.0, "per_boc": 10.0}
    pdf = _rapport("Etats financiers", 1000.0, 4000.0, annee=2025, year=2026)
    row = _ligne(base, 12000, pdf, boc, ticker="SNTS")
    assert row["bna_source"] == "rapport"
    assert row["bna"] == 1000.0
    assert row["bna_exercice"] == 2025
    assert row["bvpa_source"] == "rapport"


def test_bvpa_boc_seulement_si_le_bulletin_en_a_un(caplog):
    """Sans P/B BOC, le BVPA du rapport reste. S'il diverge trop, le BOC gagne."""
    import logging
    caplog.set_level(logging.WARNING, logger="live_ranker")
    base = {
        "name": "Test", "shares": 1000000, "sector": "Banque",
        "country": "Côte d'Ivoire", "roe": 10, "div_hist": 0,
        "debt": "Faible", "stable": True, "pe_hist": 10, "pb_hist": 1,
    }
    pdf = _rapport("Etats financiers", 1000.0, 5000.0, annee=2025, year=2026)
    sans = _ligne(base, 12000, pdf, {"date": "2026-09-25", "cours_clot": 9000, "per_boc": 10})
    assert sans["bvpa"] == 5000.0
    assert sans["bvpa_source"] == "rapport"
    # cours 9000 / P/B 1 = 9 000, rapport 5 000, ratio 0,56 : hors bande.
    avec = _ligne(
        base, 12000, pdf,
        {"date": "2026-09-25", "cours_clot": 9000, "per_boc": 10, "pb_boc": 1},
        ticker="BV",
    )
    assert avec["bvpa"] == 9000.0
    assert avec["bvpa_source"] == "boc"
    assert "BVPA BV" in caplog.text


def test_sans_bna_pas_de_plantage(fixtures_dir):
    cas = _cas(fixtures_dir)
    row = _ligne(cas["base"], 5000, None, None)
    assert row["bna"] is None
    assert row["eps"] is None
    assert row["bvpa"] is None
    assert row["bna_source"] is None
    assert row["bvpa_source"] is None
    assert row.get("pe_ref") is None
    vide = _build_enriched_row("TEST", {"name": "Vide"}, {}, None, {})
    assert vide["bna"] is None
    scores = _compute_scores(row)
    assert scores["score_epv"] == score_epv(row)["score"]
    assert "score_graham" in scores
    _compute_scores(vide)


def test_cibles_epv_graham_inchangees_si_seul_le_cours_bouge(fixtures_dir, monkeypatch, tmp_path):
    cas = _cas(fixtures_dir)
    bas = _ligne(cas["base"], 12000, cas["rapport_2024"], cas["boc"])
    haut = _ligne(cas["base"], 15000, cas["rapport_2024"], cas["boc"])
    assert bas["bna"] == haut["bna"]
    assert bas["bvpa"] == haut["bvpa"]

    def cibles(row, prix):
        payload = {
            "ranking": [{
                "ticker": "TEST",
                "name": "Societe test",
                "price": prix,
                "eps": row["eps"],
                "bna": row["bna"],
                "bvpa": row["bvpa"],
                "roe": 18,
                "composite_adj": 40,
            }]
        }
        chemin = tmp_path / ("ranking_%s.json" % prix)
        chemin.write_text(json.dumps(payload), encoding="utf-8")
        monkeypatch.setattr("features.DATA_DIR", str(tmp_path))
        # lire_lignes lit DATA_DIR/live_ranking.json
        (tmp_path / "live_ranking.json").write_text(json.dumps(payload), encoding="utf-8")
        return get_price_targets()[0]

    a = cibles(bas, 12000)
    b = cibles(haut, 15000)
    assert a["epv_target"] == b["epv_target"] == 10000
    assert a["graham_target"] == b["graham_target"]
    assert a["current_price"] != b["current_price"]


def _bna_ancien(prix, per, bna_rapport):
    """Ancienne règle : BNA = cours live / PER, sauf si trop bas face au rapport."""
    if per and 0 < per < 500 and prix and prix > 0:
        bna_boc = round(prix / float(per), 1)
        if bna_rapport and bna_rapport > 0:
            if bna_boc > 0 and bna_boc >= bna_rapport * 0.7:
                return bna_boc, float(per)
            return bna_rapport, round(prix / bna_rapport, 2)
        if bna_boc > 0:
            return bna_boc, float(per)
    if bna_rapport and bna_rapport > 0 and prix and prix > 0:
        return bna_rapport, round(prix / bna_rapport, 2)
    return None, None


def test_univers_47_bna_bvpa_et_conseils(fixtures_dir):
    """Mesure sur le fixture des 47 sociétés (pas les données de production)."""
    univers = _univers(fixtures_dir)
    assert set(univers["groupes"]) == set(STOCK_FUNDAMENTALS)
    assert len(STOCK_FUNDAMENTALS) == 47

    sans_bna = []
    sans_bvpa = []
    conseils = []
    for ticker, base in STOCK_FUNDAMENTALS.items():
        prix = univers["prix"][ticker]
        boc = univers["boc"].get(ticker)
        pdf = univers["pdf"].get(ticker)
        row = _ligne(base, prix, pdf, boc, ticker=ticker)
        autre = _ligne(base, prix + 250, pdf, boc, ticker=ticker)
        assert row["bna"] == autre["bna"]
        assert row["bvpa"] == autre["bvpa"]
        source_attendue = {
            "rapport": "rapport",
            "boc": "boc",
            "aucun": None,
        }[univers["groupes"][ticker]]
        # PALC : ratio 1,39. Le BOC vaut encore au moins 70 % du rapport.
        if ticker == "PALC":
            source_attendue = "boc"
        assert row["bna_source"] == source_attendue
        if row["bna"] is None:
            sans_bna.append(ticker)
            assert row.get("pe_ref") is None
        else:
            assert _proche(row["pe_ref"] * row["bna"], prix)
        if row["bvpa"] is None:
            sans_bvpa.append(ticker)
        else:
            assert row["bvpa_source"] == "rapport"
            assert _proche(row["pb_ref"] * row["bvpa"], prix)

        bna_pdf = row["bna"] if univers["groupes"][ticker] == "rapport" else None
        per = (boc or {}).get("per_boc")
        ancien_bna, ancien_pe = _bna_ancien(prix, per, bna_pdf)
        ancien = dict(row)
        ancien["bna"] = ancien_bna
        ancien["eps"] = ancien_bna
        if ancien_pe:
            ancien["pe_ref"] = ancien_pe
        else:
            ancien.pop("pe_ref", None)
        conseil_avant = _compute_scores(ancien)["conseil"]
        conseil_apres = _compute_scores(row)["conseil"]
        conseils.append((ticker, ancien_bna, row["bna"], conseil_avant, conseil_apres))

    assert sorted(sans_bna) == [
        "ABJC", "BNBC", "NEIC", "SCRC", "SDSC", "SEMC", "SIVC", "STAC", "UNXC",
    ]
    assert len(sans_bna) == 9
    assert len(sans_bvpa) == 27
    assert sum(1 for t, g in univers["groupes"].items() if g == "rapport") == 20

    par = dict(
        (t, (avant, apres, c_avant, c_apres))
        for t, avant, apres, c_avant, c_apres in conseils
    )
    assert par["ORAC"][0] == 1129.5
    assert par["ORAC"][1] == 1000.0
    assert par["SNTS"][0] == 4135.6
    assert par["SNTS"][1] == 4000.0
    assert par["SGBC"][0] == 2800.0
    assert par["SGBC"][1] == 2500.0
    assert par["STBC"][0] == 2100.0
    assert par["STBC"][1] == 1800.0
    # PALC : le rapport 2 000 / BOC 1 438,8 = 1,39.
    # Le BOC vaut encore 70 % du rapport : il est retenu.
    # Le nombre d'actions faux n'est pas corrigé ici.
    assert par["PALC"][1] == 1438.8
    palc = _ligne(
        STOCK_FUNDAMENTALS["PALC"],
        univers["prix"]["PALC"],
        univers["pdf"]["PALC"],
        univers["boc"]["PALC"],
        ticker="PALC",
    )
    assert palc["bna_source"] == "boc"
    assert palc["bna_ecart_boc"] == 1.39
    assert palc["bvpa_source"] == "rapport"

    changements = sorted(
        (t, c_avant, c_apres)
        for t, _a, _b, c_avant, c_apres in conseils
        if c_avant != c_apres
    )
    # Mesure sur ce fixture : 4 conseils passent de « À surveiller » à « Prudence ».
    # Les 43 autres gardent le même mot. ORAC, SNTS et SGBC ne changent pas de mot.
    assert changements == [
        ("LNBB", "À surveiller", "Prudence"),
        ("NSBC", "À surveiller", "Prudence"),
        ("SMBC", "À surveiller", "Prudence"),
        ("STBC", "À surveiller", "Prudence"),
    ]


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


@pytest.fixture
def gel(tmp_path, monkeypatch):
    monkeypatch.setattr(live_ranker, "RANKING_PATH", str(tmp_path / "live_ranking.json"))
    monkeypatch.setattr(live_ranker, "HISTORY_PATH", str(tmp_path / "ranking_history.json"))
    monkeypatch.setattr(live_ranker, "_last_prices", {})
    monkeypatch.setattr(live_ranker, "_last_ranking", None)
    monkeypatch.setattr("scraper.STOCK_FUNDAMENTALS", FOND)
    monkeypatch.setattr(
        live_ranker, "empreinte_faits", lambda chemins=None, moment=None: "fixe",
    )
    monkeypatch.setattr(
        "price_history_builder.load_history",
        lambda: {"ALPH": [{"date": "2026-09-28", "price": 8000, "volume": 100}]},
    )
    boc = {
        "last_update": "2026-09-28T19:00:00",
        "ALPH": {"date": "2026-09-25", "cours_clot": 8000, "per_boc": 8, "div_net": 100},
    }
    for nom, contenu in (
        ("boc_data.json", boc),
        ("analyses_summary.json", {}),
        ("external_dividends.json", {}),
    ):
        (tmp_path / nom).write_text(json.dumps(contenu), encoding="utf-8")
    chemins = tuple(str(tmp_path / nom) for nom in (
        "boc_data.json", "analyses_summary.json", "external_dividends.json",
    ))
    monkeypatch.setattr(live_ranker, "chemins_faits", lambda: chemins)
    etat = {"prix": 12000}

    def lire(force_refresh=False):
        return {"prices": {"ALPH": {
            "price": etat["prix"], "open": etat["prix"], "change_pct": 1.0,
            "volume": 10, "trend": None,
        }}}

    monkeypatch.setattr("live_data.get_live_data", lire)
    return {"chemin": tmp_path / "live_ranking.json", "etat": etat, "dossier": tmp_path}


def _ecrire(chemin, formule, quand):
    payload = {
        "updated_at": quand,
        "note_calculee_le": quand,
        "note_formule": formule,
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
            "note_calculee_le": quand,
            "price": 8000,
        }],
    }
    chemin.write_text(json.dumps(payload), encoding="utf-8")


def test_pe_ref_vide_quand_il_ny_a_pas_de_bna(gel):
    """Sans BNA, le classement ne montre pas le P/E statique à la place."""
    (gel["dossier"] / "boc_data.json").write_text("{}", encoding="utf-8")
    _ecrire(gel["chemin"], NOTE_FORMULE, NOTE_VEILLE)
    resultat = compute_live_ranking(trigger="startup", moment=SEANCE)
    ligne = resultat["ranking"][0]
    assert ligne["bna"] is None
    assert ligne["pe_ref"] is None
    assert ligne["pe_hist"] == 8.0


def test_pb_ref_vide_quand_il_ny_a_pas_de_bvpa(gel):
    """Sans BVPA, le classement ne montre pas le P/B statique à la place.

    C'est le P/B que les modèles lisent (cours / BVPA), ou rien.
    """
    _ecrire(gel["chemin"], NOTE_FORMULE, NOTE_VEILLE)
    resultat = compute_live_ranking(trigger="startup", moment=SEANCE)
    ligne = resultat["ranking"][0]
    assert ligne["bna"] == 1000.0
    assert ligne["bvpa"] is None
    assert ligne["pb_ref"] is None
    assert ligne["pb_hist"] == 1.2

    analyse = {
        "ALPH": _rapport("Données financières enrichies", 1.0, 4.0, annee=2025, year=2026),
    }
    (gel["dossier"] / "analyses_summary.json").write_text(
        json.dumps(analyse), encoding="utf-8",
    )
    avec = compute_live_ranking(trigger="startup", moment=SEANCE)
    ligne = avec["ranking"][0]
    assert ligne["bvpa_source"] == "estime"
    assert ligne["bvpa"] == 4000.0
    assert ligne["pb_ref"] == round(12000 / 4000.0, 2)
    assert ligne["pb_ref"] != ligne["pb_hist"]


def test_formule_v1_gardee_en_seance(gel):
    assert NOTE_FORMULE == "cloture-v2"
    _ecrire(gel["chemin"], ANCIENNE_FORMULE, NOTE_VEILLE)
    resultat = compute_live_ranking(trigger="startup", moment=SEANCE)
    ligne = resultat["ranking"][0]
    assert resultat["note_recalculee"] is False
    assert resultat["note_formule"] == ANCIENNE_FORMULE
    assert ligne["composite_adj"] == 3.3
    assert ligne["conseil"] == "Prudence"
    assert ligne["note_calculee_le"] == NOTE_VEILLE
    # Le BNA affiché est déjà le bon, le cours live (12 000) ne le fabrique pas.
    assert ligne["bna"] == 1000.0
    assert ligne["bna_source"] == "boc"
    assert ligne["bna_date"] == "2026-09-25"
    assert ligne["price"] == 12000
    assert _proche(ligne["pe_ref"] * ligne["bna"], 12000)


def test_formule_v1_recalculee_apres_la_cloture_du_jour(gel):
    """La note du jour a déjà été faite avec l'ancienne formule : on la refait une fois."""
    _ecrire(gel["chemin"], ANCIENNE_FORMULE, NOTE_DEJA_DU_JOUR)
    resultat = compute_live_ranking(trigger="startup", moment=APRES_NOTE_DU_JOUR)
    ligne = resultat["ranking"][0]
    assert resultat["note_recalculee"] is True
    assert resultat["note_formule"] == "cloture-v2"
    assert ligne["note_calculee_le"] == APRES_NOTE_DU_JOUR.isoformat()
    assert ligne["composite_adj"] != 3.3
    assert ligne["bna"] == 1000.0
    deuxieme = compute_live_ranking(
        trigger="scheduler",
        moment=APRES_NOTE_DU_JOUR.replace(minute=5),
    )
    assert deuxieme["note_recalculee"] is False
    assert deuxieme["ranking"][0]["composite_adj"] == ligne["composite_adj"]
    assert deuxieme["ranking"][0]["bna"] == 1000.0


LIGNE_SEMC = (
    "SEMC SONOCO METAL 1 495 SP SP 0,00 % 1 495 113,57 % "
    "14 28-déc.-21 0,94 % 37,21"
)


def test_semc_bna_boc_vaut_40_2_et_pas_40180():
    """Le cours 1 495 ne doit pas avaler le pourcentage 113,57.

    Sans ce découpage, le cours lu est 1 495 113,57 et le BNA vaut
    environ 40 180, soit un P/E de 0,04. Le bon BNA est 1 495 / 37,21 = 40,2.
    """
    from boc_scraper import nombres_ligne_boc
    from live_ranker import _bna_depuis_boc

    nombres = nombres_ligne_boc(LIGNE_SEMC)
    assert 1495113.57 not in nombres
    assert nombres[0] == 1495.0
    assert nombres[2] == 1495.0
    assert nombres[-1] == 37.21
    assert _bna_depuis_boc(1495, 37.21) == 40.2
    assert _bna_depuis_boc(1495113.57, 37.21) is None
    assert _bna_depuis_boc(1495, 0.04) is None

    base = dict(STOCK_FUNDAMENTALS["SEMC"])
    # Exercice 2023 : trop ancien le 29 septembre 2026, donc le BOC sert.
    pdf = _rapport("Etats financiers", 500.0, 2800.0, annee=2023, year=2024)
    boc = {"date": "2026-09-29", "cours_clot": 1495, "per_boc": 37.21}
    row = _ligne(base, 1495, pdf, boc, ticker="SEMC")
    assert row["bna"] == 40.2
    assert row["bna_source"] == "boc"
    assert row["pe_ref"] == round(1495 / 40.2, 2)
    assert row["pe_ref"] > 1


def test_formule_v1_recalculee_le_week_end(gel):
    _ecrire(gel["chemin"], ANCIENNE_FORMULE, "2026-10-02T16:00:00+00:00")
    donnees = json.loads(gel["chemin"].read_text(encoding="utf-8"))
    donnees["ranking"][0]["note_calculee_le"] = "2026-10-02T16:00:00+00:00"
    gel["chemin"].write_text(json.dumps(donnees), encoding="utf-8")
    resultat = compute_live_ranking(trigger="startup", moment=SAMEDI)
    assert resultat["market_open"] is False
    assert resultat["note_recalculee"] is True
    assert resultat["note_formule"] == "cloture-v2"
    assert resultat["ranking"][0]["bna"] == 1000.0
