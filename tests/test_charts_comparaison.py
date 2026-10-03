# -*- coding: utf-8 -*-
"""CHARTS-2 : base 100 au premier jour commun, graphique Comparer sur la fiche.

Exemple chiffré (sources price_history et index_history, jours ouvrés) :

    SNTS, price_history
      2026-08-31  cours 1      source synthetic  ignoré (pas une donnée réelle)
      2026-09-01  cours 20 000 source live       ignoré (le Composite n'a pas ce jour)
      2026-09-02  cours 21 000 puis 22 000 live  le dernier cours du jour est gardé
      2026-09-03  cours 27 500 source live
      2026-09-04  cours 25 000 source live       ignoré (le Composite n'a pas ce jour)
      2026-09-05  cours 99 999 source live       ignoré (samedi)
    BRVM-COMPOSITE, index_history points [date, valeur]
      2026-09-02  400
      2026-09-03  440
      2026-09-05  100                             ignoré (samedi)
      2026-09-07  500                             ignoré (SNTS n'a pas de cours réel)

    Premier jour commun : 2026-09-02.
    SNTS             22 000 / 22 000 × 100 = 100
                     27 500 / 22 000 × 100 = 125
                     performance = 125 − 100 = +25,0 %
    BRVM-COMPOSITE  400 / 400 × 100 = 100
                     440 / 400 × 100 = 110
                     performance = 110 − 100 = +10,0 %

Moins de 20 séances communes : message, aucune courbe.
"""
import json
import os
import socket
import subprocess
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "dashboard" / "js" / "charts_comparaison.js"

_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes") or os.environ.get("GITHUB_ACTIONS") == "true"
_REEL_CONNECT = socket.socket.connect
_REEL_CONNECT_EX = socket.socket.connect_ex
_REEL_CREATE = socket.create_connection
_REEL_DNS = socket.getaddrinfo

MOIS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def _js(nom, *args):
    code = (
        "const api = require(%s);\n"
        "const r = api[%s].apply(null, %s);\n"
        "process.stdout.write(JSON.stringify(r));\n"
    ) % (json.dumps(str(JS)), json.dumps(nom), json.dumps(args))
    out = subprocess.check_output(["node", "-e", code], cwd=str(ROOT))
    return json.loads(out.decode("utf-8"))


def _exemple():
    return [
        {
            "id": "SNTS",
            "nom": "Sonatel",
            "points": [
                {"date": "2026-08-31", "price": 1, "source": "synthetic"},
                {"date": "2026-09-01", "price": 20000, "source": "live"},
                {"date": "2026-09-02", "price": 21000, "source": "live"},
                {"date": "2026-09-02", "price": 22000, "source": "live"},
                {"date": "2026-09-03", "price": 27500, "source": "live"},
                {"date": "2026-09-04", "price": 25000, "source": "live"},
                {"date": "2026-09-05", "price": 99999, "source": "live"},
            ],
        },
        {
            "id": "BRVM-COMPOSITE",
            "nom": "BRVM-COMPOSITE",
            "points": [
                {"date": "2026-09-02", "price": 400},
                {"date": "2026-09-03", "price": 440},
                {"date": "2026-09-05", "price": 100},
                {"date": "2026-09-07", "price": 500},
            ],
        },
    ]


def test_base100_exemple_manuel():
    """Calcul à la main : 27 500 / 22 000 × 100 = 125 et 440 / 400 × 100 = 110."""
    brut = _js("serieBase100", _exemple(), 1)
    assert brut["ok"] is True
    assert brut["n"] == 2
    assert brut["base"] == "2026-09-02"
    snts, composite = brut["series"]
    assert [v["base100"] for v in snts["valeurs"]] == pytest.approx([100, 125])
    assert [v["base100"] for v in composite["valeurs"]] == pytest.approx([100, 110])
    assert snts["perf"] == pytest.approx(25)
    assert composite["perf"] == pytest.approx(10)
    assert 27500 * 100 // 22000 == 125
    assert 440 * 100 // 400 == 110
    assert _js("textePerf", 25) == "+25,0 %"
    assert _js("textePerf", 10) == "+10,0 %"
    assert _js("textePerf", -16.8) == "-16,8 %"
    assert _js("textePerf", 0) == "0,0 %"
    court = _js("serieBase100", _exemple(), 20)
    assert court["ok"] is False
    assert court["n"] == 2
    assert court["base"] == "2026-09-02"


def test_seuil_vingt_seances():
    jours = []
    d = date(2026, 9, 1)
    while len(jours) < 20:
        if d.weekday() < 5:
            jours.append(d.isoformat())
        d += timedelta(days=1)
    entrees = [
        {"id": "SNTS", "nom": "Sonatel", "points": [
            {"date": j, "price": 100 + i, "source": "live"} for i, j in enumerate(jours)
        ]},
        {"id": "BRVM-COMPOSITE", "nom": "BRVM-COMPOSITE", "points": [
            {"date": j, "price": 200 + i} for i, j in enumerate(jours)
        ]},
    ]
    assert _js("serieBase100", entrees)["ok"] is True
    assert _js("serieBase100", entrees)["n"] == 20
    manque = [
        {"id": "SNTS", "nom": "Sonatel", "points": entrees[0]["points"][:-1]},
        {"id": "BRVM-COMPOSITE", "nom": "BRVM-COMPOSITE", "points": entrees[1]["points"][:-1]},
    ]
    refuse = _js("serieBase100", manque)
    assert refuse["n"] == 19
    assert refuse["ok"] is False


def test_fichier_isole_du_modal_et_du_backtest():
    src = JS.read_text(encoding="utf-8")
    assert "openCompareModal" not in src
    assert "backtest" not in src.lower()
    assert "/api/market" not in src
    assert "/api/price-history" in src
    assert "/api/index-history?index=BRVM-COMPOSITE&range=1A" in src
    core = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
    assert "cmp-courbes" not in core
    assert "charts_comparaison" not in core
    assert "function openCompareModal()" in core


def _jours_ouvres(n, fin=None):
    fin = fin or date.today()
    if fin.weekday() >= 5:
        fin = fin - timedelta(days=fin.weekday() - 4)
    jours = []
    d = fin
    while len(jours) < n:
        if d.weekday() < 5:
            jours.append(d)
        d -= timedelta(days=1)
    jours.reverse()
    return jours


def _date_fr(iso):
    annee, mois, jour = iso.split("-")
    return "%d %s %s" % (int(jour), MOIS[int(mois) - 1], annee)


def _serie_fiche(n_composite=22):
    """22 séances communes. SNTS +100/séance, Composite +1, SGBC −40, BOAC +10.

    Derniers cours sur la base du premier jour commun :
    SNTS 12 100 / 10 000 × 100 = 121 → +21,0 %
    Composite 321 / 300 × 100 = 107 → +7,0 %
    SGBC 4 160 / 5 000 × 100 = 83,2 → −16,8 %
    BOAC 2 210 / 2 000 × 100 = 110,5 → +10,5 %
    """
    jours = _jours_ouvres(22)
    veille = jours[0] - timedelta(days=1)
    while veille.weekday() >= 5:
        veille -= timedelta(days=1)
    samedi = jours[0] + timedelta(days=(5 - jours[0].weekday()) % 7)
    snts = [{"date": veille.isoformat(), "price": 5000, "source": "live"}]
    snts.append({"date": jours[0].isoformat(), "price": 1, "source": "synthetic"})
    snts.append({"date": samedi.isoformat(), "price": 1, "source": "live"})
    sgbc = []
    boac = []
    ecoc = []
    seances = []
    for i, jour in enumerate(jours):
        iso = jour.isoformat()
        snts.append({"date": iso, "price": 10000 + i * 100, "source": "live"})
        sgbc.append({"date": iso, "price": 5000 - i * 40, "source": "live"})
        boac.append({"date": iso, "price": 2000 + i * 10, "source": "live"})
        if i < 5:
            ecoc.append({"date": iso, "price": 1000 + i * 10, "source": "live"})
        if i < n_composite:
            seances.append({"date": iso, "indices": {"BRVM-C": 300 + i}})
    seances.append({"date": samedi.isoformat(), "indices": {"BRVM-C": 1}})
    return {
        "jours": [j.isoformat() for j in jours],
        "prix": {"SNTS": snts, "SGBC": sgbc, "BOAC": boac, "ECOC": ecoc},
        "seances": seances,
    }


def _ecrire(nom, payload):
    chemin = os.path.join(os.environ["BRVM_DATA_DIR"], nom)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _caches(n_composite=22):
    maintenant = datetime.now(timezone.utc).isoformat()
    serie = _serie_fiche(n_composite)
    _ecrire("live_ranking.json", {
        "updated_at": maintenant,
        "market_open": False,
        "total": 4,
        "ranking": [
            {"ticker": "SNTS", "name": "Sonatel", "sector": "Télécommunications", "country": "Sénégal",
             "price": 12100, "composite_adj": 58, "note10": 7.3, "change_pct": 0.2, "rank": 1, "statut": "cote"},
            {"ticker": "SGBC", "name": "Société Générale CI", "sector": "Banque", "country": "Côte d'Ivoire",
             "price": 4160, "composite_adj": 50, "note10": 6.3, "change_pct": -0.1, "rank": 2, "statut": "cote"},
            {"ticker": "BOAC", "name": "BOA Côte d'Ivoire", "sector": "Banque", "country": "Côte d'Ivoire",
             "price": 2210, "composite_adj": 48, "note10": 6.0, "change_pct": 0.1, "rank": 3, "statut": "cote"},
            {"ticker": "ECOC", "name": "Ecobank CI", "sector": "Banque", "country": "Côte d'Ivoire",
             "price": 1040, "composite_adj": 40, "note10": 5.0, "change_pct": 0, "rank": 4, "statut": "cote"},
        ],
    })
    _ecrire("price_history.json", serie["prix"])
    _ecrire("index_history.json", {"seances": serie["seances"]})
    _ecrire("market_cache.json", {
        "updated_at": maintenant,
        "market_activity": {"Capitalisation Actions": "10 000 000 000"},
        "top5": [],
        "flop5": [],
        "indices": [
            {"name": "BRVM - COMPOSITE", "prev": 320.0, "current": 321.0, "change": 0.31, "ytd": 0.05},
            {"name": "BRVM-30", "prev": 140.0, "current": 141.0, "change": 0.71, "ytd": 0.02},
        ],
        "sector_indices": [],
        "total_return": {},
    })
    _ecrire("live_cache.json", {
        "updated_at": maintenant,
        "market_open": False,
        "prices": {"SNTS": {"price": 12100, "change_pct": 0.2, "volume": 10}},
    })
    import index_history
    import market_data
    index_history.invalider_cache()
    market_data._memoire = None
    return serie


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


@pytest.mark.skipif(_CI, reason="Playwright hors CI. Local : pytest tests/test_charts_comparaison.py -q -s")
def test_comparer_fiche_1280_390_clair_sombre(monkeypatch):
    """Étiquettes lisibles, une requête /api/market, message si le Composite est court."""
    pytest.importorskip("playwright.sync_api")
    _autoriser_local(monkeypatch)
    from playwright.sync_api import sync_playwright

    preuves = Path(os.environ.get("BRVM_PREUVE_DIR") or "/opt/cursor/artifacts/screenshots")
    preuves.mkdir(parents=True, exist_ok=True)
    serie = _caches(22)
    base_attendue = serie["jours"][0]

    import app as application
    from werkzeug.serving import make_server

    serveur = make_server("127.0.0.1", 0, application.app, threaded=True)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    base = "http://127.0.0.1:%d" % serveur.server_address[1]
    erreurs = []
    try:
        with sync_playwright() as pw:
            navigateur = pw.chromium.launch(
                channel="chrome",
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = navigateur.new_page()
            page.on("pageerror", lambda err: erreurs.append("pageerror: " + str(err)))
            page.on("console", lambda msg: erreurs.append(msg.text) if msg.type == "error" else None)

            def route(route):
                url = route.request.url
                if not url.startswith(base):
                    route.abort()
                    return
                route.continue_()

            page.route("**/*", route)

            def marches_de(url):
                return url == base + "/api/market" or url.startswith(base + "/api/market?")

            def theme_clair():
                if page.evaluate("() => !document.documentElement.classList.contains('light')"):
                    page.click("#topnav [data-theme-btn]")
                assert page.evaluate("() => document.documentElement.classList.contains('light')")

            def theme_sombre():
                theme_clair()
                page.click("#topnav [data-theme-btn]")
                assert page.evaluate("() => !document.documentElement.classList.contains('light')")

            def etiquettes():
                return page.evaluate(
                    """() => {
                      var out = {};
                      document.querySelectorAll('#cmp-courbes .cmp-label').forEach(function (el) {
                        var id = el.getAttribute('data-cmp-id');
                        var role = el.getAttribute('data-cmp-role');
                        out[id] = out[id] || {};
                        out[id][role] = el.textContent;
                      });
                      return out;
                    }"""
                )

            def tient():
                return page.evaluate(
                    """() => {
                      var carte = document.getElementById('cmp-courbes');
                      if (!carte) return 'carte absente';
                      if (carte.scrollWidth > carte.clientWidth + 2) return 'debordement carte';
                      var tab = document.querySelector('.tabbar');
                      var limite = window.innerHeight - (tab ? tab.getBoundingClientRect().height : 0) + 1;
                      var noeuds = carte.querySelectorAll('.cmp-label, #cmp-courbes-titre, .cmp-intro, .cmp-message');
                      var i, el, r, style;
                      for (i = 0; i < noeuds.length; i++) {
                        el = noeuds[i];
                        r = el.getBoundingClientRect();
                        style = getComputedStyle(el);
                        if (r.width < 1 || r.height < 1) return 'invisible ' + (el.getAttribute('data-cmp-id') || el.id || el.className);
                        if (r.left < -1 || r.right > window.innerWidth + 1) return 'hors cadre';
                        if (r.bottom > limite + 1) return 'sous le menu';
                        if (parseFloat(style.fontSize) < 12) return 'texte trop petit ' + style.fontSize;
                      }
                      if (carte.querySelector('title')) return 'legende title';
                      return 'ok';
                    }"""
                )

            def cadrer():
                page.evaluate(
                    """() => {
                      var el = document.getElementById('cmp-courbes');
                      var header = document.querySelector('.topnav');
                      var headerH = 0;
                      if (header) {
                        var pos = getComputedStyle(header).position;
                        if (pos === 'fixed' || pos === 'sticky') headerH = header.getBoundingClientRect().height;
                      }
                      var cible = Math.max(headerH, 0) + 8;
                      function decaler(delta) {
                        if (Math.abs(delta) < 2) return;
                        var main = document.querySelector('.main');
                        if (main && main.scrollHeight > main.clientHeight + 4) main.scrollTop += delta;
                        var encore = el.getBoundingClientRect().top - cible;
                        if (Math.abs(encore) > 2) window.scrollBy(0, encore);
                      }
                      el.scrollIntoView({block: 'start', inline: 'nearest'});
                      decaler(el.getBoundingClientRect().top - cible);
                      decaler(el.getBoundingClientRect().top - cible);
                    }"""
                )

            def ouvrir_chiffres():
                page.wait_for_selector("#page-stock .ctab-btn[data-ctab='chiffres']", timeout=15000)
                page.click("#page-stock .ctab-btn[data-ctab='chiffres']")
                page.wait_for_selector("#cmp-courbes", timeout=15000)

            vus = []

            def noter(req):
                if req.method == "GET" and marches_de(req.url):
                    vus.append(req.url.split("?")[0])

            page.on("request", noter)
            page.set_viewport_size({"width": 1280, "height": 800})
            page.goto(base + "/societe/SNTS", wait_until="load", timeout=20000)
            ouvrir_chiffres()
            page.wait_for_selector("#cmp-courbes svg polyline", timeout=15000)
            page.wait_for_timeout(400)
            assert len(page.locator("#cmp-courbes polyline").all()) == 2
            assert page.locator("#cmp-courbes title").count() == 0
            lu = etiquettes()
            assert lu["SNTS"]["nom"] == "Sonatel"
            assert lu["SNTS"]["perf"] == "+21,0 %"
            assert lu["BRVM-COMPOSITE"]["nom"] == "BRVM-COMPOSITE"
            assert lu["BRVM-COMPOSITE"]["perf"] == "+7,0 %"
            intro = page.locator("#cmp-courbes .cmp-intro").inner_text()
            assert "Base 100 au %s" % _date_fr(base_attendue) in intro
            assert "premier jour commun" in intro
            assert page.locator("#cmp-courbes .cmp-intro").get_attribute("data-cmp-base") == base_attendue
            page.hover("#cmp-courbes svg")
            assert page.locator("#cmp-courbes title").count() == 0
            assert page.locator("#cmp-modal").evaluate("el => getComputedStyle(el).display") == "none"

            page.select_option("#cmp-courbes-ajout", "SGBC")
            page.click("#cmp-courbes-btn")
            page.wait_for_function(
                "() => document.querySelectorAll('#cmp-courbes polyline').length === 3",
                timeout=8000,
            )
            lu = etiquettes()
            assert lu["SGBC"]["nom"] == "Société Générale CI"
            assert lu["SGBC"]["perf"] == "-16,8 %"
            assert lu["SNTS"]["perf"] == "+21,0 %"
            assert lu["BRVM-COMPOSITE"]["perf"] == "+7,0 %"

            for largeur, hauteur in ((1280, 800), (390, 844)):
                page.set_viewport_size({"width": largeur, "height": hauteur})
                page.wait_for_timeout(200)
                theme_clair()
                cadrer()
                page.wait_for_timeout(150)
                assert tient() == "ok", (largeur, "clair", tient())
                page.screenshot(path=str(preuves / ("comparer-%d-clair.png" % largeur)))
                theme_sombre()
                cadrer()
                page.wait_for_timeout(150)
                assert tient() == "ok", (largeur, "sombre", tient())
                page.screenshot(path=str(preuves / ("comparer-%d-sombre.png" % largeur)))

            theme_clair()
            page.select_option("#cmp-courbes-ajout", "BOAC")
            page.click("#cmp-courbes-btn")
            page.wait_for_function(
                "() => document.querySelectorAll('#cmp-courbes polyline').length === 4",
                timeout=8000,
            )
            lu = etiquettes()
            assert lu["BOAC"]["nom"] == "BOA Côte d'Ivoire"
            assert lu["BOAC"]["perf"] == "+10,5 %"
            assert page.locator("#cmp-courbes-btn").is_disabled()
            page.click("#cmp-courbes [data-cmp-retirer='BOAC']")
            page.wait_for_function(
                "() => document.querySelectorAll('#cmp-courbes polyline').length === 3",
                timeout=8000,
            )
            page.select_option("#cmp-courbes-ajout", "ECOC")
            page.click("#cmp-courbes-btn")
            page.wait_for_selector("#cmp-courbes [data-cmp-note]", timeout=8000)
            note = page.locator("#cmp-courbes [data-cmp-note]").inner_text()
            assert "Ecobank CI" in note
            assert "5" in note
            assert "20" in note
            assert len(page.locator("#cmp-courbes polyline").all()) == 3
            page.wait_for_timeout(600)
            assert vus == [base + "/api/market"], vus

            vus_court = []

            def noter_court(req):
                if req.method == "GET" and marches_de(req.url):
                    vus_court.append(req.url.split("?")[0])

            _caches(8)
            page.on("request", noter_court)
            page.set_viewport_size({"width": 1280, "height": 800})
            page.goto(base + "/societe/SNTS", wait_until="load", timeout=20000)
            ouvrir_chiffres()
            page.wait_for_selector("#cmp-courbes [data-cmp-message='court']", timeout=15000)
            message = page.locator("#cmp-courbes [data-cmp-message='court']").inner_text()
            assert "trop court" in message
            assert "8 séances en commun avec Sonatel" in message
            assert "au moins 20" in message
            assert "Aucune courbe" in message
            assert page.locator("#cmp-courbes polyline").count() == 0
            assert page.locator("#cmp-courbes path").count() == 0
            assert page.locator("#cmp-courbes circle").count() == 0
            theme_sombre()
            cadrer()
            page.screenshot(path=str(preuves / "comparer-court-1280-sombre.png"))
            page.set_viewport_size({"width": 390, "height": 844})
            theme_clair()
            cadrer()
            page.wait_for_timeout(150)
            assert tient() == "ok", tient()
            page.screenshot(path=str(preuves / "comparer-court-390-clair.png"))
            page.wait_for_timeout(400)
            assert vus_court == [base + "/api/market"], vus_court
            navigateur.close()
    finally:
        serveur.shutdown()
    assert erreurs == [], erreurs
