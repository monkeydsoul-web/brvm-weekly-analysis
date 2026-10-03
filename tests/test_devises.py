# -*- coding: utf-8 -*-
"""Conversion XOF / EUR / USD.

EUR : une seule parité, 655,957 XOF. USD : FCFA_per_USD de /api/macro.
Les trois cours ci-dessous sont convertis à la main (division, demi vers
l'éloigné, deux décimales). L'affichage doit reprendre ces chaînes, pas
un autre taux.
"""
import json
import os
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORE = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
DASHBOARD = ROOT / "dashboard"

XOF_PAR_EUR = Decimal("655.957")
XOF_PAR_USD = Decimal("580.49")

# 16 500 / 655,957 = 25,1539… → 25,15 €
# 44 995 / 655,957 = 68,5944… → 68,59 €
# 32 510 / 655,957 = 49,5611… → 49,56 €
# 16 500 / 580,49 = 28,4242… → 28,42 $
# 44 995 / 580,49 = 77,5121… → 77,51 $
# 32 510 / 580,49 = 56,0044… → 56,00 $
# 1 000 / 655,957 = 1,5244… → 1,52 €
# 1 000 / 580,49 = 1,7226… → 1,72 $
PRIX = (
    ("SMBC", 16500, "25,15 €", "28,42 $"),
    ("SNTS", 44995, "68,59 €", "77,51 $"),
    ("BICC", 32510, "49,56 €", "56,00 $"),
)
ENTETE = "1 000 XOF = 1,52 € / 1,72 $"
CAPTURES = Path(os.environ.get("BRVM_PREUVES", tempfile.gettempdir())) / "devises"


def _fr(montant, taux):
    q = (Decimal(montant) / taux).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{q:.2f}".replace(".", ",")


def _entre(source, debut, fin):
    i = source.index(debut)
    j = source.index(fin, i)
    return source[i:j]


def test_trois_prix_convertis_a_la_main():
    assert _fr(1000, XOF_PAR_EUR) == "1,52"
    assert _fr(1000, XOF_PAR_USD) == "1,72"
    assert _fr(16500, Decimal("657.9")) == "25,08"
    for _ticker, montant, eur, usd in PRIX:
        assert eur == _fr(montant, XOF_PAR_EUR) + " €"
        assert usd == _fr(montant, XOF_PAR_USD) + " $"
    assert ENTETE == "1 000 XOF = %s € / %s $" % (_fr(1000, XOF_PAR_EUR), _fr(1000, XOF_PAR_USD))


def test_une_seule_parite_eur_et_aucun_taux_de_repli():
    front = []
    for chemin in DASHBOARD.rglob("*"):
        if chemin.suffix not in {".js", ".html", ".css"}:
            continue
        front.append(chemin.read_text(encoding="utf-8"))
    texte = "\n".join(front)
    assert texte.count("655.957") == 1
    assert "var XOF_PAR_EUR = 655.957;" in CORE
    for interdit in (
        "655.96",
        "655,96",
        "exchangerate-api",
        "1 / 600",
        "1/600",
        "1/615",
        "1/655",
        "656 XOF",
        "fetchExchangeRates",
    ):
        assert interdit not in texte
    assert 'id="parite-xof-eur"' in HTML
    assert "1000 / XOF_PAR_EUR" in CORE
    assert "1000 / window._xofParUsd" in CORE
    assert "FCFA_per_USD" in CORE
    assert "FCFA_per_EUR" not in CORE


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_affichage_js_reprend_les_trois_prix():
    source = _entre(CORE, "var XOF_PAR_EUR", "function toggleMobMenu")
    attendus = []
    for _ticker, montant, eur, usd in PRIX:
        attendus.append("attend(fmtMontant(%d, 'EUR') === %r, 'EUR %d ' + fmtMontant(%d, 'EUR'));" % (montant, eur, montant, montant))
        attendus.append("attend(fmtMontant(%d, 'USD') === %r, 'USD %d ' + fmtMontant(%d, 'USD'));" % (montant, usd, montant, montant))
    script = """
global.window = { _currency: 'XOF', _xofParUsd: null, _rates: {} };
var _els = {};
global.document = { getElementById: function(id) {
  if (!_els[id]) _els[id] = { textContent: '', classList: { toggle: function(){} } };
  return _els[id];
}, querySelectorAll: function(){ return []; }, querySelector: function(){ return null; } };
function attend(cond, msg) { if (!cond) { console.error(msg); process.exit(1); } }
""" + source + """
appliquerTauxMacro({ FCFA_per_USD: 580.49, FCFA_per_EUR: 657.9 });
attend(document.getElementById('curr-rate').textContent === %r, 'entete ' + document.getElementById('curr-rate').textContent);
attend(document.getElementById('parite-xof-eur').textContent === '655,957', 'parite ' + document.getElementById('parite-xof-eur').textContent);
%s
var _mem = {};
global.localStorage = {
  setItem: function(k, v) { _mem[k] = String(v); },
  getItem: function(k) { return Object.prototype.hasOwnProperty.call(_mem, k) ? _mem[k] : null; }
};
setCurrency('USD');
attend(_mem.brvm_currency === 'USD', 'cle ' + _mem.brvm_currency);
attend(fmtXOF(16500) === '28,42 $', 'fmt usd ' + fmtXOF(16500));
window._xofParUsd = null;
window._rates.USD = null;
appliquerTauxMacro({});
attend(fmtMontant(16500, 'USD') === '\\u2014', 'usd absent ' + fmtMontant(16500, 'USD'));
setCurrency('USD');
attend(fmtXOF(16500) === '\\u2014', 'setCurrency sans taux ' + fmtXOF(16500));
attend(_mem.brvm_currency === 'USD', 'choix conserve');
attend(document.getElementById('curr-rate').textContent.indexOf('1,73') === -1, 'pas 1,73');
attend(fmtMontant(16500, 'EUR') === '25,15 €', 'eur reste la parite fixe');
""" % (ENTETE, "\n".join(attendus))
    resultat = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
    assert resultat.returncode == 0, resultat.stderr or resultat.stdout


def _ligne(ticker, nom, secteur, prix, note, rang):
    return {
        "ticker": ticker,
        "name": nom,
        "sector": secteur,
        "country": "CI",
        "price": prix,
        "note10": note,
        "composite_adj": round(note * 8, 1),
        "rank": rang,
        "change_pct": 0,
        "statut": "cote",
        "conseil": "Intéressant",
        "conseil_libelle": "Intéressant",
        "conseil_couleur": "vert",
    }


def _ecrire_fixtures():
    dossier = os.environ["BRVM_DATA_DIR"]
    os.makedirs(dossier, exist_ok=True)
    maintenant = datetime.now(timezone.utc).isoformat()
    rangs = (
        _ligne("SMBC", "SMB CI", "Industriel", 16500, 8.4, 1),
        _ligne("SNTS", "Sonatel", "Télécoms", 44995, 7.3, 2),
        _ligne("BICC", "BICI CI", "Banque", 32510, 7.1, 3),
    )
    with open(os.path.join(dossier, "live_ranking.json"), "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": maintenant,
            "market_open": False,
            "total": len(rangs),
            "ranking": rangs,
        }, f)
    with open(os.path.join(dossier, "macro_cache.json"), "w", encoding="utf-8") as f:
        json.dump({
            "date": maintenant,
            "FCFA_per_EUR": 657.9,
            "FCFA_per_USD": 580.49,
        }, f)
    with open(os.path.join(dossier, "market_cache.json"), "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": maintenant,
            "market_activity": {},
            "top5": [{"ticker": "SMBC", "price": 16500, "change": 1.25}],
            "flop5": [{"ticker": "BICC", "price": 32510, "change": -0.58}],
            "indices": [{"name": "CACHE-TEST", "current": 100, "change": 0}],
            "sector_indices": [],
            "total_return": {},
        }, f)
    prix = {ligne["ticker"]: {"price": ligne["price"], "change_pct": 0, "volume": 100, "source": "fixture"} for ligne in rangs}
    with open(os.path.join(dossier, "live_cache.json"), "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": maintenant,
            "market_open": False,
            "prices": prix,
            "stats": {"total": len(prix), "with_price": len(prix), "sources": {"fixture": len(prix)}},
        }, f)


@pytest.fixture(autouse=True)
def interdire_reseau_et_cle(monkeypatch):
    """Le serveur et Chrome parlent à 127.0.0.1. Tout autre hôte est refusé."""
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
    yield


@pytest.fixture(scope="module")
def base_url():
    pytest.importorskip("playwright.sync_api")
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    _ecrire_fixtures()
    import app as application
    import market_data
    with market_data._verrou:
        market_data._memoire = None
    from werkzeug.serving import make_server

    serveur = make_server("127.0.0.1", 0, application.app, threaded=True)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    url = "http://127.0.0.1:%d" % serveur.server_address[1]
    yield url
    serveur.shutdown()


def _norm(texte):
    return (texte or "").replace("\u202f", " ").replace("\u00a0", " ")


def _lancer_chromium(pw):
    return pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )


def test_pages_affichent_les_trois_prix(base_url):
    from playwright.sync_api import sync_playwright

    pages = (
        ("accueil", base_url + "/", "#accueil-top"),
        ("classement", base_url + "/#rank", "#page-rank"),
        ("fiche", base_url + "/societe/SMBC", "#stockDetail"),
    )
    CAPTURES.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        navigateur = _lancer_chromium(pw)
        try:
            for nom, url, selecteur in pages:
                for devise, code in (("eur", "EUR"), ("usd", "USD")):
                    _verifier_page(navigateur, nom, url, selecteur, devise, code, base_url)
        finally:
            navigateur.close()


def _verifier_page(navigateur, nom, url, selecteur, devise, code, base_url):
    contexte = navigateur.new_context(viewport={"width": 1280, "height": 900}, locale="fr-FR")
    page = contexte.new_page()
    erreurs = []
    marche = {"n": 0}
    page.on("pageerror", lambda err: erreurs.append("pageerror: " + str(err)))
    page.on("console", lambda msg: erreurs.append(msg.text) if msg.type == "error" else None)

    def _compte(req):
        if req.method != "GET":
            return
        if urlparse(req.url).path == "/api/market":
            marche["n"] += 1

    page.on("request", _compte)

    def _route(route):
        if not route.request.url.startswith(base_url):
            route.abort()
            return
        route.continue_()

    page.route("**/*", _route)
    page.goto(url, wait_until="domcontentloaded", timeout=20000)
    pret = {
        "accueil": "() => { var p = document.getElementById('page-welcome'); var t = document.getElementById('accueil-top'); return !!(p && p.classList.contains('on') && t && t.innerText.indexOf('SMBC') !== -1 && document.getElementById('curr-rate') && document.getElementById('curr-rate').textContent.indexOf('1,52') !== -1); }",
        "classement": "() => { var p = document.getElementById('page-rank'); return !!(p && p.classList.contains('on') && p.innerText.indexOf('SMBC') !== -1 && document.getElementById('curr-rate') && document.getElementById('curr-rate').textContent.indexOf('1,52') !== -1); }",
        "fiche": "() => { var p = document.getElementById('page-stock'); var d = document.getElementById('stockDetail'); return !!(p && p.classList.contains('on') && d && d.innerText.indexOf('SMBC') !== -1 && !d.querySelector('.stock-skeleton') && document.getElementById('curr-rate') && document.getElementById('curr-rate').textContent.indexOf('1,52') !== -1); }",
    }[nom]
    page.wait_for_function(pret, timeout=20000)
    page.locator('.topnav-curr [data-curr="%s"]' % devise).click()
    if nom == "fiche":
        page.locator('.ctab-btn[data-ctab="chiffres"]').click()
    morceaux = []
    for ticker, _montant, eur, usd in PRIX:
        if nom == "fiche" and ticker != "SMBC":
            continue
        morceaux.append(eur if code == "EUR" else usd)
    cible = ".ctab-score-block" if nom == "fiche" else selecteur
    for morceau in morceaux:
        page.wait_for_function(
            "(attendu) => { var el = document.querySelector(%r); return !!(el && !el.querySelector('.stock-skeleton') && el.innerText.indexOf(attendu) !== -1); }" % cible,
            arg=morceau,
            timeout=20000,
        )
    page.wait_for_timeout(1200)
    entete = _norm(page.locator("#curr-rate").inner_text())
    assert entete == ENTETE, entete
    corps = _norm(page.locator(cible).inner_text())
    for morceau in morceaux:
        assert morceau in corps, "%s manque dans %s (%s)" % (morceau, nom, devise)
    if code == "EUR":
        assert "25,08" not in corps
    if nom == "fiche":
        en_tete = _norm(page.locator("#stockDetail .stock-main-col").inner_text())
        assert "25,15" not in en_tete
        assert "28,42" not in en_tete
    assert "1,73" not in entete
    assert marche["n"] == 1, "%s %s : %d GET /api/market" % (nom, devise, marche["n"])
    assert erreurs == [], erreurs
    if nom == "fiche" and devise == "eur":
        _capture_entete_fiche(page)
    _captures(page, nom, devise)
    contexte.close()


def _capture_entete_fiche(page):
    page.evaluate("() => window.scrollTo(0, 0)")
    for largeur, px in (("1280", 1280), ("390", 390)):
        page.set_viewport_size({"width": px, "height": 900})
        page.wait_for_timeout(200)
        chemin = CAPTURES / ("fiche-entete-smbc-%s.png" % largeur)
        page.screenshot(path=str(chemin), full_page=False)
        assert chemin.stat().st_size > 1000


def _captures(page, nom, devise):
    for largeur, px in (("1280", 1280), ("390", 390)):
        page.set_viewport_size({"width": px, "height": 900})
        page.wait_for_timeout(250)
        for theme in ("clair", "sombre"):
            clair = page.evaluate("() => document.documentElement.classList.contains('light')")
            if clair != (theme == "clair"):
                page.evaluate("() => toggleTheme()")
                page.wait_for_timeout(100)
            chemin = CAPTURES / ("%s-%s-%s-%s.png" % (nom, devise, largeur, theme))
            page.screenshot(path=str(chemin), full_page=True)
            assert chemin.stat().st_size > 1000


def test_sources_memorisent_la_devise_et_convertissent_comparer():
    compare = (DASHBOARD / "compare.js").read_text(encoding="utf-8")
    screener = (DASHBOARD / "screener.js").read_text(encoding="utf-8")
    assert "localStorage.setItem('brvm_currency', c)" in CORE
    assert "localStorage.getItem('brvm_currency')" in CORE
    assert "fmtXOF(x.price)" in CORE
    assert "fmtXOF(x.price)" in compare
    assert "Cours (XOF)" not in compare
    assert "fmtXOF(target)" in screener
    assert "target.toLocaleString('fr-FR') + ' XOF'" not in screener
    assert "_remplirMouvements(window._accueilMarche)" in CORE
    assert "return str + ' $'" in CORE
    assert "return '$ ' + str" not in CORE


def _ecouter(page, base_url):
    erreurs = []
    marche = {"n": 0}
    page.on("pageerror", lambda err: erreurs.append("pageerror: " + str(err)))
    page.on("console", lambda msg: erreurs.append(msg.text) if msg.type == "error" else None)

    def _compte(req):
        if req.method == "GET" and urlparse(req.url).path == "/api/market":
            marche["n"] += 1

    page.on("request", _compte)

    def _route(route):
        if not route.request.url.startswith(base_url):
            route.abort()
            return
        route.continue_()

    page.route("**/*", _route)
    return erreurs, marche


def test_devise_memorisee_apres_rechargement(base_url):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        navigateur = _lancer_chromium(pw)
        try:
            contexte = navigateur.new_context(viewport={"width": 1280, "height": 900}, locale="fr-FR")
            page = contexte.new_page()
            erreurs, marche = _ecouter(page, base_url)
            page.goto(base_url + "/", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_function(
                "() => { var p = document.getElementById('page-welcome'); var t = document.getElementById('accueil-top'); return !!(p && p.classList.contains('on') && t && t.innerText.indexOf('SMBC') !== -1); }",
                timeout=20000,
            )
            page.locator('.topnav-curr [data-curr="usd"]').click()
            page.wait_for_function(
                "() => { var t = document.getElementById('accueil-top'); var b = document.querySelector('.topnav-curr [data-curr=\"usd\"]'); return !!(t && t.innerText.indexOf('28,42 $') !== -1 && b && b.classList.contains('on')); }",
                timeout=20000,
            )
            assert page.evaluate("() => localStorage.getItem('brvm_currency')") == "USD"
            marche["n"] = 0
            page.reload(wait_until="domcontentloaded", timeout=20000)
            page.wait_for_function(
                "() => { var p = document.getElementById('page-welcome'); var t = document.getElementById('accueil-top'); var b = document.querySelector('.topnav-curr [data-curr=\"usd\"]'); var x = document.querySelector('.topnav-curr [data-curr=\"xof\"]'); return !!(p && p.classList.contains('on') && t && t.innerText.indexOf('28,42 $') !== -1 && b && b.classList.contains('on') && x && !x.classList.contains('on')); }",
                timeout=20000,
            )
            assert _norm(page.locator("#curr-rate").inner_text()) == ENTETE
            assert "28,42 $" in _norm(page.locator("#accueil-top").inner_text())
            assert page.evaluate("() => localStorage.getItem('brvm_currency')") == "USD"
            assert marche["n"] == 1, marche["n"]
            assert erreurs == [], erreurs
            contexte.close()
        finally:
            navigateur.close()


def test_comparer_converti_en_eur(base_url):
    from playwright.sync_api import sync_playwright

    CAPTURES.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        navigateur = _lancer_chromium(pw)
        try:
            contexte = navigateur.new_context(viewport={"width": 1280, "height": 900}, locale="fr-FR")
            page = contexte.new_page()
            erreurs, marche = _ecouter(page, base_url)
            page.goto(base_url + "/#rank", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_function(
                "() => { var p = document.getElementById('page-rank'); return !!(p && p.classList.contains('on') && p.innerText.indexOf('SMBC') !== -1); }",
                timeout=20000,
            )
            page.locator('.topnav-curr [data-curr="eur"]').click()
            page.wait_for_function(
                "() => { var p = document.getElementById('page-rank'); return !!(p && p.innerText.indexOf('25,15 €') !== -1); }",
                timeout=20000,
            )
            page.locator('.cmp-cb[data-ticker="SMBC"]').click()
            page.locator('.cmp-cb[data-ticker="SNTS"]').click()
            page.evaluate("() => openCompareModal()")
            page.wait_for_function(
                "() => { var c = document.getElementById('cmp-modal-content'); var m = document.getElementById('cmp-modal'); return !!(m && m.classList.contains('show') && c && c.innerText.indexOf('25,15 €') !== -1 && c.innerText.indexOf('68,59 €') !== -1); }",
                timeout=20000,
            )
            page.evaluate("() => setCurrency('USD')")
            page.wait_for_function(
                "() => { var c = document.getElementById('cmp-modal-content'); return !!(c && c.innerText.indexOf('28,42 $') !== -1 && c.innerText.indexOf('77,51 $') !== -1); }",
                timeout=20000,
            )
            page.evaluate("() => { compareList = ['SMBC','SNTS']; renderCompare(); }")
            page.wait_for_function(
                "() => { var c = document.getElementById('compare-content'); return !!(c && c.innerText.indexOf('Cours (USD)') !== -1 && c.innerText.indexOf('28,42 $') !== -1); }",
                timeout=10000,
            )
            page.evaluate("() => setCurrency('EUR')")
            page.wait_for_function(
                "() => { var a = document.getElementById('cmp-modal-content'); var b = document.getElementById('compare-content'); return !!(a && a.innerText.indexOf('25,15 €') !== -1 && b && b.innerText.indexOf('Cours (EUR)') !== -1 && b.innerText.indexOf('25,15 €') !== -1); }",
                timeout=20000,
            )
            contenu = _norm(page.locator("#cmp-modal-content").inner_text())
            assert "25,15 €" in contenu
            assert "68,59 €" in contenu
            assert "XOF" not in contenu
            assert "25,08" not in contenu
            autre = _norm(page.locator("#compare-content").inner_text())
            assert "Cours (EUR)" in autre
            assert "25,15 €" in autre
            assert "XOF" not in autre
            assert _norm(page.locator("#curr-rate").inner_text()) == ENTETE
            assert marche["n"] == 1, marche["n"]
            assert erreurs == [], erreurs
            page.evaluate("() => closeCompare()")
            _captures(page, "comparer", "eur")
            contexte.close()
        finally:
            navigateur.close()


def _seance(page):
    return _norm(page.locator("#accueil-mvt-grille").inner_text())


def test_seance_du_jour_suit_la_devise_sans_rechargement(base_url):
    from playwright.sync_api import sync_playwright

    etapes = (
        ("xof", "16 500 XOF", "32 510 XOF", "XOF"),
        ("eur", "25,15 €", "49,56 €", "€"),
        ("usd", "28,42 $", "56,00 $", "$"),
    )
    with sync_playwright() as pw:
        navigateur = _lancer_chromium(pw)
        try:
            contexte = navigateur.new_context(viewport={"width": 1280, "height": 900}, locale="fr-FR")
            page = contexte.new_page()
            erreurs, marche = _ecouter(page, base_url)
            page.goto(base_url + "/", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_function(
                """() => {
                  var g = document.getElementById('accueil-mvt-grille');
                  var t = document.getElementById('accueil-top');
                  if (!g || !t) return false;
                  var seance = g.innerText.replace(/\\u202f/g, ' ').replace(/\\u00a0/g, ' ');
                  return seance.indexOf('16 500 XOF') !== -1 && seance.indexOf('32 510 XOF') !== -1
                    && t.innerText.indexOf('SMBC') !== -1;
                }""",
                timeout=20000,
            )
            for devise, smbc, bicc, signe in etapes:
                if devise != "xof":
                    page.locator('.topnav-curr [data-curr="%s"]' % devise).click()
                page.wait_for_function(
                    """(attendu) => {
                      var g = document.getElementById('accueil-mvt-grille');
                      if (!g) return false;
                      var seance = g.innerText.replace(/\\u202f/g, ' ').replace(/\\u00a0/g, ' ');
                      return seance.indexOf(attendu[0]) !== -1 && seance.indexOf(attendu[1]) !== -1;
                    }""",
                    arg=[smbc, bicc],
                    timeout=20000,
                )
                seance = _seance(page)
                assert smbc in seance, seance
                assert bicc in seance, seance
                if devise == "eur":
                    assert "XOF" not in seance
                    assert "25,08" not in seance
                if devise == "usd":
                    assert "€" not in seance
                    assert "XOF" not in seance
                assert signe in seance
            assert page.evaluate("() => performance.getEntriesByType('navigation').length") == 1
            assert _norm(page.locator("#curr-rate").inner_text()) == ENTETE
            assert marche["n"] == 1, marche["n"]
            assert erreurs == [], erreurs
            contexte.close()
        finally:
            navigateur.close()
