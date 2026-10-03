# -*- coding: utf-8 -*-
"""Fiche ouverte avant /api/live : la variation datée apparaît à la réponse.

Hors CI (Playwright n'est pas installé dans le workflow pytest) :

    pip install playwright
    playwright install chromium
    pytest tests/test_fiche_avant_live.py -q -s
"""
import json
import os
import socket
import threading
import time
from datetime import datetime, timezone

import pytest

_REEL_CONNECT = socket.socket.connect
_REEL_CONNECT_EX = socket.socket.connect_ex
_REEL_CREATE = socket.create_connection
_REEL_DNS = socket.getaddrinfo

_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes") or os.environ.get("GITHUB_ACTIONS") == "true"
pytestmark = pytest.mark.skipif(
    _CI,
    reason="Playwright hors CI. Local : pytest tests/test_fiche_avant_live.py -q -s",
)

pytest.importorskip("playwright.sync_api")

_RETARD_S = 4
_SESSION = "2026-10-01"


@pytest.fixture(autouse=True)
def autoriser_local(monkeypatch):
    """Le filet global bloque les sockets. Chromium et Werkzeug restent sur la machine."""
    locaux = ("127.0.0.1", "::1", "localhost")

    def _hote(adresse):
        if isinstance(adresse, tuple) and adresse:
            return adresse[0]
        return adresse

    def connect(self, adresse):
        if _hote(adresse) not in locaux:
            raise RuntimeError("appel reseau interdit dans les tests")
        return _REEL_CONNECT(self, adresse)

    def connect_ex(self, adresse):
        if _hote(adresse) not in locaux:
            raise RuntimeError("appel reseau interdit dans les tests")
        return _REEL_CONNECT_EX(self, adresse)

    def create_connection(adresse, *args, **kwargs):
        if _hote(adresse) not in locaux:
            raise RuntimeError("appel reseau interdit dans les tests")
        return _REEL_CREATE(adresse, *args, **kwargs)

    def getaddrinfo(hote, *args, **kwargs):
        if hote not in locaux and hote not in (None, ""):
            raise RuntimeError("appel reseau interdit dans les tests")
        return _REEL_DNS(hote, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


def _ecrire(nom, payload):
    chemin = os.path.join(os.environ["BRVM_DATA_DIR"], nom)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _caches():
    maintenant = datetime.now(timezone.utc).isoformat()
    _ecrire("live_ranking.json", {
        "updated_at": maintenant,
        "market_open": False,
        "total": 1,
        "ranking": [{
            "ticker": "BICC",
            "name": "BICI CI",
            "sector": "Banque",
            "country": "Côte d'Ivoire",
            "price": 32510,
            "change_pct": -6.56,
            "composite_adj": 61.6,
            "note10": 7.7,
            "statut": "cote",
            "rank": 1,
            "conseil": "acheter",
            "prix_cible": 41000,
        }],
    })
    _ecrire("live_cache.json", {
        "updated_at": maintenant,
        "market_open": False,
        "session_date": _SESSION,
        "seance_ouverte": False,
        "prices": {
            "BICC": {
                "price": 32510,
                "change_pct": -1.57,
                "volume": 1525,
                "source": "brvm.org",
                "session_date": _SESSION,
            },
        },
    })
    _ecrire("market_cache.json", {
        "updated_at": maintenant,
        "session_date": _SESSION,
        "market_activity": {},
        "top5": [],
        "flop5": [],
        "indices": [],
        "sector_indices": [],
        "total_return": {},
    })


class _LiveRetarde(object):
    """Garde /api/live jusqu'au signal. La fiche est déjà peinte pendant l'attente."""

    def __init__(self, app, porte):
        self.app = app
        self.porte = porte

    def __call__(self, environ, start_response):
        if environ.get("PATH_INFO") == "/api/live":
            self.porte.wait(timeout=20)
        return self.app(environ, start_response)


@pytest.fixture
def page_et_porte(autoriser_local):
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    _caches()
    import app as application
    from werkzeug.serving import make_server
    from playwright.sync_api import sync_playwright

    porte = threading.Event()
    serveur = make_server(
        "127.0.0.1", 0, _LiveRetarde(application.app, porte), threaded=True
    )
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    url = "http://127.0.0.1:%d" % serveur.server_address[1]

    pw = sync_playwright().start()
    navigateur = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
    contexte = navigateur.new_context(viewport={"width": 1280, "height": 800})
    onglet = contexte.new_page()
    erreurs = []
    appels = []

    def _console(msg):
        if msg.type == "error":
            erreurs.append(msg.text)

    def _requete(req):
        chemin = req.url.split("?")[0].rstrip("/")
        if chemin.endswith("/api/live"):
            appels.append(req.url)

    onglet.on("pageerror", lambda err: erreurs.append("pageerror: " + str(err)))
    onglet.on("console", _console)
    onglet.on("request", _requete)
    yield onglet, porte, url, erreurs, appels
    contexte.close()
    navigateur.close()
    pw.stop()
    serveur.shutdown()
    assert erreurs == []


def test_fiche_ouverte_avant_live_retarde_affiche_la_variation_datee(page_et_porte):
    page, porte, url, _erreurs, appels = page_et_porte
    page.goto(url + "/societe/BICC", wait_until="domcontentloaded", timeout=20000)
    page.wait_for_function(
        """() => {
          var pageStock = document.getElementById('page-stock');
          var el = document.querySelector('#page-stock [data-var-ticker="BICC"]');
          return pageStock && pageStock.classList.contains('on')
            && el && el.getAttribute('data-var-texte') === '\\u2014'
            && !el.getAttribute('data-var-seance');
        }""",
        timeout=15000,
    )
    time.sleep(_RETARD_S)
    encore = page.evaluate(
        """() => document.querySelector('#page-stock [data-var-ticker="BICC"]').getAttribute('data-var-texte')"""
    )
    assert encore == "\u2014"
    avant = len(appels)
    assert avant >= 1
    porte.set()
    page.wait_for_function(
        """() => {
          var el = document.querySelector('#page-stock [data-var-texte]');
          if (!el) return false;
          var texte = el.getAttribute('data-var-texte') || '';
          var seance = el.getAttribute('data-var-seance') || '';
          return texte.indexOf('1,57') !== -1 && seance.indexOf('s\\u00e9ance du 01/10') !== -1;
        }""",
        timeout=10000,
    )
    page.locator('#page-stock button[data-ctab="chiffres"]').click()
    page.wait_for_function(
        """() => {
          var el = document.querySelector('#page-stock .ctab-panel.active [data-var-ticker="BICC"]');
          if (!el) return false;
          var boite = el.getBoundingClientRect();
          var texte = el.getAttribute('data-var-texte') || '';
          var seance = el.getAttribute('data-var-seance') || '';
          return boite.width > 0 && boite.height > 0
            && texte.indexOf('1,57') !== -1
            && seance.indexOf('s\\u00e9ance du 01/10') !== -1;
        }""",
        timeout=5000,
    )
    etat = page.evaluate(
        """() => {
          var el = document.querySelector('#page-stock .ctab-panel.active [data-var-ticker="BICC"]');
          return {
            pct: variationJour('BICC').pct,
            volume: _variationLive.prices.BICC.volume,
            texte: el.getAttribute('data-var-texte'),
            autour: el.parentElement.parentElement.innerText
          };
        }"""
    )
    assert abs(etat["pct"] - (-1.57)) < 1e-9
    assert etat["volume"] == 1525
    assert "1,57" in etat["texte"] and "1,57" in etat["autour"]
    assert "séance du 01/10" in etat["autour"]
    assert "6,56" not in etat["autour"]
    time.sleep(0.8)
    assert len(appels) == avant
