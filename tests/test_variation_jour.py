# -*- coding: utf-8 -*-
"""La variation du jour est la même partout, et elle est datée."""
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

import live_data
import live_ranker

ROOT = Path(__file__).resolve().parents[1]
ACCUEIL = (ROOT / "dashboard" / "welcome_v2.js").read_text(encoding="utf-8")


def _page(volume, variation="0"):
    ligne = (
        "<tr><td>BICC</td><td>BICI</td><td>%s</td><td>100</td>"
        "<td>0</td><td>32510</td><td>%s</td></tr>" % (volume, variation)
    )
    return (
        "<html><body><p>Jeudi, 1 octobre, 2026 - 09:04</p>"
        "<table><tr><th>Top 5</th></tr></table>"
        "<table><tr><th>Flop 5</th></tr></table>"
        "<table><tr><th>Autre</th></tr></table>"
        "<table><tr><th>Titre</th></tr>%s</table></body></html>" % ligne
    )


def _get(html):
    class Reponse:
        text = html
        status_code = 200

    def get(url, headers=None, timeout=None):
        return Reponse()

    return get


def test_cours_actions_publient_la_date_et_l_echange(monkeypatch):
    monkeypatch.setattr(live_data.requests, "get", _get(_page("0", "0")))
    prices, session, ouverte = live_data.fetch_brvm_org()
    assert session == "2026-10-01"
    assert ouverte is False
    assert prices["BICC"]["change_pct"] == 0
    assert prices["BICC"]["volume"] == 0

    monkeypatch.setattr(live_data.requests, "get", _get(_page("150", "-6,56%")))
    prices, session, ouverte = live_data.fetch_brvm_org()
    assert session == "2026-10-01"
    assert ouverte is True
    assert prices["BICC"]["change_pct"] == -6.56
    assert prices["BICC"]["volume"] == 150


def test_api_live_range_la_seance_sans_recalcul(monkeypatch, data_dir):
    monkeypatch.setattr(live_data.requests, "get", _get(_page("0", "0")))
    monkeypatch.setattr(live_data, "fetch_live_prices", lambda all_tickers=None: (
        {"BICC": {"price": 32510, "change_pct": 0.0, "volume": 0, "source": "brvm.org"}},
        "2026-09-30",
        False,
    ))
    payload = live_data.get_live_data(force_refresh=True)
    assert payload["session_date"] == "2026-09-30"
    assert payload["seance_ouverte"] is False
    assert payload["prices"]["BICC"]["session_date"] == "2026-09-30"
    assert payload["prices"]["BICC"]["change_pct"] == 0.0
    with open(os.path.join(data_dir, "live_cache.json"), encoding="utf-8") as f:
        disque = json.load(f)
    assert disque["session_date"] == "2026-09-30"
    assert disque["seance_ouverte"] is False


def _ecrire_classement(dossier):
    live_ranker._last_ranking = None
    live_ranker._last_stamp = None
    live_ranker._last_updated_at = None
    payload = {
        "updated_at": "2026-09-30T16:00:00+00:00",
        "ranking": [{
            "ticker": "BICC",
            "name": "BICI CI",
            "note10": 7.7,
            "composite_adj": 61.6,
            "conseil": "acheter",
            "conseil_libelle": "Intéressant",
            "prix_cible": 41000,
            "change_pct": -6.56,
        }],
    }
    with open(os.path.join(dossier, "live_ranking.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return payload


@pytest.fixture
def client():
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    import app as application
    return application.app.test_client()


def test_scores_recoivent_la_date_sans_toucher_au_chiffre(data_dir, client):
    _ecrire_classement(data_dir)
    cache = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "session_date": "2026-09-30",
        "seance_ouverte": False,
        "prices": {"BICC": {"change_pct": 0, "session_date": "2026-09-30"}},
    }
    with open(os.path.join(data_dir, "live_cache.json"), "w", encoding="utf-8") as f:
        json.dump(cache, f)

    rep = client.get("/api/scores")
    assert rep.status_code == 200
    ligne = rep.get_json()[0]
    assert ligne["session_date"] == "2026-09-30"
    assert ligne["change_pct"] == -6.56
    assert ligne["note10"] == 7.7
    assert ligne["conseil"] == "acheter"
    assert ligne["conseil_libelle"] == "Intéressant"
    assert ligne["prix_cible"] == 41000

    brut = live_ranker.load_ranking()["ranking"][0]
    assert "session_date" not in brut
    assert brut["change_pct"] == -6.56
    assert brut["note10"] == 7.7

    os.remove(os.path.join(data_dir, "live_cache.json"))
    live_ranker._last_ranking = None
    live_ranker._last_stamp = None
    live_ranker._last_updated_at = None
    _ecrire_classement(data_dir)
    sans = client.get("/api/scores").get_json()[0]
    assert "session_date" not in sans
    assert sans["change_pct"] == -6.56


def test_une_promesse_par_source_et_six_vues():
    assert ACCUEIL.count("fetch('/api/market'") == 1
    assert ACCUEIL.count("fetch('/api/live'") == 1
    assert "function variationJour" in ACCUEIL
    assert "function demanderVariation" in ACCUEIL
    assert "function redessinerVariations" in ACCUEIL
    if shutil.which("node") is None:
        pytest.skip("node absent")
    fini = subprocess.run(
        ["node", str(Path(__file__).with_name("variation_jour_vues.js"))],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert fini.returncode == 0, fini.stderr or fini.stdout
