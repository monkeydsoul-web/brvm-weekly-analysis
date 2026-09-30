# -*- coding: utf-8 -*-
"""D-10 : 301, retour vers /#page, ticker hors classement, pas de hash sous /societe/."""
import json
import os
import threading
from datetime import datetime, timezone

import pytest

_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes") or os.environ.get("GITHUB_ACTIONS") == "true"
pytestmark = pytest.mark.skipif(
    _CI,
    reason="Playwright hors CI. Local : pytest tests/test_societe_historique.py -q -s",
)

pytest.importorskip("playwright.sync_api")


@pytest.fixture(autouse=True)
def autoriser_local(monkeypatch):
    """Le filet global bloque les sockets. Chromium et Werkzeug restent sur la machine."""
    import socket

    reel_connect = socket.socket.connect
    reel_connect_ex = socket.socket.connect_ex
    reel_create = socket.create_connection
    reel_dns = socket.getaddrinfo
    locaux = ("127.0.0.1", "::1", "localhost")

    def _hote(adresse):
        if isinstance(adresse, tuple) and adresse:
            return adresse[0]
        return adresse

    def connect(self, adresse):
        if _hote(adresse) not in locaux:
            raise RuntimeError("appel reseau interdit dans les tests")
        return reel_connect(self, adresse)

    def connect_ex(self, adresse):
        if _hote(adresse) not in locaux:
            raise RuntimeError("appel reseau interdit dans les tests")
        return reel_connect_ex(self, adresse)

    def create_connection(adresse, *args, **kwargs):
        if _hote(adresse) not in locaux:
            raise RuntimeError("appel reseau interdit dans les tests")
        return reel_create(adresse, *args, **kwargs)

    def getaddrinfo(hote, *args, **kwargs):
        if hote not in locaux and hote not in (None, ""):
            raise RuntimeError("appel reseau interdit dans les tests")
        return reel_dns(hote, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


def _ecrire_caches():
    dossier = os.environ["BRVM_DATA_DIR"]
    maintenant = datetime.now(timezone.utc).isoformat()
    classement = os.path.join(dossier, "live_ranking.json")
    with open(classement, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": maintenant,
            "market_open": False,
            "total": 2,
            "ranking": [
                {
                    "ticker": "ETIT",
                    "name": "Ecobank Transnational",
                    "sector": "Banque",
                    "country": "Togo",
                    "price": 20,
                    "change_pct": 0.1,
                    "composite_adj": 48,
                    "note10": 6.0,
                    "statut": "cote",
                    "rank": 2,
                },
                {
                    "ticker": "SNTS",
                    "name": "Sonatel Senegal",
                    "sector": "Telecoms",
                    "country": "Senegal",
                    "price": 17500,
                    "change_pct": 0.4,
                    "composite_adj": 58.4,
                    "note10": 7.3,
                    "statut": "cote",
                    "rank": 1,
                },
            ],
        }, f)
    with open(os.path.join(dossier, "market_cache.json"), "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": maintenant,
            "top5": [{"ticker": "BBGC", "change": 1.2}, {"ticker": "SNTS", "change": 0.4}],
            "flop5": [{"ticker": "ETIT", "change": -0.3}],
            "indices": [
                {"name": "BRVM COMPOSITE", "current": 250, "change": 0.1},
                {"name": "BRVM 30", "current": 140, "change": -0.1},
            ],
        }, f)
    return classement


@pytest.fixture(scope="module")
def base_url():
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    classement = _ecrire_caches()
    import app as application
    from werkzeug.serving import make_server

    serveur = make_server("127.0.0.1", 0, application.app, threaded=True)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    url = "http://127.0.0.1:%d" % serveur.server_address[1]
    yield url
    serveur.shutdown()
    dossier = os.environ.get("BRVM_DATA_DIR")
    if dossier:
        for nom in ("live_ranking.json", "market_cache.json"):
            chemin = os.path.join(dossier, nom)
            if os.path.exists(chemin):
                os.remove(chemin)
    if classement and os.path.exists(classement):
        os.remove(classement)


@pytest.fixture(scope="module")
def navigateur():
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
    yield browser
    browser.close()
    pw.stop()


@pytest.fixture
def page(navigateur, base_url):
    erreurs = []
    contexte = navigateur.new_context(viewport={"width": 1280, "height": 800})
    onglet = contexte.new_page()

    def _console(msg):
        if msg.type == "error":
            erreurs.append(msg.text)

    onglet.on("pageerror", lambda err: erreurs.append("pageerror: " + str(err)))
    onglet.on("console", _console)
    onglet.base = base_url
    yield onglet
    contexte.close()
    assert erreurs == []


def test_parcours_retour_sur_le_classement(page):
    page.goto(page.base + "/societe/ETIT", wait_until="domcontentloaded", timeout=20000)
    page.wait_for_function(
        """() => location.pathname === '/societe/ETIT'
          && document.title.indexOf('Ecobank Transnational (ETIT)') === 0
          && document.title.indexOf('Ecobank Togo') === -1
          && document.getElementById('page-stock').classList.contains('on')""",
        timeout=20000,
    )
    page.locator("button[data-nav='rank']").first.click()
    page.wait_for_function(
        """() => location.pathname === '/' && location.hash === '#rank'
          && location.href.indexOf('/societe/') === -1
          && document.getElementById('page-rank').classList.contains('on')""",
        timeout=10000,
    )
    page.evaluate("_openStock('SNTS')")
    page.wait_for_function(
        """() => location.pathname === '/societe/SNTS'
          && document.title.indexOf('Sonatel Senegal (SNTS)') === 0
          && document.getElementById('page-stock').classList.contains('on')""",
        timeout=15000,
    )
    page.go_back(wait_until="domcontentloaded")
    page.wait_for_function(
        """() => location.pathname === '/' && location.hash === '#rank'
          && document.getElementById('page-rank').classList.contains('on')
          && !document.getElementById('page-stock').classList.contains('on')""",
        timeout=10000,
    )
    page.go_forward(wait_until="domcontentloaded")
    page.wait_for_function(
        """() => location.pathname === '/societe/SNTS'
          && document.getElementById('page-stock').classList.contains('on')
          && (document.getElementById('stockDetail').innerText || '').indexOf('SNTS') !== -1""",
        timeout=15000,
    )


def test_minuscules_ne_bouclent_pas(page):
    page.goto(page.base + "/#rank", wait_until="domcontentloaded", timeout=20000)
    page.wait_for_function("() => location.hash === '#rank'", timeout=10000)
    page.goto(page.base + "/societe/snts", wait_until="domcontentloaded", timeout=20000)
    page.wait_for_function(
        "() => location.pathname === '/societe/SNTS'",
        timeout=15000,
    )
    page.go_back(wait_until="domcontentloaded")
    page.wait_for_function(
        "() => location.pathname === '/' && location.hash === '#rank'",
        timeout=10000,
    )
    page.wait_for_timeout(1200)
    assert page.evaluate("() => location.pathname + location.hash") == "/#rank"


def test_bbgc_sans_url_societe(page):
    page.goto(page.base + "/societe/SNTS", wait_until="domcontentloaded", timeout=20000)
    page.wait_for_function(
        "() => location.pathname === '/societe/SNTS' && document.title.indexOf('Sonatel Senegal') === 0",
        timeout=20000,
    )
    page.evaluate("_openStock('BBGC')")
    page.wait_for_function(
        """() => (document.getElementById('stockDetail').innerText || '').indexOf('Ticker non trouvé') !== -1""",
        timeout=15000,
    )
    etat = page.evaluate(
        """() => ({
          url: location.pathname + location.hash,
          titre: document.title,
          canon: (document.querySelector('link[rel="canonical"]') || {getAttribute: function(){return '';}}).getAttribute('href') || ''
        })"""
    )
    assert etat["url"] == "/"
    assert "/societe/BBGC" not in etat["url"]
    assert "BBGC" not in etat["titre"]
    assert "Sonatel" not in etat["titre"]
    assert "/societe/" not in etat["canon"]


def test_welcome_ne_reste_pas_sous_societe(page):
    page.goto(page.base + "/societe/SNTS", wait_until="domcontentloaded", timeout=20000)
    page.wait_for_function("() => location.pathname === '/societe/SNTS'", timeout=20000)
    page.evaluate("nav('welcome')")
    page.wait_for_function(
        "() => location.pathname === '/' && location.hash === '#welcome' && location.href.indexOf('/societe/') === -1",
        timeout=10000,
    )
    page.goto(page.base + "/societe/ETIT#welcome", wait_until="domcontentloaded", timeout=20000)
    page.wait_for_function(
        "() => location.pathname === '/' && location.hash === '#welcome' && location.href.indexOf('/societe/') === -1",
        timeout=10000,
    )
