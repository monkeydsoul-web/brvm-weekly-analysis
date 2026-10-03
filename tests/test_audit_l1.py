# -*- coding: utf-8 -*-
"""AUDIT-L1 : date de séance, largeur sur 47, cibles douteuses, CSV du classement.

Les captures vont dans tmp_path, ou dans BRVM_PREUVE_DIR si cette variable
est posée. Aucun chemin n'est exigé.
"""
import csv
import io
import json
import os
import socket
import threading
from urllib.parse import urlparse
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import live_data
import live_ranker
import market_data
from features import _texte_valeur_api, export_csv


_REEL_CONNECT = socket.socket.connect
_REEL_CONNECT_EX = socket.socket.connect_ex
_REEL_CREATE = socket.create_connection
_REEL_DNS = socket.getaddrinfo


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


@contextmanager
def _joue(noms):
    """Écrit dans le répertoire de test, puis remet les fichiers et les caches."""
    dossier = os.environ["BRVM_DATA_DIR"]
    avant = {}
    for nom in noms:
        chemin = os.path.join(dossier, nom)
        avant[chemin] = Path(chemin).read_bytes() if os.path.exists(chemin) else None
    try:
        yield dossier
    finally:
        for chemin, contenu in avant.items():
            if contenu is None:
                if os.path.exists(chemin):
                    os.remove(chemin)
            else:
                Path(chemin).write_bytes(contenu)
        live_ranker._oublier_cache()
        market_data._memoire = None
        market_data._en_cours = False
        market_data._references_2025 = None


def _ecrire(dossier, nom, payload):
    Path(os.path.join(dossier, nom)).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def _client():
    import app as application
    return application.app.test_client()


def _vider_caches():
    live_ranker._oublier_cache()
    market_data._memoire = None
    market_data._en_cours = False


def test_samedi_recule_a_la_seance_du_vendredi():
    """Le 3 octobre 2026 est un samedi. Les cours datent du vendredi 2."""
    with _joue(("live_cache.json", "price_history.json")) as dossier:
        _ecrire(dossier, "live_cache.json", {
            "updated_at": "2026-10-03T14:39:00+00:00",
            "session_date": "2026-10-02",
            "market_open": False,
            "prices": {"SNTS": {"price": 43000, "change_pct": 0.1, "session_date": "2026-10-02"}},
        })
        assert live_data.date_derniere_seance("2026-10-03") == "2026-10-02"
        assert live_data.date_derniere_seance("2026-10-02T18:00:00+00:00") == "2026-10-02T18:00:00+00:00"


def test_semaine_iso_40_la_ou_python_donne_39():
    """%W vaut 39 le vendredi comme le samedi. La semaine affichée est l'ISO 40."""
    assert date(2026, 10, 2).strftime("%W") == "39"
    assert date(2026, 10, 3).strftime("%W") == "39"
    assert live_data.libelle_semaine_iso("2026-10-02") == "Semaine 40/2026"
    assert live_data.libelle_semaine_iso("2026-10-03") == "Semaine 40/2026"
    assert live_data.libelle_semaine_iso(date(2026, 10, 2)) == "Semaine 40/2026"


def test_week_end_sans_cache_recule_au_vendredi():
    with _joue(("live_cache.json", "price_history.json")) as dossier:
        for nom in ("live_cache.json", "price_history.json"):
            chemin = os.path.join(dossier, nom)
            if os.path.exists(chemin):
                os.remove(chemin)
        assert live_data.date_derniere_seance("2026-10-03") == "2026-10-02"


def test_seance_de_semaine_ancienne_n_est_pas_ecrasee():
    with _joue(("live_cache.json",)) as dossier:
        _ecrire(dossier, "live_cache.json", {
            "session_date": "2026-09-01",
            "prices": {"SNTS": {"price": 1, "session_date": "2026-09-01"}},
        })
        assert live_data.date_derniere_seance("2026-10-02") == "2026-10-02"


def test_api_market_affiche_la_seance_pas_le_jour_de_recuperation():
    maintenant = datetime.now(timezone.utc).isoformat()
    with _joue(("market_cache.json", "live_cache.json")) as dossier:
        _ecrire(dossier, "live_cache.json", {
            "updated_at": maintenant,
            "session_date": "2026-10-02",
            "market_open": False,
            "prices": {"SNTS": {"price": 43000, "change_pct": 0.1, "session_date": "2026-10-02"}},
        })
        _ecrire(dossier, "market_cache.json", {
            "updated_at": maintenant,
            "session_date": "2026-10-03",
            "market_activity": {"Capitalisation Actions": "1 000"},
            "top5": [],
            "flop5": [],
            "indices": [{"name": "BRVM - COMPOSITE", "prev": 540.0, "current": 548.38, "change": 1.55}],
            "sector_indices": [],
            "total_return": {},
        })
        _vider_caches()
        corps = _client().get("/api/market").get_json()
        assert corps["session_date"] == "2026-10-02"
        disque = json.loads(Path(os.path.join(dossier, "market_cache.json")).read_text(encoding="utf-8"))
        assert disque["session_date"] == "2026-10-03"


def test_api_market_n_ajoute_pas_session_date():
    maintenant = datetime.now(timezone.utc).isoformat()
    with _joue(("market_cache.json", "live_cache.json")) as dossier:
        _ecrire(dossier, "market_cache.json", {
            "updated_at": maintenant,
            "market_activity": {},
            "top5": [],
            "flop5": [],
            "indices": [{"name": "BRVM - COMPOSITE", "prev": 540.0, "current": 548.38, "change": 1.55}],
            "sector_indices": [],
            "total_return": {},
        })
        _vider_caches()
        corps = _client().get("/api/market").get_json()
        assert "session_date" not in corps


def test_api_macro_semaine_40_et_date_de_seance():
    with _joue(("macro_cache.json", "live_cache.json")) as dossier:
        _ecrire(dossier, "live_cache.json", {
            "session_date": "2026-10-02",
            "prices": {"SNTS": {"price": 1, "session_date": "2026-10-02"}},
        })
        _ecrire(dossier, "macro_cache.json", {
            "date": "2026-10-03",
            "week": "Semaine 39/2026",
            "BRVM_30": 264.57,
            "BRVM_COMPOSITE": 546.78,
            "FCFA_per_USD": 580.49,
        })
        corps = _client().get("/api/macro").get_json()
        assert corps["date"] == "2026-10-02"
        assert corps["week"] == "Semaine 40/2026"
        assert corps["BRVM_30"] == 264.57
        assert corps["FCFA_per_USD"] == 580.49
        disque = json.loads(Path(os.path.join(dossier, "macro_cache.json")).read_text(encoding="utf-8"))
        assert disque["week"] == "Semaine 39/2026"
        assert disque["date"] == "2026-10-03"


def test_api_macro_sans_semaine_reste_intact():
    with _joue(("macro_cache.json", "live_cache.json")) as dossier:
        brut = {"date": "2026-10-03T14:00:00+00:00", "FCFA_per_USD": 580.49, "FCFA_per_EUR": 655.957}
        _ecrire(dossier, "macro_cache.json", brut)
        assert _client().get("/api/macro").get_json() == brut


def test_collecte_macro_ne_date_pas_le_samedi(monkeypatch):
    import news_scraper

    class Horloge(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 3, 15, 0)

    monkeypatch.setattr(news_scraper, "datetime", Horloge)
    monkeypatch.setattr(
        news_scraper.requests, "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("reseau")),
    )
    monkeypatch.setattr(market_data, "get_market_data", lambda **kwargs: {"indices": []})
    with _joue(("live_cache.json", "price_history.json")) as dossier:
        for nom in ("live_cache.json", "price_history.json"):
            chemin = os.path.join(dossier, nom)
            if os.path.exists(chemin):
                os.remove(chemin)
        macro = news_scraper.fetch_macro_context()
    assert macro["date"] == "2026-10-02"
    assert macro["week"] == "Semaine 40/2026"


def _societe(ticker, nom, secteur, cours, variation, note, composite, conseil, cible, libelle, rendement, rang):
    return {
        "ticker": ticker,
        "name": nom,
        "sector": secteur,
        "price": cours,
        "change_pct": variation,
        "note10": note,
        "composite_adj": composite,
        "conseil": conseil,
        "conseil_libelle": conseil,
        "prix_cible": cible,
        "ecart_pct": -98.2 if libelle == "incertain" else 10.0,
        "libelle_valeur": libelle,
        "div_yield": rendement,
        "rank": rang,
    }


def _univers_47():
    """47 lignes figées : 3 / 13 / 29 conseils et 2 sans conseil. Rien n'est recalculé."""
    lignes = []
    lignes.append(_societe(
        "SMBC", "SMB CI", "Industriel", 16450.0, 0.24, 8.4, 67.0,
        "Intéressant", 25440, "Forte décote", 4.28, 1,
    ))
    lignes.append(_societe(
        "SNTS", "Sonatel", "Télécoms", 43000.0, 1.2, 8.1, 64.0,
        "Intéressant", 50000, "Décote modérée", 3.1, 2,
    ))
    lignes.append(_societe(
        "BICC", "BICI CI", "Banque", 32510.0, -1.1, 7.9, 63.0,
        "Intéressant", 36000, "Décote modérée", 2.2, 3,
    ))
    for i in range(13):
        lignes.append(_societe(
            "A%02d" % i, "Surveiller %d" % i, "Banque", 1000.0 + i, 0.5,
            6.0, 48.0, "À surveiller", 1200, "Décote modérée", 1.5, 4 + i,
        ))
    douteuses = {"UNLC", "SIVC", "SHEC", "ABJC", "SCRC"}
    prudence = ["UNLC", "SIVC", "SHEC", "ABJC", "SCRC"] + ["P%02d" % i for i in range(24)]
    assert len(prudence) == 29
    for i, ticker in enumerate(prudence):
        if ticker == "UNLC":
            lignes.append(_societe(
                "UNLC", "Unilever CI", "Consommation", 50900.0, -0.2, 3.6, 29.0,
                "Prudence", 930, "incertain", 1.77, 20 + i,
            ))
            continue
        libelle = "incertain" if ticker in douteuses else "Proche du prix cible"
        cible = 400 + i if libelle == "incertain" else 2000
        lignes.append(_societe(
            ticker, "Prudence %s" % ticker, "Industrie", 2000.0 + i, -0.4,
            3.0, 24.0, "Prudence", cible, libelle, 0.5, 20 + i,
        ))
    for ticker, nom, cours, cible, note in (
        ("SICC", "Sicor CI", 8400.0, 856, 3.3),
        ("SEMC", "Crown Siem CI", 1495.0, 402, 0.7),
    ):
        ligne = _societe(
            ticker, nom, "Industriel", cours, 0.0, note, note * 8,
            None, cible, "incertain", 0.9, 50,
        )
        ligne["conseil"] = None
        ligne["conseil_libelle"] = None
        lignes.append(ligne)
    assert len(lignes) == 47
    return lignes


def test_csv_reprend_le_classement_sans_recalculer():
    with _joue(("live_ranking.json",)) as dossier:
        lignes = _univers_47()
        payload = {
            "updated_at": "2026-10-03T14:49:39+00:00",
            "market_open": False,
            "total": 47,
            "ranking": lignes,
        }
        chemin = os.path.join(dossier, "live_ranking.json")
        Path(chemin).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        avant = Path(chemin).read_bytes()
        _vider_caches()
        client = _client()
        reponse = client.get("/api/live-ranking")
        assert reponse.status_code == 200
        recu = reponse.get_json()["ranking"]
        assert len(recu) == 47
        assert [r.get("conseil_libelle") for r in recu].count("Intéressant") == 3
        assert [r.get("conseil_libelle") for r in recu].count("À surveiller") == 13
        assert [r.get("conseil_libelle") for r in recu].count("Prudence") == 29
        assert [r.get("conseil_libelle") for r in recu].count(None) == 2
        for source, api in zip(lignes, recu):
            assert api["note10"] == source["note10"]
            assert api["conseil_libelle"] == source["conseil_libelle"]
            assert api["prix_cible"] == source["prix_cible"]
            assert api["libelle_valeur"] == source["libelle_valeur"]
            assert api["composite_adj"] == source["composite_adj"]
        csv_resp = client.get("/api/export/csv")
        assert csv_resp.status_code == 200
        assert Path(chemin).read_bytes() == avant
        texte = csv_resp.get_data(as_text=True)
        lecteur = list(csv.DictReader(io.StringIO(texte)))
        assert list(lecteur[0].keys()) == [
            "ticker", "nom", "secteur", "cours", "variation",
            "note /10", "conseil", "prix cible", "rendement",
        ]
        assert "composite_adj" not in texte.splitlines()[0]
        assert [ligne["ticker"] for ligne in lecteur] == [ligne["ticker"] for ligne in recu]
        for source, ligne in zip(recu, lecteur):
            assert ligne["nom"] == (source.get("name") or "")
            assert ligne["secteur"] == (source.get("sector") or "")
            assert float(ligne["cours"]) == float(source["price"])
            assert float(ligne["variation"]) == float(source["change_pct"])
            assert ligne["note /10"] == _texte_valeur_api(source["note10"])
            assert float(ligne["note /10"]) == float(source["note10"])
            attendu = source.get("conseil_libelle") or ""
            if attendu not in ("Intéressant", "À surveiller", "Prudence"):
                attendu = ""
            assert ligne["conseil"] == attendu
            if source.get("libelle_valeur") == "incertain":
                assert ligne["prix cible"] == ""
            else:
                assert float(ligne["prix cible"]) == float(source["prix_cible"])
            assert float(ligne["rendement"]) == float(source["div_yield"])
        smbc = next(ligne for ligne in lecteur if ligne["ticker"] == "SMBC")
        assert smbc["note /10"] == "8.4"
        assert smbc["note /10"] != "67"
        assert "67" not in smbc["note /10"]
        assert smbc["conseil"] == "Intéressant"
        assert smbc["prix cible"] == "25440"
        assert smbc["cours"] == "16450"
        assert smbc["variation"] == "0.24"
        assert smbc["rendement"] == "4.28"
        unlc = next(ligne for ligne in lecteur if ligne["ticker"] == "UNLC")
        assert unlc["prix cible"] == ""
        assert "930" not in unlc["prix cible"]
        api_unlc = next(ligne for ligne in recu if ligne["ticker"] == "UNLC")
        assert api_unlc["prix_cible"] == 930
        sicc = next(ligne for ligne in lecteur if ligne["ticker"] == "SICC")
        assert sicc["conseil"] == ""
        assert sicc["variation"] == "0"
        assert export_csv().splitlines()[1].startswith("SMBC,")


def test_affichage_retire_le_montant_des_cibles_douteuses():
    core = (Path(__file__).resolve().parents[1] / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
    accueil = (Path(__file__).resolve().parents[1] / "dashboard" / "welcome_v2.js").read_text(encoding="utf-8")
    screener = (Path(__file__).resolve().parents[1] / "dashboard" / "screener.js").read_text(encoding="utf-8")
    assert "function cibleDouteuse" in core
    assert "function htmlCartePrixCible" in core
    debut = core.index("function htmlCartePrixCible")
    fin = core.index("async function renderTargets")
    carte = core[debut:fin]
    assert "Cible à vérifier" in carte
    assert "fmtXOF(s.prix_cible)" in carte
    assert carte.index("cibleDouteuse") < carte.index("fmtXOF(s.prix_cible)")
    assert "Le chiffre reste affiché" not in core
    assert "function _largeurDesCotees" in accueil
    assert "_largeurDesCotees" in core
    assert "function _phraseLargeur" in accueil
    assert "_phraseLargeur" in core
    assert "BBGC" not in accueil[accueil.index("function _largeurDesCotees"):accueil.index("function _phraseLargeur")]
    bloc = screener[screener.index("const douteuse"):screener.index("return `<tr")]
    assert "Cible à vérifier" in bloc
    assert "pdf_verdict" not in bloc
    compare = core[core.index("function openCompareModal"):core.index("function closeCompareModal")]
    assert "cibleDouteuse" not in compare


def _marche(maintenant):
    return {
        "updated_at": maintenant,
        "session_date": "2026-10-03",
        "market_activity": {"Capitalisation Actions": "10 234 567 890 123", "Valeur échangée Actions": "1 250 000 000"},
        "top5": [{"ticker": "SNTS", "price": 43000, "change": 1.2}],
        "flop5": [{"ticker": "BICC", "price": 32510, "change": -1.1}],
        "indices": [
            {"name": "BRVM - COMPOSITE", "prev": 540.0, "current": 548.38, "change": 1.55, "ytd": 0.58},
            {"name": "BRVM-30", "prev": 260.0, "current": 266.08, "change": 2.34, "ytd": 0.60},
        ],
        "sector_indices": [],
        "total_return": {},
    }


def _prix(ticker, cours, variation):
    return {
        "price": cours,
        "change_pct": variation,
        "volume": 100,
        "source": "brvm.org",
        "session_date": "2026-10-02",
    }


def _classement_pages(maintenant):
    return {
        "updated_at": maintenant,
        "market_open": False,
        "total": 4,
        "ranking": [
            _societe("SNTS", "Sonatel", "Télécoms", 43000.0, 1.2, 8.4, 67.0, "Intéressant", 50000, "Forte décote", 3.1, 1),
            _societe("BICC", "BICI CI", "Banque", 32510.0, -1.1, 7.1, 56.0, "À surveiller", 36000, "Décote modérée", 2.2, 2),
            _societe("CABC", "SICABLE", "Industrie", 1500.0, 0.0, 5.0, 40.0, "Prudence", 1600, "Proche du prix cible", 1.0, 3),
            _societe("UNLC", "Unilever CI", "Consommation", 50900.0, 0.5, 3.6, 29.0, "Prudence", 930, "incertain", 1.77, 4),
        ],
    }


def test_pages_dates_compteurs_et_cible_1280_390(tmp_path, monkeypatch):
    """1280 et 390, clair et sombre : une lecture /api/market, zéro erreur console."""
    pytest.importorskip("playwright.sync_api")
    _autoriser_local(monkeypatch)
    from playwright.sync_api import sync_playwright

    if os.environ.get("BRVM_PREUVE_DIR"):
        preuves = Path(os.environ["BRVM_PREUVE_DIR"])
        preuves.mkdir(parents=True, exist_ok=True)
    else:
        preuves = tmp_path

    maintenant = datetime.now(timezone.utc).isoformat()
    with _joue(("live_ranking.json", "live_cache.json", "market_cache.json", "macro_cache.json")) as dossier:
        _ecrire(dossier, "live_ranking.json", _classement_pages(maintenant))
        _ecrire(dossier, "live_cache.json", {
            "updated_at": maintenant,
            "market_open": False,
            "session_date": "2026-10-02",
            "seance_ouverte": False,
            "prices": {
                "SNTS": _prix("SNTS", 43000, 1.2),
                "BICC": _prix("BICC", 32510, -1.1),
                "CABC": _prix("CABC", 1500, 0),
                "UNLC": _prix("UNLC", 50900, 0.5),
                "BBGC": _prix("BBGC", 8995, 2.22),
            },
            "stats": {"total": 5, "with_price": 5, "sources": {"brvm.org": 5}, "unknown_tickers": ["BBGC"]},
        })
        _ecrire(dossier, "market_cache.json", _marche(maintenant))
        _ecrire(dossier, "macro_cache.json", {
            "date": "2026-10-03",
            "week": "Semaine 39/2026",
            "FCFA_per_USD": 580.49,
            "FCFA_per_EUR": 655.957,
            "BRVM_COMPOSITE": 546.78,
            "BRVM_30": 264.57,
        })
        _vider_caches()
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

                lectures_marche = []

                def route(interception):
                    url = interception.request.url
                    if interception.request.method == "GET" and urlparse(url).path == "/api/market":
                        lectures_marche.append(url.split("?")[0])
                    if not url.startswith(base):
                        interception.abort()
                        return
                    interception.continue_()

                page.route("**/*", route)

                def theme_clair():
                    if page.evaluate("() => !document.documentElement.classList.contains('light')"):
                        page.click("#topnav [data-theme-btn]")
                    assert page.evaluate("() => document.documentElement.classList.contains('light')")

                def theme_sombre():
                    theme_clair()
                    page.click("#topnav [data-theme-btn]")
                    assert page.evaluate("() => !document.documentElement.classList.contains('light')")

                def charger(chemin, pret):
                    deja = len(lectures_marche)
                    page.goto(base + chemin, wait_until="load", timeout=20000)
                    try:
                        page.wait_for_function(pret, timeout=12000)
                    except Exception:
                        extrait = page.evaluate(
                            """() => ({
                              detail: ((document.getElementById('stockDetail') || {}).innerText || '').slice(0, 800),
                              up: (document.getElementById('mkt-up') || {}).textContent || '',
                              marche: !!(document.getElementById('page-marche') && document.getElementById('page-marche').classList.contains('on')),
                              rang: ((document.getElementById('rank-row-SNTS') || {}).innerText || '').slice(0, 300),
                              hash: location.hash,
                              path: location.pathname
                            })"""
                        )
                        raise AssertionError("%s %s %s" % (chemin, extrait, erreurs[-8:]))
                    page.wait_for_timeout(300)
                    vus = lectures_marche[deja:]
                    assert vus == [base + "/api/market"], vus

                def cadrer(selecteur):
                    page.evaluate(
                        """(sel) => {
                          var el = document.querySelector(sel);
                          if (el) el.scrollIntoView({block: 'center', inline: 'nearest'});
                        }""",
                        selecteur,
                    )

                pages = (
                    ("/", "accueil", "#accueil-composite-etat",
                     "() => (document.getElementById('accueil-largeur-n') || {}).textContent.replace(/\\s/g, '') === '2/1'"
                     " && (document.getElementById('accueil-composite-etat') || {}).textContent.indexOf('2 octobre 2026') >= 0"),
                    ("/?ecran=marche#marche", "marche", "#mkt-largeur-detail",
                     "() => document.getElementById('page-marche') && document.getElementById('page-marche').classList.contains('on')"
                     " && (document.getElementById('mkt-up') || {}).textContent === '2'"
                     " && (document.getElementById('mkt-down') || {}).textContent === '1'"),
                    ("/societe/UNLC", "fiche-unlc", "[data-ctab='chiffres'].ctab-panel",
                     """() => {
                       var btn = document.querySelector('.ctab-btn[data-ctab="chiffres"]');
                       if (btn) btn.click();
                       var t = ((document.getElementById('stockDetail') || {}).innerText || '');
                       return t.indexOf('Cible à vérifier') >= 0 && t.indexOf('930') < 0;
                     }"""),
                    ("/?ecran=classement#rank", "classement", "#rank-row-SNTS",
                     "() => (document.getElementById('rank-row-SNTS') || {}).innerText.indexOf('8,4') >= 0"),
                )

                for largeur, hauteur in ((1280, 800), (390, 844)):
                    page.set_viewport_size({"width": largeur, "height": hauteur})
                    for chemin, nom, selecteur, pret in pages:
                        charger(chemin, pret)
                        if nom == "accueil":
                            etat = page.locator("#accueil-composite-etat").inner_text()
                            assert "Dernière séance : 2 octobre 2026" in etat
                            assert "3 octobre" not in etat
                            bandeau = page.locator("#index-session").inner_text()
                            assert "ven. 02/10" in bandeau
                            assert page.locator("#accueil-largeur-s").inner_text().strip() == "1 stable"
                            assert "48" not in page.locator("#accueil-largeur-n").inner_text()
                        elif nom == "marche":
                            detail = page.locator("#mkt-largeur-detail").inner_text()
                            assert detail == "2 en hausse · 1 stable · 1 en baisse, sur 4 sociétés cotées"
                            assert page.locator("#mkt-up").inner_text() == "2"
                            assert page.locator("#mkt-down").inner_text() == "1"
                        elif nom == "fiche-unlc":
                            fiche = page.locator("#stockDetail").inner_text().replace("\u202f", " ").replace("\u00a0", " ")
                            assert "Cible à vérifier" in fiche
                            assert "930" not in fiche
                            assert "50 900" in fiche or "50900" in fiche
                        elif nom == "classement":
                            ligne = page.locator("#rank-row-SNTS").inner_text()
                            assert "8,4" in ligne
                            assert "67" not in ligne
                            assert "Intéressant" in ligne
                            assert page.locator("a[href='/api/export/csv']").inner_text().replace("⬇", "").strip().startswith("CSV")
                        cadrer(selecteur)
                        theme_clair()
                        page.screenshot(path=str(preuves / ("%s-%d-clair.png" % (nom, largeur))))
                        theme_sombre()
                        cadrer(selecteur)
                        page.screenshot(path=str(preuves / ("%s-%d-sombre.png" % (nom, largeur))))

                navigateur.close()
        finally:
            serveur.shutdown()

    assert erreurs == [], erreurs
    for nom in ("accueil", "marche", "fiche-unlc", "classement"):
        for largeur in (1280, 390):
            for theme in ("clair", "sombre"):
                fichier = preuves / ("%s-%d-%s.png" % (nom, largeur, theme))
                assert fichier.is_file()
                assert fichier.stat().st_size > 1000
