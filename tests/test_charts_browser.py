# -*- coding: utf-8 -*-
"""CHARTS-1 : lecture au doigt, périodes réelles, 1280 et 390, clair et sombre.

Hors CI (Playwright n'est pas installé dans le workflow pytest) :

    pip install playwright
    pytest tests/test_charts_browser.py -q -s
"""
import calendar
import json
import os
import socket
import tempfile
import threading
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

import pytest

_REEL_CONNECT = socket.socket.connect
_REEL_CONNECT_EX = socket.socket.connect_ex
_REEL_CREATE = socket.create_connection
_REEL_DNS = socket.getaddrinfo

_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes") or os.environ.get("GITHUB_ACTIONS") == "true"
pytestmark = pytest.mark.skipif(
    _CI,
    reason="Playwright hors CI. Local : pytest tests/test_charts_browser.py -q -s",
)

pytest.importorskip("playwright.sync_api")

CAPTURES = os.environ.get("BRVM_CAPTURES") or tempfile.mkdtemp(prefix="charts_")


def _decaler_mois(jour, delta):
    index = jour.year * 12 + (jour.month - 1) + delta
    annee, mois0 = divmod(index, 12)
    mois = mois0 + 1
    dernier = calendar.monthrange(annee, mois)[1]
    return date(annee, mois, min(jour.day, dernier))


def _seances():
    fin = date.today()
    while fin.weekday() >= 5:
        fin -= timedelta(days=1)
    debut = fin - timedelta(days=150)
    jours = []
    curseur = debut
    while curseur <= fin:
        if curseur.weekday() < 5:
            jours.append(curseur)
        curseur += timedelta(days=1)
    return jours


_FICHIERS_FIXTURE = (
    "live_ranking.json",
    "macro_cache.json",
    "market_cache.json",
    "live_cache.json",
    "price_history_extended.json",
    "price_history.json",
    "index_history.json",
)


def _sauver_fichiers(dossier):
    """Le score technique lit price_history.json. On rend les fichiers après le test."""
    sauve = {}
    for nom in _FICHIERS_FIXTURE:
        chemin = os.path.join(dossier, nom)
        if os.path.isfile(chemin):
            with open(chemin, "rb") as f:
                sauve[nom] = f.read()
        else:
            sauve[nom] = None
    return sauve


def _rendre_fichiers(dossier, sauve):
    for nom, contenu in sauve.items():
        chemin = os.path.join(dossier, nom)
        if contenu is None:
            if os.path.isfile(chemin):
                os.remove(chemin)
        else:
            with open(chemin, "wb") as f:
                f.write(contenu)


def _ecrire_fixtures():
    dossier = os.environ["BRVM_DATA_DIR"]
    os.makedirs(dossier, exist_ok=True)
    sauve = _sauver_fichiers(dossier)
    maintenant = datetime.now(timezone.utc).isoformat()
    rangs = [{
        "ticker": "SMBC",
        "name": "SMB CI",
        "sector": "Industriel",
        "country": "CI",
        "price": 16500,
        "note10": 8.4,
        "composite_adj": 67.2,
        "rank": 1,
        "change_pct": 0.4,
        "statut": "cote",
        "conseil": "Intéressant",
        "conseil_libelle": "Intéressant",
        "conseil_couleur": "vert",
    }]
    with open(os.path.join(dossier, "live_ranking.json"), "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": maintenant,
            "market_open": False,
            "total": 1,
            "ranking": rangs,
        }, f)
    with open(os.path.join(dossier, "macro_cache.json"), "w", encoding="utf-8") as f:
        json.dump({"date": maintenant, "FCFA_per_EUR": 655.957, "FCFA_per_USD": 580.49}, f)
    with open(os.path.join(dossier, "market_cache.json"), "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": maintenant,
            "market_activity": {},
            "top5": [],
            "flop5": [],
            "indices": [
                {"name": "BRVM - COMPOSITE", "prev": 240.0, "current": 245.2, "change": 2.1, "ytd": 0.04},
                {"name": "BRVM-30", "prev": 130.0, "current": 132.4, "change": 1.8, "ytd": 0.03},
            ],
            "sector_indices": [],
            "total_return": {},
        }, f)
    with open(os.path.join(dossier, "live_cache.json"), "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": maintenant,
            "market_open": False,
            "prices": {"SMBC": {"price": 16500, "change_pct": 0.4, "volume": 100, "source": "fixture"}},
            "stats": {"total": 1, "with_price": 1, "sources": {"fixture": 1}},
        }, f)
    jours = _seances()
    cours = []
    seances = []
    for i, jour in enumerate(jours):
        iso = jour.isoformat()
        cours.append({"date": iso, "close": 15000 + i * 25, "volume": 100})
        seances.append({
            "date": iso,
            "indices": {
                "BRVM-C": round(200 + i * 0.35, 2),
                "BRVM-30": round(120 + i * 0.2, 2),
            },
            "societes": [],
        })
    with open(os.path.join(dossier, "price_history_extended.json"), "w", encoding="utf-8") as f:
        json.dump({"SMBC": cours}, f)
    with open(os.path.join(dossier, "price_history.json"), "w", encoding="utf-8") as f:
        json.dump({
            "SMBC": [{"date": p["date"], "price": p["close"], "source": "live"} for p in cours],
        }, f)
    with open(os.path.join(dossier, "index_history.json"), "w", encoding="utf-8") as f:
        json.dump({"seances": seances}, f)
    return jours, sauve


@pytest.fixture(autouse=True)
def interdire_reseau_et_cle(monkeypatch):
    """Le serveur et Chrome parlent à 127.0.0.1. Tout autre hôte est refusé."""
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
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture(scope="module")
def base_url():
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    jours, sauve = _ecrire_fixtures()
    import app as application
    import index_history
    import market_data
    with market_data._verrou:
        market_data._memoire = None
    with index_history._CACHE_LOCK:
        index_history._CACHE["stamp"] = None
        index_history._CACHE["data"] = None
    application._EXTENDED_HISTORY_CACHE = None
    from werkzeug.serving import make_server

    serveur = make_server("127.0.0.1", 0, application.app, threaded=True)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    url = "http://127.0.0.1:%d" % serveur.server_address[1]
    yield url, jours
    serveur.shutdown()
    _rendre_fichiers(os.environ["BRVM_DATA_DIR"], sauve)
    with market_data._verrou:
        market_data._memoire = None
    with index_history._CACHE_LOCK:
        index_history._CACHE["stamp"] = None
        index_history._CACHE["data"] = None
    application._EXTENDED_HISTORY_CACHE = None


def _norm(texte):
    return (texte or "").replace("\u202f", " ").replace("\u00a0", " ").replace("\n", " ")


def _theme(page, sombre):
    clair = page.evaluate("() => document.documentElement.classList.contains('light')")
    if sombre == (not clair):
        return
    page.locator("[data-theme-btn]").first.click()
    page.wait_for_function(
        "(sombre) => document.documentElement.classList.contains('light') === !sombre",
        arg=sombre,
        timeout=5000,
    )


def _compter(journal, morceau):
    return sum(1 for url in journal if morceau in url)


def _indices_module(journal):
    """BRVM-C et BRVM-30 seulement. BRVM-COMPOSITE (comparaison) ne compte pas."""
    return [u for u in journal if "index=BRVM-C&" in u or "index=BRVM-30" in u]


def _taille_axe(page, selecteur):
    """Taille écran des graduations, en px, après le passage du viewBox."""
    return page.evaluate(
        """(sel) => {
          var t = document.querySelector(sel + ' .ci-svg text');
          if (!t) return 0;
          var ctm = t.getScreenCTM();
          var taille = parseFloat(t.getAttribute('font-size')) || 0;
          if (!ctm || !taille) return 0;
          return Math.abs(taille * ctm.a);
        }""",
        selecteur,
    )


def _ouvrir(navigateur, url, largeur):
    from playwright.sync_api import expect  # noqa: F401

    contexte = navigateur.new_context(
        viewport={"width": largeur, "height": 900},
        locale="fr-FR",
        has_touch=True,
    )
    page = contexte.new_page()
    erreurs = []
    journal = []
    page.on("pageerror", lambda err: erreurs.append("pageerror: " + str(err)))
    page.on("console", lambda msg: erreurs.append(msg.text) if msg.type == "error" else None)

    def _note(req):
        if req.method != "GET":
            return
        u = urlparse(req.url)
        if u.path == "/api/market" or u.path == "/api/index-history" or u.path.startswith("/api/price-history-extended/"):
            journal.append(u.path + (("?" + u.query) if u.query else ""))

    page.on("request", _note)

    def _route(route):
        if not route.request.url.startswith(url):
            route.abort()
            return
        route.continue_()

    page.route("**/*", _route)
    return contexte, page, erreurs, journal


def _poser_doigt(page, selecteur, ratio):
    """Clic aux coordonnées de la courbe, même si une couche couvre le SVG."""
    cible = page.locator(selecteur)
    cible.scroll_into_view_if_needed()
    boite = cible.bounding_box()
    assert boite and boite["width"] > 80, selecteur
    x = boite["x"] + boite["width"] * ratio
    y = boite["y"] + min(boite["height"] * 0.45, boite["height"] - 4)
    if page.viewport_size["width"] <= 500:
        page.touchscreen.tap(x, y)
    else:
        page.mouse.click(x, y)


def test_fiche_et_marche(base_url):
    from playwright.sync_api import sync_playwright

    url, jours = base_url
    fin = jours[-1]
    seuil_1m = _decaler_mois(fin, -1).isoformat()
    os.makedirs(CAPTURES, exist_ok=True)
    with sync_playwright() as pw:
        navigateur = pw.chromium.launch(
            executable_path="/usr/bin/google-chrome",
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            for largeur, nom_l in ((1280, "1280"), (390, "390")):
                for sombre, nom_t in ((False, "clair"), (True, "sombre")):
                    _verifier_fiche(navigateur, url, largeur, sombre, nom_l, nom_t, seuil_1m)
                    _verifier_marche(navigateur, url, largeur, sombre, nom_l, nom_t, seuil_1m)
        finally:
            navigateur.close()


def _verifier_fiche(navigateur, url, largeur, sombre, nom_l, nom_t, seuil_1m):
    contexte, page, erreurs, journal = _ouvrir(navigateur, url, largeur)
    try:
        page.goto(url + "/societe/SMBC", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_function(
            """() => {
              var p = document.getElementById('page-stock');
              var d = document.getElementById('stockDetail');
              return !!(p && p.classList.contains('on') && d && d.innerText.indexOf('SMBC') !== -1
                && !d.querySelector('.stock-skeleton'));
            }""",
            timeout=20000,
        )
        _theme(page, sombre)
        page.locator('.ctab-btn[data-ctab="chiffres"]').click()
        page.wait_for_function(
            """() => {
              var l = document.querySelector('#stockChartDiv .ci-lecture');
              var s = document.querySelector('#stockChartDiv .ci-svg');
              var b = document.querySelector('#stockChartDiv .ci-periodes');
              if (!l || !s || !b) return false;
              var lr = l.getBoundingClientRect();
              var sr = s.getBoundingClientRect();
              var br = b.getBoundingClientRect();
              return lr.height > 8 && sr.width > 80 && lr.bottom <= sr.top + 2 && br.top >= sr.bottom - 2;
            }""",
            timeout=15000,
        )
        boutons = page.locator("#stockChartDiv .ci-periode").all_inner_texts()
        assert boutons == ["1M", "3M", "Tout"], boutons
        assert _compter(journal, "/api/market") == 1, journal
        assert _compter(journal, "price-history-extended") == 1, journal
        assert "period=tout" in journal[-1] or any("period=tout" in u for u in journal)
        assert _indices_module(journal) == []

        x_avant = float(page.locator("#stockChartDiv .ci-repere").get_attribute("x1"))
        date_avant = page.locator("#stockChartDiv .ci-date").inner_text()
        _poser_doigt(page, "#stockChartDiv .ci-svg", 0.22)
        page.wait_for_timeout(150)
        x_apres = float(page.locator("#stockChartDiv .ci-repere").get_attribute("x1"))
        lecture = _norm(page.locator("#stockChartDiv .ci-lecture").inner_text())
        assert x_apres < x_avant, (x_avant, x_apres)
        assert page.locator("#stockChartDiv .ci-date").inner_text() != date_avant
        assert "XOF" in lecture
        assert "%" in page.locator("#stockChartDiv .ci-var").inner_text()
        garde = page.locator("#stockChartDiv .ci-lecture").inner_text()
        page.mouse.move(2, 2)
        page.wait_for_timeout(200)
        assert page.locator("#stockChartDiv .ci-lecture").inner_text() == garde

        if largeur >= 800:
            page.mouse.move(
                page.locator("#stockChartDiv .ci-svg").bounding_box()["x"] + 30,
                page.locator("#stockChartDiv .ci-svg").bounding_box()["y"] + 40,
            )
            page.wait_for_timeout(150)
            survole = page.locator("#stockChartDiv .ci-lecture").inner_text()
            page.mouse.move(2, 2)
            page.wait_for_timeout(150)
            assert page.locator("#stockChartDiv .ci-lecture").inner_text() == survole

        avant_ext = _compter(journal, "price-history-extended")
        avant_marche = _compter(journal, "/api/market")
        page.locator('#stockChartDiv .ci-periode[data-periode="1M"]').click()
        page.wait_for_function(
            "(seuil) => (document.getElementById('stockChartDiv').getAttribute('data-ci-debut') || '') >= seuil",
            arg=seuil_1m,
            timeout=5000,
        )
        page.wait_for_timeout(400)
        assert _compter(journal, "price-history-extended") == avant_ext, journal
        assert _compter(journal, "/api/market") == avant_marche, journal
        assert _indices_module(journal) == []
        if largeur <= 500:
            assert _taille_axe(page, "#stockChartDiv") >= 10
        assert page.locator('#stockChartDiv .ci-periode[data-periode="1M"]').get_attribute("aria-pressed") == "true"
        page.locator("#stockChartDiv").scroll_into_view_if_needed()
        page.locator("#stockChartDiv").screenshot(path=os.path.join(CAPTURES, "fiche-%s-%s.png" % (nom_l, nom_t)))
        assert erreurs == [], erreurs
    finally:
        contexte.close()


def _verifier_marche(navigateur, url, largeur, sombre, nom_l, nom_t, seuil_1m):
    contexte, page, erreurs, journal = _ouvrir(navigateur, url, largeur)
    try:
        page.goto(url + "/#marche", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_function(
            """() => {
              var p = document.getElementById('page-marche');
              var a = document.querySelector('#mkt-courbe-brvm-c .ci-lecture');
              var b = document.querySelector('#mkt-courbe-brvm-30 .ci-lecture');
              return !!(p && p.classList.contains('on') && a && b && a.innerText.trim() && b.innerText.trim());
            }""",
            timeout=20000,
        )
        _theme(page, sombre)
        boutons = page.locator("#mkt-courbe-brvm-c .ci-periode").all_inner_texts()
        assert boutons == ["1M", "3M", "Tout"], boutons
        assert page.locator("#mkt-courbe-brvm-30 .ci-periode").all_inner_texts() == boutons
        assert "XOF" not in _norm(page.locator("#mkt-courbe-brvm-c .ci-lecture").inner_text())
        assert _compter(journal, "/api/market") == 1, journal
        urls_idx = _indices_module(journal)
        assert len(urls_idx) == 2, urls_idx
        assert any("BRVM-C" in u and "range=1A" in u for u in urls_idx), urls_idx
        assert any("BRVM-30" in u and "range=1A" in u for u in urls_idx), urls_idx

        _poser_doigt(page, "#mkt-courbe-brvm-c .ci-svg", 0.25)
        page.wait_for_timeout(150)
        assert "%" in page.locator("#mkt-courbe-brvm-c .ci-var").inner_text()
        assert page.locator("#mkt-courbe-brvm-c .ci-repere").count() == 1
        garde = page.locator("#mkt-courbe-brvm-c .ci-lecture").inner_text()
        page.mouse.move(2, 2)
        page.wait_for_timeout(200)
        assert page.locator("#mkt-courbe-brvm-c .ci-lecture").inner_text() == garde

        avant_idx = len(urls_idx)
        avant_marche = _compter(journal, "/api/market")
        page.locator('#mkt-courbe-brvm-c .ci-periode[data-periode="1M"]').click()
        page.locator('#mkt-courbe-brvm-30 .ci-periode[data-periode="3M"]').click()
        page.wait_for_function(
            "(seuil) => (document.getElementById('mkt-courbe-brvm-c').getAttribute('data-ci-debut') || '') >= seuil",
            arg=seuil_1m,
            timeout=5000,
        )
        page.wait_for_timeout(400)
        assert len(_indices_module(journal)) == avant_idx, journal
        if largeur <= 500:
            assert _taille_axe(page, "#mkt-courbe-brvm-c") >= 10
            assert _taille_axe(page, "#mkt-courbe-brvm-30") >= 10
        assert _compter(journal, "/api/market") == avant_marche, journal
        assert _compter(journal, "price-history-extended") == 0
        page.locator("#mkt-indices-courbes").scroll_into_view_if_needed()
        page.locator("#mkt-indices-courbes").screenshot(path=os.path.join(CAPTURES, "marche-%s-%s.png" % (nom_l, nom_t)))
        assert erreurs == [], erreurs
    finally:
        contexte.close()


def test_accueil_reste_masque(base_url):
    from playwright.sync_api import sync_playwright

    url, _jours = base_url
    with sync_playwright() as pw:
        navigateur = pw.chromium.launch(
            executable_path="/usr/bin/google-chrome",
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            contexte, page, erreurs, journal = _ouvrir(navigateur, url, 1280)
            page.goto(url + "/", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_function(
                "() => document.getElementById('page-welcome').classList.contains('on')",
                timeout=20000,
            )
            page.wait_for_timeout(1200)
            assert page.evaluate("() => { var z = document.getElementById('accueil-courbe'); return !!(z && z.hidden); }")
            assert _compter(journal, "/api/index-history") == 0, journal
            assert _compter(journal, "/api/market") == 1, journal
            assert erreurs == [], erreurs
            contexte.close()
        finally:
            navigateur.close()
