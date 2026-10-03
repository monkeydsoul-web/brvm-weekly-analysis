# -*- coding: utf-8 -*-
"""Le JavaScript du tableau de bord est un fichier, servi comme les autres JS."""
import os

import pytest


@pytest.fixture(scope="module")
def client():
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    import app as application
    return application.app.test_client()


def _source_index():
    return os.path.join(os.path.dirname(__file__), "..", "dashboard", "index.html")


def _source_core():
    return os.path.join(os.path.dirname(__file__), "..", "dashboard", "js", "core.js")


def test_source_pointe_core_et_garde_la_carte_prix_cible():
    with open(_source_index(), encoding="utf-8") as f:
        source = f.read()
    assert '<script src="/js/core.js?v={{ASSET_V}}" data-brvm-mod="js/core.js" onerror="brvmScriptError(this)"></script>' in source
    assert source.count("<script>") == 1
    assert 'window.BRVM_ASSET_V="{{ASSET_V}}"' in source
    assert 'id="methodo-prix-cible"' in source
    assert "Le prix cible" in source
    assert "moins du tiers du cours" in source
    assert "function fmtLibelleValeur" not in source
    with open(_source_core(), encoding="utf-8") as f:
        core = f.read()
    assert "function(){ if(typeof loadRankDash==='function') loadRankDash(); }" in core
    assert "function(){ if(typeof loadSignauxValoAlertes==='function') loadSignauxValoAlertes(); }" in core
    assert "Prix cible inférieur au tiers du cours, ou supérieur à 3 fois le cours." in core
    assert "async function init()" in core


def test_core_js_repond_200_javascript(client):
    import app as application
    sans = client.get("/js/core.js")
    assert sans.status_code == 200
    assert "javascript" in (sans.content_type or "")
    assert b"async function init()" in sans.get_data()
    versionne = client.get("/js/core.js?v=%s" % application.ASSET_V)
    assert versionne.status_code == 200
    assert "javascript" in (versionne.content_type or "")
    assert versionne.get_data() == sans.get_data()


def test_core_js_v_different_renvoie_503(client):
    import app as application
    reponse = client.get("/js/core.js?v=pas-cette-instance")
    assert reponse.status_code == 503
    assert "no-store" in (reponse.headers.get("Cache-Control") or "")
    assert application.ASSET_V != "pas-cette-instance"
    assert b"async function init()" not in reponse.get_data()
