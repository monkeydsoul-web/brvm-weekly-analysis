# -*- coding: utf-8 -*-
"""Caracterisation de live_ranker._hysteresis_conseil (comportement actuel).

Bandes : repere 60 / 40, amortisseur 57,6 (rester acheter),
37,6 (sortir d'attendre vers eviter), 42,4 (sortir d'eviter).
"""
import pytest

from live_ranker import _hysteresis_conseil


@pytest.mark.parametrize(
    "adj,prev,price,attendu",
    [
        (60, None, 1000, "acheter"),
        (59.9, None, 1000, "attendre"),
        (40, None, 1000, "attendre"),
        (39.9, None, 1000, "eviter"),
        (80, None, 1000, "acheter"),
        (0, None, 1000, "eviter"),
        (57.6, "acheter", 1000, "acheter"),
        (57.5, "acheter", 1000, "attendre"),
        (39, "acheter", 1000, "eviter"),
        (60, "attendre", 1000, "acheter"),
        (59.9, "attendre", 1000, "attendre"),
        (37.6, "attendre", 1000, "attendre"),
        (37.5, "attendre", 1000, "eviter"),
        (42.3, "eviter", 1000, "eviter"),
        (42.4, "eviter", 1000, "attendre"),
        (60, "eviter", 1000, "acheter"),
        (50, "inconnu", 1000, "attendre"),
    ],
)
def test_hysteresis_bandes(adj, prev, price, attendu):
    assert _hysteresis_conseil(adj, prev, price) == attendu


@pytest.mark.parametrize("prix", [None, 0, 0.0])
def test_hysteresis_sans_prix(prix):
    assert _hysteresis_conseil(70, "acheter", prix) is None
