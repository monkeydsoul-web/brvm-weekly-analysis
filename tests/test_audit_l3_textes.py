# -*- coding: utf-8 -*-
"""AUDIT-L3 : aides visibles, seuils justes, décimales françaises.

Le bouton « ? » de Marché, Signaux et de la fiche ne reprend plus l'aide
générique (podiums, heatmap, exemple chiffré sur une société réelle, seuils
sur 100). Les explications utiles sont dans la page, pas seulement au survol.

Playwright : 1280 et 390, clair et sombre. Captures dans tmp_path
(aucune variable BRVM_PREUVE_DIR). Hors CI, Chromium n'est pas lancé.
"""
import json
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes") or os.environ.get("GITHUB_ACTIONS") == "true"

_PHRASE_SIBC = "Si SIBC est en vert vif (+3.2%) avec un score de 8.5/10"


def _entre(texte, debut, fin):
    i = texte.index(debut)
    j = texte.index(fin, i)
    return texte[i:j]


def _bloc(src, titre, titre_suivant):
    return _entre(src, "title: '%s'" % titre, "title: '%s'" % titre_suivant)


def test_aide_par_page_sans_chiffre_invente():
    """Marché, Signaux et fiche ont leur aide. Actualités garde l'ancien texte."""
    core = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
    defaut = _bloc(core, "Aide", "Marché")
    marche = _bloc(core, "Marché", "Signaux")
    signaux = _bloc(core, "Signaux", "Fiche société")
    fiche = _bloc(core, "Fiche société", "Tableau de bord")
    news = _entre(core, "title: 'Tableau de bord'", "welcome:")
    screener = _bloc(core, "Screener", "Analyse & Optimisation")

    for nom, bloc in (("marché", marche), ("signaux", signaux), ("fiche", fiche), ("repli", defaut)):
        assert "SIBC" not in bloc, nom
        assert "8.5/10" not in bloc, nom
        assert "8,5/10" not in bloc, nom
        assert "6.9" not in bloc, nom
        assert "podium" not in bloc.lower(), nom
        assert "heatmap" not in bloc.lower(), nom
        assert "7,5" in bloc, nom
        assert "6 %" in bloc, nom
        assert "3 %" in bloc, nom

    assert "Score min : 55" not in screener
    assert "Score ≥ 55" not in screener
    assert "Score ≥ 60" not in screener
    assert "7,5" in screener
    assert "6 %" in screener
    assert _PHRASE_SIBC in news
    assert "Les 3 podiums" in news
    assert "Heatmap BRVM" in news
    assert core.count(_PHRASE_SIBC) == 1


def test_legendes_visibles_et_seuils_du_code():
    """Les title faux deviennent une légende. Les seuils cités sont ceux du code."""
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    core = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
    verdict = (ROOT / "verdict.py").read_text(encoding="utf-8")
    css = (ROOT / "dashboard" / "css" / "app.css").read_text(encoding="utf-8")

    assert "SEUIL_NOTE_FORT = 7.5" in core
    assert "SEUIL_NOTE_MODERE = 5" in core
    assert "if(p>=6) return 'var(--note-green)'" in core
    assert "if(p>=3) return 'var(--note-amber)'" in core
    assert "SEUIL_COULEUR_VERT = 7.5" in verdict
    assert "SEUIL_COULEUR_ORANGE = 5.0" in verdict

    prix = _entre(html, 'id="rank-table-wrap"', 'id="rank-cards"')
    assert "en haut à droite" in prix
    assert "en haut à gauche" not in prix
    assert "vert à partir de 6 %" in prix
    legende = _entre(html, 'id="rank-cards"', 'id="top3-podium"')
    assert 'id="rank-aide-legende"' in legende
    assert "en haut à droite" in legende
    assert "vert à partir de 6 %" in legende
    assert "orange à partir de 3 %" in legende

    filtres = _entre(html, 'id="sc-score"', 'id="sc-count"')
    assert "≥ 7 = signal fort" not in filtres
    assert "≥ 7,5 = signal fort" in filtres
    assert "≥ 5% = excellent" not in filtres
    assert "Vert à partir de 6 %" in filtres
    assert 'id="screener-aide-legende"' in filtres

    cibles = _entre(html, 'id="targetsTable"', 'id="valuation-tab-perf"')
    assert 'id="cibles-aide-legende"' in cibles
    assert "~ une source" in cibles
    assert "⚠ à recouper" in cibles
    assert "Cible à vérifier" in cibles
    assert "<p class=\"aide-legende\"" in cibles
    assert ".aide-legende{" in css

    pastilles = (ROOT / "dashboard" / "data_confidence.js").read_text(encoding="utf-8")
    moyenne = _entre(pastilles, "conf === 'moyenne'", "conf === 'faible'")
    faible = _entre(pastilles, "conf === 'faible'", "icon  = '?'")
    assert "une source" in moyenne
    assert "à recouper" in faible
    assert "opts.short ? ''" not in moyenne
    assert "opts.short ? ''" not in faible


def test_decimales_francaises_sans_toucher_au_csv_ni_a_la_comparaison():
    core = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
    rang = _entre(core, "function renderRank()", "function renderRankLive")
    assert "toFixed(1).replace('.',',')" in rang
    assert "String(x.pe_ref||'—').replace('.',',')" in rang
    comparaison = _entre(core, "function openCompareModal", "function closeCompare")
    assert ".replace('.',',')" not in comparaison
    ecran = (ROOT / "dashboard" / "screener.js").read_text(encoding="utf-8")
    tableau = _entre(ecran, "function _renderScreenerTable", "function _triScreener")
    export = _entre(ecran, "function screenerExportCSV", "async function screenerAnalyseAI")
    assert ".replace('.', ',')" in tableau
    assert "7,3" not in export
    assert "note10num(x).toFixed(1)" in export
    cartes = (ROOT / "dashboard" / "ranking.js").read_text(encoding="utf-8")
    assert "toFixed(1).replace('.', ',')" in cartes


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
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("BRVM_PREUVE_DIR", raising=False)


def _classement_affiche():
    """Fixture versionnée, avec des décimales et des pastilles pour l'écran."""
    data = json.loads((ROOT / "tests" / "fixtures" / "live_ranking.json").read_text(encoding="utf-8"))
    for row in data["ranking"]:
        if row["ticker"] == "ALPH":
            row["div_yield"] = 6.5
            row["pe_ref"] = 8.25
            row["div_confidence"] = "moyenne"
            row["score_graham"] = 7.3
        elif row["ticker"] == "BRAV":
            row["div_yield"] = 3.25
            row["pe_ref"] = 12.4
            row["div_confidence"] = "faible"
            row["div_ecart_boc_pdf"] = 35
    return data


def _ecrire(dossier, nom, payload):
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, nom)
    with open(chemin, "w", encoding="utf-8") as f:
        if isinstance(payload, str):
            f.write(payload)
        else:
            json.dump(payload, f)
    return chemin


@pytest.fixture(scope="module")
def base_url():
    if _CI:
        pytest.skip("Playwright hors CI")
    pytest.importorskip("playwright.sync_api")
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    dossier = os.environ["BRVM_DATA_DIR"]
    maintenant = datetime.now(timezone.utc).isoformat()
    chemins = [
        _ecrire(dossier, "live_ranking.json", _classement_affiche()),
        _ecrire(dossier, "price_history.json", "{}"),
        _ecrire(dossier, "analyses_summary.json", {"ALPH": {"kpis": {}}}),
        _ecrire(dossier, "market_cache.json", {
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
        }),
    ]
    live = json.loads((ROOT / "tests" / "fixtures" / "live_cache.json").read_text(encoding="utf-8"))
    live["updated_at"] = maintenant
    chemins.append(_ecrire(dossier, "live_cache.json", live))
    import market_data
    market_data._memoire = None
    market_data._en_cours = False
    import app as application
    from werkzeug.serving import make_server

    serveur = make_server("127.0.0.1", 0, application.app, threaded=True)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    url = "http://127.0.0.1:%d" % serveur.server_address[1]
    yield url
    serveur.shutdown()
    market_data._memoire = None
    for chemin in chemins:
        if os.path.exists(chemin):
            os.remove(chemin)


_PAGES = (
    ("rank", "/#rank"),
    ("screener", "/#screener"),
    ("marche", "/#marche"),
    ("signals", "/#signals"),
    ("fiche", "/societe/ALPH"),
)
_AIDES = {
    "rank": "Classement",
    "screener": "Screener",
    "marche": "Marché",
    "signals": "Signaux",
    "fiche": "Fiche société",
}
_INTERDIT_AIDE = (
    "SIBC",
    "8.5/10",
    "8,5/10",
    "+3.2%",
    "podium",
    "heatmap",
    "Score min : 55",
    "Score ≥ 60",
    "Score ≥ 6.9",
)


def _est_marche(url, base):
    return url.split("?")[0] == base + "/api/market"


@pytest.mark.skipif(_CI, reason="Playwright hors CI. Local : pytest tests/test_audit_l3_textes.py -q -s")
def test_pages_aide_1280_390_clair_sombre(base_url, tmp_path):
    """0 erreur console, 1 GET /api/market par page, pas de débordement horizontal."""
    from playwright.sync_api import sync_playwright

    preuves = tmp_path
    erreurs = []
    marches = []

    with sync_playwright() as pw:
        navigateur = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            for largeur in (1280, 390):
                for theme in ("clair", "sombre"):
                    for nom, chemin in _PAGES:
                        etiquette = "%s-%d-%s" % (nom, largeur, theme)
                        contexte = navigateur.new_context(
                            viewport={"width": largeur, "height": 800},
                            service_workers="block",
                        )
                        page = contexte.new_page()
                        page.route("https://api.exchangerate-api.com/**", lambda route: route.fulfill(
                            status=200, content_type="application/json", body=b'{"rates":{"EUR":0.0015}}'
                        ))

                        def _console(msg, _et=etiquette):
                            if msg.type == "error":
                                erreurs.append(_et + ": " + msg.text)

                        page.on("pageerror", lambda err, _et=etiquette: erreurs.append(_et + ": pageerror: " + str(err)))
                        page.on("console", _console)
                        page.on(
                            "request",
                            lambda req, _et=etiquette: marches.append(_et)
                            if req.method == "GET" and _est_marche(req.url, base_url) else None,
                        )
                        page.goto(base_url + chemin, wait_until="domcontentloaded", timeout=20000)
                        page.wait_for_function(
                            """(nom) => {
                              if (nom === 'fiche') {
                                var d = document.getElementById('stockDetail');
                                return !!(d && (d.innerText || '').indexOf('ALPH') !== -1);
                              }
                              var page = document.getElementById('page-' + nom);
                              return !!(page && page.classList.contains('on'));
                            }""",
                            arg=nom,
                            timeout=20000,
                        )
                        if nom == "signals":
                            page.wait_for_function(
                                """() => {
                                  var el = document.getElementById('cibles-aide-legende');
                                  return !!(el && (el.innerText || '').indexOf('une source') !== -1);
                                }""",
                                timeout=20000,
                            )
                        if nom == "rank":
                            page.wait_for_function(
                                """() => {
                                  var t = (document.getElementById('rankBody') || {}).innerText || '';
                                  var c = (document.getElementById('rank-cards') || {}).innerText || '';
                                  return (t + c).indexOf('6,5') !== -1;
                                }""",
                                timeout=20000,
                            )
                        if nom == "screener":
                            page.locator("#sc-div").fill("0")
                            page.wait_for_function(
                                """() => ((document.getElementById('screener-table') || {}).innerText || '').indexOf('8,3') !== -1""",
                                timeout=20000,
                            )
                        if theme == "sombre":
                            page.locator("[data-theme-btn]").click()
                            page.wait_for_function("() => !document.documentElement.classList.contains('light')")
                        else:
                            page.wait_for_function("() => document.documentElement.classList.contains('light')")
                        page.wait_for_timeout(900)
                        debord = page.evaluate(
                            """() => document.documentElement.scrollWidth - window.innerWidth"""
                        )
                        assert debord <= 0, "%s déborde de %s px" % (etiquette, debord)
                        if nom == "rank":
                            leg = page.locator("#rank-aide-legende").inner_text()
                            assert "en haut à droite" in leg
                            assert "à gauche" not in leg
                            assert "6 %" in leg
                        if nom == "screener":
                            assert "7,5" in page.locator("#screener-aide-legende").inner_text()
                            assert "≥ 7 = signal fort" not in page.locator("#page-screener").inner_text()
                        if nom == "signals":
                            cibles = page.locator("#cibles-aide-legende").inner_text()
                            assert "une source" in cibles
                            assert "à recouper" in cibles
                            assert "Cible à vérifier" in cibles
                        page.screenshot(path=str(preuves / (etiquette + ".png")))
                        page.locator("#help-fab").click()
                        page.wait_for_function(
                            """(titre) => {
                              var el = document.getElementById('help-page-title');
                              var tiroir = document.getElementById('help-drawer');
                              return !!(el && tiroir && tiroir.classList.contains('open') && el.textContent === titre);
                            }""",
                            arg=_AIDES[nom],
                            timeout=5000,
                        )
                        corps = page.locator("#help-drawer-body").inner_text()
                        assert "7,5" in corps
                        if nom in ("marche", "signals", "fiche", "screener"):
                            assert "6 %" in corps
                            for mot in _INTERDIT_AIDE:
                                assert mot.lower() not in corps.lower(), "%s contient %s" % (etiquette, mot)
                        page.screenshot(path=str(preuves / (etiquette + "-aide.png")))
                        contexte.close()
        finally:
            navigateur.close()

    assert erreurs == [], "\n".join(erreurs)
    assert sorted(marches) == sorted(
        "%s-%d-%s" % (nom, largeur, theme)
        for largeur in (1280, 390)
        for theme in ("clair", "sombre")
        for nom, _chemin in _PAGES
    )
    for nom, _chemin in _PAGES:
        for largeur in (1280, 390):
            for theme in ("clair", "sombre"):
                etiquette = "%s-%d-%s" % (nom, largeur, theme)
                assert (preuves / (etiquette + ".png")).is_file()
                assert (preuves / (etiquette + "-aide.png")).is_file()

    destination = Path("/opt/cursor/artifacts/screenshots/apres")
    if destination.parent.parent.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for png in preuves.glob("*.png"):
            shutil.copy(png, destination / png.name)
