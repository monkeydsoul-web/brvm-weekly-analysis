# -*- coding: utf-8 -*-
"""ACTU-1 : l'encadre « Comment lire cette page » des Actualites decrit ce que la page affiche.

La page n'affiche que Google News (news_v2.js masque la carte des annonces
officielles). L'aide ne parle donc plus d'annonces classees par categorie
ni de pastilles 🟢.

Le test Playwright est hors CI (Chromium non installe dans le workflow) :

    pytest tests/test_actualites_aide.py -q -s
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


def _texte_aide():
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    debut = html.index('id="beginner-banner-news"')
    return html[debut:html.index("<button", debut)].replace("\u00a0", " ")


def test_aide_ne_promet_plus_les_annonces_officielles():
    aide = _texte_aide()
    assert "annonces officielles" not in aide.lower()
    assert "🟢" not in aide
    assert "Google News" in aide
    assert "« Très pertinent » et « Pertinent »" in aide
    assert "« Tous les tickers »" in aide


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


def _article(n, score, jour):
    return {"titre": "Article %d sur la BRVM" % n, "lien": "https://exemple.invalid/article-%d" % n,
            "date": "2026-10-%02d" % jour, "source": "Source %d" % n, "resume": "Resume de l'article %d." % n,
            "relevance": {"score": score, "category": "cours"}}


@pytest.fixture(scope="module")
def base_url():
    pytest.importorskip("playwright.sync_api")
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    maintenant = datetime.now(timezone.utc).isoformat()

    def ligne(t, n, c):
        return {"ticker": t, "name": n, "sector": "Banque", "price": 10000, "composite_adj": c, "change_pct": 0.1,
                "div_yield": 5.0, "pe_ref": 10, "pdf_verdict": "NEUTRE"}

    fichiers = [
        _ecrire("live_ranking.json", {"updated_at": maintenant, "market_open": False, "total": 2,
                                      "ranking": [ligne("SNTS", "Sonatel", 64), ligne("SGBC", "SGB CI", 58)]}),
        _ecrire("market_cache.json", {
            "updated_at": maintenant, "market_activity": {"Capitalisation Actions": "10 000"}, "top5": [], "flop5": [],
            "indices": [
                {"name": "BRVM - COMPOSITE", "prev": 200.0, "current": 201.0, "change": 0.5, "ytd": 3.0},
                {"name": "BRVM - 30", "prev": 100.0, "current": 101.0, "change": 1.0, "ytd": 2.0},
            ],
            "sector_indices": [], "total_return": {}}),
        # Google News : un article tres pertinent, un pertinent, un sans pastille par societe.
        _ecrire("brvm_news.json", {
            "SNTS": [_article(1, 90, 2), _article(2, 60, 1), _article(3, 20, 3)],
            "SGBC": [_article(4, 85, 1), _article(5, 55, 2)],
        }),
        # Annonces comme en prod : titres « Telecharger », ticker vide. Elles ne doivent pas apparaitre.
        _ecrire("brvm_announcements.json", {
            "communiques": [{"titre": "Télécharger", "ticker": None, "date": "2026-10-0%d" % i} for i in (1, 2, 3)],
        }),
    ]
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
    for f in fichiers:
        _restaurer(*f)


@pytest.mark.skipif(_CI, reason="Playwright hors CI. Local : pytest tests/test_actualites_aide.py -q -s")
def test_chaque_phrase_de_l_aide_correspond_a_la_page(base_url, tmp_path):
    from playwright.sync_api import expect, sync_playwright

    preuves = Path(os.environ.get("BRVM_PREUVE_DIR") or tmp_path)
    preuves.mkdir(parents=True, exist_ok=True)
    erreurs = []
    with sync_playwright() as pw:
        navigateur = pw.chromium.launch(
            headless=True,
            executable_path=os.environ.get("BRVM_CHROMIUM") or None,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = navigateur.new_page()
        page.on("pageerror", lambda err: erreurs.append("pageerror: " + str(err)))
        page.on("console", lambda msg: erreurs.append(msg.text) if msg.type == "error" else None)

        def route(route):
            url = route.request.url
            if "exchangerate-api.com" in url:
                route.fulfill(status=200, content_type="application/json", body='{"rates":{"EUR":0.001524,"USD":0.001667}}')
                return
            if not url.startswith(base_url):
                route.abort()
                return
            route.continue_()

        page.route("**/*", route)
        page.add_init_script("localStorage.setItem('brvm_visited','1')")
        for largeur, hauteur in ((1280, 800), (390, 844)):
            page.set_viewport_size({"width": largeur, "height": hauteur})
            page.goto(base_url + "/", wait_until="load", timeout=20000)
            page.wait_for_function("() => (window.scores || []).length === 2", timeout=10000)
            page.evaluate("() => navTo('news')")
            cartes = page.locator("#nv2-gnews-list .gnews-card")
            expect(cartes.first).to_be_visible(timeout=10000)

            aide = page.locator("#beginner-banner-news")
            expect(aide).to_be_visible()
            texte = aide.inner_text().replace("\u00a0", " ")
            phrases = [p.strip() for p in re.split(r"(?<=\.)\s+", texte.split(":", 1)[1].replace("OK", "").strip()) if p.strip()]
            assert len(phrases) == 5, phrases

            # 1. « Articles ... repris de Google News, les plus pertinents en premier. »
            assert "repris de Google News" in phrases[0]
            expect(page.locator("#news-v2-main .ct")).to_contain_text("Google News")
            scores = page.evaluate("""() => Array.from(document.querySelectorAll('#nv2-gnews-list .gnews-card')).map(c =>
                c.innerText.includes('Très pertinent') ? 2 : c.innerText.includes('Pertinent') ? 1 : 0)""")
            assert scores == sorted(scores, reverse=True), scores

            # 2. « Chaque article indique la societe concernee, sa date et sa source. »
            assert "la société concernée, sa date et sa source" in phrases[1]
            details = page.evaluate("""() => Array.from(document.querySelectorAll('#nv2-gnews-list .gnews-card')).map(c => c.firstElementChild.innerText)""")
            assert len(details) == 5
            for d in details:
                assert re.search(r"\b(SNTS|SGBC)\b", d) and re.search(r"2026-10-0\d", d) and "Source " in d, d

            # 3. « Les pastilles « Tres pertinent » et « Pertinent » ... »
            assert "« Très pertinent » et « Pertinent »" in phrases[2]
            expect(page.locator("#nv2-gnews-list span", has_text="Très pertinent").first).to_be_visible()
            expect(page.locator("#nv2-gnews-list span", has_text=re.compile(r"^Pertinent$")).first).to_be_visible()

            # 4. « Le menu « Tous les tickers » limite la liste a une societe. »
            assert "« Tous les tickers »" in phrases[3]
            filtre = page.locator("#news-ticker-filter")
            expect(filtre).to_be_visible()
            assert filtre.locator("option").first.inner_text() == "Tous les tickers"

            # 5. « Cliquez sur un titre pour lire l'article sur le site d'origine. »
            assert "Cliquez sur un titre" in phrases[4]
            lien = page.locator("#nv2-gnews-list .gnews-card a").first
            assert lien.get_attribute("target") == "_blank"
            assert lien.get_attribute("href").startswith("https://exemple.invalid/article-")

            # Ce qui n'est pas affiche n'est pas decrit
            assert "annonces officielles" not in texte.lower() and "🟢" not in texte
            assert page.locator("#annc-list").is_hidden()
            assert page.locator("text=Télécharger").count() == 0

            page.screenshot(path=str(preuves / ("actualites_%d.png" % largeur)))

            filtre.select_option("SGBC")
            page.wait_for_function("() => document.querySelectorAll('#nv2-gnews-list .gnews-card').length === 2")
            assert all("SGBC" in d for d in page.evaluate(
                "() => Array.from(document.querySelectorAll('#nv2-gnews-list .gnews-card')).map(c => c.firstElementChild.innerText)"))
        navigateur.close()
    assert erreurs == [], erreurs
