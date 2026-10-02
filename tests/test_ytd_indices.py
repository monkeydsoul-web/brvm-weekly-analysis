# -*- coding: utf-8 -*-
"""YTD des indices : clôture du 31/12/2025, pas la colonne figée de brvm.org."""
import json
import os
import shutil
import socket
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ["BRVM_DISABLE_SCHEDULER"] = "1"

import market_data


ROOT = Path(__file__).resolve().parents[1]
_REEL_CONNECT = socket.socket.connect
_REEL_CONNECT_EX = socket.socket.connect_ex
_REEL_CREATE = socket.create_connection
_REEL_DNS = socket.getaddrinfo
REFERENCE = ROOT / "data" / "indices_reference_2025.json"
SOURCE_BOC_249 = "https://bfin.brvm.org/boc/BOC_JOUR/BOC_20251231.pdf"

# Variation annuelle du BOC n° 185 du 30/09/2026.
# Composite 548,38 / 345,75 − 1 = +58,61 %. BRVM 30 266,08 / 166,24 − 1 = +60,06 %.
_CAS = (
    ("BRVM - COMPOSITE", 548.38, 345.75, 58.61),
    ("BRVM-30", 266.08, 166.24, 60.06),
)


@pytest.fixture
def md():
    market_data._memoire = None
    market_data._en_cours = False
    market_data._dernier_essai = 0.0
    market_data._dernier_fil = None
    market_data._references_2025 = None
    if os.path.exists(market_data.CACHE_PATH):
        os.remove(market_data.CACHE_PATH)
    yield market_data
    fil = market_data._dernier_fil
    if fil is not None and fil.is_alive():
        fil.join(3)
    market_data._memoire = None
    market_data._en_cours = False
    market_data._dernier_essai = 0.0
    market_data._dernier_fil = None
    market_data._references_2025 = None
    if os.path.exists(market_data.CACHE_PATH):
        os.remove(market_data.CACHE_PATH)


def test_reference_boc_249():
    brut = json.loads(REFERENCE.read_text(encoding="utf-8"))
    assert brut["source"] == SOURCE_BOC_249
    assert brut["date"] == "2025-12-31"
    assert brut["closes"] == {
        "BRVM Composite": 345.75,
        "BRVM 30": 166.24,
        "Prestige": 144.25,
        "Principal": 217.65,
    }


def test_variation_annuelle_boc_185():
    """548,38 / 345,75 − 1 = +58,61 %, variation annuelle du BOC n° 185."""
    ratio = market_data.ytd_depuis_cloture(548.38, 345.75)
    assert ratio == pytest.approx(548.38 / 345.75 - 1)
    assert round(ratio * 100, 2) == 58.61


def test_deuxieme_valeur_brvm30_boc_185():
    ratio = market_data.ytd_depuis_cloture(266.08, 166.24)
    assert ratio == pytest.approx(266.08 / 166.24 - 1)
    assert round(ratio * 100, 2) == 60.06


def test_colonne_figee_ignoree_et_secteur_sans_reference():
    data = {
        "indices": [{
            "name": "BRVM - COMPOSITE",
            "current": 548.38,
            "ytd": 1.70,
        }],
        "sector_indices": [{
            "name": "BRVM - SERVICES FINANCIERS",
            "current": 247.54,
            "ytd": 0.56,
        }],
    }
    out = market_data.appliquer_ytd_reference(data)
    assert round(out["indices"][0]["ytd"] * 100, 2) == 58.61
    assert out["indices"][0]["ytd"] != 1.70
    assert out["sector_indices"][0]["ytd"] is None
    assert data["indices"][0]["ytd"] == 1.70


def test_api_market_calcule_deux_ytd(md, monkeypatch):
    maintenant = datetime(2026, 9, 30, 16, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    payload = {
        "updated_at": (maintenant - timedelta(seconds=10)).isoformat(),
        "market_activity": {},
        "top5": [],
        "flop5": [],
        "indices": [
            {"name": nom, "prev": 100.0, "current": cours, "change": 0.1, "ytd": 1.70}
            for nom, cours, _cloture, _pct in _CAS
        ],
        "sector_indices": [{
            "name": "BRVM - INDUSTRIELS",
            "prev": 222.90,
            "current": 219.19,
            "change": -1.66,
            "ytd": 0.12,
        }],
        "total_return": {},
    }
    md._ecrire(payload)
    md._memoire = None
    monkeypatch.setattr(md, "fetch_market_data", lambda: (_ for _ in ()).throw(AssertionError("scrape")))

    import app as application
    corps = application.app.test_client().get("/api/market").get_json()
    assert set(corps) == {
        "updated_at", "market_activity", "top5", "flop5",
        "indices", "sector_indices", "total_return",
    }
    recus = {item["name"]: item["ytd"] for item in corps["indices"]}
    for nom, cours, cloture, pct in _CAS:
        assert recus[nom] == pytest.approx(cours / cloture - 1)
        assert round(recus[nom] * 100, 2) == pct
        assert recus[nom] != 1.70
    assert corps["sector_indices"][0]["ytd"] is None


def test_aucun_ytd_fige_dans_les_sources():
    interdits = ("+1,7%", "YTD +1,70", "cols[4]")
    fichiers = (
        ROOT / "market_data.py",
        ROOT / "dashboard" / "index.html",
        ROOT / "dashboard" / "js" / "core.js",
        ROOT / "dashboard" / "welcome_v2.js",
    )
    for chemin in fichiers:
        texte = chemin.read_text(encoding="utf-8")
        for mot in interdits:
            assert mot not in texte, f"{mot} dans {chemin.name}"
    macro = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
    bloc = macro[macro.index("function renderMacroPage"):macro.index("let _anncCurrentTab")]
    assert "change_pct" not in bloc
    assert "avgChg" not in bloc
    assert "_texteMacroYtd" in bloc
    assert "demanderMarche(false)" in bloc
    assert "fetch('/api/market'" not in bloc


def _fonctions_accueil():
    js = (ROOT / "dashboard" / "welcome_v2.js").read_text(encoding="utf-8")
    debut = js.index("function _nombreAccueil")
    fin = js.index("function _comptesConseil")
    return js[debut:fin]


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_accueil_et_macro_affichent_le_calcul():
    script = _fonctions_accueil() + r"""
function attend(cond, msg) {
  if (!cond) { console.error(msg); process.exit(1); }
}
function plat(s) { return String(s).replace(/\u202f|\u00a0/g, ' '); }

var cas = [
  { cours: 548.38, cloture: 345.75, texte: '+58,61 %' },
  { cours: 266.08, cloture: 166.24, texte: '+60,06 %' }
];
cas.forEach(function(c) {
  var ratio = c.cours / c.cloture - 1;
  var home = plat(_ligneSeanceIndice({ current: c.cours, prev: c.cours - 1, change: 0, ytd: ratio }));
  var macro = plat(_texteMacroYtd({ indices: [{ name: 'BRVM - COMPOSITE', current: c.cours, ytd: ratio }] }));
  attend(home.indexOf('depuis le 1er janvier : ' + c.texte) >= 0, home + ' != ' + c.texte);
  attend(home.indexOf('YTD') < 0, 'mot YTD accueil ' + home);
  attend(macro === c.texte, macro + ' != ' + c.texte);
  attend(macro.indexOf('YTD') < 0, 'mot YTD macro');
  attend(home.indexOf(c.texte) >= 0 && macro === c.texte, 'accueil et macro');
});
var negatif = plat(_phraseDepuisJanvier(-0.1234));
attend(negatif === 'depuis le 1er janvier : -12,34 %', negatif);
attend(negatif.indexOf('YTD') < 0, 'mot YTD negatif');
attend(_texteMacroYtd({ indices: [{ name: 'BRVM - INDUSTRIELS', ytd: null }] }) === '—', 'secteur');
attend(_texteYtdIndice(null) === '—', 'ratio nul');
attend(_texteMacroYtd({ indices: [{ name: 'BRVM - COMPOSITE', ytd: null }] }) === '—', 'composite sans ytd');
var sans = plat(_ligneSeanceIndice({ current: 200, prev: 190, ytd: null }));
attend(sans === '+10,00 pts sur la séance · depuis le 1er janvier : —', sans);
attend(sans.indexOf('YTD') < 0, 'mot YTD nul');
"""
    resultat = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultat.returncode == 0, resultat.stderr or resultat.stdout


def test_libelle_indices_en_toutes_lettres_sans_mot_ytd():
    """Le ytd des indices s'écrit en toutes lettres. Le mot YTD ne sert plus de libellé."""
    accueil = (ROOT / "dashboard" / "welcome_v2.js").read_text(encoding="utf-8")
    assert "depuis\\u00a0le\\u00a01er\\u00a0janvier\\u00a0:" in accueil
    assert "L'affichage multiplie par 100 une seule fois." in accueil
    assert "fraction renvoyée par /api/market" in accueil
    assert "YTD" not in accueil

    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    ancre = html.index('id="macro-brvm-ytd"')
    carte = html[html.rindex('<div class="card"', 0, ancre):html.index("</div>", ancre)]
    assert "BRVM-COMPOSITE depuis le&nbsp;1er&nbsp;janvier" in carte
    assert "YTD" not in carte
    assert "title=" not in carte
    assert "BRVM-COMPOSITE YTD" not in html


_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes") or os.environ.get("GITHUB_ACTIONS") == "true"


def _autoriser_local(monkeypatch):
    reel_connect = _REEL_CONNECT
    reel_connect_ex = _REEL_CONNECT_EX
    reel_create = _REEL_CREATE
    reel_dns = _REEL_DNS
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


@pytest.mark.skipif(_CI, reason="Playwright hors CI. Local : pytest tests/test_ytd_indices.py -q -s")
def test_affichage_ytd_indices_libelle_visible(tmp_path, monkeypatch):
    """1280 et 390, clair et sombre : libellé lisible, une requête /api/market, même fraction."""
    pytest.importorskip("playwright.sync_api")
    _autoriser_local(monkeypatch)
    import threading
    from datetime import datetime, timezone

    from playwright.sync_api import sync_playwright

    if os.environ.get("BRVM_PREUVE_DIR"):
        preuves = Path(os.environ["BRVM_PREUVE_DIR"])
        preuves.mkdir(parents=True, exist_ok=True)
    else:
        preuves = tmp_path

    maintenant = datetime.now(timezone.utc).isoformat()
    dossier = os.environ["BRVM_DATA_DIR"]
    os.makedirs(dossier, exist_ok=True)
    classement = os.path.join(dossier, "live_ranking.json")
    marche = os.path.join(dossier, "market_cache.json")
    avant = {}
    for chemin in (classement, marche):
        avant[chemin] = Path(chemin).read_bytes() if os.path.exists(chemin) else None
    Path(classement).write_text(json.dumps({
        "updated_at": maintenant,
        "market_open": False,
        "total": 1,
        "ranking": [{
            "ticker": "SNTS",
            "name": "Sonatel",
            "sector": "Telecoms",
            "price": 43000,
            "composite_adj": 54,
            "change_pct": 0.1,
            "div_yield": 1.0,
            "pe_ref": 10,
            "pdf_verdict": "NEUTRE",
        }],
    }), encoding="utf-8")
    Path(marche).write_text(json.dumps({
        "updated_at": maintenant,
        "market_activity": {"Capitalisation Actions": "10 234 567 890 123"},
        "top5": [],
        "flop5": [],
        "indices": [
            {"name": "BRVM - COMPOSITE", "prev": 540.0, "current": 548.38, "change": 1.55, "ytd": 1.70},
            {"name": "BRVM-30", "prev": 260.0, "current": 266.08, "change": 2.34, "ytd": 1.70},
        ],
        "sector_indices": [{
            "name": "BRVM - INDUSTRIELS",
            "prev": 222.90,
            "current": 219.19,
            "change": -1.66,
            "ytd": 0.12,
        }],
        "total_return": {},
    }), encoding="utf-8")

    import market_data
    market_data._memoire = None
    market_data._en_cours = False
    market_data._references_2025 = None
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
            page.on("console", lambda msg: erreurs.append(msg.text()) if msg.type == "error" else None)

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

            def marches_de(url):
                return url == base + "/api/market" or url.startswith(base + "/api/market?")

            def charger(chemin):
                vus = []
                def noter(req):
                    if req.method == "GET" and marches_de(req.url):
                        vus.append(req.url)
                page.on("request", noter)
                page.goto(base + chemin, wait_until="load", timeout=20000)
                page.wait_for_function("() => window._marketData && window._marketData.composite", timeout=10000)
                page.wait_for_timeout(400)
                page.remove_listener("request", noter)
                assert vus == [base + "/api/market"], vus
                return vus

            def theme_clair():
                if page.evaluate("() => !document.documentElement.classList.contains('light')"):
                    page.click("#topnav [data-theme-btn]")
                assert page.evaluate("() => document.documentElement.classList.contains('light')")

            def theme_sombre():
                theme_clair()
                page.click("#topnav [data-theme-btn]")
                assert page.evaluate("() => !document.documentElement.classList.contains('light')")

            def tient(selecteur):
                return page.evaluate(
                    """(sel) => {
                      var el = document.querySelector(sel);
                      if (!el) return 'absent';
                      var r = el.getBoundingClientRect();
                      var style = getComputedStyle(el);
                      if (r.width < 1 || r.height < 1) return 'invisible';
                      if (r.left < -1 || r.right > window.innerWidth + 1) return 'hors cadre';
                      if (el.scrollWidth > el.clientWidth + 2) return 'debordement';
                      if (style.textOverflow === 'ellipsis' && el.scrollWidth > el.clientWidth + 1) return 'coupe';
                      return 'ok';
                    }""",
                    selecteur,
                )

            attendu = "+8,38 pts sur la séance · depuis le 1er janvier : +58,61 %"

            def lire_seance():
                brut = page.locator("#accueil-composite-seance").inner_text()
                return brut.replace("\u202f", " ").replace("\u00a0", " ").replace("\n", " ")

            for largeur, hauteur in ((1280, 800), (390, 844)):
                page.set_viewport_size({"width": largeur, "height": hauteur})
                charger("/")
                page.wait_for_function(
                    "() => (document.getElementById('accueil-composite-seance') || {}).textContent.indexOf('depuis') >= 0",
                    timeout=8000,
                )
                assert lire_seance() == attendu
                assert "YTD" not in page.locator("#accueil-composite-seance").inner_text()
                assert tient("#accueil-composite-seance") == "ok"
                assert tient(".accueil-composite") == "ok"

                def cadrer_accueil():
                    page.evaluate(
                        """() => {
                          var el = document.querySelector('.accueil-composite');
                          var main = document.querySelector('.main');
                          var delta = el.getBoundingClientRect().top - main.getBoundingClientRect().top;
                          main.scrollTop += delta - 12;
                        }"""
                    )

                theme_clair()
                cadrer_accueil()
                page.screenshot(path=str(preuves / ("accueil-%d-clair.png" % largeur)))
                theme_sombre()
                cadrer_accueil()
                page.screenshot(path=str(preuves / ("accueil-%d-sombre.png" % largeur)))

                vus_macro = []

                def noter_macro(req):
                    if req.method == "GET" and marches_de(req.url):
                        vus_macro.append(req.url)

                page.on("request", noter_macro)
                page.goto(base + "/?ecran=marche#marche", wait_until="load", timeout=20000)
                page.wait_for_function(
                    "() => document.getElementById('page-marche').classList.contains('on')",
                    timeout=8000,
                )
                page.locator("#page-marche .tab-bar button").nth(2).click()
                page.wait_for_function(
                    """() => {
                      var el = document.getElementById('macro-brvm-ytd');
                      var pageMacro = document.getElementById('page-marche');
                      return pageMacro && pageMacro.classList.contains('on')
                        && el && el.textContent.indexOf('%') >= 0;
                    }""",
                    timeout=8000,
                )
                page.wait_for_timeout(300)
                page.remove_listener("request", noter_macro)
                assert vus_macro == [base + "/api/market"], vus_macro
                infos = page.evaluate(
                    """() => {
                      var el = document.getElementById('macro-brvm-ytd');
                      var carte = el.closest('.card');
                      var titre = el.previousElementSibling;
                      return {
                        texte: (carte.innerText || '').replace(/\\u202f|\\u00a0/g, ' '),
                        titreTitle: titre ? (titre.getAttribute('title') || '') : 'absent',
                        valeur: (el.textContent || '').replace(/\\u202f|\\u00a0/g, ' '),
                        ratio: window._marketData.composite.ytd
                      };
                    }"""
                )
                assert "BRVM-COMPOSITE depuis le 1er janvier" in infos["texte"]
                assert "YTD" not in infos["texte"]
                assert infos["titreTitle"] == ""
                assert infos["valeur"] == "+58,61 %"
                assert round(infos["ratio"] * 100, 2) == 58.61
                assert infos["ratio"] != 1.70
                onglets = page.evaluate(
                    """() => ({
                      macro: document.getElementById('marche-tab-macro').classList.contains('on'),
                      indices: document.getElementById('marche-tab-indices').classList.contains('on')
                    })"""
                )
                assert onglets["macro"] and not onglets["indices"], onglets
                assert tient("#macro-brvm-ytd") == "ok"
                assert tient("#marche-tab-macro .g3 .card:nth-child(3)") == "ok"

                def cadrer_macro():
                    page.evaluate(
                        """() => {
                          document.getElementById('macro-brvm-ytd').scrollIntoView({block: 'center', inline: 'nearest'});
                        }"""
                    )

                visible = page.locator("#page-marche").inner_text().replace("\u00a0", " ").replace("\u202f", " ")
                assert "BRVM-COMPOSITE depuis le 1er janvier" in visible
                assert "Heatmap" not in visible
                assert "+58,61 %" in visible
                theme_clair()
                cadrer_macro()
                page.locator("#marche-tab-macro .g3").screenshot(
                    path=str(preuves / ("macro-cartes-%d-clair.png" % largeur))
                )
                page.screenshot(path=str(preuves / ("macro-%d-clair.png" % largeur)))
                theme_sombre()
                cadrer_macro()
                page.locator("#marche-tab-macro .g3").screenshot(
                    path=str(preuves / ("macro-cartes-%d-sombre.png" % largeur))
                )
                page.screenshot(path=str(preuves / ("macro-%d-sombre.png" % largeur)))

            navigateur.close()
    finally:
        serveur.shutdown()
        market_data._memoire = None
        market_data._en_cours = False
        market_data._references_2025 = None
        for chemin, contenu in avant.items():
            if contenu is None:
                if os.path.exists(chemin):
                    os.remove(chemin)
            else:
                Path(chemin).write_bytes(contenu)

    assert erreurs == [], erreurs
    for nom in (
        "accueil-1280-clair.png",
        "accueil-1280-sombre.png",
        "accueil-390-clair.png",
        "accueil-390-sombre.png",
        "macro-1280-clair.png",
        "macro-1280-sombre.png",
        "macro-390-clair.png",
        "macro-390-sombre.png",
    ):
        assert (preuves / nom).is_file()
        assert (preuves / nom).stat().st_size > 1000
