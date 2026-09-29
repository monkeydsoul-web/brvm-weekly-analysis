# -*- coding: utf-8 -*-
"""verdict.py : note /10, seuils 60/40, amortisseur, suspension."""
import pytest

from live_ranker import _compute_scores, _hysteresis_conseil
from live_valuation import compute_live_score
from verdict import (
    CONSEIL_INTERESSANT,
    CONSEIL_PRUDENCE,
    CONSEIL_SURVEILLER,
    STATUT_COTE,
    STATUT_NON_NOTE,
    STATUT_SUSPENDU,
    conseil,
    couleur,
    libelle_conseil,
    note10,
)

from test_valuation import ROW


def test_constantes_d1():
    assert CONSEIL_INTERESSANT == "Intéressant"
    assert CONSEIL_SURVEILLER == "À surveiller"
    assert CONSEIL_PRUDENCE == "Prudence"
    assert libelle_conseil() == (
        "Intéressant",
        "À surveiller",
        "Prudence",
    )
    assert couleur() == (7.5, 5.0)
    assert STATUT_COTE == "cote"
    assert STATUT_SUSPENDU == "suspendu"
    assert STATUT_NON_NOTE == "non_note"


@pytest.mark.parametrize(
    "composite,attendu",
    [
        (0, 0.0),
        (39.99, 5.0),
        (40, 5.0),
        (59.99, 7.5),
        (60, 7.5),
        (80, 10.0),
        (57.6, 7.2),
        (41, 5.1),
    ],
)
def test_note10_bornes(composite, attendu):
    assert note10(composite) == attendu


@pytest.mark.parametrize("valeur", [None, "x", True, float("nan")])
def test_note10_invalide(valeur):
    assert note10(valeur) is None


@pytest.mark.parametrize(
    "composite,attendu",
    [
        (60, "Intéressant"),
        (80, "Intéressant"),
        (59.99, "À surveiller"),
        (40, "À surveiller"),
        (39.99, "Prudence"),
        (0, "Prudence"),
    ],
)
def test_conseil_bornes_sans_precedent(composite, attendu):
    assert conseil(composite, None, "cote") == attendu
    assert _hysteresis_conseil(composite, None, 1000) == attendu


@pytest.mark.parametrize(
    "composite,precedent,attendu",
    [
        (57.6, "Intéressant", "Intéressant"),
        (57.6, "acheter", "Intéressant"),
        (57.59, "Intéressant", "À surveiller"),
        (57.59, "acheter", "À surveiller"),
        (39.99, "À surveiller", "À surveiller"),
        (39.99, "attendre", "À surveiller"),
        (37.6, "À surveiller", "À surveiller"),
        (37.59, "attendre", "Prudence"),
        (42.39, "Prudence", "Prudence"),
        (42.39, "eviter", "Prudence"),
        (42.4, "Prudence", "À surveiller"),
        (42.4, "eviter", "À surveiller"),
        (60, "Prudence", "Intéressant"),
        (40, "eviter", "Prudence"),
        (59.99, "inconnu", "À surveiller"),
    ],
)
def test_amortisseur(composite, precedent, attendu):
    assert conseil(composite, precedent, "cote") == attendu


@pytest.mark.parametrize("statut", ["suspendu", "suspendue", "suspended"])
def test_suspendu_sans_conseil(statut):
    assert conseil(80, "Intéressant", statut) is None
    assert conseil(39.99, "acheter", statut) is None
    assert _hysteresis_conseil(80, "acheter", 1000, statut) is None


@pytest.mark.parametrize("statut", ["non_note", "non note", None, "inconnu"])
def test_non_note_sans_conseil(statut):
    assert conseil(60, None, statut) is None


def test_libelle_et_couleur_suivent_la_note():
    assert libelle_conseil("Intéressant") == "Intéressant"
    assert libelle_conseil("acheter") == "Intéressant"
    assert libelle_conseil("attendre") == "À surveiller"
    assert libelle_conseil("eviter") == "Prudence"
    assert libelle_conseil(None) is None
    assert libelle_conseil("autre") is None

    assert couleur(7.5) == "vert"
    assert couleur(10) == "vert"
    assert couleur(7.49) == "orange"
    assert couleur(5) == "orange"
    assert couleur(4.99) == "rouge"
    assert couleur(0) == "rouge"
    assert couleur(None) is None

    # 59,99 reste sous 60 (À surveiller) mais s'affiche 7,5, donc vert.
    assert conseil(59.99, None, "cote") == "À surveiller"
    assert note10(59.99) == 7.5
    assert couleur(note10(59.99)) == "vert"
    # 39,99 est Prudence, affiche 5,0, donc orange.
    assert conseil(39.99, None, "cote") == "Prudence"
    assert note10(39.99) == 5.0
    assert couleur(note10(39.99)) == "orange"


def test_compute_scores_champs_additifs():
    scores = _compute_scores(dict(ROW))
    assert scores["statut"] == "cote"
    assert scores["note10"] == note10(scores["composite_adj"])
    assert scores["conseil"] == conseil(scores["composite_adj"], None, "cote")
    assert scores["conseil_libelle"] == scores["conseil"]
    assert scores["conseil_couleur"] == couleur(scores["note10"])
    assert isinstance(scores["note_calculee_le"], str)
    assert "T" in scores["note_calculee_le"]


def test_compute_scores_suspendu():
    scores = _compute_scores(dict(ROW, statut="suspendu"))
    assert scores["statut"] == "suspendu"
    assert scores["conseil"] is None
    assert scores["conseil_libelle"] is None
    assert scores["conseil_couleur"] is None
    assert scores["note10"] == note10(scores["composite_adj"])


def test_compute_scores_sans_prix():
    scores = _compute_scores(dict(ROW, price=None))
    assert scores["statut"] == "non_note"
    assert scores["conseil"] is None
    assert scores["conseil_libelle"] is None


def test_live_valuation_memes_seuils_sans_amortisseur():
    cache = {
        "prices": {
            "ALPH": {"price": 10000, "change_pct": 0, "volume": 0},
        },
        "market_open": False,
    }
    cote = compute_live_score("ALPH", dict(ROW), cache)
    assert cote["conseil"] == conseil(cote["composite_adj"], None, "cote")
    assert cote["note10"] == note10(cote["composite_adj"])
    assert cote["conseil_libelle"] == cote["conseil"]
    assert cote["statut"] == "cote"
    assert cote["conseil"] in ("Intéressant", "À surveiller", "Prudence")

    suspendu = compute_live_score("ALPH", dict(ROW, statut="suspended"), cache)
    assert suspendu["statut"] == "suspendu"
    assert suspendu["conseil"] is None
    assert suspendu["conseil_libelle"] is None
    assert suspendu["note10"] == note10(suspendu["composite_adj"])
