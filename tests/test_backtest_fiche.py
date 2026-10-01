# -*- coding: utf-8 -*-
"""Backtest ouvert depuis une fiche : message, etendue reelle, puces justes.

1. Avec moins de 2 titres, launchBacktest() affiche un message et n'appelle
   pas /api/backtest.
2. Le resultat indique la date de debut, la date de fin et le nombre de
   points reellement utilises, et previent si la periode choisie depasse
   les donnees.
3. Les puces affichent les ponderations reelles apres ajout ou retrait.

Le test Playwright est hors CI (Chromium non installe dans le workflow) :

    pip install playwright
    playwright install chromium
    pytest tests/test_backtest_fiche.py -q -s
"""
import json
import os
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes") or os.environ.get("GITHUB_ACTIONS") == "true"


def test_backtest_garde_etendue_puces():
    js = (ROOT / "dashboard" / "backtest.js").read_text(encoding="utf-8")
    debut = js.index("async function launchBacktest()")
    garde = js[debut:js.index("btUpdateWeights();", debut)]
    assert "_btMsg('Choisissez au moins 2 sociétés pour lancer le backtest.')" in garde
    assert garde.index("_btMsg(") < garde.index("return;")
    assert "fetch(" not in garde
    assert 'id="bt-msg"' in js
    assert "function _renderBTRange(d)" in js
    assert "_renderBTRange(d);" in js
    maj = js[js.index("function btUpdateWeights()"):js.index("function btToggle(")]
    assert "_btRenderChips();" in maj


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


def _jours_ouvres(nb_jours):
    """Jours ouvres des nb_jours derniers jours : historique plus court qu'un an."""
    aujourd_hui = date.today()
    jours = [aujourd_hui - timedelta(days=i) for i in range(nb_jours, 0, -1)]
    return [j.isoformat() for j in jours if j.weekday() < 5]


@pytest.fixture(scope="module")
def base_url():
    pytest.importorskip("playwright.sync_api")
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    maintenant = datetime.now(timezone.utc).isoformat()

    def ligne(ticker, nom, secteur, prix, note):
        return {
            "ticker": ticker,
            "name": nom,
            "sector": secteur,
            "price": prix,
            "composite_adj": note,
            "change_pct": 0.1,
            "div_yield": 5.0,
            "pe_ref": 10,
            "pdf_verdict": "NEUTRE",
        }

    classement, avant_classement = _ecrire("live_ranking.json", {
        "updated_at": maintenant,
        "market_open": False,
        "total": 3,
        "ranking": [
            ligne("SMBC", "SMB", "Industrie", 12900, 60),
            ligne("BICC", "BICI CI", "Banque", 26450, 58),
            ligne("SNTS", "Sonatel", "Telecoms", 43000, 54),
        ],
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
    dates = _jours_ouvres(110)
    historique, avant_historique = _ecrire("price_history.json", {
        "SMBC": [{"date": d, "price": 12000 + 10 * i, "source": "live"} for i, d in enumerate(dates)],
        "BICC": [{"date": d, "price": 26000 - 5 * i, "source": "live"} for i, d in enumerate(dates)],
        "SNTS": [{"date": d, "price": 43000 + i, "source": "live"} for i, d in enumerate(dates)],
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
    yield url, dates
    serveur.shutdown()
    market_data._memoire = None
    market_data._en_cours = False
    _restaurer(classement, avant_classement)
    _restaurer(marche, avant_marche)
    _restaurer(historique, avant_historique)


@pytest.mark.skipif(_CI, reason="Playwright hors CI. Local : pytest tests/test_backtest_fiche.py -q -s")
def test_backtest_depuis_fiche(base_url, tmp_path):
    """1280 et 390 : message a 1 titre sans appel, dates reelles, puces justes, 0 erreur console."""
    from playwright.sync_api import expect, sync_playwright

    base, dates = base_url
    if os.environ.get("BRVM_PREUVE_DIR"):
        preuves = Path(os.environ["BRVM_PREUVE_DIR"])
        preuves.mkdir(parents=True, exist_ok=True)
    else:
        preuves = tmp_path
    erreurs = []
    appels = []

    with sync_playwright() as pw:
        navigateur = pw.chromium.launch(
            headless=True,
            executable_path=os.environ.get("BRVM_CHROMIUM") or None,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = navigateur.new_page()
        page.on("pageerror", lambda err: erreurs.append("pageerror: " + str(err)))
        page.on("console", lambda msg: erreurs.append(msg.text) if msg.type == "error" else None)
        page.on("request", lambda req: appels.append(req.url) if "/api/backtest" in req.url else None)

        def route(route):
            url = route.request.url
            if "exchangerate-api.com" in url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"rates":{"EUR":0.001524,"USD":0.001667}}',
                )
                return
            if not url.startswith(base):
                route.abort()
                return
            route.continue_()

        page.route("**/*", route)

        def puces():
            return page.evaluate(
                """() => Array.from(document.querySelectorAll('#bt-selected > span')).map(s =>
                  s.querySelector('strong').textContent.trim() + ' ' + s.querySelector('span').textContent.trim())"""
            )

        for largeur, hauteur in ((1280, 800), (390, 844)):
            page.set_viewport_size({"width": largeur, "height": hauteur})
            page.goto(base + "/", wait_until="load", timeout=20000)
            page.wait_for_function("() => (window.scores || []).length === 3", timeout=10000)
            page.wait_for_function("() => typeof openBacktest === 'function'", timeout=10000)
            del appels[:]

            # Meme appel que le bouton Backtest de la fiche societe (core.js)
            page.evaluate("() => openBacktest(['SMBC'])")
            expect(page.locator("#bt-modal")).to_be_visible()
            assert puces() == ["SMBC 100%"]

            # (a) 1 titre : message visible, aucun appel reseau
            page.get_by_role("button", name="Lancer le backtesting").click()
            message = page.locator("#bt-msg")
            expect(message).to_be_visible()
            expect(message).to_have_text("Choisissez au moins 2 sociétés pour lancer le backtest.")
            message.scroll_into_view_if_needed()
            assert page.evaluate(
                """() => {
                  var m = document.getElementById('bt-msg').getBoundingClientRect();
                  var el = document.elementFromPoint(m.left + m.width / 2, m.top + m.height / 2);
                  return el && el.id === 'bt-msg';
                }"""
            )
            page.screenshot(path=str(preuves / ("backtest_%d_un_titre.png" % largeur)))
            page.wait_for_timeout(300)
            assert appels == [], appels
            expect(page.locator("#bt-result")).to_be_hidden()

            # (c) puces : ajout puis retrait
            page.evaluate("() => btToggle('BICC')")
            assert puces() == ["SMBC 50%", "BICC 50%"]
            expect(message).to_be_hidden()
            page.evaluate("() => btToggle('SNTS')")
            assert puces() == ["SMBC 33%", "BICC 33%", "SNTS 33%"]
            page.locator('#bt-selected > span:has(strong:text-is("SNTS")) button').click()
            assert puces() == ["SMBC 50%", "BICC 50%"]

            # (b) SMBC + BICC : dates reelles et avertissement de periode
            page.get_by_role("button", name="Lancer le backtesting").click()
            plage = page.locator("#bt-range")
            expect(plage).to_contain_text("Données utilisées : du %s au %s (%d points)." % (dates[0], dates[-1], len(dates)))
            expect(plage).to_contain_text("La période « 1an » demandée commence le")
            expect(plage).to_contain_text("ne remontent qu'au %s" % dates[0])
            assert len(appels) == 1, appels
            assert page.evaluate(
                "() => document.documentElement.scrollWidth <= window.innerWidth"
            ), "debordement horizontal"
            plage.scroll_into_view_if_needed()
            page.screenshot(path=str(preuves / ("backtest_%d_resultat.png" % largeur)))
            page.evaluate("() => closeBT()")

        navigateur.close()

    assert erreurs == [], erreurs
