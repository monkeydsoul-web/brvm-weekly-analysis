# -*- coding: utf-8 -*-
"""AUDIT-L2 : boutons qui ne servaient à rien, retirés plutôt que réparés.

Le test navigateur parcourt le menu à 1280 et 390, en clair et en sombre.
Les captures vont dans tmp_path. Aucun chemin en dur.
"""
import json
import os
import subprocess
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

    assert "function injectEpurationSignaux" in signaux
    assert "appendChild(pageValuation)" in signaux
    assert "function loadSignauxValoAlertes" in signaux
    assert "injectEpurationSignaux: \"signaux_v2.js\"" in loader
    assert "function verifierAlertesMaintenant" in core
    assert "Vérifier maintenant" in html
    assert "renderSmartAlertsPanel()" not in html
    assert ">Vérifier</button>" not in html
    assert "id === 'valuation' || id === 'alerts'" not in core

    assert "Activer notifications push" not in html
    assert "arrière-plan" not in html
    assert "requestPushPermission" not in html
    assert "function requestPushPermission" not in core
    assert "function initServiceWorker" not in core
    assert "function _updatePushUI" not in core
    assert "function _setupSWMessaging" not in core
    assert "function triggerSWAlertCheck" not in core
    assert "function testPushNotification" not in core
    assert "initServiceWorker()" not in core
    assert "desinstallerServiceWorkerPrix" in core
    assert 'id="push-btn"' not in html
    sw = (ROOT / "dashboard" / "sw.js").read_text(encoding="utf-8")
    assert "skipWaiting" in sw
    assert "brvm-sw-" in sw
    assert "unregister" in sw
    assert "addEventListener('fetch'" not in sw
    assert "setInterval" not in sw
    assert "postMessage" not in sw
    assert "clients.openWindow" not in sw

    assert "v9.0" in html
    assert "Mai 2026" in html
    assert "Changelog v9.0" in core
    assert "Copiez ce texte" in core
    assert "Copié !" in core

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
                        assert "Valorisation" in texte
                        assert "Alertes" in texte
                        assert "Vérifier maintenant" in texte
                        assert "alerte intelligente" in texte.lower()
                        assert page.evaluate(
                            "() => Array.from(document.querySelectorAll('button')).every(b => b.textContent.trim() !== 'Vérifier')"
                        )
                        page.locator("text=Vérifier maintenant").scroll_into_view_if_needed()
                    if ident == "settings":
                        assert "v14.2" in texte
                        assert "notifications push" not in texte
                        assert "Activer notifications" not in texte
                        assert "arrière-plan" not in texte
                    if ident == "signals" and largeur == 1280 and theme == "clair":
                        def _prix(route):
                            route.fulfill(
                                status=200,
                                content_type="application/json",
                                body='{"prices":{"SNTS":{"price":50000}}}',
                            )
                        page.route("**/api/live", _prix)
                        page.evaluate("setAlert('SNTS', 1, 'above'); renderAlertsPanel();")
                        page.click("text=Vérifier maintenant")
                        page.wait_for_function(
                            "() => { var el = document.getElementById('alertsList'); return !!(el && el.innerText.indexOf('Déclenchée') !== -1); }",
                            timeout=10000,
                        )
                        page.unroute("**/api/live")
                    if largeur == 1280 and theme == "clair" and ident in ("screener", "signals", "settings"):
                        nom = "signaux" if ident == "signals" else ident
                        page.screenshot(path=str(preuves / ("apres-%s-1280-clair.png" % nom)))
                    if largeur == 390 and theme == "clair" and ident == "signals":
                        page.screenshot(path=str(preuves / "apres-signaux-390-clair.png"))
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
                    assert "Valorisation" in texte
                    assert "Vérifier maintenant" in texte
                    assert len(" ".join(texte.split())) > 40
                    assert page.locator("#page-valuation.on").count() == 0
                    assert page.locator("#page-alerts.on").count() == 0

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
        "apres-signaux-390-clair.png",
        "apres-signaux-390-sombre.png",
        "apres-accueil-1280-sombre.png",
    ):
        assert (preuves / nom).is_file(), nom


def _etat_worker(page):
    return page.evaluate(
        """async () => {
          var regs = await navigator.serviceWorker.getRegistrations();
          var cles = await caches.keys();
          return {
            regs: regs.map(function (r) {
              var w = r.active || r.waiting || r.installing;
              return w ? w.scriptURL : '';
            }),
            cles: cles
          };
        }"""
    )


def _afficher_etat(page, titre, etat):
    page.evaluate(
        """(payload) => {
          var pre = document.getElementById('preuve-sw');
          if (!pre) {
            pre = document.createElement('pre');
            pre.id = 'preuve-sw';
            pre.style.cssText = 'position:fixed;inset:24px;z-index:99999;background:#fff;color:#111;padding:16px;font:16px/1.45 ui-monospace,monospace;overflow:auto;border:2px solid #111';
            document.body.appendChild(pre);
          }
          pre.textContent = payload.titre + '\\n' + JSON.stringify(payload.etat, null, 2);
        }""",
        {"titre": titre, "etat": etat},
    )


@pytest.mark.skipif(_CI, reason="Playwright hors CI")
def test_ancien_worker_desinstalle_et_cache_efface(base_url, tmp_path):
    """Local : l'ancien sw.js de c370954 est installé, puis une visite le retire."""
    from playwright.sync_api import sync_playwright

    ancien = subprocess.check_output(
        ["git", "show", "c370954:dashboard/sw.js"],
        cwd=str(ROOT),
    )
    servir_ancien = {"on": True}
    erreurs = []

    with sync_playwright() as pw:
        navigateur = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        contexte = navigateur.new_context(viewport={"width": 1280, "height": 800})
        page = contexte.new_page()
        page.on("pageerror", lambda err: erreurs.append("pageerror: " + str(err)))
        page.on("console", lambda msg: erreurs.append(msg.text) if msg.type == "error" else None)

        def route(route):
            url = route.request.url
            if "/sw.js" in url and servir_ancien["on"]:
                route.fulfill(
                    status=200,
                    content_type="application/javascript",
                    headers={"Service-Worker-Allowed": "/"},
                    body=ancien,
                )
                return
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

        contexte.route("**/*", route)
        with page.expect_console_message(
            lambda msg: "workers /sw.js désinstallés : 0" in msg.text,
            timeout=10000,
        ):
            page.goto(base_url + "/", wait_until="load", timeout=20000)
        page.wait_for_function("() => window._marketData", timeout=10000)
        page.evaluate(
            """async () => {
              await navigator.serviceWorker.register('/sw.js', { scope: '/' });
              var cache = await caches.open('brvm-sw-v2');
              await cache.put(location.origin + '/preuve-sw', new Response('ancien'));
            }"""
        )
        page.wait_for_function(
            """async () => {
              var regs = await navigator.serviceWorker.getRegistrations();
              var cles = await caches.keys();
              return regs.some(function (r) {
                var w = r.active || r.waiting || r.installing;
                return w && w.scriptURL.endsWith('/sw.js');
              }) && cles.indexOf('brvm-sw-v2') !== -1;
            }""",
            timeout=10000,
        )
        avant = _etat_worker(page)
        (tmp_path / "sw-avant.json").write_text(
            json.dumps(avant, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        _afficher_etat(page, "AVANT — worker c370954 installé", avant)
        page.screenshot(path=str(tmp_path / "sw-avant.png"))

        servir_ancien["on"] = False
        with page.expect_console_message(
            lambda msg: "workers /sw.js désinstallés : 1" in msg.text,
            timeout=15000,
        ):
            page.goto(base_url + "/", wait_until="load", timeout=20000)
        apres = _etat_worker(page)
        (tmp_path / "sw-apres.json").write_text(
            json.dumps(apres, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        _afficher_etat(page, "APRÈS — visite du code de la branche", apres)
        page.screenshot(path=str(tmp_path / "sw-apres.png"))
        navigateur.close()

    assert any(url.endswith("/sw.js") for url in avant["regs"]), avant
    assert "brvm-sw-v2" in avant["cles"], avant
    assert apres["regs"] == [], apres
    assert "brvm-sw-v2" not in apres["cles"], apres
    assert erreurs == [], erreurs
