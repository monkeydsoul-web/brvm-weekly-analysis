# -*- coding: utf-8 -*-
"""Signaux : la section Portefeuilles IA disparaît, la phrase de page est entière.

La section contredisait « pas un conseil en investissement » : rendements
visés codés en dur, bouton Adopter, « score ≥50 » et « Taux BCEAO 6.5 % ».
Le front ne doit plus l'afficher ni appeler la route qui ne servait qu'à elle.
"""
import json
import os
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PREV = ROOT / "dashboard" / "previsions.js"
HTML = ROOT / "dashboard" / "index.html"

# Chaînes de la section retirée. Elles viennent du rendu, pas d'un autre écran.
CHAINES_SECTION = (
    "Portefeuilles IA",
    "Adopter",
    "score ≥50",
    "Taux BCEAO 6.5%",
    "+8–12",
    "+15–25",
    "+25–40",
    "objectif 12 mois",
    "Rendement visé",
)
PHRASE_TRONQUEE = (
    "Elle affiche les signaux des modèles.  pour accéder à l'analyse complète."
)
PHRASE_ENTIERE = "Elle affiche les signaux des modèles."


def _js():
    return PREV.read_text(encoding="utf-8")


def _page_signaux():
    html = HTML.read_text(encoding="utf-8")
    debut = html.index('id="page-signals"')
    fin = html.index('id="help-fab"')
    return html[debut:fin]


def test_le_front_ne_dessine_plus_les_portefeuilles():
    src = _js()
    for chaine in ("Portefeuilles IA", "Adopter", "objectif 12 mois", "Rendement visé"):
        assert chaine not in src
    assert "/api/previsions/portfolios" not in src
    assert "_prevRenderPortfolios" not in src
    assert "_prevDrawPortfolios" not in src
    assert "_prevAdopter" not in src
    assert "_prevBacktestPortfolio" not in src
    assert "_prevPortfolios" not in src
    assert "fetch('/api/previsions/signaux')" in src
    assert "function renderPrevisionsPage" in src


def test_phrase_de_signaux_nest_plus_tronquee():
    page = _page_signaux()
    assert PHRASE_TRONQUEE not in page
    assert "pour accéder à l'analyse complète" not in page
    assert PHRASE_ENTIERE in page
    assert page.count(PHRASE_ENTIERE) == 1


_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes") or os.environ.get("GITHUB_ACTIONS") == "true"


@pytest.fixture(autouse=True)
def autoriser_local(monkeypatch):
    """Chromium et Werkzeug restent sur la machine. Le scrape externe reste refusé."""
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


_TAUX_REEL = None


def _telecharger_taux_reel():
    """Corps réel de l'API de change, lu avant le filet qui bloque le réseau."""
    import urllib.request

    try:
        with urllib.request.urlopen(
            "https://api.exchangerate-api.com/v4/latest/XOF", timeout=8
        ) as reponse:
            return reponse.read()
    except Exception:
        return b""


def _ecrire_caches(dossier):
    """Classement de test déjà versionné, historique de cours vide (aucun cours inventé)."""
    fixture = ROOT / "tests" / "fixtures" / "live_ranking.json"
    classement = os.path.join(dossier, "live_ranking.json")
    with open(fixture, encoding="utf-8") as src, open(classement, "w", encoding="utf-8") as out:
        out.write(src.read())
    historique = os.path.join(dossier, "price_history.json")
    with open(historique, "w", encoding="utf-8") as out:
        out.write("{}")
    return classement, historique


@pytest.fixture(scope="module")
def base_url():
    if _CI:
        pytest.skip("Playwright hors CI")
    pytest.importorskip("playwright.sync_api")
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    dossier = os.environ["BRVM_DATA_DIR"]
    classement, historique = _ecrire_caches(dossier)
    global _TAUX_REEL
    if _TAUX_REEL is None:
        _TAUX_REEL = _telecharger_taux_reel()
    import app as application
    from werkzeug.serving import make_server

    serveur = make_server("127.0.0.1", 0, application.app, threaded=True)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    url = "http://127.0.0.1:%d" % serveur.server_address[1]
    yield url
    serveur.shutdown()
    for chemin in (classement, historique):
        if os.path.exists(chemin):
            os.remove(chemin)


@pytest.mark.skipif(_CI, reason="Playwright hors CI. Local : pytest tests/test_signaux_sans_portefeuilles.py -q -s")
def test_page_signaux_sans_section_ni_requete_portefeuille(base_url, tmp_path):
    """Aucune chaîne de la section, aucune requête portefeuille, un seul GET /api/market."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    preuves = Path(os.environ.get("BRVM_PREUVES", str(tmp_path)))
    preuves.mkdir(parents=True, exist_ok=True)
    erreurs = []
    market = []
    portefeuille = []

    with sync_playwright() as pw:
        navigateur = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            for largeur, theme, nom in (
                (1280, "clair", "signaux-1280-clair"),
                (1280, "sombre", "signaux-1280-sombre"),
                (390, "clair", "signaux-390-clair"),
                (390, "sombre", "signaux-390-sombre"),
            ):
                contexte = navigateur.new_context(
                    viewport={"width": largeur, "height": 800},
                    color_scheme="dark" if theme == "sombre" else "light",
                )
                page = contexte.new_page()
                if _TAUX_REEL:
                    def _servir_taux(route):
                        route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=_TAUX_REEL,
                        )
                    page.route("https://api.exchangerate-api.com/**", _servir_taux)

                def _console(msg, _nom=nom):
                    if msg.type == "error":
                        erreurs.append(_nom + ": " + msg.text)

                page.on("pageerror", lambda err, _nom=nom: erreurs.append(_nom + ": pageerror: " + str(err)))
                page.on("console", _console)

                def _requete(req, _nom=nom):
                    if req.method != "GET":
                        return
                    if req.url.endswith("/api/market") or "/api/market?" in req.url:
                        market.append(_nom)
                    if "/api/previsions/portfolios" in req.url:
                        portefeuille.append(req.url)

                page.on("request", _requete)
                page.goto(base_url + "/#signals", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_function(
                    """() => {
                      var page = document.getElementById('page-signals');
                      var panneau = document.getElementById('prev-signaux-panel');
                      if (!page || !page.classList.contains('on') || !panneau) return false;
                      var texte = panneau.innerText || '';
                      return texte.indexOf('Prévision favorable') !== -1
                        && texte.indexOf('Calcul des signaux') === -1;
                    }""",
                    timeout=20000,
                )
                if theme == "sombre":
                    page.evaluate("dark = true; _applyTheme();")
                else:
                    page.evaluate("dark = false; _applyTheme();")
                if _TAUX_REEL:
                    page.wait_for_function(
                        """() => {
                          var el = document.getElementById('curr-rate');
                          if (!el) return true;
                          var t = el.textContent || '';
                          return t.indexOf('€') !== -1 && t.indexOf('1,67') === -1;
                        }""",
                        timeout=10000,
                    )
                page.wait_for_timeout(400)
                texte = page.locator("#page-signals").inner_text()
                for chaine in CHAINES_SECTION:
                    assert chaine not in texte, chaine
                assert "pour accéder à l'analyse complète" not in texte
                assert PHRASE_ENTIERE in texte
                page.screenshot(path=str(preuves / (nom + ".png")))
                contexte.close()
        finally:
            navigateur.close()

    assert erreurs == []
    assert portefeuille == []
    assert market == [
        "signaux-1280-clair",
        "signaux-1280-sombre",
        "signaux-390-clair",
        "signaux-390-sombre",
    ]
    for nom in ("signaux-1280-clair", "signaux-1280-sombre", "signaux-390-clair", "signaux-390-sombre"):
        assert (preuves / (nom + ".png")).is_file()
