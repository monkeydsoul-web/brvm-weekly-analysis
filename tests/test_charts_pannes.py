# -*- coding: utf-8 -*-
"""CHARTS-ERR-1 : panne réseau sur les courbes, message et un seul Réessayer.

Hors CI (Playwright) :

    pytest tests/test_charts_pannes.py -q -s
"""
import json
import os
import socket
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
INTERACTIFS = (ROOT / "dashboard" / "js" / "charts_interactifs.js").read_text(encoding="utf-8")
COMPARAISON = (ROOT / "dashboard" / "js" / "charts_comparaison.js").read_text(encoding="utf-8")

_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes") or os.environ.get("GITHUB_ACTIONS") == "true"
_REEL_CONNECT = socket.socket.connect
_REEL_CONNECT_EX = socket.socket.connect_ex
_REEL_CREATE = socket.create_connection
_REEL_DNS = socket.getaddrinfo

_FICHIERS = (
    "live_ranking.json",
    "macro_cache.json",
    "market_cache.json",
    "live_cache.json",
    "price_history.json",
    "index_history.json",
)


def test_sources_pannes_sans_repli():
    """Délai, r.ok, message, bouton. Le message « trop peu » et les seuils restent."""
    for src in (INTERACTIFS, COMPARAISON):
        assert "DELAI_LECTURE_MS = 10000" in src
        assert "if (!r.ok) throw new Error" in src
        assert "Données indisponibles" in src
        assert "Réessayer" in src
        assert "console.error(" in src
        assert "return [];" not in src.split("function lireJson")[1].split("function ")[0]
    assert "catch(function() { return []; })" not in INTERACTIFS
    assert "catch(function () { resolve(window._priceHistory || {}); })" not in COMPARAISON
    assert "L'historique n'a pas pu être lu" not in COMPARAISON
    assert "Trop peu de séances en commun" in COMPARAISON
    assert "var SEUIL = 20;" in COMPARAISON
    assert 'SEUIL_COURS_FIABLE = "2026-05-19"' in INTERACTIFS
    assert "historique absent" not in COMPARAISON
    assert "setInterval" not in COMPARAISON
    assert "function attendrePrix" not in COMPARAISON
    assert "lirePrix()" in COMPARAISON


def _jours(n=82):
    fin = date(2026, 10, 2)
    trouve = []
    curseur = fin
    while len(trouve) < n:
        if curseur.weekday() < 5:
            trouve.append(curseur)
        curseur -= timedelta(days=1)
    trouve.reverse()
    return trouve


def _sauver(dossier):
    sauve = {}
    for nom in _FICHIERS:
        chemin = os.path.join(dossier, nom)
        if os.path.isfile(chemin):
            with open(chemin, "rb") as f:
                sauve[nom] = f.read()
        else:
            sauve[nom] = None
    return sauve


def _rendre(dossier, sauve):
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
    sauve = _sauver(dossier)
    maintenant = datetime.now(timezone.utc).isoformat()
    jours = _jours(82)
    assert jours[0].isoformat() >= "2026-05-19"
    cours = []
    seances = []
    for i, jour in enumerate(jours):
        iso = jour.isoformat()
        prix = 45000 if i == len(jours) - 1 else 10000 + i
        cours.append({"date": iso, "price": prix, "source": "live"})
        seances.append({"date": iso, "indices": {"BRVM-C": 300 + i}})
    with open(os.path.join(dossier, "price_history.json"), "w", encoding="utf-8") as f:
        json.dump({"SNTS": cours}, f)
    with open(os.path.join(dossier, "index_history.json"), "w", encoding="utf-8") as f:
        json.dump({"seances": seances}, f)
    with open(os.path.join(dossier, "live_ranking.json"), "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": maintenant,
            "market_open": False,
            "total": 1,
            "ranking": [{
                "ticker": "SNTS",
                "name": "Sonatel",
                "sector": "Télécommunications",
                "country": "Sénégal",
                "price": 45000,
                "note10": 7.3,
                "composite_adj": 58,
                "rank": 1,
                "change_pct": 0.2,
                "statut": "cote",
                "conseil": "À surveiller",
                "conseil_libelle": "À surveiller",
                "conseil_couleur": "orange",
            }],
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
                {"name": "BRVM - COMPOSITE", "prev": 320.0, "current": 321.0, "change": 0.3, "ytd": 0.05},
                {"name": "BRVM-30", "prev": 140.0, "current": 141.0, "change": 0.7, "ytd": 0.02},
            ],
            "sector_indices": [],
            "total_return": {},
        }, f)
    with open(os.path.join(dossier, "live_cache.json"), "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": maintenant,
            "market_open": False,
            "prices": {"SNTS": {"price": 45000, "change_pct": 0.2, "volume": 10, "source": "fixture"}},
            "stats": {"total": 1, "with_price": 1, "sources": {"fixture": 1}},
        }, f)
    return sauve


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


def _compter(journal, chemin):
    return sum(1 for url in journal if url.split("?", 1)[0] == chemin)


def _ouvrir(navigateur, base, largeur, blocage):
    contexte = navigateur.new_context(
        viewport={"width": largeur, "height": 900},
        locale="fr-FR",
        has_touch=True,
    )
    page = contexte.new_page()
    console = []
    pageerrors = []
    journal = []
    page.on("pageerror", lambda err: pageerrors.append(str(err)))
    page.on("console", lambda msg: console.append(msg.text) if msg.type == "error" else None)

    def noter(req):
        if req.method != "GET":
            return
        u = urlparse(req.url)
        if u.path in ("/api/price-history", "/api/index-history", "/api/market"):
            journal.append(u.path + (("?" + u.query) if u.query else ""))

    page.on("request", noter)

    def route(route):
        if not route.request.url.startswith(base):
            route.abort()
            return
        chemin = urlparse(route.request.url).path
        if blocage.get("prix") and chemin == "/api/price-history":
            route.abort()
            return
        if blocage.get("indice") and chemin == "/api/index-history":
            route.abort()
            return
        route.continue_()

    page.route("**/*", route)
    return contexte, page, console, pageerrors, journal


def _fiche(page, base):
    page.goto(base + "/societe/SNTS", wait_until="domcontentloaded", timeout=20000)
    page.wait_for_function(
        """() => {
          var p = document.getElementById('page-stock');
          var d = document.getElementById('stockDetail');
          return !!(p && p.classList.contains('on') && d && d.innerText.indexOf('SNTS') !== -1
            && !d.querySelector('.stock-skeleton'));
        }""",
        timeout=20000,
    )
    page.locator("#page-stock .ctab-btn[data-ctab='chiffres']").click()


def _courbe_snts(page):
    page.wait_for_function(
        """() => document.getElementById('stockChartDiv').getAttribute('data-ci-n') === '82'""",
        timeout=15000,
    )
    assert page.locator("#stockChartDiv .ci-lecture").get_attribute("data-ci-valeur") == "45000"


@pytest.mark.skipif(_CI, reason="Playwright hors CI. Local : pytest tests/test_charts_pannes.py -q -s")
def test_pannes_puis_reessayer(monkeypatch):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    _autoriser_local(monkeypatch)
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    sauve = _ecrire_fixtures()
    import app as application
    import index_history
    import market_data
    market_data._memoire = None
    index_history.invalider_cache()
    from werkzeug.serving import make_server

    serveur = make_server("127.0.0.1", 0, application.app, threaded=True)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    base = "http://127.0.0.1:%d" % serveur.server_address[1]
    try:
        with sync_playwright() as pw:
            navigateur = pw.chromium.launch(
                executable_path="/usr/bin/google-chrome",
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            try:
                for largeur in (1280, 390):
                    _scenario_normal(navigateur, base, largeur)
                    _scenario_prix(navigateur, base, largeur)
                    _scenario_indice(navigateur, base, largeur)
            finally:
                navigateur.close()
    finally:
        serveur.shutdown()
        _rendre(os.environ["BRVM_DATA_DIR"], sauve)
        market_data._memoire = None
        index_history.invalider_cache()


def _scenario_normal(navigateur, base, largeur):
    contexte, page, console, pageerrors, _journal = _ouvrir(navigateur, base, largeur, {})
    try:
        _fiche(page, base)
        _courbe_snts(page)
        page.wait_for_selector("#cmp-courbes [data-cmp-graphique]", timeout=15000)
        assert "Trop peu" not in page.locator("#cmp-courbes").inner_text()
        assert page.locator("#stockChartDiv .ci-reessayer").count() == 0
        assert page.locator("#cmp-courbes .ci-reessayer").count() == 0
        assert console == [], console
        assert pageerrors == [], pageerrors
    finally:
        contexte.close()


def _scenario_prix(navigateur, base, largeur):
    blocage = {"prix": True}
    contexte, page, _console, pageerrors, journal = _ouvrir(navigateur, base, largeur, blocage)
    try:
        _fiche(page, base)
        page.wait_for_selector("#stockChartDiv .ci-reessayer", timeout=15000)
        assert page.locator("#stockChartDiv .ci-vide").inner_text().strip() == "Données indisponibles"
        assert page.locator("#stockChartDiv .ci-reessayer").inner_text() == "Réessayer"
        page.wait_for_timeout(400)
        avant = _compter(journal, "/api/price-history")
        assert avant >= 1
        page.wait_for_timeout(3000)
        assert _compter(journal, "/api/price-history") == avant, journal
        blocage["prix"] = False
        page.locator("#stockChartDiv .ci-reessayer").click()
        _courbe_snts(page)
        assert _compter(journal, "/api/price-history") == avant + 1, journal
        assert pageerrors == [], pageerrors
    finally:
        contexte.close()


def _scenario_indice(navigateur, base, largeur):
    blocage = {"indice": True}
    contexte, page, _console, pageerrors, journal = _ouvrir(navigateur, base, largeur, blocage)
    try:
        _fiche(page, base)
        _courbe_snts(page)
        page.wait_for_selector("#cmp-courbes .ci-reessayer", timeout=15000)
        texte = page.locator("#cmp-courbes").inner_text()
        assert "Données indisponibles" in texte
        assert "Trop peu" not in texte
        assert page.locator("#cmp-courbes .ci-reessayer").inner_text() == "Réessayer"
        avant_idx = _compter(journal, "/api/index-history")
        avant_prix = _compter(journal, "/api/price-history")
        assert avant_idx >= 1
        page.wait_for_timeout(3000)
        assert _compter(journal, "/api/index-history") == avant_idx, journal
        assert _compter(journal, "/api/price-history") == avant_prix, journal
        blocage["indice"] = False
        page.locator("#cmp-courbes .ci-reessayer").click()
        page.wait_for_selector("#cmp-courbes [data-cmp-graphique]", timeout=15000)
        apres = page.locator("#cmp-courbes").inner_text()
        assert "Données indisponibles" not in apres
        assert "Trop peu" not in apres
        assert _compter(journal, "/api/index-history") == avant_idx + 1, journal
        assert _compter(journal, "/api/price-history") == avant_prix, journal
        assert pageerrors == [], pageerrors
    finally:
        contexte.close()
