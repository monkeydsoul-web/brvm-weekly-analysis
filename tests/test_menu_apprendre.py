# -*- coding: utf-8 -*-
"""Menu Apprendre de la barre du haut : visible, donc cliquable.

Le menu s'ouvrait (display:flex, aria-expanded, z-index 40) mais
#topnav-links le rognait. Il est maintenant hors de ce conteneur,
comme le menu Plus.

Le test Playwright est hors CI (Chromium non installe dans le workflow) :

    pip install playwright
    playwright install chromium
    pytest tests/test_menu_apprendre.py -q -s
"""
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes") or os.environ.get("GITHUB_ACTIONS") == "true"


def test_apprendre_hors_du_conteneur_rogne():
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    debut = html.index('<nav class="topnav-links"')
    fin = html.index("</nav>", debut)
    assert "topnav-apprendre" not in html[debut:fin]
    entre = html[fin:html.index('id="topnav-more"')]
    assert 'id="topnav-apprendre"' in entre
    assert 'id="topnav-apprendre-menu"' in entre
    assert "navTo('glossaire')" in entre
    assert "navTo('methodo')" in entre
    assert 'onclick="toggleApprendre()"' in entre

    css = (ROOT / "dashboard" / "css" / "app.css").read_text(encoding="utf-8")
    assert "overflow:hidden" in css[css.index(".topnav-links{"):css.index(".topnav-links{") + 180]
    assert ".topnav-links,#topnav-more,#topnav-apprendre,.topnav-search{display:none!important}" in css

    core = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
    assert "if (drop && drop.parentNode === nav) nav.insertBefore(btn, drop);" in core
    assert "else nav.appendChild(btn);" in core
    mobile = html[html.index('<div id="tab-plus"'):html.index("<!-- LOADJS-1")]
    assert 'data-nav="glossaire"' in mobile
    assert 'data-nav="methodo"' in mobile


@pytest.fixture(autouse=True)
def interdire_reseau_hors_local(monkeypatch):
    """Chromium et le serveur local parlent a 127.0.0.1. Tout autre hote est refuse."""
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
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


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
            "change_pct": 0.1,
            "div_yield": 1.0,
            "pe_ref": 10,
            "pdf_verdict": "NEUTRE",
        }],
    })
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


def _est_marche(url, base):
    return url == base + "/api/market" or url.startswith(base + "/api/market?")


@pytest.mark.skipif(_CI, reason="Playwright hors CI. Local : pytest tests/test_menu_apprendre.py -q -s")
def test_menu_apprendre_glossaire_et_methode(base_url):
    """1280 et 1100 : Glossaire, Methode, elementFromPoint, Echap, clic exterieur."""
    from playwright.sync_api import expect, sync_playwright

    preuves = Path(os.environ.get("BRVM_PREUVE_DIR", "/opt/cursor/artifacts"))
    preuves.mkdir(parents=True, exist_ok=True)
    erreurs = []
    marches = []

    with sync_playwright() as pw:
        navigateur = pw.chromium.launch(
            channel="chrome",
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = navigateur.new_page()
        page.on("pageerror", lambda err: erreurs.append("pageerror: " + str(err)))
        page.on("console", lambda msg: erreurs.append(msg.text()) if msg.type == "error" else None)
        page.on("request", lambda req: marches.append(req.url) if req.method == "GET" and _est_marche(req.url, base_url) else None)

        def route(route):
            url = route.request.url
            if "exchangerate-api.com" in url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"rates":{"EUR":0.001524,"USD":0.001667}}',
                )
                return
            if not url.startswith(base_url):
                route.abort()
                return
            route.continue_()

        page.route("**/*", route)

        def charger():
            del marches[:]
            page.goto(base_url + "/", wait_until="load", timeout=20000)
            page.wait_for_function("() => window._marketData", timeout=10000)
            page.wait_for_timeout(900)
            assert marches == [base_url + "/api/market"], marches

        def menu_au_centre():
            return page.evaluate(
                """() => {
                  var menu = document.getElementById('topnav-apprendre-menu');
                  var r = menu.getBoundingClientRect();
                  var el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
                  return !!(el && (el === menu || menu.contains(el)));
                }"""
            )

        def ouvrir():
            page.click("#topnav-apprendre-btn")
            expect(page.locator("#topnav-apprendre-menu")).to_be_visible()
            assert page.locator("#topnav-apprendre-btn").get_attribute("aria-expanded") == "true"
            style = page.evaluate(
                """() => {
                  var menu = document.getElementById('topnav-apprendre-menu');
                  var cs = getComputedStyle(menu);
                  return {display: cs.display, z: cs.zIndex};
                }"""
            )
            assert style["display"] == "flex", style
            assert style["z"] == "40", style
            assert menu_au_centre()

        def page_atteinte(ident, extrait):
            page.wait_for_function(
                "(id) => document.getElementById('page-' + id).classList.contains('on')",
                arg=ident,
            )
            assert page.evaluate("() => location.hash") == "#" + ident
            texte = page.locator("#page-" + ident).inner_text()
            assert extrait in texte
            assert page.locator("#topnav-apprendre-menu").is_hidden()

        for largeur in (1280, 1100):
            page.set_viewport_size({"width": largeur, "height": 800})
            charger()
            assert page.evaluate(
                """() => {
                  var nav = document.getElementById('topnav-links');
                  var menu = document.getElementById('topnav-apprendre');
                  if (nav.contains(menu)) return 'dans le conteneur';
                  if (getComputedStyle(nav).overflow === 'visible') return 'overflow visible';
                  var zone = nav.getBoundingClientRect();
                  var noeuds = nav.querySelectorAll(':scope > button[data-nav]');
                  for (var i = 0; i < noeuds.length; i++) {
                    var r = noeuds[i].getBoundingClientRect();
                    if (r.width < 1) continue;
                    if (r.right > zone.right + 1 || r.left < zone.left - 1) return 'lien rogne';
                  }
                  var btn = document.getElementById('topnav-apprendre-btn').getBoundingClientRect();
                  if (btn.width < 10 || btn.left < 0 || btn.right > window.innerWidth + 1) return 'bouton hors cadre';
                  return 'ok';
                }"""
            ) == "ok"
            ouvrir()
            if largeur == 1280:
                page.screenshot(path=str(preuves / "menu_apprendre_1280_clair.png"))
            page.keyboard.press("Escape")
            expect(page.locator("#topnav-apprendre-menu")).to_be_hidden()
            assert page.locator("#topnav-apprendre-btn").get_attribute("aria-expanded") == "false"
            ouvrir()
            page.locator("#accueil-chapo").click()
            expect(page.locator("#topnav-apprendre-menu")).to_be_hidden()
            assert page.locator("#topnav-apprendre-btn").get_attribute("aria-expanded") == "false"
            ouvrir()
            page.click('#topnav-apprendre-menu button[data-nav="glossaire"]')
            page_atteinte("glossaire", "Glossaire")
            ouvrir()
            page.click('#topnav-apprendre-menu button[data-nav="methodo"]')
            page_atteinte("methodo", "méthodologie")
            assert len(marches) == 1, marches

        page.set_viewport_size({"width": 1280, "height": 800})
        page.click("#topnav [data-theme-btn]")
        assert page.evaluate("() => !document.documentElement.classList.contains('light')")
        ouvrir()
        page.screenshot(path=str(preuves / "menu_apprendre_1280_sombre.png"))
        page.keyboard.press("Escape")

        page.set_viewport_size({"width": 390, "height": 844})
        charger()
        expect(page.locator("#topnav-apprendre-btn")).to_be_hidden()
        expect(page.locator('#tabbar [data-nav="apprendre"]')).to_be_visible()
        assert page.evaluate(
            "() => getComputedStyle(document.querySelector('.index-band-scroll')).overflowX"
        ) == "auto"
        page.click('#tabbar [data-nav="apprendre"]')
        expect(page.locator("#tab-plus")).to_have_class(re.compile(r"\bopen\b"))
        page.screenshot(path=str(preuves / "menu_apprendre_390_clair.png"))
        page.click('#tab-plus button[data-nav="glossaire"]')
        page_attente = page.locator("#page-glossaire")
        expect(page_attente).to_be_visible()
        assert "Glossaire" in page_attente.inner_text()
        page.click('#tabbar [data-nav="apprendre"]')
        page.click('#tab-plus button[data-nav="methodo"]')
        expect(page.locator("#page-methodo")).to_be_visible()
        assert len(marches) == 1, marches
        page.click("#topnav [data-theme-btn]")
        assert page.evaluate("() => !document.documentElement.classList.contains('light')")
        page.click('#tabbar [data-nav="apprendre"]')
        expect(page.locator("#tab-plus")).to_be_visible()
        page.screenshot(path=str(preuves / "menu_apprendre_390_sombre.png"))

        navigateur.close()

    assert erreurs == [], erreurs
