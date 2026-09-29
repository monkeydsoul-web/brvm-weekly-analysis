# -*- coding: utf-8 -*-
"""Le CSS du tableau de bord est un fichier, servi en text/css."""
import os

import pytest


@pytest.fixture(scope="module")
def client():
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    import app as application
    return application.app.test_client()


def _source_index():
    return os.path.join(os.path.dirname(__file__), "..", "dashboard", "index.html")


def test_source_pointe_le_css_versionne():
    with open(_source_index(), encoding="utf-8") as f:
        source = f.read()
    assert '<link rel="stylesheet" href="/css/app.css?v={{ASSET_V}}">' in source
    assert "<style>" not in source
    assert "<style " not in source


def test_css_app_repond_200_text_css(client):
    import app as application
    reponse = client.get("/css/app.css")
    assert reponse.status_code == 200
    assert (reponse.content_type or "").startswith("text/css")
    assert "nosniff" in (reponse.headers.get("X-Content-Type-Options") or "")
    assert "no-cache" in (reponse.headers.get("Cache-Control") or "")
    corps = reponse.get_data()
    assert b":root{" in corps
    assert b"#sb-compact-btn{display:none!important}" in corps
    versionne = client.get("/css/app.css?v=%s" % application.ASSET_V)
    assert versionne.status_code == 200
    assert (versionne.content_type or "").startswith("text/css")
    assert versionne.get_data() == corps
    assert "immutable" in (versionne.headers.get("Cache-Control") or "")


def test_page_charge_le_css_au_meme_jeton(client):
    import app as application
    reponse = client.get("/")
    assert reponse.status_code == 200
    html = reponse.get_data(as_text=True)
    assert "/css/app.css?v=%s" % application.ASSET_V in html
    assert "<style>" not in html
    assert client.get("/ranking.js").status_code == 200


def test_css_ne_sort_pas_du_dossier(client):
    for chemin in (
        "/css/../scraper.py",
        "/css/..%2Fscraper.py",
        "/css/app.js",
        "/css/inconnu.css",
    ):
        reponse = client.get(chemin)
        assert reponse.status_code == 404, chemin
        texte = reponse.get_data(as_text=True)
        assert "STOCK_FUNDAMENTALS" not in texte
