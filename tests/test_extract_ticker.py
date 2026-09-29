# -*- coding: utf-8 -*-
"""Extraction ticker / cran de notation.

Les cas qui decrivent le comportement juste et echouent aujourd'hui
sont marques xfail : ils documentent le bug B-5, ils ne le corrigent pas.
"""
import importlib.util
from pathlib import Path

import pytest

_CHEMIN = Path(__file__).resolve().parents[1] / "scripts" / "brvm_market_data_scraper.py"
_spec = importlib.util.spec_from_file_location("brvm_market_data_scraper", str(_CHEMIN))
_scraper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_scraper)

_extract_ticker = _scraper._extract_ticker
_extract_rating_info = _scraper._extract_rating_info


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


@pytest.mark.xfail(
    strict=False,
    reason=(
        "B-5 : _extract_ticker rattache « TotalEnergies Marketing CI » a ETIT "
        "car la cle « eti » est un bout de « marketing » (la cible est TTLC)"
    ),
)
def test_extract_ticker_marketing_ci_pas_etit():
    texte = "TotalEnergies Marketing CI — notation financiere long terme"
    assert _extract_ticker(texte) == "TTLC"


@pytest.mark.xfail(
    strict=False,
    reason=(
        "B-5 : _extract_ticker rattache « TotalEnergies Marketing Senegal » a ETIT "
        "car la cle « eti » est un bout de « marketing » (la cible est TTLS)"
    ),
)
def test_extract_ticker_marketing_sn_pas_etit():
    texte = "TotalEnergies Marketing Senegal — notation"
    assert _extract_ticker(texte) == "TTLS"


@pytest.mark.xfail(
    strict=False,
    reason=(
        "B-5 : _extract_ticker rattache une « Societe Financiere » a CIEC "
        "car la cle « cie » est un bout de mot (la cible est None)"
    ),
)
def test_extract_ticker_financiere_pas_ciec():
    texte = "Notation de la Societe Financiere de l'Ouest"
    assert _extract_ticker(texte) is None


@pytest.mark.xfail(
    strict=False,
    reason=(
        "B-5 : _extract_rating_info lit « A » au lieu de « A+ » "
        "(pas de frontiere de mot apres le signe +)"
    ),
)
def test_cran_a_plus_conserve():
    info = _extract_rating_info("Note long terme A+ perspective Stable")
    assert info["note"] == "A+"


@pytest.mark.xfail(
    strict=False,
    reason=(
        "B-5 : _extract_rating_info lit « AA » au lieu de « AA- » "
        "(meme defaut de regex que pour A+)"
    ),
)
def test_cran_aa_moins_conserve():
    info = _extract_rating_info("Note long terme AA- perspective Stable")
    assert info["note"] == "AA-"
