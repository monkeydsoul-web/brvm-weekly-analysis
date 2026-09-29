# -*- coding: utf-8 -*-
"""Caracterisation de live_ranker._hysteresis_conseil.

Bandes inchangees (D-2) : repere 60 / 40, amortisseur 57,6
(rester Intéressant), 37,6 (sortir d'À surveiller vers Prudence),
42,4 (sortir de Prudence). Les jetons historiques acheter / attendre /
eviter restent des precedents valides. Les libelles renvoyes sont ceux
de D-1.
"""
import pytest

from live_ranker import _hysteresis_conseil


@pytest.mark.parametrize(
    "adj,prev,price,attendu",
    [
        (60, None, 1000, "Intéressant"),
        (59.9, None, 1000, "À surveiller"),
        (40, None, 1000, "À surveiller"),
        (39.9, None, 1000, "Prudence"),
        (80, None, 1000, "Intéressant"),
        (0, None, 1000, "Prudence"),
        (57.6, "acheter", 1000, "Intéressant"),
        (57.5, "acheter", 1000, "À surveiller"),
        (39, "acheter", 1000, "Prudence"),
        (60, "attendre", 1000, "Intéressant"),
        (59.9, "attendre", 1000, "À surveiller"),
        (37.6, "attendre", 1000, "À surveiller"),
        (37.5, "attendre", 1000, "Prudence"),
        (42.3, "eviter", 1000, "Prudence"),
        (42.4, "eviter", 1000, "À surveiller"),
        (60, "eviter", 1000, "Intéressant"),
        (50, "inconnu", 1000, "À surveiller"),
    ],
)
def test_hysteresis_bandes(adj, prev, price, attendu):
    assert _hysteresis_conseil(adj, prev, price) == attendu


@pytest.mark.parametrize("prix", [None, 0, 0.0])
def test_hysteresis_sans_prix(prix):
    assert _hysteresis_conseil(70, "acheter", prix) is None
