# -*- coding: utf-8 -*-
"""CHARTS-FIX-2 : après un changement de fenêtre, le libellé montre le dernier point."""
import json
import os
import shutil
import socket
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes") or os.environ.get("GITHUB_ACTIONS") == "true"
_REEL_CONNECT = socket.socket.connect
_REEL_CONNECT_EX = socket.socket.connect_ex
_REEL_CREATE = socket.create_connection
_REEL_DNS = socket.getaddrinfo


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


def _seances(depart, pas):
    debut = date(2026, 5, 20)
    fin = date(2026, 10, 2)
    points = []
    i = 0
    jour = debut
    while jour <= fin:
        if jour.weekday() < 5:
            points.append({
                "date": jour.isoformat(),
                "price": depart + i * pas,
                "volume": 1000 + i,
                "source": "live",
            })
            i += 1
        jour += timedelta(days=1)
    return points


def _fiche(ticker, nom, secteur, cours):
    return {
        "ticker": ticker,
        "name": nom,
        "sector": secteur,
        "country": "Côte d'Ivoire",
        "price": cours,
        "composite_adj": 50,
        "note10": 6.0,
        "change_pct": 0.2,
        "div_yield": 3.0,
        "pe_ref": 10,
        "pdf_verdict": "NEUTRE",
        "conseil": "attendre",
        "conseil_libelle": "À surveiller",
        "conseil_couleur": "orange",
        "statut": "cote",
    }


def _caches():
    maintenant = datetime.now(timezone.utc).isoformat()
    snts = _seances(30000, 50)
    orac = _seances(8000, 20)
    _ecrire("price_history.json", {"SNTS": snts, "ORAC": orac})
    _ecrire("price_history_extended.json", {})
    _ecrire("live_ranking.json", {
        "updated_at": maintenant,
        "market_open": False,
        "total": 2,
        "ranking": [
            _fiche("SNTS", "Sonatel", "Télécommunications", snts[-1]["price"]),
            _fiche("ORAC", "Orange CI", "Télécommunications", orac[-1]["price"]),
        ],
    })
    _ecrire("market_cache.json", {
        "updated_at": maintenant,
        "market_activity": {"Capitalisation Actions": "10 234 567 890 123"},
        "top5": [],
        "flop5": [],
        "indices": [
            {"name": "BRVM - COMPOSITE", "prev": 540.0, "current": 548.38, "change": 1.55, "ytd": 0.02},
        ],
        "sector_indices": [],
        "total_return": {},
    })
    _ecrire("live_cache.json", {
        "updated_at": maintenant,
        "market_open": False,
        "session_date": "2026-10-02",
        "seance_ouverte": False,
        "prices": {},
        "stats": {"total": 2, "with_price": 2, "sources": {"fixture": 2}},
    })
    _ecrire("macro_cache.json", {})


@pytest.mark.skipif(_CI, reason="Playwright hors CI")
def test_libelle_dernier_point_fenetre(monkeypatch, tmp_path):
    """SNTS et ORAC, 1280 et 390 : chargement, +, Réinitialiser, 1M, Tout."""
    pytest.importorskip("playwright.sync_api")
    _autoriser_local(monkeypatch)
    from playwright.sync_api import sync_playwright

    _caches()
    import market_data
    market_data._memoire = None
    from werkzeug.serving import make_server
    import app as application

    serveur = make_server("127.0.0.1", 0, application.app, threaded=True)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    base = "http://127.0.0.1:%d" % serveur.server_address[1]
    erreurs = []
    rapport = []
    try:
        with sync_playwright() as pw:
            navigateur = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            contexte = navigateur.new_context(
                has_touch=True,
                locale="fr-FR",
                viewport={"width": 1280, "height": 800},
            )
            page = contexte.new_page()
            page.on("pageerror", lambda err: erreurs.append("pageerror: " + str(err)))
            page.on("console", lambda msg: erreurs.append(msg.text) if msg.type == "error" else None)

            def route(route):
                if not route.request.url.startswith(base):
                    route.abort()
                    return
                route.continue_()

            page.route("**/*", route)

            def lire():
                return page.evaluate(
                    """() => {
                      var el = document.getElementById('stockChartDiv');
                      var vis = el._ciVisible || [];
                      var dernier = vis.length ? vis[vis.length - 1] : null;
                      var prec = vis.length > 1 ? vis[vis.length - 2] : null;
                      var lecture = el.querySelector('.ci-lecture');
                      var pct = null;
                      var variationAttendue = '';
                      if (dernier && prec && prec.value > 0) {
                        pct = (dernier.value - prec.value) / prec.value * 100;
                        variationAttendue = pct.toFixed(2).replace('.', ',');
                        if (pct > 0) variationAttendue = '+' + variationAttendue;
                        variationAttendue += ' %';
                      }
                      return {
                        date: (el.querySelector('.ci-date') || {}).textContent || '',
                        cours: (el.querySelector('.ci-cours') || {}).textContent || '',
                        variation: (el.querySelector('.ci-var') || {}).textContent || '',
                        iso: lecture ? lecture.getAttribute('data-ci-date') : '',
                        valeur: lecture ? Number(lecture.getAttribute('data-ci-valeur')) : null,
                        debut: el.getAttribute('data-ci-debut'),
                        fin: el.getAttribute('data-ci-fin'),
                        dernierIso: dernier ? dernier.date : '',
                        dernierValeur: dernier ? dernier.value : null,
                        variationAttendue: variationAttendue
                      };
                    }"""
                )

            def assert_dernier(info):
                assert info["iso"] == info["fin"] == info["dernierIso"], info
                assert info["valeur"] == info["dernierValeur"], info
                assert info["variation"] == info["variationAttendue"], info
                assert "XOF" in info["cours"]
                assert info["date"]

            def libelle(info):
                return "%s · %s · %s" % (
                    info["date"].strip(),
                    info["cours"].strip(),
                    info["variation"].strip(),
                )

            def ouvrir(ticker):
                page.goto(base + "/societe/" + ticker, wait_until="load", timeout=20000)
                page.locator('.ctab-btn[data-ctab="chiffres"]').click()
                page.locator("#stockChartDiv .ci-date").wait_for(state="visible", timeout=15000)
                page.locator('#stockChartDiv button[data-brvm-zoom="reset"]').wait_for(state="visible")

            def capturer(ticker, largeur, etape):
                page.locator("#stockChartDiv .ci-lecture").scroll_into_view_if_needed()
                page.locator("#stockChartDiv").screenshot(
                    path=str(tmp_path / ("libelle-%s-%d-%s.png" % (ticker, largeur, etape)))
                )

            def noter(ticker, largeur, etape, info):
                rapport.append({
                    "ticker": ticker,
                    "largeur": largeur,
                    "etape": etape,
                    "libelle": libelle(info),
                    "debut": info["debut"],
                    "fin": info["fin"],
                })

            for largeur, hauteur in ((1280, 800), (390, 844)):
                page.set_viewport_size({"width": largeur, "height": hauteur})
                for ticker in ("SNTS", "ORAC"):
                    ouvrir(ticker)
                    charge = lire()
                    assert_dernier(charge)
                    noter(ticker, largeur, "chargement", charge)
                    capturer(ticker, largeur, "chargement")

                    page.locator('#stockChartDiv button[data-brvm-zoom="plus"]').click()
                    page.wait_for_function(
                        "(fin) => document.getElementById('stockChartDiv').getAttribute('data-ci-fin') !== fin",
                        arg=charge["fin"],
                        timeout=5000,
                    )
                    zoom = lire()
                    assert_dernier(zoom)
                    assert zoom["fin"] != charge["fin"]
                    assert libelle(zoom) != libelle(charge)
                    noter(ticker, largeur, "plus", zoom)
                    capturer(ticker, largeur, "plus")

                    page.locator('#stockChartDiv button[data-brvm-zoom="reset"]').click()
                    page.wait_for_function(
                        "(fin) => document.getElementById('stockChartDiv').getAttribute('data-ci-fin') === fin",
                        arg=charge["fin"],
                        timeout=5000,
                    )
                    reset = lire()
                    assert_dernier(reset)
                    assert libelle(reset) == libelle(charge)
                    assert reset["debut"] == charge["debut"]
                    noter(ticker, largeur, "reinitialiser", reset)
                    capturer(ticker, largeur, "reinitialiser")

                    page.locator('#stockChartDiv .ci-periode[data-periode="1M"]').click()
                    page.wait_for_function(
                        "(debut) => document.getElementById('stockChartDiv').getAttribute('data-ci-debut') !== debut",
                        arg=charge["debut"],
                        timeout=5000,
                    )
                    un_mois = lire()
                    assert_dernier(un_mois)
                    assert un_mois["debut"] > charge["debut"]
                    noter(ticker, largeur, "1M", un_mois)
                    capturer(ticker, largeur, "1M")

                    page.locator('#stockChartDiv .ci-periode[data-periode="Tout"]').click()
                    page.wait_for_function(
                        "(debut) => document.getElementById('stockChartDiv').getAttribute('data-ci-debut') === debut",
                        arg=charge["debut"],
                        timeout=5000,
                    )
                    tout = lire()
                    assert_dernier(tout)
                    assert libelle(tout) == libelle(charge)
                    noter(ticker, largeur, "Tout", tout)
                    capturer(ticker, largeur, "Tout")

                    if largeur == 1280:
                        page.locator('#stockChartDiv button[data-brvm-zoom="plus"]').click()
                        page.wait_for_function(
                            "(fin) => document.getElementById('stockChartDiv').getAttribute('data-ci-fin') !== fin",
                            arg=charge["fin"],
                        )
                        boite = page.locator("#stockChartDiv .ci-svg").bounding_box()
                        y = boite["y"] + boite["height"] * 0.45
                        page.mouse.move(boite["x"] + boite["width"] * 0.55, y)
                        page.mouse.down()
                        page.mouse.move(boite["x"] + boite["width"] * 0.9, y, steps=8)
                        page.mouse.up()
                        page.mouse.move(8, 8)
                        glisse = lire()
                        assert_dernier(glisse)

            navigateur.close()
    finally:
        serveur.shutdown()

    assert not erreurs, erreurs[:8]
    texte = json.dumps(rapport, ensure_ascii=False, indent=2)
    (tmp_path / "libelles.json").write_text(texte, encoding="utf-8")
    for ligne in rapport:
        assert "XOF" in ligne["libelle"]
        assert ligne["fin"]
        fichier = tmp_path / ("libelle-%s-%d-%s.png" % (ligne["ticker"], ligne["largeur"], ligne["etape"]))
        assert fichier.is_file() and fichier.stat().st_size > 1000
    assert len(rapport) == 2 * 2 * 5
    copie = Path("/opt/cursor/artifacts/charts-fix2")
    copie.mkdir(parents=True, exist_ok=True)
    (copie / "libelles.json").write_text(texte, encoding="utf-8")
    for fichier in tmp_path.glob("libelle-*.png"):
        shutil.copy(fichier, copie / fichier.name)
