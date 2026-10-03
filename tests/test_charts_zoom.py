# -*- coding: utf-8 -*-
"""CHARTS-3 : zoom, glisser et réinitialiser la courbe de /societe/<TICKER>.

La courbe est le SVG de stock_chart.js (pas de librairie, pas de plugin).
Hors CI :

    pip install playwright
    playwright install chromium
    pytest tests/test_charts_zoom.py -q -s
"""
import json
import math
import os
import socket
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes") or os.environ.get("GITHUB_ACTIONS") == "true"
_REEL_CONNECT = socket.socket.connect
_REEL_CONNECT_EX = socket.socket.connect_ex
_REEL_CREATE = socket.create_connection
_REEL_DNS = socket.getaddrinfo


def _lire(relatif):
    chemin = Path(__file__).resolve().parents[1].joinpath(relatif)
    return chemin.read_text(encoding="utf-8")


def test_zoom_local_sans_cdn_ni_plugin():
    """Pas de Chart.js : le zoom vit dans charts_zoom.js, servi avec le dashboard."""
    source = _lire("dashboard/js/charts_zoom.js")
    assert "function drawPriceChart" not in source
    assert "new Chart" not in source
    assert "chartjs" not in source.lower()
    assert "http://" not in source
    assert "https://" not in source
    assert "cdn." not in source.lower()
    assert "Réinitialiser" in source
    assert "touch-action:pan-y" in source
    assert "e.ctrlKey" in source
    assert "p.mode = 'scroll'" in source
    assert "api/market" not in source
    assert "onmousemove" in source
    index = _lire("dashboard/index.html")
    balise = '<script src="/js/charts_zoom.js?v={{ASSET_V}}" data-brvm-mod="js/charts_zoom.js" onerror="brvmScriptError(this)"></script>'
    assert balise in index
    assert index.index("stock_chart.js") < index.index("js/charts_zoom.js")
    core = _lire("dashboard/js/core.js")
    assert "charts_zoom" not in core
    assert "loadPriceChart(ticker, 'stockChartDiv')" in core
    assert "brvm-zoom" not in _lire("dashboard/stock_chart.js")
    assert "function drawPriceChart" in _lire("dashboard/stock_chart.js")
    for relatif in (
        "dashboard/compare.js",
        "dashboard/backtest.js",
        "dashboard/welcome_v2.js",
        "dashboard/performance.js",
        "dashboard/css/accueil.css",
    ):
        assert "brvm-zoom" not in _lire(relatif)
        assert "charts_zoom" not in _lire(relatif)


def test_zoom_js_repond_200():
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    import app as application
    client = application.app.test_client()
    reponse = client.get("/js/charts_zoom.js?v=%s" % application.ASSET_V)
    assert reponse.status_code == 200
    assert "javascript" in (reponse.content_type or "")
    assert "Réinitialiser" in reponse.get_data(as_text=True)
    autre = client.get("/js/charts_zoom.js?v=pas-cette-instance")
    assert autre.status_code == 503


def _autoriser_local(monkeypatch):
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


def _serie():
    fin = date.today() - timedelta(days=2)
    debut = fin - timedelta(days=280)
    points = []
    i = 0
    jour = debut
    while jour <= fin:
        if jour.weekday() < 5:
            prix = 14000 + i * 25 + int(600 * math.sin(i / 6.0))
            points.append({
                "date": jour.isoformat(),
                "close": prix,
                "volume": 1000 + i * 3,
            })
            i += 1
        jour += timedelta(days=1)
    return points


def _caches():
    maintenant = datetime.now(timezone.utc).isoformat()
    points = _serie()
    _ecrire("price_history_extended.json", {"SNTS": points})
    _ecrire("price_history.json", {})
    _ecrire("live_ranking.json", {
        "updated_at": maintenant,
        "market_open": False,
        "total": 1,
        "ranking": [{
            "ticker": "SNTS",
            "name": "Sonatel",
            "sector": "Télécommunications",
            "country": "Sénégal",
            "price": 25500,
            "composite_adj": 54,
            "note10": 6.8,
            "change_pct": 0.4,
            "div_yield": 4.2,
            "pe_ref": 11,
            "pdf_verdict": "NEUTRE",
            "conseil": "attendre",
            "conseil_libelle": "À surveiller",
            "conseil_couleur": "orange",
            "statut": "cote",
        }],
    })
    _ecrire("market_cache.json", {
        "updated_at": maintenant,
        "market_activity": {"Capitalisation Actions": "10 234 567 890 123"},
        "top5": [],
        "flop5": [],
        "indices": [
            {"name": "BRVM - COMPOSITE", "prev": 540.0, "current": 548.38, "change": 1.55, "ytd": 0.02},
            {"name": "BRVM-30", "prev": 260.0, "current": 266.08, "change": 2.34, "ytd": 0.02},
        ],
        "sector_indices": [],
        "total_return": {},
    })
    _ecrire("live_cache.json", {
        "updated_at": maintenant,
        "market_open": False,
        "session_date": (date.today() - timedelta(days=1)).isoformat(),
        "seance_ouverte": False,
        "prices": {
            "SNTS": {
                "price": 25500,
                "change_pct": 0.4,
                "volume": 1200,
                "source": "fixture",
                "fetched_at": maintenant,
            }
        },
        "stats": {"total": 1, "with_price": 1, "sources": {"fixture": 1}},
    })
    _ecrire("macro_cache.json", {})
    return len(points)


@pytest.mark.skipif(_CI, reason="Playwright hors CI. Local : pytest tests/test_charts_zoom.py -q -s")
def test_zoom_glisser_reinitialiser_fiche(monkeypatch, tmp_path):
    """1280 et 390, clair et sombre : zoom, glisser, réinitialiser, défilement intact."""
    pytest.importorskip("playwright.sync_api")
    _autoriser_local(monkeypatch)
    from playwright.sync_api import sync_playwright

    n_points = _caches()
    assert n_points >= 40
    import market_data
    market_data._memoire = None
    from werkzeug.serving import make_server
    import app as application

    if os.environ.get("BRVM_PREUVE_DIR"):
        preuves = Path(os.environ["BRVM_PREUVE_DIR"])
    else:
        preuves = tmp_path
    preuves.mkdir(parents=True, exist_ok=True)

    serveur = make_server("127.0.0.1", 0, application.app, threaded=True)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    base = "http://127.0.0.1:%d" % serveur.server_address[1]
    erreurs = []
    try:
        with sync_playwright() as pw:
            navigateur = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            contexte = navigateur.new_context(has_touch=True, viewport={"width": 1280, "height": 800})
            page = contexte.new_page()
            page.on("pageerror", lambda err: erreurs.append("pageerror: " + str(err)))
            page.on("console", lambda msg: erreurs.append(msg.text) if msg.type == "error" else None)

            def route(route):
                if not route.request.url.startswith(base):
                    route.abort()
                    return
                route.continue_()

            page.route("**/*", route)

            def marches_de(url):
                return url == base + "/api/market" or url.startswith(base + "/api/market?")

            def fenetre():
                return page.evaluate(
                    """() => {
                      var host = document.getElementById('stockChartDiv_svg');
                      var poly = host && host.querySelector('polyline');
                      var brut = poly ? (poly.getAttribute('points') || '').trim() : '';
                      var pts = brut ? brut.split(/\\s+/).length : 0;
                      return {
                        debut: Number(host.getAttribute('data-zoom-debut')),
                        fin: Number(host.getAttribute('data-zoom-fin')),
                        total: Number(host.getAttribute('data-zoom-total')),
                        points: pts,
                        plage: (document.querySelector('#stockChartDiv .brvm-zoom-plage') || {}).textContent || ''
                      };
                    }"""
                )

            def span(info):
                return info["fin"] - info["debut"]

            def preparer_courbe():
                page.locator('#page-stock .ctab-btn[data-ctab="chiffres"]').click()
                page.locator("#stockChartDiv .brvm-zoom-bar").wait_for(state="visible", timeout=8000)
                page.locator("#stockChartDiv svg").scroll_into_view_if_needed()
                info = fenetre()
                assert info["total"] == n_points
                assert info["debut"] == 0
                assert info["fin"] == n_points - 1
                assert info["points"] == n_points
                assert page.locator(".brvm-zoom-bar").count() == 1
                assert page.locator("#accueil-courbe .brvm-zoom-bar").count() == 0
                assert page.locator("#bt-chart .brvm-zoom-bar").count() == 0
                bouton = page.locator('#stockChartDiv button[data-brvm-zoom="reset"]')
                assert bouton.inner_text() == "Réinitialiser"
                boite = bouton.bounding_box()
                assert boite and boite["width"] > 40 and boite["height"] >= 30
                return info

            def centre_svg():
                boite = page.locator("#stockChartDiv svg").bounding_box()
                assert boite and boite["width"] > 80 and boite["height"] > 40
                return boite["x"] + boite["width"] / 2, boite["y"] + boite["height"] / 2, boite

            def infobulle_absente():
                x, y, _boite = centre_svg()
                page.mouse.move(x - 40, y)
                page.mouse.move(x + 30, y)
                etat = page.evaluate(
                    """() => {
                      var prix = document.querySelector('#stockChartDiv svg text[id$="_price"]');
                      var flottant = document.getElementById('floating-tooltip');
                      return {
                        opacity: prix ? prix.getAttribute('opacity') : 'absent',
                        texte: prix ? (prix.textContent || '') : '',
                        flottant: flottant ? getComputedStyle(flottant).opacity : '1'
                      };
                    }"""
                )
                assert etat["opacity"] in ("0", "absent", None)
                assert etat["texte"] == ""
                assert float(etat["flottant"]) == 0

            def zoom_plus():
                avant = fenetre()
                page.locator('#stockChartDiv button[data-brvm-zoom="plus"]').click()
                apres = fenetre()
                assert span(apres) < span(avant)
                assert apres["points"] == span(apres) + 1
                assert apres["points"] < avant["points"]
                return apres

            def glisser_souris():
                avant = fenetre()
                _x, y, boite = centre_svg()
                page.mouse.move(boite["x"] + boite["width"] * 0.55, y)
                page.mouse.down()
                page.mouse.move(boite["x"] + boite["width"] * 0.9, y, steps=8)
                page.mouse.up()
                apres = fenetre()
                assert apres["debut"] < avant["debut"]
                assert span(apres) == span(avant)
                assert apres["plage"] != avant["plage"]
                return apres

            def reinitialiser():
                page.locator('#stockChartDiv button[data-brvm-zoom="reset"]').click()
                info = fenetre()
                assert info["debut"] == 0
                assert info["fin"] == info["total"] - 1
                assert info["points"] == info["total"]
                return info

            def molette_ctrl():
                avant = fenetre()
                x, y, _boite = centre_svg()
                page.mouse.move(x, y)
                page.keyboard.down("Control")
                page.mouse.wheel(0, -240)
                page.keyboard.up("Control")
                apres = fenetre()
                assert span(apres) < span(avant)
                echelle = page.evaluate("() => (window.visualViewport && window.visualViewport.scale) || 1")
                assert echelle == 1
                return apres

            def molette_sans_ctrl_defile():
                avant = fenetre()
                place = page.evaluate(
                    """() => {
                      var main = document.querySelector('.main');
                      var svg = document.querySelector('#stockChartDiv svg');
                      var haut = svg.getBoundingClientRect().top - main.getBoundingClientRect().top;
                      main.scrollTop += haut - 70;
                      var reste = main.scrollHeight - main.clientHeight - main.scrollTop;
                      if (reste < 160) main.scrollTop -= (160 - reste);
                      return {
                        scroll: main.scrollTop,
                        reste: main.scrollHeight - main.clientHeight - main.scrollTop,
                        svgTop: svg.getBoundingClientRect().top
                      };
                    }"""
                )
                assert place["reste"] > 80, place
                assert 0 < place["svgTop"] < page.viewport_size["height"] - 40
                x, y, _boite = centre_svg()
                page.mouse.move(x, y)
                page.mouse.wheel(0, 180)
                page.wait_for_timeout(80)
                apres_scroll = page.evaluate("() => document.querySelector('.main').scrollTop")
                assert apres_scroll > place["scroll"] + 20
                assert fenetre()["debut"] == avant["debut"]
                assert fenetre()["fin"] == avant["fin"]

            def doigt_horizontal():
                avant = fenetre()
                _x, y, boite = centre_svg()
                client = page.context.new_cdp_session(page)
                x0 = boite["x"] + boite["width"] * 0.4
                client.send("Input.dispatchTouchEvent", {
                    "type": "touchStart",
                    "touchPoints": [{"x": x0, "y": y, "id": 1}],
                })
                pas = 0
                while pas < 8:
                    pas += 1
                    client.send("Input.dispatchTouchEvent", {
                        "type": "touchMove",
                        "touchPoints": [{"x": x0 + pas * 16, "y": y, "id": 1}],
                    })
                client.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
                client.detach()
                apres = fenetre()
                assert apres["debut"] < avant["debut"], (avant, apres)
                assert span(apres) == span(avant)

            def pincer():
                avant = fenetre()
                _x, y, boite = centre_svg()
                cx = boite["x"] + boite["width"] / 2
                client = page.context.new_cdp_session(page)
                client.send("Input.dispatchTouchEvent", {
                    "type": "touchStart",
                    "touchPoints": [{"x": cx - 36, "y": y, "id": 1}],
                })
                client.send("Input.dispatchTouchEvent", {
                    "type": "touchStart",
                    "touchPoints": [
                        {"x": cx - 36, "y": y, "id": 1},
                        {"x": cx + 36, "y": y, "id": 2},
                    ],
                })
                ecart = 36
                while ecart < 120:
                    ecart += 16
                    client.send("Input.dispatchTouchEvent", {
                        "type": "touchMove",
                        "touchPoints": [
                            {"x": cx - ecart, "y": y, "id": 1},
                            {"x": cx + ecart, "y": y, "id": 2},
                        ],
                    })
                client.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
                client.detach()
                apres = fenetre()
                assert span(apres) < span(avant), (avant, apres)
                return apres

            def doigt_vertical_defile():
                avant = fenetre()
                place = page.evaluate(
                    """() => {
                      var main = document.querySelector('.main');
                      var svg = document.querySelector('#stockChartDiv svg');
                      var haut = svg.getBoundingClientRect().top - main.getBoundingClientRect().top;
                      main.scrollTop += haut - 90;
                      return {
                        scroll: main.scrollTop,
                        max: main.scrollHeight - main.clientHeight,
                        svgTop: svg.getBoundingClientRect().top
                      };
                    }"""
                )
                assert place["scroll"] > 40, place
                x, y, _boite = centre_svg()
                client = page.context.new_cdp_session(page)
                client.send("Input.dispatchTouchEvent", {
                    "type": "touchStart",
                    "touchPoints": [{"x": x, "y": y, "id": 1}],
                })
                dep = 0
                while dep < 140:
                    dep += 20
                    client.send("Input.dispatchTouchEvent", {
                        "type": "touchMove",
                        "touchPoints": [{"x": x, "y": y + dep, "id": 1}],
                    })
                client.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
                client.detach()
                page.wait_for_timeout(80)
                apres_scroll = page.evaluate("() => document.querySelector('.main').scrollTop")
                assert apres_scroll < place["scroll"] - 20, (place, apres_scroll)
                info = fenetre()
                assert info["debut"] == avant["debut"]
                assert info["fin"] == avant["fin"]

            def theme(clair):
                est_clair = page.evaluate("() => document.documentElement.classList.contains('light')")
                if est_clair != clair:
                    page.locator("#topnav [data-theme-btn]").click()
                assert page.evaluate("() => document.documentElement.classList.contains('light')") is clair

            def capturer(largeur, nom):
                page.evaluate(
                    """() => {
                      var main = document.querySelector('.main');
                      var barre = document.querySelector('#stockChartDiv .brvm-zoom-bar');
                      var haut = barre.getBoundingClientRect().top - main.getBoundingClientRect().top;
                      main.scrollTop += haut - 8;
                    }"""
                )
                page.screenshot(path=str(preuves / ("fiche-zoom-%d-%s.png" % (largeur, nom))))

            for largeur, hauteur in ((1280, 800), (390, 844)):
                page.set_viewport_size({"width": largeur, "height": hauteur})
                vus = []

                def noter(req, _vus=vus):
                    if req.method == "GET" and marches_de(req.url):
                        _vus.append(req.url)

                page.on("request", noter)
                page.goto(base + "/societe/SNTS", wait_until="load", timeout=20000)
                page.wait_for_function(
                    "() => document.querySelector('#stockChartDiv svg polyline')",
                    timeout=15000,
                )
                borne = time.time() + 8
                while time.time() < borne and len(vus) < 1:
                    page.wait_for_timeout(100)
                page.remove_listener("request", noter)
                assert vus == [base + "/api/market"], vus
                preparer_courbe()
                infobulle_absente()
                zoom_plus()
                glisser_souris()
                reinitialiser()
                molette_ctrl()
                reinitialiser()
                molette_sans_ctrl_defile()
                if largeur == 390:
                    zoom_plus()
                    doigt_horizontal()
                    reinitialiser()
                    pincer()
                    reinitialiser()
                    doigt_vertical_defile()
                zoom_plus()
                theme(True)
                capturer(largeur, "clair")
                theme(False)
                capturer(largeur, "sombre")
                assert not erreurs, erreurs[:8]

            navigateur.close()
    finally:
        serveur.shutdown()

    assert not erreurs, erreurs[:8]
    for largeur in (1280, 390):
        for nom in ("clair", "sombre"):
            fichier = preuves / ("fiche-zoom-%d-%s.png" % (largeur, nom))
            assert fichier.is_file() and fichier.stat().st_size > 1000
