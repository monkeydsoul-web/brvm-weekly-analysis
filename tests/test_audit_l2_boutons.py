# -*- coding: utf-8 -*-
"""AUDIT-L2 : boutons qui ne servaient à rien, retirés plutôt que réparés.

Le test navigateur parcourt le menu à 1280 et 390, en clair et en sombre.
Les captures vont dans tmp_path. Aucun chemin en dur.
"""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes") or os.environ.get("GITHUB_ACTIONS") == "true"

PAGES = (
    ("welcome", "Comprendre la BRVM"),
    ("rank", "Classement complet"),
    ("screener", "Screener avancé"),
    ("marche", "Marché"),
    ("news", "Actualités"),
    ("glossaire", "Glossaire"),
    ("methodo", "méthodologie"),
    ("signals", "Signaux"),
    ("settings", "Paramètres"),
)


def test_boutons_morts_retires_et_sidebar_encore_utilisee():
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    screener = (ROOT / "dashboard" / "screener.js").read_text(encoding="utf-8")
    signaux = (ROOT / "dashboard" / "signaux_v2.js").read_text(encoding="utf-8")
    core = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
    loader = (ROOT / "dashboard" / "js_loader.js").read_text(encoding="utf-8")
    accueil = (ROOT / "dashboard" / "css" / "accueil.css").read_text(encoding="utf-8")

    assert "Export CSV" not in html
    assert "screenerExportCSV" not in html
    assert "function screenerExportCSV" not in screener
    assert "screenerExportCSV" not in loader
    assert "screenerExportCSV" not in core
    assert "let _scrResults = []" in screener

    assert "pageValuation" not in signaux
    assert "pageAlerts" not in signaux
    assert "appendChild(pageValuation)" not in signaux
    assert "injectEpurationSignaux" not in signaux
    assert "function loadSignauxValoAlertes" in signaux
    assert "renderPrevisionsPage" in signaux
    assert "id === 'valuation' || id === 'alerts'" in core
    assert "return nav('signals', pushHistory);" in core
    assert "Vérifier maintenant" not in html
    assert ">Vérifier</button>" not in html

    assert "Activer notifications push" not in html
    assert "requestPushPermission" not in html
    assert "function requestPushPermission" not in core
    assert "function initServiceWorker" not in core
    assert 'id="push-btn"' not in html

    assert "v9.0" not in html
    assert "Mai 2026" not in html
    assert "Changelog v9.0" not in core
    assert ">v14.2</span>" in html
    assert ">v14.2</div>" in html
    assert "n'est plus tenu" in html

    assert "Copiez ce texte" not in core
    assert "navigator.share" in core
    assert "Lien copié" in core
    assert "function _copierLien" in core

    # La barre latérale reste : le classement des tickers (tlItems) sert hors accueil.
    # display:none à 1280 ne concerne que l'accueil. Le mobile (≤768) la cache aussi.
    assert 'id="tlItems"' in html
    assert "<aside class=\"sb\">" in html
    assert "function loadSidebar()" in core
    assert "body:has(#page-welcome.on) .sb{display:none!important}" in accueil
    assert "@media(min-width:769px)" in (ROOT / "dashboard" / "css" / "app.css").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def interdire_reseau_hors_local(monkeypatch):
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


def _ecrire(nom, payload):
    dossier = os.environ.get("BRVM_DATA_DIR")
    if not dossier:
        return None, None
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, nom)
    avant = None
    if os.path.exists(chemin):
        with open(chemin, "rb") as f:
            avant = f.read()
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return chemin, avant


def _restaurer(chemin, avant):
    if not chemin:
        return
    if avant is None:
        if os.path.exists(chemin):
            os.remove(chemin)
        return
    with open(chemin, "wb") as f:
        f.write(avant)


@pytest.fixture(scope="module")
def base_url():
    if _CI:
        pytest.skip("Playwright hors CI")
    pytest.importorskip("playwright.sync_api")
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    maintenant = datetime.now(timezone.utc).isoformat()
    classement, avant_classement = _ecrire("live_ranking.json", {
        "updated_at": maintenant,
        "market_open": False,
        "total": 1,
        "ranking": [{
            "ticker": "SNTS",
            "name": "Sonatel",
            "sector": "Telecoms",
            "price": 43000,
            "composite_adj": 54,
            "note10": 6.8,
            "change_pct": 0.1,
            "div_yield": 1.0,
            "pe_ref": 10,
            "pdf_verdict": "NEUTRE",
            "conseil_libelle": "À surveiller",
            "conseil_couleur": "orange",
        }],
    })
    historique, avant_historique = _ecrire("price_history.json", {})
    marche, avant_marche = _ecrire("market_cache.json", {
        "updated_at": maintenant,
        "market_activity": {"Capitalisation Actions": "10 000"},
        "top5": [],
        "flop5": [],
        "indices": [
            {"name": "BRVM - COMPOSITE", "prev": 200.0, "current": 201.0, "change": 0.5, "ytd": 3.0},
            {"name": "BRVM - 30", "prev": 100.0, "current": 101.0, "change": 1.0, "ytd": 2.0},
        ],
        "sector_indices": [],
        "total_return": {},
    })
    import market_data
    market_data._memoire = None
    market_data._en_cours = False
    import app as application
    from werkzeug.serving import make_server

    serveur = make_server("127.0.0.1", 0, application.app, threaded=True)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    url = "http://127.0.0.1:%d" % serveur.server_address[1]
    yield url
    serveur.shutdown()
    market_data._memoire = None
    market_data._en_cours = False
    _restaurer(classement, avant_classement)
    _restaurer(marche, avant_marche)
    _restaurer(historique, avant_historique)


def _est_marche(url, base):
    return url == base + "/api/market" or url.startswith(base + "/api/market?")


def _cliquer_menu(page, ident, largeur):
    if largeur >= 769:
        if ident in ("glossaire", "methodo"):
            page.click("#topnav-apprendre-btn")
            page.click('#topnav-apprendre-menu button[data-nav="%s"]' % ident)
            return
        if ident == "signals":
            page.click("#topnav-more-btn")
            page.click('#topnav-more-menu button[data-nav="signals"]')
            return
        if ident == "settings":
            page.click('#topnav [data-nav="settings"]')
            return
        lien = page.locator('#topnav-links button[data-nav="%s"]' % ident)
        if lien.count() and lien.is_visible():
            lien.click()
            return
        page.click("#topnav-more-btn")
        page.click('#topnav-more-menu button[data-nav="%s"]' % ident)
        return
    if ident == "settings":
        page.click('#topnav [data-nav="settings"]')
        return
    if ident in ("welcome", "rank", "marche"):
        page.click('#tabbar button[data-nav="%s"]' % ident)
        return
    page.click('#tabbar [data-nav="apprendre"]')
    page.click('#tab-plus button[data-nav="%s"]' % ident)


@pytest.mark.skipif(_CI, reason="Playwright hors CI")
def test_menu_1280_390_clair_sombre(base_url, tmp_path):
    """Chaque entrée du menu, 1 GET /api/market, aucune page blanche, 0 erreur console."""
    from playwright.sync_api import sync_playwright

    preuves = tmp_path
    preuves.mkdir(parents=True, exist_ok=True)
    erreurs = []

    with sync_playwright() as pw:
        navigateur = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            for largeur, theme in ((1280, "clair"), (1280, "sombre"), (390, "clair"), (390, "sombre")):
                contexte = navigateur.new_context(
                    viewport={"width": largeur, "height": 800},
                    color_scheme="dark" if theme == "sombre" else "light",
                )
                page = contexte.new_page()
                market = []

                def _console(msg, _nom="%s-%s" % (largeur, theme)):
                    if msg.type == "error":
                        erreurs.append(_nom + ": " + msg.text)

                page.on("pageerror", lambda err, _nom="%s-%s" % (largeur, theme): erreurs.append(_nom + ": pageerror: " + str(err)))
                page.on("console", _console)
                page.on(
                    "request",
                    lambda req: market.append(req.url)
                    if req.method == "GET" and _est_marche(req.url, base_url)
                    else None,
                )

                def route(route):
                    url = route.request.url
                    if "exchangerate-api.com" in url:
                        route.fulfill(
                            status=200,
                            content_type="application/json",
                            body='{"rates":{"EUR":0.001524,"USD":0.0016}}',
                        )
                        return
                    if not url.startswith(base_url):
                        route.abort()
                        return
                    route.continue_()

                page.route("**/*", route)

                for ident, extrait in PAGES:
                    del market[:]
                    page.goto(base_url + "/", wait_until="load", timeout=20000)
                    page.wait_for_function("() => window._marketData", timeout=10000)
                    if theme == "sombre":
                        page.evaluate("dark = true; _applyTheme();")
                    else:
                        page.evaluate("dark = false; _applyTheme();")
                    assert market == [base_url + "/api/market"], market
                    _cliquer_menu(page, ident, largeur)
                    page.wait_for_function(
                        "(id) => { var p = document.getElementById('page-' + id); return !!(p && p.classList.contains('on')); }",
                        arg=ident,
                        timeout=10000,
                    )
                    assert market == [base_url + "/api/market"], (ident, market)
                    texte = page.locator("#page-" + ident).inner_text()
                    assert extrait in texte, (ident, texte[:180])
                    assert len(" ".join(texte.split())) > 40, ident
                    assert page.locator(".page.on").count() == 1
                    if ident == "screener":
                        assert "Export CSV" not in texte
                    if ident == "signals":
                        assert "Valorisation" not in texte
                        assert "Vérifier maintenant" not in texte
                        assert "Alertes intelligentes" not in texte
                    if ident == "settings":
                        assert "v14.2" in texte
                        assert "notifications push" not in texte
                        assert "Activer notifications" not in texte
                    if largeur == 1280 and theme == "clair" and ident in ("screener", "signals", "settings"):
                        nom = "signaux" if ident == "signals" else ident
                        page.screenshot(path=str(preuves / ("apres-%s-1280-clair.png" % nom)))
                    if largeur == 390 and theme == "sombre" and ident == "signals":
                        page.screenshot(path=str(preuves / "apres-signaux-390-sombre.png"))
                    if largeur == 1280 and theme == "sombre" and ident == "welcome":
                        page.screenshot(path=str(preuves / "apres-accueil-1280-sombre.png"))

                # Anciennes adresses : même document, toujours une seule lecture marché, page Signaux.
                for ancre in ("valuation", "alerts"):
                    del market[:]
                    # Le fragment seul ne recharge pas le document : une query force
                    # un vrai chargement, donc exactement un GET /api/market.
                    page.goto(base_url + "/?p=" + ancre + "#" + ancre, wait_until="load", timeout=20000)
                    page.wait_for_function(
                        "() => document.getElementById('page-signals') && document.getElementById('page-signals').classList.contains('on') && location.hash === '#signals'",
                        timeout=10000,
                    )
                    assert market == [base_url + "/api/market"], (ancre, market)
                    texte = page.locator("#page-signals").inner_text()
                    assert "Signaux" in texte
                    assert len(" ".join(texte.split())) > 40
                    assert "Vérifier maintenant" not in texte
                    assert page.locator("#page-valuation.on").count() == 0
                    assert page.locator("#page-alerts.on").count() == 0

                # Partager : navigator.share s'il existe, sinon le presse-papiers et « Lien copié ».
                page.goto(base_url + "/", wait_until="load", timeout=20000)
                page.wait_for_function("() => typeof _shareStockText === 'function'", timeout=10000)
                partage = page.evaluate(
                    """() => {
                      window.scores = [{
                        ticker: 'SNTS', name: 'Sonatel', note10: 6.8,
                        conseil_libelle: 'À surveiller', conseil_couleur: 'orange',
                        pdf_verdict: 'POSITIF', price: 43000, change_pct: 0.1,
                        pe_ref: 8, div_yield: 6, roe: 20
                      }];
                      var appels = { share: null, copie: null, prompt: 0 };
                      window.prompt = function() { appels.prompt += 1; return ''; };
                      Object.defineProperty(navigator, 'share', {
                        configurable: true,
                        writable: true,
                        value: function(data) {
                          appels.share = data;
                          return Promise.resolve();
                        }
                      });
                      _shareStockText('SNTS');
                      return appels;
                    }"""
                )
                assert partage["prompt"] == 0
                assert partage["share"]["url"].endswith("/societe/SNTS")
                assert "6,8/10" in partage["share"]["text"]
                copie = page.evaluate(
                    """() => new Promise(function(ok) {
                      var appels = { copie: null, prompt: 0, banner: '' };
                      window.prompt = function() { appels.prompt += 1; return ''; };
                      Object.defineProperty(navigator, 'share', {
                        configurable: true,
                        writable: true,
                        value: undefined
                      });
                      Object.defineProperty(navigator, 'clipboard', {
                        configurable: true,
                        writable: true,
                        value: {
                          writeText: function(t) {
                            appels.copie = t;
                            return Promise.resolve();
                          }
                        }
                      });
                      _shareStockText('SNTS');
                      setTimeout(function() {
                        var el = document.getElementById('share-copie-banner');
                        appels.banner = el ? el.textContent : '';
                        ok(appels);
                      }, 50);
                    })"""
                )
                assert copie["prompt"] == 0
                assert copie["copie"].endswith("/societe/SNTS")
                assert copie["banner"] == "Lien copié"
                if largeur == 1280 and theme == "clair":
                    page.screenshot(path=str(preuves / "apres-lien-copie-1280-clair.png"))

                # Changelog aligné sur v14.2, sans l'entrée de mai 2026.
                page.evaluate("showChangelog()")
                journal = page.locator("#changelog-modal").inner_text()
                assert "v14.2" in journal
                assert "v9.0" not in journal
                assert "Mai 2026" not in journal
                if largeur == 1280 and theme == "clair":
                    page.screenshot(path=str(preuves / "apres-changelog-1280-clair.png"))
                page.evaluate("document.getElementById('changelog-modal').style.display='none'")

                # Comparer et Chercher ne vident pas la page.
                if largeur >= 769:
                    page.click("#topnav-more-btn")
                    page.click('#topnav-more-menu button[onclick="navCompare()"]')
                else:
                    page.click('#tabbar [data-nav="apprendre"]')
                    page.click('#tab-plus button[onclick="navCompare()"]')
                page.wait_for_selector("#nav-cmp-overlay", timeout=5000)
                assert page.locator(".page.on").count() == 1
                assert len(" ".join(page.locator(".page.on").inner_text().split())) > 40
                page.click("#nav-cmp-overlay [data-cmp-cancel]")
                if largeur >= 769:
                    page.click(".topnav-search")
                else:
                    page.click('#tabbar [data-nav="chercher"]')
                page.wait_for_selector("#g-search-overlay.open", timeout=5000)
                assert page.locator(".page.on").count() == 1

                contexte.close()
        finally:
            navigateur.close()

    assert erreurs == [], erreurs
    for nom in (
        "apres-screener-1280-clair.png",
        "apres-signaux-1280-clair.png",
        "apres-settings-1280-clair.png",
        "apres-signaux-390-sombre.png",
        "apres-accueil-1280-sombre.png",
        "apres-lien-copie-1280-clair.png",
        "apres-changelog-1280-clair.png",
    ):
        assert (preuves / nom).is_file(), nom
