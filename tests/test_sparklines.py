# -*- coding: utf-8 -*-
"""SPARK-1 : /api/sparklines lit price_history.json.

30 dernieres clotures reelles par action (prix > 0, pas de synthetique,
pas de week-end), sortie {date, close}, cache sur le mtime du fichier.
"""
import json
import logging
import os
import time
from datetime import date, timedelta

import pytest


def _historique():
    """SNTS : 60 jours civils (week-ends compris), SGBC : 3 points, ORAC : rien de valide."""
    debut = date.today() - timedelta(days=200)
    snts = []
    for i in range(60):
        jour = debut + timedelta(days=i)
        snts.append({"date": jour.isoformat(), "price": 25000 + i, "source": "live"})
    snts.append({"date": (debut + timedelta(days=61)).isoformat(), "price": 0, "source": "live"})
    snts.append({"date": (debut + timedelta(days=62)).isoformat(), "price": 1, "source": "synthetic"})
    snts.reverse()  # ordre du fichier sans importance
    sgbc = [
        {"date": "2026-05-18", "price": 30000, "source": "live"},
        {"date": "2026-05-19", "price": 30100, "source": "live"},
        {"date": "2026-05-20", "price": 30200, "source": "live"},
    ]
    orac = [{"date": "2026-05-16", "price": 14000, "source": "live"}]  # samedi
    return {"SNTS": snts, "SGBC": sgbc, "ORAC": orac}


@pytest.fixture
def client_sparklines(data_dir, monkeypatch):
    import app as application
    import price_history_builder

    chemin = os.path.join(data_dir, "price_history.json")
    monkeypatch.setattr(price_history_builder, "HISTORY_PATH", chemin)
    avant = open(chemin, "rb").read() if os.path.exists(chemin) else None
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(_historique(), f)
    application._SPARKLINES_CACHE = None
    yield application.app.test_client(), chemin
    application._SPARKLINES_CACHE = None
    if avant is None:
        os.remove(chemin)
    else:
        with open(chemin, "wb") as f:
            f.write(avant)


def _derniere_cloture_fichier(chemin, ticker):
    with open(chemin, encoding="utf-8") as f:
        pts = json.load(f)[ticker]
    valides = [
        p for p in pts
        if (p.get("price") or 0) > 0
        and p.get("source") != "synthetic"
        and date.fromisoformat(p["date"]).weekday() < 5
    ]
    dernier = max(valides, key=lambda p: p["date"])
    return {"date": dernier["date"], "close": float(dernier["price"])}


def test_sparklines_lit_price_history(client_sparklines):
    client, chemin = client_sparklines
    r = client.get("/api/sparklines")
    assert r.status_code == 200
    d = r.get_json()
    assert sorted(d) == ["SGBC", "SNTS"]
    assert len(d["SNTS"]) == 30
    assert len(d["SGBC"]) == 3
    for pts in d.values():
        assert all(set(p) == {"date", "close"} for p in pts)
        assert all(p["close"] > 0 for p in pts)
        assert all(date.fromisoformat(p["date"]).weekday() < 5 for p in pts)
        assert [p["date"] for p in pts] == sorted(p["date"] for p in pts)
    for ticker in ("SNTS", "SGBC"):
        assert d[ticker][-1] == _derniere_cloture_fichier(chemin, ticker)


def test_sparklines_cache_sur_mtime(client_sparklines, caplog):
    client, chemin = client_sparklines
    caplog.set_level(logging.INFO, logger="app")
    t0 = time.perf_counter()
    for _ in range(3):
        assert client.get("/api/sparklines").status_code == 200
    assert time.perf_counter() - t0 < 0.2
    recalculs = [m for m in caplog.messages if m.startswith("SPARK-1: recalcul sparklines")]
    assert recalculs == ["SPARK-1: recalcul sparklines (2 tickers)"]

    mtime = os.path.getmtime(chemin)
    os.utime(chemin, (mtime + 5, mtime + 5))
    client.get("/api/sparklines")
    client.get("/api/sparklines")
    recalculs = [m for m in caplog.messages if m.startswith("SPARK-1: recalcul sparklines")]
    assert len(recalculs) == 2


def test_sparklines_fichier_illisible_sert_le_cache(client_sparklines, caplog):
    client, chemin = client_sparklines
    bon = client.get("/api/sparklines").get_json()
    with open(chemin, "w", encoding="utf-8") as f:
        f.write("{" + "x" * 200)
    mtime = os.path.getmtime(chemin)
    os.utime(chemin, (mtime + 5, mtime + 5))
    caplog.set_level(logging.WARNING, logger="app")
    assert client.get("/api/sparklines").get_json() == bon
    assert any("SPARK-1:" in m and "illisible ou vide" in m for m in caplog.messages)
    import app as application
    assert application._SPARKLINES_CACHE[1] == bon
