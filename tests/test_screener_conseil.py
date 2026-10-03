# -*- coding: utf-8 -*-
"""SCREENCOL-1 : la colonne Conseil du Screener affiche le conseil officiel.

Elle lisait pdf_verdict (« Tendance positive / neutre »). Elle passe par
fmtConseil(x), la fonction du Classement : meme libelle, meme rendu,
meme traitement des societes suspendues.

Le test Playwright est hors CI (Chromium non installe dans le workflow) :

    pytest tests/test_screener_conseil.py -q -s
"""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes") or os.environ.get("GITHUB_ACTIONS") == "true"
STRATEGIES = ("value", "croissance", "revenus", "defensif")


def test_cellule_conseil_du_screener_lit_le_conseil_officiel():
    js = (ROOT / "dashboard" / "screener.js").read_text(encoding="utf-8")
    debut = js.index("function _renderScreenerTable()")
    rendu = js[debut:js.index("function _triScreener(", debut)]
    assert "${fmtConseil(x)}" in rendu
    assert "fmtVerdict" not in rendu
    assert "pdf_verdict" not in rendu


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


def classement_de_test():
    """47 lignes comme en prod le 03/10 : 3 Interessant, 13 A surveiller, 29 Prudence, SICC et SEMC suspendues.

    Les ratios sont choisis pour que chaque strategie retienne des lignes des trois conseils,
    et que SICC et SEMC passent la strategie Revenus. pdf_verdict est toujours POSITIF ou
    NEUTRE, comme le constat (« Tendance positive / neutre »).
    """
    conseils = (["Intéressant"] * 3) + (["À surveiller"] * 13) + (["Prudence"] * 29)
    code = {"Intéressant": ("acheter", "vert"), "À surveiller": ("attendre", "orange"), "Prudence": ("eviter", "rouge")}
    lignes = []
    for i, lib in enumerate(conseils):
        c, coul = code[lib]
        lignes.append({
            "ticker": "T%02d" % i, "name": "Societe %02d" % i, "sector": ("Banque", "Industrie", "Telecoms")[i % 3],
            "price": 1000 + 10 * i, "composite_adj": 80 - i, "pe_ref": 6 + (i % 12), "pb_ref": 0.8 + (i % 5) * 0.3,
            "div_yield": 2 + (i % 8), "roe": 8 + (i % 14), "change_pct": 0.1,
            "pdf_verdict": "POSITIF" if i % 2 else "NEUTRE",
            "conseil": c, "conseil_libelle": lib, "conseil_couleur": coul, "statut": "cote",
        })
    for t in ("SICC", "SEMC"):
        lignes.append({
            "ticker": t, "name": t, "sector": "Agriculture", "price": 5000, "composite_adj": 60,
            "pe_ref": 9, "pb_ref": 1.0, "div_yield": 7, "roe": 12, "change_pct": 0,
            "pdf_verdict": "POSITIF", "conseil": None, "conseil_libelle": None, "conseil_couleur": None,
            "statut": "suspendu", "statut_depuis": "2026-09-16",
        })
    return lignes


@pytest.fixture(scope="module")
def base_url():
    pytest.importorskip("playwright.sync_api")
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    maintenant = datetime.now(timezone.utc).isoformat()
    lignes = classement_de_test()
    classement = _ecrire("live_ranking.json", {"updated_at": maintenant, "market_open": False, "total": len(lignes), "ranking": lignes})
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


def conseils_classement(page):
    page.evaluate("() => nav('rank')")
    page.wait_for_function("() => document.querySelectorAll('#rankBody tr[id^=\"rank-row-\"]').length > 0")
    return page.evaluate(
        """() => Object.fromEntries(Array.from(document.querySelectorAll('#rankBody tr[id^="rank-row-"]')).map(tr =>
             [tr.id.replace('rank-row-',''), {texte: tr.children[9].innerText.trim(), html: tr.children[9].innerHTML.trim()}]))"""
    )


def conseils_screener(page, strategie):
    page.evaluate("() => nav('screener')")
    page.wait_for_function("() => typeof screenerPreset === 'function'")
    page.evaluate("(s) => screenerPreset(s)", strategie)
    page.wait_for_function("() => document.querySelectorAll('#screener-table tr[onclick]').length > 0")
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('#screener-table tr[onclick]')).map(tr => {
             var cell = tr.lastElementChild, span = cell.querySelector('span');
             return {ticker: tr.querySelector('strong').innerText.trim(), texte: span.innerText.trim(), html: span.innerHTML.trim()};
           })"""
    )


@pytest.mark.skipif(_CI, reason="Playwright hors CI. Local : pytest tests/test_screener_conseil.py -q -s")
def test_screener_meme_conseil_que_le_classement(base_url, tmp_path):
    from playwright.sync_api import sync_playwright

    preuves = Path(os.environ.get("BRVM_PREUVE_DIR") or tmp_path)
    preuves.mkdir(parents=True, exist_ok=True)
    erreurs = []
    rapport = {}
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
            page.wait_for_function("() => (window.scores || []).length === 47", timeout=10000)
            reference = conseils_classement(page)
            assert reference["SICC"]["texte"] == "Cotation suspendue depuis le 16/09/2026"
            assert reference["SEMC"]["texte"] == "Cotation suspendue depuis le 16/09/2026"
            for strategie in STRATEGIES:
                lignes = conseils_screener(page, strategie)
                rapport[(largeur, strategie)] = [(x["ticker"], x["texte"], reference[x["ticker"]]["texte"]) for x in lignes]
                for x in lignes:
                    assert x["texte"] == reference[x["ticker"]]["texte"], (strategie, x)
                    assert x["html"] == reference[x["ticker"]]["html"], (strategie, x)
                    assert not x["texte"].startswith("Tendance"), (strategie, x)
                page.screenshot(path=str(preuves / ("screener_%s_%d.png" % (strategie, largeur))), full_page=False)
            assert {"SICC", "SEMC"} <= {t for t, _, _ in rapport[(largeur, "revenus")]}
        navigateur.close()

    if os.environ.get("BRVM_PREUVE_DIR"):
        with open(preuves / "screener_conseil.json", "w", encoding="utf-8") as f:
            json.dump({"%d_%s" % k: v for k, v in rapport.items()}, f, ensure_ascii=False, indent=1)
    assert erreurs == [], erreurs
