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


def _source_index():
    return (os.path.join(os.path.dirname(__file__), "..", "dashboard", "index.html"))


def test_source_sans_jeton_manuel():
    with open(_source_index(), encoding="utf-8") as f:
        source = f.read()
    assert "?v=2026" not in source
    assert "{{ASSET_V}}" in source
    assert 'window.BRVM_ASSET_V="{{ASSET_V}}"' in source


def test_page_reference_le_chargeur(client):
    import app as application
    reponse = client.get("/")
    assert reponse.status_code == 200
    assert "no-cache" in (reponse.headers.get("Cache-Control") or "")
    html = reponse.get_data(as_text=True)
    assert "{{ASSET_V}}" not in html
    jeton = re.search(r'window\.BRVM_ASSET_V="([^"]+)"', html)
    assert jeton, "jeton de cache absent"
    version = jeton.group(1)
    assert version == application.ASSET_V
    assert "?v=%s" % version in html
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
    import app as application
    reponse = client.get("/js_loader.js?v=%s" % application.ASSET_V)
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
    import app as application
    for nom in MODULES:
        bon = client.get("/%s?v=%s" % (nom, application.ASSET_V))
        assert bon.status_code == 200, nom
        sans = client.get("/" + nom)
        assert sans.status_code == 200, nom


def test_js_v_different_renvoie_503(client):
    import app as application
    reponse = client.get("/rank_v2.js?v=pas-cette-instance")
    assert reponse.status_code == 503
    assert "no-store" in (reponse.headers.get("Cache-Control") or "")
    assert application.ASSET_V != "pas-cette-instance"


def test_asset_v_commit_ou_empreinte(monkeypatch):
    import app as application
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567890extra")
    assert application._calcul_asset_v() == "abcdef123456"
    monkeypatch.setenv("RENDER_GIT_COMMIT", "")
    empreinte = application._calcul_asset_v()
    assert len(empreinte) == 12
    int(empreinte, 16)


def test_index_html_redirige_vers_la_racine(client):
    from urllib.parse import urlparse
    reponse = client.get("/index.html")
    assert reponse.status_code == 301
    assert urlparse(reponse.headers.get("Location", "")).path == "/"
    assert "{{ASSET_V}}" not in reponse.get_data(as_text=True)
    for chemin in ("/dashboard/index.html", "/foo/index.html"):
        autre = client.get(chemin)
        assert "{{ASSET_V}}" not in autre.get_data(as_text=True)
        assert autre.status_code != 200


def test_api_chat_reste_404(client):
    assert client.get("/api/chat").status_code == 404
    assert client.get("/").status_code == 200
