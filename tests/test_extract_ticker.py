# -*- coding: utf-8 -*-
"""Extraction ticker / cran de notation (RATINGS-1, audit B-5).

Le rattachement se fait par mot entier ou par nom complet d'émetteur.
Les émetteurs non cotés ne produisent pas de fiche.
"""
import importlib.util
import json
from pathlib import Path

_CHEMIN = Path(__file__).resolve().parents[1] / "scripts" / "brvm_market_data_scraper.py"
_spec = importlib.util.spec_from_file_location("brvm_market_data_scraper", str(_CHEMIN))
_scraper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_scraper)

_extract_ticker = _scraper._extract_ticker
_extract_rating_info = _scraper._extract_rating_info
_fiche_notation = _scraper._fiche_notation

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ratings_emetteurs.json"
_CLES_HISTORIQUES = {
    "ticker", "agence", "note", "score_notation", "perspective",
    "date", "source_url", "resume",
}


def _charger_fixture():
    with open(str(_FIXTURE), encoding="utf-8") as f:
        return json.load(f)["entrees"]


def _fiches(entrees):
    """Même forme que brvm_ratings.json : les ticker null ne sont pas émis."""
    fiches = []
    for entree in entrees:
        ticker = _extract_ticker(entree["texte"])
        if not ticker:
            continue
        fiches.append(_fiche_notation(entree["texte"], entree["texte"], ticker, None, "", None))
    return fiches


def test_extract_ticker_sonatel():
    assert _extract_ticker("Communique Sonatel notation BBB+") == "SNTS"


def test_extract_ticker_symbole_majuscule():
    assert _extract_ticker("Rapport SNTS exercice") == "SNTS"


def test_extract_ticker_ecobank():
    assert _extract_ticker("Ecobank CI resultats") == "ECOC"


def test_extract_ticker_unilever():
    assert _extract_ticker("Unilever CI notation B-") == "UNLC"


def test_extract_rating_bbb_et_perspective():
    info = _extract_rating_info("Note long terme BBB perspective Stable")
    assert info["note"] == "BBB"
    assert info["score_notation"] == 6
    assert info["perspective"] == "Stable"


def test_extract_ticker_marketing_ci_pas_etit():
    texte = "TotalEnergies Marketing CI — notation financiere long terme"
    assert _extract_ticker(texte) == "TTLC"


def test_extract_ticker_marketing_sn_pas_etit():
    texte = "TotalEnergies Marketing Senegal — notation"
    assert _extract_ticker(texte) == "TTLS"


def test_extract_ticker_financiere_pas_ciec():
    texte = "Notation de la Societe Financiere de l'Ouest"
    assert _extract_ticker(texte) is None


def test_cran_a_plus_conserve():
    info = _extract_rating_info("Note long terme A+ perspective Stable")
    assert info["note"] == "A+"
    assert info["score_notation"] == 8


def test_cran_aa_moins_conserve():
    info = _extract_rating_info("Note long terme AA- perspective Stable")
    assert info["note"] == "AA-"
    assert info["score_notation"] == 8.5


def test_cran_a_sans_signe_reste_a():
    info = _extract_rating_info("Note long terme A perspective Stable")
    assert info["note"] == "A"
    assert info["score_notation"] == 7.5


def test_cran_bbb_moins_conserve():
    info = _extract_rating_info("Note long terme BBB- perspective Stable")
    assert info["note"] == "BBB-"
    assert info["score_notation"] == 5.5


def test_cran_b_moins_conserve():
    info = _extract_rating_info("Unilever CI notation B- perspective Négative")
    assert info["note"] == "B-"
    assert info["score_notation"] == 2.5
    assert _extract_ticker("Unilever CI notation B- perspective Négative") == "UNLC"


def test_cran_c_ne_lit_pas_cote():
    info = _extract_rating_info("République de Côte d'Ivoire")
    assert info["note"] is None


def test_date_validite_en_lettres():
    info = _extract_rating_info(
        "Note long terme A+ perspective Stable. Date de validité : 30 juin 2026."
    )
    assert info["date_validite"] == "2026-06-30"


def test_date_validite_numerique():
    info = _extract_rating_info("Valable jusqu'au 31/12/2025. Note AA-.")
    assert info["note"] == "AA-"
    assert info["date_validite"] == "2025-12-31"


def test_compagnie_ivoirienne_electricite():
    assert _extract_ticker("Compagnie Ivoirienne d'Electricite — notation") == "CIEC"
    assert _extract_ticker("Compagnie Ivoirienne d'Électricité — notation") == "CIEC"


def test_eti_mot_entier_pas_dans_marketing():
    assert _extract_ticker("Campagne marketing de la societe") is None
    assert _extract_ticker("Notation ETI long terme BBB") == "ETIT"


def test_emetteurs_non_cotes_ignores():
    assert _extract_ticker("CRRH-UEMOA — Note long terme AA-") is None
    assert _extract_ticker("BOAD — Banque Ouest Africaine de Développement") is None
    assert _extract_ticker("Etat du Sénégal — Note long terme B+") is None
    assert _extract_ticker("Ecobank Ghana — Note long terme A-") is None
    assert _extract_ticker("NSIA Banque Bénin — Note long terme BBB") is None


def test_noms_stock_fundamentals_retrouvent_leur_ticker():
    from scraper import STOCK_FUNDAMENTALS
    assert len(STOCK_FUNDAMENTALS) == 47
    for ticker, info in STOCK_FUNDAMENTALS.items():
        assert _extract_ticker(info["name"]) == ticker


def test_fixture_rattachement_et_affichage():
    """Après correction : ETIT sans notes étrangères, CIEC <= 2, pas de ticker null."""
    entrees = _charger_fixture()
    for entree in entrees:
        obtenu = _extract_ticker(entree["texte"])
        attendu = entree["apres"]
        assert obtenu == attendu, entree["id"]
        info = _extract_rating_info(entree["texte"])
        if "note" in entree:
            assert info["note"] == entree["note"], entree["id"]
        if "date_validite" in entree:
            assert info["date_validite"] == entree["date_validite"], entree["id"]

    fiches = _fiches(entrees)
    assert all(f["ticker"] for f in fiches)
    assert _CLES_HISTORIQUES <= set(fiches[0])
    assert "date_validite" in fiches[0]

    par_ticker = {}
    for fiche in fiches:
        par_ticker.setdefault(fiche["ticker"], []).append(fiche)

    etit = par_ticker.get("ETIT", [])
    assert etit
    for fiche in etit:
        resume = fiche["resume"].lower()
        assert "totalenergies" not in resume
        assert "unilever" not in resume
        assert "smb" not in resume

    assert len(par_ticker.get("CIEC", [])) <= 2
    assert par_ticker["TTLC"][0]["note"] == "A+"
    assert par_ticker["TTLS"][0]["note"] == "AA-"
    assert par_ticker["TTLC"][0]["date_validite"] == "2026-06-30"

    ignores = {
        e["texte"] for e in entrees if e["apres"] is None
    }
    assert ignores
    assert not any(fiche["resume"] in ignores for fiche in fiches)


def test_titre_prime_sur_le_corps():
    corps = "Ecobank Transnational Incorporated publie ses comptes."
    assert _extract_ticker(corps, titre="Ecobank Côte d'Ivoire") == "ECOC"


def test_premier_nom_dans_le_texte():
    assert _extract_ticker(
        "Ecobank Côte d'Ivoire, filiale d'Ecobank Transnational Incorporated"
    ) == "ECOC"


def test_cie_mentionne_sodeci():
    texte = (
        "La Compagnie Ivoirienne d'Electricite informe ses actionnaires. "
        "La Société de Distribution d'Eau de Côte d'Ivoire est citée."
    )
    assert _extract_ticker(texte) == "CIEC"


def test_sgbc_mentionne_sodeci():
    texte = (
        "La Société Générale Côte d'Ivoire publie sa notation. "
        "SODECI est mentionnée dans le secteur."
    )
    assert _extract_ticker(texte) == "SGBC"


def test_coris_hors_burkina():
    assert _extract_ticker("Coris Bank International") == "CBIBF"
    assert _extract_ticker("Coris Bank International Sénégal") is None
    assert _extract_ticker("Coris Bank International Mali") is None
    assert _extract_ticker("Coris Bank International Niger") is None
    assert _extract_ticker("Coris Bank International Côte d'Ivoire") is None
    assert _extract_ticker("Coris Bank International Bénin") is None
    assert _extract_ticker("Coris Bank International Togo") is None
    assert _extract_ticker("Coris Bank International Guinée") is None


def test_filiales_nsia_et_sg_hors_cote_ivoire():
    assert _extract_ticker("NSIA Banque Côte d'Ivoire") == "NSBC"
    assert _extract_ticker("NSIA Banque Sénégal") is None
    assert _extract_ticker("NSIA Banque Guinée") is None
    assert _extract_ticker("Société Générale Côte d'Ivoire") == "SGBC"
    assert _extract_ticker("Société Générale Sénégal") is None
    assert _extract_ticker("Société Générale Burkina") is None


def test_alias_retires():
    assert _extract_ticker("Banque Atlantique CI") is None
    assert _extract_ticker("Notation BACI") is None
    assert _extract_ticker("SICOGI publie ses comptes") is None
    assert _extract_ticker("Air Burkina — note de long terme") is None
    assert _extract_ticker("Prestige motors") is None


def test_alias_ajoutes():
    assert _extract_ticker("SGBCI") == "SGBC"
    assert _extract_ticker("SGB CI") == "SGBC"
    assert _extract_ticker("Total Energies Marketing Sénégal") == "TTLS"
    assert _extract_ticker("Total Energies Marketing Côte d'Ivoire") == "TTLC"
    assert _extract_ticker("Groupe Ecobank") == "ETIT"
    assert _extract_ticker("SIVOP") == "SIVC"
    assert _extract_ticker("SOACII") == "SMBC"


def test_long_terme_prime_sur_la_note_precedente():
    info = _extract_rating_info("Long terme : A+ (précédente : BBB+)")
    assert info["note"] == "A+"
    assert info["score_notation"] == 8


def test_legende_avant_la_note_de_long_terme():
    texte = (
        "Échelle : AAA, AA, A, BBB, BB, B, CCC, CC, C, D. "
        "Note de long terme : BBB+ perspective Stable."
    )
    info = _extract_rating_info(texte)
    assert info["note"] == "BBB+"
    assert info["score_notation"] == 6.5


def test_sans_ancre_le_premier_cran_compte():
    info = _extract_rating_info("La société est notée BBB+ (échelle AAA, AA, A).")
    assert info["note"] == "BBB+"


def test_cran_ccc_plus_conserve():
    info = _extract_rating_info("Note de long terme CCC+ perspective Stable")
    assert info["note"] == "CCC+"
    assert info["score_notation"] == 2.25
    nu = _extract_rating_info("notée CCC+")
    assert nu["note"] == "CCC+"


def test_lt_abrege():
    info = _extract_rating_info("Note LT : A- perspective Stable. Précédente : BB.")
    assert info["note"] == "A-"


def test_cie_mot_entier_pas_et_cie():
    assert _extract_ticker("Dupont et Cie") is None
    assert _extract_ticker("Dupont & Cie") is None
    assert _extract_ticker("La CIE publie ses comptes") == "CIEC"
    assert _extract_ticker("Compagnie Ivoirienne d'Electricite, dite Cie") == "CIEC"
