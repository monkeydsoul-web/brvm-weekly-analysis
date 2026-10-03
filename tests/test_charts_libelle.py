# -*- coding: utf-8 -*-
"""CHARTS-FIX-2 : libellé sur l'historique réel SNTS et ORAC."""
import json
import os
import shutil
import socket
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes") or os.environ.get("GITHUB_ACTIONS") == "true"
_REEL_CONNECT = socket.socket.connect
_REEL_CONNECT_EX = socket.socket.connect_ex
_REEL_CREATE = socket.create_connection
_REEL_DNS = socket.getaddrinfo
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "price_history_snts_orac.json"
_SEP = "\u00b7"

# Libellés affichés (espaces insécables normalisés) et fenêtre visible.
_DERNIER = {
    "SNTS": "2 octobre 2026 %s 45 000 XOF %s 0,00 %%" % (_SEP, _SEP),
    "ORAC": "2 octobre 2026 %s 20 605 XOF %s -5,48 %%" % (_SEP, _SEP),
}
_HUIT_SEPT = {
    "SNTS": "8 septembre 2026 %s 39 200 XOF %s +1,29 %%" % (_SEP, _SEP),
    "ORAC": "8 septembre 2026 %s 21 260 XOF %s -2,48 %%" % (_SEP, _SEP),
}
_ATTENDU = {
    "SNTS": {
        "chargement": _DERNIER["SNTS"],
        "plus": _HUIT_SEPT["SNTS"],
        "reinitialiser": _DERNIER["SNTS"],
        "1M": _DERNIER["SNTS"],
        "Tout": _DERNIER["SNTS"],
        "survol": _HUIT_SEPT["SNTS"],
        "sortie": _DERNIER["SNTS"],
    },
    "ORAC": {
        "chargement": _DERNIER["ORAC"],
        "plus": _HUIT_SEPT["ORAC"],
        "reinitialiser": _DERNIER["ORAC"],
        "1M": _DERNIER["ORAC"],
        "Tout": _DERNIER["ORAC"],
        "survol": _HUIT_SEPT["ORAC"],
        "sortie": _DERNIER["ORAC"],
    },
}
_FENETRES = {
    "chargement": ("2026-05-20", "2026-10-02", 82),
    "plus": ("2026-07-07", "2026-09-08", 46),
    "reinitialiser": ("2026-05-20", "2026-10-02", 82),
    "1M": ("2026-09-02", "2026-10-02", 23),
    "Tout": ("2026-05-20", "2026-10-02", 82),
    "survol": ("2026-05-20", "2026-10-02", 82),
    "sortie": ("2026-05-20", "2026-10-02", 82),
}
_SERIES = {
    "SNTS": {"n": 82, "dernier": "2026-10-02", "cours": 45000},
    "ORAC": {"n": 82, "dernier": "2026-10-02", "cours": 20605},
}


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


def _historique_reel():
    with open(_FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def _caches(historique):
    maintenant = datetime.now(timezone.utc).isoformat()
    _ecrire("price_history.json", historique)
    _ecrire("price_history_extended.json", {})
    _ecrire("live_ranking.json", {
        "updated_at": maintenant,
        "market_open": False,
        "total": 2,
        "ranking": [
            _fiche("SNTS", "Sonatel", "Télécommunications", 45000),
            _fiche("ORAC", "Orange CI", "Télécommunications", 20605),
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


def _espaces(texte):
    for sep in ("\u202f", "\u00a0", "\u2009", "\u2007"):
        texte = texte.replace(sep, " ")
    return " ".join(texte.split())


@pytest.mark.skipif(_CI, reason="Playwright hors CI")
def test_libelle_dernier_point_fenetre(monkeypatch, tmp_path):
    """Deux séquences sur les cours de production : sans survol, puis avec survol."""
    pytest.importorskip("playwright.sync_api")
    _autoriser_local(monkeypatch)
    from playwright.sync_api import sync_playwright

    historique = _historique_reel()
    assert len([p for p in historique["SNTS"] if p["date"] >= "2026-05-19"]) == 82
    corps = json.dumps(historique).encode("utf-8")
    _caches(historique)
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
    historiques_servis = []
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
                chemin = route.request.url.split("?", 1)[0]
                if chemin.endswith("/api/price-history"):
                    historiques_servis.append(chemin)
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=corps,
                    )
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
                        n: Number(el.getAttribute('data-ci-n')),
                        total: Number((document.getElementById('stockChartDiv_svg') || {}).getAttribute
                          ? document.getElementById('stockChartDiv_svg').getAttribute('data-zoom-total')
                          : (el._brvmZoom && el._brvmZoom.prices ? el._brvmZoom.prices.length : 0)),
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
                return _espaces("%s · %s · %s" % (
                    info["date"].strip(),
                    info["cours"].strip(),
                    info["variation"].strip(),
                ))

            def verifier(ticker, etape, info, dernier=True):
                debut, fin, n = _FENETRES[etape]
                assert info["debut"] == debut, (ticker, etape, info)
                assert info["fin"] == fin, (ticker, etape, info)
                assert info["n"] == n, (ticker, etape, info)
                # 1M republie la fenêtre : le zoom mémorise alors ces 23 séances.
                assert info["total"] == (23 if etape == "1M" else 82), (ticker, etape, info)
                assert libelle(info) == _ATTENDU[ticker][etape], (ticker, etape, libelle(info), info)
                if etape == "survol":
                    assert info["iso"] == "2026-09-08", (ticker, etape, info)
                if dernier:
                    assert_dernier(info)

            def ouvrir(ticker):
                page.goto(base + "/societe/" + ticker, wait_until="load", timeout=20000)
                page.locator('.ctab-btn[data-ctab="chiffres"]').click()
                page.locator("#stockChartDiv .ci-date").wait_for(state="visible", timeout=15000)
                page.locator('#stockChartDiv button[data-brvm-zoom="reset"]').wait_for(state="visible")
                page.evaluate(
                    """() => {
                      window.__passesCourbe = 0;
                      var hote = document.getElementById('stockChartDiv');
                      hote.addEventListener('pointermove', function(evt) {
                        var svg = hote.querySelector('.ci-svg');
                        if (!svg) return;
                        var rect = svg.getBoundingClientRect();
                        if (evt.clientX < rect.left || evt.clientX > rect.right) return;
                        if (evt.clientY < rect.top || evt.clientY > rect.bottom) return;
                        var cible = evt.target;
                        if (cible && cible.closest && cible.closest('button, .brvm-zoom-bar, .ci-periodes, a')) return;
                        window.__passesCourbe += 1;
                      }, true);
                    }"""
                )

            def serie():
                return page.evaluate(
                    """() => {
                      var el = document.getElementById('stockChartDiv');
                      var complet = el._ciComplet || [];
                      var dernier = complet.length ? complet[complet.length - 1] : null;
                      return {
                        n: complet.length,
                        dernier: dernier ? dernier.date : '',
                        cours: dernier ? dernier.value : null
                      };
                    }"""
                )

            def capturer(ticker, largeur, sequence, etape):
                page.locator("#stockChartDiv .ci-lecture").scroll_into_view_if_needed()
                page.locator("#stockChartDiv").screenshot(
                    path=str(tmp_path / ("libelle-%s-%d-%s-%s.png" % (ticker, largeur, sequence, etape)))
                )

            def noter(ticker, largeur, sequence, etape, info):
                rapport.append({
                    "sequence": sequence,
                    "ticker": ticker,
                    "largeur": largeur,
                    "etape": etape,
                    "libelle": libelle(info),
                    "debut": info["debut"],
                    "fin": info["fin"],
                    "n": info["n"],
                    "iso": info["iso"],
                })

            def clic(selecteur):
                page.locator(selecteur).click()

            def periode(nom, debut):
                clic('#stockChartDiv .ci-periode[data-periode="%s"]' % nom)
                page.wait_for_function(
                    "(debut) => document.getElementById('stockChartDiv').getAttribute('data-ci-debut') === debut",
                    arg=debut,
                    timeout=5000,
                )

            def point_du(iso):
                page.locator("#stockChartDiv .ci-svg").scroll_into_view_if_needed()
                return page.evaluate(
                    """(iso) => {
                      var el = document.getElementById('stockChartDiv');
                      var vis = el._ciVisible || [];
                      var idx = -1;
                      var i;
                      for (i = 0; i < vis.length; i++) {
                        if (vis[i].date === iso) idx = i;
                      }
                      var geom = el._ciGeom;
                      var svg = el.querySelector('.ci-svg');
                      var rect = svg.getBoundingClientRect();
                      var xView = geom.padL + (idx / (vis.length - 1)) * geom.CW;
                      var yView = geom.padT + geom.CH * 0.55;
                      return {
                        idx: idx,
                        x: rect.left + (xView / geom.W) * rect.width,
                        y: rect.top + (yView / geom.H) * rect.height
                      };
                    }""",
                    iso,
                )

            series = {}
            for largeur, hauteur in ((1280, 800), (390, 844)):
                page.set_viewport_size({"width": largeur, "height": hauteur})
                for ticker in ("SNTS", "ORAC"):
                    ouvrir(ticker)
                    brut = serie()
                    assert brut == _SERIES[ticker], (ticker, brut)
                    series[ticker] = brut
                    page.mouse.move(8, 8)

                    charge = lire()
                    verifier(ticker, "chargement", charge)
                    noter(ticker, largeur, "sans-survol", "chargement", charge)
                    capturer(ticker, largeur, "sans-survol", "chargement")

                    clic('#stockChartDiv button[data-brvm-zoom="plus"]')
                    page.wait_for_function(
                        "() => document.getElementById('stockChartDiv').getAttribute('data-ci-fin') === '2026-09-08'",
                        timeout=5000,
                    )
                    zoom = lire()
                    verifier(ticker, "plus", zoom)
                    noter(ticker, largeur, "sans-survol", "plus", zoom)
                    capturer(ticker, largeur, "sans-survol", "plus")

                    clic('#stockChartDiv button[data-brvm-zoom="reset"]')
                    page.wait_for_function(
                        "() => document.getElementById('stockChartDiv').getAttribute('data-ci-fin') === '2026-10-02'",
                        timeout=5000,
                    )
                    reset = lire()
                    verifier(ticker, "reinitialiser", reset)
                    noter(ticker, largeur, "sans-survol", "reinitialiser", reset)
                    capturer(ticker, largeur, "sans-survol", "reinitialiser")

                    periode("1M", "2026-09-02")
                    un_mois = lire()
                    verifier(ticker, "1M", un_mois)
                    noter(ticker, largeur, "sans-survol", "1M", un_mois)
                    capturer(ticker, largeur, "sans-survol", "1M")

                    periode("Tout", "2026-05-20")
                    tout = lire()
                    verifier(ticker, "Tout", tout)
                    noter(ticker, largeur, "sans-survol", "Tout", tout)
                    capturer(ticker, largeur, "sans-survol", "Tout")
                    assert page.evaluate("() => window.__passesCourbe") == 0, (ticker, largeur)

                    ouvrir(ticker)
                    assert serie() == _SERIES[ticker]
                    page.mouse.move(8, 8)
                    visee = point_du("2026-09-08")
                    assert visee["idx"] == 63, (ticker, visee)
                    page.mouse.move(visee["x"], visee["y"])
                    page.wait_for_function(
                        "() => document.querySelector('#stockChartDiv .ci-lecture').getAttribute('data-ci-date') === '2026-09-08'",
                        timeout=5000,
                    )
                    survol = lire()
                    verifier(ticker, "survol", survol, dernier=False)
                    noter(ticker, largeur, "avec-survol", "survol", survol)
                    capturer(ticker, largeur, "avec-survol", "survol")

                    page.locator("#topnav").hover()
                    page.wait_for_function(
                        "() => document.querySelector('#stockChartDiv .ci-lecture').getAttribute('data-ci-date') === '2026-10-02'",
                        timeout=5000,
                    )
                    sortie = lire()
                    verifier(ticker, "sortie", sortie)
                    noter(ticker, largeur, "avec-survol", "sortie", sortie)
                    capturer(ticker, largeur, "avec-survol", "sortie")

                    clic('#stockChartDiv button[data-brvm-zoom="reset"]')
                    page.wait_for_function(
                        "() => document.querySelector('#stockChartDiv .ci-lecture').getAttribute('data-ci-date') === '2026-10-02'",
                        timeout=5000,
                    )
                    retour = lire()
                    verifier(ticker, "reinitialiser", retour)
                    noter(ticker, largeur, "avec-survol", "reinitialiser", retour)
                    capturer(ticker, largeur, "avec-survol", "reinitialiser")

                    periode("1M", "2026-09-02")
                    un_mois = lire()
                    verifier(ticker, "1M", un_mois)
                    noter(ticker, largeur, "avec-survol", "1M", un_mois)
                    capturer(ticker, largeur, "avec-survol", "1M")

                    periode("Tout", "2026-05-20")
                    tout = lire()
                    verifier(ticker, "Tout", tout)
                    noter(ticker, largeur, "avec-survol", "Tout", tout)
                    capturer(ticker, largeur, "avec-survol", "Tout")

            navigateur.close()
    finally:
        serveur.shutdown()

    assert not erreurs, erreurs[:8]
    assert len(historiques_servis) == 8, historiques_servis
    preuve = {
        "lieu": "local",
        "donnees": "production /api/price-history, servies en local sur le code de la branche",
        "erreurs_console": len(erreurs),
        "series": series,
        "etapes": rapport,
    }
    texte = json.dumps(preuve, ensure_ascii=False, indent=2)
    (tmp_path / "libelles.json").write_text(texte, encoding="utf-8")
    for ligne in rapport:
        assert "XOF" in ligne["libelle"]
        assert ligne["fin"]
        fichier = tmp_path / ("libelle-%s-%d-%s-%s.png" % (
            ligne["ticker"], ligne["largeur"], ligne["sequence"], ligne["etape"],
        ))
        assert fichier.is_file() and fichier.stat().st_size > 1000
    assert len(rapport) == 2 * 2 * 2 * 5
    copie = Path("/opt/cursor/artifacts/charts-fix2")
    copie.mkdir(parents=True, exist_ok=True)

    def _io(action):
        dernier = None
        for _essai in range(5):
            try:
                action()
                return
            except OSError as exc:
                dernier = exc
        raise dernier

    for ancien in list(copie.glob("libelle-*.png")):
        _io(ancien.unlink)
    _io(lambda: (copie / "libelles.json").write_text(texte, encoding="utf-8"))
    for fichier in tmp_path.glob("libelle-*.png"):
        _io(lambda fichier=fichier: shutil.copy(fichier, copie / fichier.name))
