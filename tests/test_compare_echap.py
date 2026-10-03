# -*- coding: utf-8 -*-
"""COMPARE-1 : Echap ferme la liste « Choisir une societe a comparer » puis la
fenetre de comparaison, rend le focus au bouton d'ouverture, sans fermer
autre chose (panneau d'aide, fiche laterale) et sans empiler d'ecouteur.

Les tests Playwright sont hors CI (Chromium non installe dans le workflow) :

    pytest tests/test_compare_echap.py -q -s
"""
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import json
import pytest

ROOT = Path(__file__).resolve().parents[1]
_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes") or os.environ.get("GITHUB_ACTIONS") == "true"
HORS_CI = pytest.mark.skipif(_CI, reason="Playwright hors CI. Local : pytest tests/test_compare_echap.py -q -s")


def test_un_seul_ecouteur_nomme_en_capture():
    js = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
    assert js.count("addEventListener('keydown', _cmpEchap, true)") == 1
    assert js.count("removeEventListener('keydown', _cmpEchap, true)") == 1
    picker = js[js.index("function _openComparePicker()"):js.index("// COMPARE-1")]
    assert "_cmpArmerEchap();" in picker
    assert "_cmpApresFermeture();" in picker
    fermer = js[js.index("function closeCompareModal()"):]
    assert "_cmpApresFermeture();" in fermer[:fermer.index("}")]


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
    dossier = os.environ["BRVM_DATA_DIR"]
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, nom)
    avant = open(chemin, "rb").read() if os.path.exists(chemin) else None
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return chemin, avant


def _restaurer(chemin, avant):
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

    def ligne(t, n, c):
        return {"ticker": t, "name": n, "sector": "Banque", "price": 10000, "composite_adj": c, "change_pct": 0.1,
                "div_yield": 5.0, "pe_ref": 10, "pdf_verdict": "NEUTRE"}

    classement = _ecrire("live_ranking.json", {"updated_at": maintenant, "market_open": False, "total": 3,
                                               "ranking": [ligne("SNTS", "Sonatel", 64), ligne("SGBC", "SGB CI", 58), ligne("ORAC", "Orange CI", 52)]})
    marche = _ecrire("market_cache.json", {
        "updated_at": maintenant, "market_activity": {"Capitalisation Actions": "10 000"}, "top5": [], "flop5": [],
        "indices": [
            {"name": "BRVM - COMPOSITE", "prev": 200.0, "current": 201.0, "change": 0.5, "ytd": 3.0},
            {"name": "BRVM - 30", "prev": 100.0, "current": 101.0, "change": 1.0, "ytd": 2.0},
        ],
        "sector_indices": [], "total_return": {},
    })
    import market_data
    market_data._memoire = None
    market_data._en_cours = False
    import app as application
    from werkzeug.serving import make_server

    serveur = make_server("127.0.0.1", 0, application.app, threaded=True)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % serveur.server_address[1]
    serveur.shutdown()
    market_data._memoire = None
    market_data._en_cours = False
    _restaurer(*classement)
    _restaurer(*marche)


@pytest.fixture
def page(base_url, tmp_path):
    from playwright.sync_api import sync_playwright

    erreurs = []
    with sync_playwright() as pw:
        navigateur = pw.chromium.launch(
            headless=True,
            executable_path=os.environ.get("BRVM_CHROMIUM") or None,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        contexte = navigateur.new_context()
        onglet = contexte.new_page()
        onglet.on("pageerror", lambda err: erreurs.append("pageerror: " + str(err)))
        onglet.on("console", lambda msg: erreurs.append(msg.text) if msg.type == "error" else None)

        def route(route):
            url = route.request.url
            if "exchangerate-api.com" in url:
                route.fulfill(status=200, content_type="application/json", body='{"rates":{"EUR":0.001524,"USD":0.001667}}')
                return
            if not url.startswith(base_url):
                route.abort()
                return
            route.continue_()

        onglet.route("**/*", route)
        onglet.add_init_script("localStorage.setItem('brvm_visited','1')")
        cdp = contexte.new_cdp_session(onglet)

        def charger(largeur, hauteur):
            onglet.set_viewport_size({"width": largeur, "height": hauteur})
            onglet.goto(base_url + "/", wait_until="load", timeout=20000)
            onglet.wait_for_function("() => (window.scores || []).length === 3", timeout=10000)
            onglet.wait_for_timeout(500)

        def ecouteurs_keydown():
            doc = cdp.send("Runtime.evaluate", {"expression": "document"})["result"]["objectId"]
            liste = cdp.send("DOMDebugger.getEventListeners", {"objectId": doc})["listeners"]
            return sum(1 for x in liste if x["type"] == "keydown")

        onglet.charger = charger
        onglet.ecouteurs_keydown = ecouteurs_keydown
        onglet.preuves = Path(os.environ.get("BRVM_PREUVE_DIR") or tmp_path)
        onglet.preuves.mkdir(parents=True, exist_ok=True)
        yield onglet
        navigateur.close()
    assert erreurs == [], erreurs


def _liste_ouverte(page):
    return page.locator("#nav-cmp-overlay").count() == 1


def _fenetre_ouverte(page):
    return page.evaluate("() => document.getElementById('cmp-modal').classList.contains('show')")


def _focus(page):
    return page.evaluate("() => { var a = document.activeElement; return a ? (a.id || a.getAttribute('data-nav') || a.tagName) : null; }")


def _ouvrir_liste_desktop(page):
    page.click("#topnav-more-btn")
    page.click("#topnav-more-menu button[onclick='navCompare()']")
    page.wait_for_selector("#nav-cmp-overlay")


@HORS_CI
def test_echap_ferme_liste_puis_fenetre_desktop(page):
    page.charger(1280, 800)
    base = page.ecouteurs_keydown()

    # (a) Echap ferme la liste, focus rendu au bouton « Plus » qui portait « Comparer »
    _ouvrir_liste_desktop(page)
    assert page.ecouteurs_keydown() == base + 1
    page.screenshot(path=str(page.preuves / "compare_liste_1280.png"))
    page.keyboard.press("Escape")
    assert not _liste_ouverte(page)
    assert _focus(page) == "topnav-more-btn"
    assert page.ecouteurs_keydown() == base
    assert page.locator("#topnav-more-menu").is_hidden()

    # Clic a cote et « Annuler » : inchanges
    _ouvrir_liste_desktop(page)
    page.mouse.click(5, 400)
    assert not _liste_ouverte(page)
    assert page.ecouteurs_keydown() == base
    _ouvrir_liste_desktop(page)
    page.click("#nav-cmp-overlay [data-cmp-cancel]")
    assert not _liste_ouverte(page)
    assert page.ecouteurs_keydown() == base

    # (a) Liste -> choix de 2 societes -> fenetre de comparaison -> Echap la ferme
    _ouvrir_liste_desktop(page)
    page.click("#nav-cmp-overlay [data-cmp='SNTS']")
    page.click("#nav-cmp-overlay [data-cmp='SGBC']")
    assert _fenetre_ouverte(page) and not _liste_ouverte(page)
    assert page.ecouteurs_keydown() == base + 1
    page.screenshot(path=str(page.preuves / "compare_fenetre_1280.png"))
    page.keyboard.press("Escape")
    assert not _fenetre_ouverte(page)
    assert _focus(page) == "topnav-more-btn"
    assert page.ecouteurs_keydown() == base

    # (b) 10 ouvertures / fermetures : jamais plus d'un ecouteur en plus
    page.evaluate("() => { _cmpSelected.clear(); _updateCmpBar(); }")
    releves = []
    for i in range(10):
        _ouvrir_liste_desktop(page)
        releves.append(page.ecouteurs_keydown() - base)
        if i % 3 == 0:
            page.keyboard.press("Escape")
        elif i % 3 == 1:
            page.mouse.click(5, 400)
        else:
            page.click("#nav-cmp-overlay [data-cmp-cancel]")
        assert not _liste_ouverte(page)
        releves.append(page.ecouteurs_keydown() - base)
    assert releves == [1, 0] * 10, releves


@HORS_CI
def test_echap_aide_et_fiche_comme_avant(page):
    """(c) Doit passer avant et apres COMPARE-1."""
    page.charger(1280, 800)
    # Panneau d'aide : Echap ne le fermait pas, il ne le ferme toujours pas.
    page.click("#help-fab")
    assert page.evaluate("() => _helpOpen") is True
    page.keyboard.press("Escape")
    assert page.evaluate("() => _helpOpen") is True
    page.evaluate("() => closeHelpDrawer()")
    # Fiche laterale : Echap la ferme.
    page.evaluate("() => openStockSlideover('SNTS')")
    assert page.locator("#stock-slideover.open").count() == 1
    page.keyboard.press("Escape")
    assert page.locator("#stock-slideover.open").count() == 0


@HORS_CI
def test_echap_ne_ferme_que_la_comparaison(page):
    page.charger(1280, 800)
    # Aide ouverte + liste ouverte : Echap ferme la liste, l'aide reste ouverte.
    page.click("#help-fab")
    page.evaluate("() => navCompare()")
    assert _liste_ouverte(page)
    page.keyboard.press("Escape")
    assert not _liste_ouverte(page)
    assert page.evaluate("() => _helpOpen") is True
    page.evaluate("() => closeHelpDrawer()")
    # Fiche laterale ouverte + fenetre de comparaison : Echap ferme la fenetre, puis la fiche.
    page.evaluate("() => openStockSlideover('SNTS')")
    page.evaluate("() => { _cmpSelected.clear(); _cmpSelected.add('SNTS'); _cmpSelected.add('SGBC'); _updateCmpBar(); openCompareModal(); }")
    assert _fenetre_ouverte(page)
    page.keyboard.press("Escape")
    assert not _fenetre_ouverte(page)
    assert page.locator("#stock-slideover.open").count() == 1
    page.keyboard.press("Escape")
    assert page.locator("#stock-slideover.open").count() == 0


@HORS_CI
def test_echap_ferme_liste_390(page):
    page.charger(390, 844)
    base = page.ecouteurs_keydown()
    for _ in range(3):
        page.click('#tabbar [data-nav="apprendre"]')
        page.click("#tab-plus button[onclick='navCompare()']")
        page.wait_for_selector("#nav-cmp-overlay")
        assert page.ecouteurs_keydown() == base + 1
        page.screenshot(path=str(page.preuves / "compare_liste_390.png"))
        page.keyboard.press("Escape")
        assert not _liste_ouverte(page)
        assert _focus(page) == "apprendre"
        assert not page.evaluate("() => document.getElementById('tab-plus').classList.contains('open')")
        assert page.ecouteurs_keydown() == base
    # Fenetre de comparaison a 390 px
    page.click('#tabbar [data-nav="apprendre"]')
    page.click("#tab-plus button[onclick='navCompare()']")
    page.click("#nav-cmp-overlay [data-cmp='SNTS']")
    page.click("#nav-cmp-overlay [data-cmp='SGBC']")
    assert _fenetre_ouverte(page)
    page.screenshot(path=str(page.preuves / "compare_fenetre_390.png"))
    page.keyboard.press("Escape")
    assert not _fenetre_ouverte(page)
    assert _focus(page) == "apprendre"
    assert page.ecouteurs_keydown() == base
