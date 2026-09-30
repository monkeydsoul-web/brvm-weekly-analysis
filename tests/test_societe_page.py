# -*- coding: utf-8 -*-
"""D-10 : URL /societe/<TICKER>, liste blanche, pas d'injection HTML."""
import os

import pytest


@pytest.fixture(scope="module")
def client():
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    import app as application
    return application.app.test_client()


def _html(reponse):
    return reponse.get_data(as_text=True)


def test_snts_renvoie_la_page_avec_le_jeton(client):
    import app as application
    reponse = client.get("/societe/SNTS")
    assert reponse.status_code == 200
    assert "no-cache" in (reponse.headers.get("Cache-Control") or "")
    html = _html(reponse)
    assert "{{ASSET_V}}" not in html
    assert 'window.BRVM_ASSET_V="%s"' % application.ASSET_V in html
    assert "/js/core.js?v=%s" % application.ASSET_V in html
    assert 'id="page-stock"' in html
    assert 'id="stockDetail"' in html
    assert "<title>Sonatel (SNTS) – BRVM Analyzer</title>" in html
    assert 'rel="canonical" href="https://brvm-weekly-analysis.onrender.com/societe/SNTS"' in html
    assert "fiche-directe" in html
    assert "Sonatel (SNTS). Fiche de la société cotée à la BRVM." in html


def test_minuscules_canonisees(client):
    reponse = client.get("/societe/snts")
    assert reponse.status_code == 200
    html = _html(reponse)
    assert "/societe/SNTS" in html
    assert "/societe/snts" not in html


def test_note_dans_le_titre(client, monkeypatch):
    import app as application
    monkeypatch.setattr(
        application,
        "load_latest_scores",
        lambda: [{"ticker": "SNTS", "name": "Sonatel", "note10": 7.3, "composite_adj": 58.4}],
    )
    reponse = client.get("/societe/SNTS")
    assert reponse.status_code == 200
    html = _html(reponse)
    assert "<title>Sonatel (SNTS) – note 7,3/10 – BRVM Analyzer</title>" in html
    assert "Sonatel (SNTS), note 7,3/10." in html
    assert 'property="og:title" content="Sonatel (SNTS) – note 7,3/10 – BRVM Analyzer"' in html


def test_inconnu_404_sans_reflet(client):
    reponse = client.get("/societe/XXXX")
    assert reponse.status_code == 404
    corps = _html(reponse)
    assert "XXXX" not in corps
    assert "Sonatel" not in corps


def test_injection_script_404(client):
    reponse = client.get("/societe/<script>alert(1)</script>")
    assert reponse.status_code == 404
    corps = _html(reponse)
    assert "<script>alert" not in corps
    assert "alert(1)" not in corps


def test_injection_attribut_404(client):
    reponse = client.get('/societe/SNTS"><svg onload=alert(1)>')
    assert reponse.status_code == 404
    corps = _html(reponse)
    assert "onload" not in corps
    assert "<svg" not in corps
    assert "alert(1)" not in corps


def test_parametre_non_reflete(client):
    reponse = client.get("/societe/SNTS?q=<script>alert(1)</script>")
    assert reponse.status_code == 200
    assert "alert(1)" not in _html(reponse)


def test_nom_echappe(client, monkeypatch):
    import company_data
    monkeypatch.setitem(
        company_data.COMPANIES["SNTS"],
        "name",
        "Sono<script>alert(1)</script>",
    )
    reponse = client.get("/societe/SNTS")
    assert reponse.status_code == 200
    html = _html(reponse)
    assert "<title>Sono&lt;script&gt;alert(1)&lt;/script&gt; (SNTS) – BRVM Analyzer</title>" in html
    assert "Sono<script>" not in html


def test_accueil_inchange_et_chat_404(client):
    accueil = client.get("/")
    assert accueil.status_code == 200
    html = _html(accueil)
    assert "<title>BRVM Analyzer — Notation des sociétés de la BRVM</title>" in html
    assert "rel=\"canonical\"" not in html
    assert "fiche-directe" not in html
    assert client.get("/api/chat").status_code == 404
    assert client.post("/api/chat").status_code == 404
