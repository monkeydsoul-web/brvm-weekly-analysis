# -*- coding: utf-8 -*-
"""LOADJS-1 : un JS bloque affiche le message, sans ReferenceError.

Hors CI (Playwright n'est pas installe dans le workflow pytest) :

    pip install playwright
    playwright install chromium
    pytest tests/test_loadjs_browser.py -q -s

En CI (variable CI=true), ce module est ignore.
"""
import os
import threading

import pytest

_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes") or os.environ.get("GITHUB_ACTIONS") == "true"
pytestmark = pytest.mark.skipif(
    _CI,
    reason="Playwright hors CI. Local : pytest tests/test_loadjs_browser.py -q -s",
)

pytest.importorskip("playwright.sync_api")

MESSAGE = "Cette partie n'a pas pu se charger. Rechargez la page."


@pytest.fixture(autouse=True)
def interdire_reseau_et_cle():
    """Le serveur local et Chromium ont besoin des sockets. Le filet reseau du conftest est leve ici."""
    yield


@pytest.fixture(scope="module")
def base_url():
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    import app as application
    from werkzeug.serving import make_server

    serveur = make_server("127.0.0.1", 0, application.app, threaded=True)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    url = "http://127.0.0.1:%d" % serveur.server_address[1]
    yield url
    serveur.shutdown()


class _Session(object):
    """Page Playwright. Les erreurs JS restent sur l'objet apres la fermeture."""

    def __init__(self, base_url, bloquer):
        self.base_url = base_url
        self.bloquer = bloquer
        self.erreurs = []
        self.page = None
        self._pw = None
        self._navigateur = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._navigateur = self._pw.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = self._navigateur.new_page()
        page.on("pageerror", lambda err: self.erreurs.append(str(err)))
        base = self.base_url
        bloquer = self.bloquer

        def route(route):
            url = route.request.url
            if not url.startswith(base):
                route.abort()
                return
            if bloquer(url):
                route.abort()
                return
            route.continue_()

        page.route("**/*", route)
        page.goto(base + "/#rank", wait_until="domcontentloaded", timeout=20000)
        self.page = page
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._navigateur:
            self._navigateur.close()
        if self._pw:
            self._pw.stop()
        return False


def test_js_bloque_affiche_le_message(base_url):
    from playwright.sync_api import expect

    with _Session(base_url, lambda url: "rank_v2.js" in url) as session:
        page = session.page
        cadre = page.locator("#page-rank [data-brvm-fallback]")
        expect(cadre).to_be_visible(timeout=10000)
        assert MESSAGE in cadre.inner_text()
        assert cadre.locator("button").count() == 1
        assert "Classement complet" in page.locator("#page-rank").inner_text()
        assert page.locator("#page-screener [data-brvm-fallback]").count() == 0
        assert "Screener" in page.locator("#page-screener").inner_text()
    assert [e for e in session.erreurs if "ReferenceError" in e] == []
    assert session.erreurs == []


def test_retry_recharge_le_module(base_url):
    from playwright.sync_api import expect

    compte = {"n": 0}

    def bloquer(url):
        if "rank_v2.js" not in url:
            return False
        compte["n"] += 1
        return compte["n"] == 1

    with _Session(base_url, bloquer) as session:
        page = session.page
        page.wait_for_function(
            "() => window.BRVM_MODULES && window.BRVM_MODULES['rank_v2.js'] === 'ok'",
            timeout=10000,
        )
        expect(page.locator("#page-rank [data-brvm-fallback]")).to_have_count(0)
        est_stub = page.evaluate("() => !!(window.loadRankDash && window.loadRankDash._brvmStub)")
        assert est_stub is False
    assert session.erreurs == []


def test_chargement_complet_sans_message(base_url):
    from playwright.sync_api import expect

    with _Session(base_url, lambda url: False) as session:
        page = session.page
        page.wait_for_timeout(1500)
        expect(page.locator("[data-brvm-fallback]")).to_have_count(0)
        assert page.evaluate("() => window.BRVM_ASSET_V") == "20260929-1"
    assert session.erreurs == []
