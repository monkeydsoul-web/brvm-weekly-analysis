# -*- coding: utf-8 -*-
"""LOADJS-1 : le chargeur JS est servi et reference par la page."""
import os
import re

import pytest


MODULES = (
    "js_loader.js",
    "simulator.js",
    "live_score.js",
    "ranking.js",
    "stock_chart.js",
    "badges.js",
    "data_confidence.js",
    "compare.js",
    "alerts.js",
    "screener.js",
    "performance.js",
    "compare_analysis.js",
    "backtest.js",
    "markowitz.js",
    "previsions.js",
    "company-tabs.js",
    "news_v2.js",
    "signaux_v2.js",
    "rank_v2.js",
    "welcome_v2.js",
    "top3_podium.js",
    "screener_lazy.js",
)

MESSAGE = "Cette partie n'a pas pu se charger. Rechargez la page."


@pytest.fixture(scope="module")
def client():
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    import app as application
    return application.app.test_client()


def test_page_reference_le_chargeur(client):
    reponse = client.get("/")
    assert reponse.status_code == 200
    html = reponse.get_data(as_text=True)
    jeton = re.search(r'window\.BRVM_ASSET_V="([^"]+)"', html)
    assert jeton, "jeton de cache absent"
    version = jeton.group(1)
    assert "/js_loader.js?v=%s" % version in html
    assert "brvmScriptError" in html
    balises = re.findall(
        r'<script src="([^"]+)" data-brvm-mod="([^"]+)" onerror="brvmScriptError\(this\)"></script>',
        html,
    )
    assert len(balises) == len(MODULES)
    vus = []
    for src, nom in balises:
        assert src == "/%s?v=%s" % (nom, version)
        vus.append(nom)
    assert tuple(vus) == MODULES
    assert MESSAGE not in html
    assert "function(){ if(typeof loadRankDash==='function') loadRankDash(); }" in html
    assert "function(){ if(typeof loadSignauxValoAlertes==='function') loadSignauxValoAlertes(); }" in html


def test_chargeur_servi_avec_retry_et_message(client):
    reponse = client.get("/js_loader.js?v=test")
    assert reponse.status_code == 200
    assert "javascript" in (reponse.content_type or "")
    corps = reponse.get_data(as_text=True)
    assert MESSAGE in corps
    assert "Recharger" in corps
    assert "var RETRIES = 2;" in corps
    assert "brvmOnScriptError" in corps
    assert "brvmCall" in corps
    assert "rank_v2.js" in corps


def test_modules_versionnes_restent_en_200(client):
    for nom in MODULES:
        reponse = client.get("/%s?v=20260929-1" % nom)
        assert reponse.status_code == 200, nom


def test_api_chat_reste_404(client):
    assert client.get("/api/chat").status_code == 404
    assert client.get("/").status_code == 200
