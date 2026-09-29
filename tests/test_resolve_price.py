# -*- coding: utf-8 -*-
"""Caracterisation de price_sanity.resolve_price (vote 2-sur-3, +/-20 %)."""
import json

import pytest

from price_sanity import resolve_price


@pytest.mark.parametrize(
    "live,hist,boc,attendu",
    [
        (1000, 1000, None, {"price": 1000.0, "source": "live", "verified": True}),
        (1000, None, 1100, {"price": 1000.0, "source": "live", "verified": True}),
        (1200, 1000, None, {"price": 1200.0, "source": "live", "verified": True}),
        (800, 1000, None, {"price": 800.0, "source": "live", "verified": True}),
        (1201, 1000, None, {"price": None, "source": "quarantaine", "verified": False}),
        (799, 1000, None, {"price": None, "source": "quarantaine", "verified": False}),
        (5000, 1000, 1100, {"price": 1000.0, "source": "repli_aberration", "verified": False}),
        (None, 1000, 1100, {"price": 1000.0, "source": "repli", "verified": False}),
        (None, 1000, 2000, {"price": None, "source": "quarantaine", "verified": False}),
        (1000, 2000, 4000, {"price": None, "source": "quarantaine", "verified": False}),
        (1500, None, None, {"price": 1500.0, "source": "live", "verified": False}),
        (None, 1500, None, {"price": 1500.0, "source": "repli", "verified": False}),
        (0, None, 500, {"price": 500.0, "source": "repli", "verified": False}),
        (None, None, None, {"price": None, "source": "quarantaine", "verified": False}),
        (0, 0, 0, {"price": None, "source": "quarantaine", "verified": False}),
        ("1000", "950", None, {"price": 1000.0, "source": "live", "verified": True}),
        ("n/a", "1000", None, {"price": 1000.0, "source": "repli", "verified": False}),
    ],
)
def test_resolve_price_branches(live, hist, boc, attendu):
    assert resolve_price(live, hist, boc) == attendu


def test_resolve_price_depuis_fixtures(fixtures_dir):
    """Le cours live et la cloture BOC du jeu fige alimentent le meme vote."""
    live = json.loads((fixtures_dir / "live_cache.json").read_text(encoding="utf-8"))
    boc = json.loads((fixtures_dir / "boc_lignes.json").read_text(encoding="utf-8"))
    assert len(boc) == 5

    def prix(ticker):
        return resolve_price(
            live["prices"][ticker]["price"],
            None,
            boc[ticker]["cours_clot"],
        )

    assert prix("ALPH") == {"price": 10000.0, "source": "live", "verified": True}
    assert prix("BRAV") == {"price": 5000.0, "source": "live", "verified": True}
    # Live 20 000 contre cloture BOC 4 000 : aucune confirmation, quarantaine.
    assert prix("CHER") == {"price": None, "source": "quarantaine", "verified": False}
    assert prix("EXCP") == {"price": 8000.0, "source": "repli", "verified": False}
    assert prix("SANS") == {"price": 1500.0, "source": "repli", "verified": False}
