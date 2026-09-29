# -*- coding: utf-8 -*-
"""Decisions D-1, D-2, D-3.

La note /10 et les libelles D-1 viennent de verdict.py (PR-03).
Le gel a la cloture et le Technique hors seance restent PR-05 :
xfail(strict=False) ou skip.
"""
import math

import pytest

from live_ranker import _compute_scores, _hysteresis_conseil
from live_valuation import score_technique_live

from test_valuation import ROW


def note_affichee(composite):
    """Contrat D-1 : note affichee = composite/8 sur 10.

    Meme arrondi que v10fmt (Math.round(v/8*10)/10), pas le round bancaire Python.
    """
    return math.floor(float(composite) / 8.0 * 10.0 + 0.5) / 10.0


@pytest.mark.parametrize(
    "composite,attendu",
    [
        (0, 0.0),
        (40, 5.0),
        (60, 7.5),
        (80, 10.0),
        (57.6, 7.2),
        (41, 5.1),
    ],
)
def test_d1_formule_note_sur_dix(composite, attendu):
    assert note_affichee(composite) == attendu


@pytest.mark.parametrize(
    "adj,attendu",
    [
        (60, "Intéressant"),
        (80, "Intéressant"),
        (59.9, "À surveiller"),
        (40, "À surveiller"),
        (39.9, "Prudence"),
        (0, "Prudence"),
    ],
)
def test_d1_libelle_selon_composite(adj, attendu):
    assert _hysteresis_conseil(adj, None, 1000) == attendu


def test_d1_compute_scores_expose_note10():
    scores = _compute_scores(dict(ROW))
    assert scores.get("note10") == note_affichee(scores["composite_adj"])


@pytest.mark.xfail(
    strict=False,
    reason=(
        "D-2 non implemente (PR-05) : la note doit rester figee a la cloture ; "
        "le composite change encore avec la variation, le volume et l'ouverture du jour. "
        "L'hysteresis actuelle est couverte par les tests qui passent"
    ),
)
def test_d2_composite_inchange_si_seule_la_seance_change():
    calme = dict(ROW, change_pct=0, open=ROW["price"], volume=0, trend=None, var_annee=0)
    seance = dict(ROW, change_pct=6, open=9000, volume=80000, trend="top", var_annee=0)
    assert _compute_scores(calme)["composite_adj"] == _compute_scores(seance)["composite_adj"]


@pytest.mark.skip(
    reason=(
        "D-2 : ne pas lancer le job de cloture "
        "(importer app.py demarre le scheduler et peut ecrire un classement). "
        "Le comportement cible est porte par "
        "test_d2_composite_inchange_si_seule_la_seance_change (xfail)"
    ),
)
def test_d2_job_cloture_non_lance():
    pass


def test_technique_seance_actuelle():
    """Comportement actuel : la seance change la note Technique (a remplacer en PR-05)."""
    calme = {
        "ticker": "ALPH", "price": 1000, "open": 1000,
        "change_pct": 0, "volume": 0, "var_annee": 0,
    }
    seance = {
        "ticker": "ALPH", "price": 1060, "open": 1000,
        "change_pct": 6, "volume": 50000, "trend": "top", "var_annee": 0,
    }
    assert score_technique_live(calme)["score"] == 2.5
    assert score_technique_live(seance)["score"] == 10.0


@pytest.mark.xfail(
    strict=False,
    reason=(
        "D-3 non implemente (PR-05) : le modele Technique doit etre calcule "
        "sur la cloture de la veille ; score_technique_live note encore la seance "
        "(variation, ouverture, volume, top/flop du jour)"
    ),
)
def test_d3_technique_ignore_la_seance():
    calme = {
        "ticker": "ALPH", "price": 1000, "open": 1000,
        "change_pct": 0, "volume": 0, "var_annee": 0,
    }
    seance = {
        "ticker": "ALPH", "price": 1060, "open": 1000,
        "change_pct": 6, "volume": 50000, "trend": "top", "var_annee": 0,
    }
    assert score_technique_live(calme)["score"] == score_technique_live(seance)["score"]
