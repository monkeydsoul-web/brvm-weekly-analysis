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


def _ligne(base, prix, pdf, boc, ticker="TEST"):
    return _build_enriched_row(
        ticker,
        base,
        {"price": prix, "change_pct": 0, "volume": 0},
        pdf,
        boc_snapshot={ticker: boc} if boc else {},
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
    assert bas["bna_exercice"] == 2024
    assert bas["bna_date"] is None
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
    assert avant["bna_exercice"] == 2024
    assert apres["bna"] == 1500.0
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


def test_boc_incoherent_ignore(fixtures_dir):
    cas = _cas(fixtures_dir)
    row = _ligne(cas["base"], 12000, cas["rapport_2024"], cas["boc_incoherent"])
    assert row["bna"] == 1000.0
    assert row["bna_source"] == "rapport"
    assert row["bna"] != 100.0
    assert _proche(row["pe_ref"] * row["bna"], 12000)


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
        assert row["bna_source"] == {
            "rapport": "rapport",
            "boc": "boc",
            "aucun": None,
        }[univers["groupes"][ticker]]
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
    # PALC : le BOC (cours live / PER = 500) est incohérent avec le rapport 2 000.
    assert par["PALC"][0] == par["PALC"][1] == 2000.0

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
    monkeypatch.setattr(live_ranker, "empreinte_faits", lambda chemins=None: "fixe")
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
    return {"chemin": tmp_path / "live_ranking.json", "etat": etat}


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
