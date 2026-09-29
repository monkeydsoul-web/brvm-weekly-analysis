# -*- coding: utf-8 -*-
"""Decisions D-1, D-2, D-3.

La note /10 et les libelles D-1 viennent de verdict.py (PR-03).
D-3 : le Technique ignore la seance (clotures et liquidite moyenne).
D-2 : le composite ne bouge pas si seule la seance change.
Le gel du classement en seance est couvert par tests/test_note_figee.py.
"""
import math
from datetime import datetime, timezone

import pytest

from live_ranker import _compute_scores, _hysteresis_conseil, doit_recalculer_note
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
        (59.9, "Intéressant"),
        (40, "À surveiller"),
        (39.9, "À surveiller"),
        (0, "Prudence"),
    ],
)
def test_d1_libelle_selon_composite(adj, attendu):
    assert _hysteresis_conseil(adj, None, 1000) == attendu


def test_d1_compute_scores_expose_note10():
    scores = _compute_scores(dict(ROW))
    assert scores.get("note10") == note_affichee(scores["composite_adj"])


def test_d2_composite_inchange_si_seule_la_seance_change():
    calme = dict(ROW, change_pct=0, open=ROW["price"], volume=0, trend=None, var_annee=0)
    seance = dict(ROW, change_pct=6, open=9000, volume=80000, trend="top", var_annee=0)
    assert _compute_scores(calme)["composite_adj"] == _compute_scores(seance)["composite_adj"]


def test_d2_job_cloture_non_lance():
    """Decision pure : aucun job, aucune ecriture de classement."""
    seance = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    apres = datetime(2026, 9, 29, 15, 35, tzinfo=timezone.utc)
    samedi = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
    payload = {
        "note_formule": "cloture-v1",
        "faits_empreinte": "fixe",
        "note_calculee_le": "2026-09-28T16:00:00+00:00",
        "ranking": [{
            "ticker": "ALPH",
            "composite_adj": 50,
            "note_calculee_le": "2026-09-28T16:00:00+00:00",
        }],
    }
    assert doit_recalculer_note(payload, seance, "fixe") is False
    assert doit_recalculer_note(payload, apres, "fixe") is True
    assert doit_recalculer_note(payload, seance, "boc-nouveau") is True
    # Samedi : pas de recalcul si la note est deja celle du vendredi soir.
    # Si la cloture du vendredi a ete manque, le week-end rattrape une fois.
    a_jour = dict(payload, note_calculee_le="2026-10-02T16:00:00+00:00")
    assert doit_recalculer_note(a_jour, samedi, "fixe") is False
    assert doit_recalculer_note(payload, samedi, "fixe") is True
    # Fichier d'avant la formule : on garde la note en seance, on recalcule marche ferme.
    ancien = dict(payload)
    ancien.pop("note_formule")
    assert doit_recalculer_note(ancien, seance, "fixe") is False
    assert doit_recalculer_note(ancien, apres, "fixe") is True


def _seance(ticker="ALPH"):
    return {
        "ticker": ticker, "price": 1060, "open": 1000,
        "change_pct": 6, "volume": 50000, "trend": "top", "var_annee": 40,
        "historique_clotures": [],
    }


def test_technique_sans_historique_est_neutre():
    """Pas de clotures : milieu de note, pas la punition volume 0 d'avant seance."""
    calme = {
        "ticker": "ALPH", "price": 1000, "open": 1000,
        "change_pct": 0, "volume": 0, "var_annee": 0,
        "historique_clotures": [],
    }
    seance = _seance()
    assert score_technique_live(calme)["score"] == 5.0
    assert score_technique_live(seance)["score"] == 5.0
    assert "historique insuffisant" in score_technique_live(calme)["details"]
    assert "volumes insuffisants" in score_technique_live(calme)["details"]


def test_d3_technique_ignore_la_seance():
    calme = {
        "ticker": "ALPH", "price": 1000, "open": 1000,
        "change_pct": 0, "volume": 0, "var_annee": 0,
        "historique_clotures": [],
    }
    seance = _seance()
    assert score_technique_live(calme)["score"] == score_technique_live(seance)["score"]


def _clotures(n, prix_de, prix_vers, volume=None):
    points = []
    for i in range(n):
        if n == 1:
            prix = prix_vers
        else:
            prix = prix_de + (prix_vers - prix_de) * i / float(n - 1)
        point = {"date": "2026-08-%02d" % (i + 1), "price": prix}
        if volume is not None:
            point["volume"] = volume
        points.append(point)
    return points


def test_technique_tendance_et_liquidite_sur_clotures():
    moment = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    hausse = {
        "ticker": "ALPH", "price": 9999, "change_pct": -8, "volume": 0,
        "open": 1, "trend": "flop", "var_annee": -40,
        "historique_clotures": _clotures(30, 100, 130, volume=20000),
        "_moment": moment,
    }
    baisse = dict(hausse, historique_clotures=_clotures(30, 100, 80, volume=20000))
    assert score_technique_live(hausse)["score"] == 10.0
    assert score_technique_live(baisse)["score"] == 3.0
    assert "30 séances" in score_technique_live(hausse)["details"]


def test_technique_historique_court_signale():
    moment = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    court = {
        "ticker": "ALPH", "price": 1000,
        "historique_clotures": _clotures(8, 100, 110, volume=5000),
        "_moment": moment,
    }
    resultat = score_technique_live(court)
    assert "historique court" in resultat["details"]
    assert "historique insuffisant" not in resultat["details"]


def test_technique_cloture_du_jour_apres_15h30():
    moment = datetime(2026, 9, 29, 15, 35, tzinfo=timezone.utc)
    base = {
        "ticker": "ALPH",
        "historique_clotures": _clotures(29, 100, 100, volume=20000),
        "_moment": moment,
        "change_pct": 30, "volume": 1, "open": 100, "trend": "top",
    }
    sans = dict(base, price=130, _inclure_cloture_du_jour=False)
    avec = dict(base, price=130, _inclure_cloture_du_jour=True)
    assert score_technique_live(sans)["score"] == 6.5
    assert score_technique_live(avec)["score"] == 10.0
