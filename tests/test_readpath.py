# -*- coding: utf-8 -*-
"""READPATH-1 : toutes les routes de note lisent le meme classement.

Le cache memoire ne doit pas survivre a une reecriture du fichier,
et aucune route ne recalcule une note si live_ranking.json manque.
"""
import json
import os

import pytest

import live_ranker

HORODATAGE = "2026-09-29T10:00:00+00:00"
CHAMPS = ("composite_adj", "note10", "conseil", "conseil_libelle", "updated_at")


def _vider():
    live_ranker._last_ranking = None
    live_ranker._last_stamp = None
    live_ranker._last_updated_at = None


@pytest.fixture(autouse=True)
def _cache_vierge(data_dir):
    _vider()
    yield
    _vider()
    chemin = os.path.join(data_dir, "live_ranking.json")
    if os.path.exists(chemin):
        os.remove(chemin)


def _payload():
    return {
        "updated_at": HORODATAGE,
        "trigger": "fixture",
        "market_open": False,
        "total": 2,
        "ranking": [
            {
                "ticker": "SNTS",
                "name": "Sonatel",
                "sector": "Telecoms",
                "country": "Senegal",
                "price": 43000,
                "composite_adj": 54.0,
                "note10": 1.2,
                "conseil": "SENTINELLE",
                "conseil_libelle": "LIBELLE-SENTINELLE",
            },
            {
                "ticker": "SGBC",
                "name": "Societe Generale",
                "sector": "Banque",
                "country": "CI",
                "price": 15000,
                "composite_adj": 61.0,
                "note10": 9.9,
                "conseil": "AUTRE",
                "conseil_libelle": "LIBELLE-AUTRE",
            },
        ],
    }


def _ecrire(dossier, payload):
    chemin = os.path.join(dossier, "live_ranking.json")
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    _vider()
    return chemin


def _champs(row):
    return tuple(row.get(k) for k in CHAMPS)


def _par_ticker(lignes, ticker):
    return next(r for r in lignes if r.get("ticker") == ticker)


@pytest.fixture(scope="module")
def app_module():
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    import app as application
    return application


@pytest.fixture
def client(app_module):
    return app_module.app.test_client()


def test_load_ranking_relit_un_fichier_reecrit(tmp_path, monkeypatch):
    """Avant READPATH-1, le second appel renvoyait le composite mis en cache."""
    chemin = tmp_path / "live_ranking.json"
    monkeypatch.setattr(live_ranker, "RANKING_PATH", str(chemin))

    def ecrire(composite, horodatage):
        payload = {
            "updated_at": horodatage,
            "ranking": [{
                "ticker": "SNTS",
                "composite_adj": composite,
                "note10": 1.2,
                "conseil": "SENTINELLE",
                "conseil_libelle": "LIBELLE-SENTINELLE",
            }],
        }
        # Comme _save_json_atomic : un temporaire puis os.replace change l'inode.
        tmp = chemin.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(str(tmp), str(chemin))

    ecrire(10.0, "2026-09-29T10:00:00+00:00")
    assert live_ranker.load_ranking()["ranking"][0]["composite_adj"] == 10.0
    ecrire(62.1, "2026-09-29T10:05:00+00:00")
    relu = live_ranker.load_ranking()
    assert relu["ranking"][0]["composite_adj"] == 62.1
    assert relu["updated_at"] == "2026-09-29T10:05:00+00:00"
    assert relu["ranking"][0]["updated_at"] == "2026-09-29T10:05:00+00:00"


def _classement_comme_en_prod(composite, horodatage):
    """Cles triees, updated_at en dernier, plus de 8 Ko de lignes.

    En prod le fichier est ecrit avec sort_keys : updated_at est vers
    l'octet 149 000, pas dans les 8 premiers Ko.
    """
    lignes = []
    for i in range(400):
        lignes.append({
            "composite_adj": composite,
            "conseil": "SENTINELLE",
            "note10": 1.2,
            "ticker": "T%03d" % i,
        })
    payload = {
        "changed_tickers": [],
        "market_open": False,
        "ranking": lignes,
        "total": len(lignes),
        "trigger": "fixture",
        "updated_at": horodatage,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def test_load_ranking_ne_reparse_pas_si_fichier_inchange(tmp_path, monkeypatch):
    chemin = tmp_path / "live_ranking.json"
    monkeypatch.setattr(live_ranker, "RANKING_PATH", str(chemin))
    texte = _classement_comme_en_prod(54.0, HORODATAGE)
    brut = texte.encode("utf-8")
    assert len(brut) > 8192
    assert list(json.loads(texte).keys())[-1] == "updated_at"
    assert brut.rfind(b'"updated_at"') > 8192
    chemin.write_text(texte, encoding="utf-8")

    appels = []
    reel = live_ranker._lire_json

    def compte(path):
        appels.append(1)
        return reel(path)

    monkeypatch.setattr(live_ranker, "_lire_json", compte)
    premier = live_ranker.load_ranking()
    assert premier["ranking"][0]["composite_adj"] == 54.0
    assert premier["updated_at"] == HORODATAGE
    assert len(appels) == 1
    second = live_ranker.load_ranking()
    assert second["ranking"][0]["composite_adj"] == 54.0
    assert len(appels) == 1


def test_load_ranking_voit_remplacement_atomique_meme_mtime(tmp_path, monkeypatch):
    chemin = tmp_path / "live_ranking.json"
    monkeypatch.setattr(live_ranker, "RANKING_PATH", str(chemin))
    ancien = _classement_comme_en_prod(10.0, "2026-09-29T10:00:00+00:00")
    nouveau = _classement_comme_en_prod(62.1, "2026-09-29T10:05:00+00:00")
    assert len(ancien) == len(nouveau)
    assert ancien.encode("utf-8").rfind(b'"updated_at"') > 8192
    chemin.write_text(ancien, encoding="utf-8")
    assert live_ranker.load_ranking()["ranking"][0]["composite_adj"] == 10.0
    stat = chemin.stat()

    tmp = tmp_path / "live_ranking.json.tmp"
    tmp.write_text(nouveau, encoding="utf-8")
    os.replace(str(tmp), str(chemin))
    os.utime(chemin, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    apres = chemin.stat()
    assert apres.st_mtime_ns == stat.st_mtime_ns
    assert apres.st_size == stat.st_size
    assert apres.st_ino != stat.st_ino

    relu = live_ranker.load_ranking()
    assert relu["ranking"][0]["composite_adj"] == 62.1
    assert relu["updated_at"] == "2026-09-29T10:05:00+00:00"


def test_load_ranking_oublie_le_cache_si_fichier_supprime(tmp_path, monkeypatch):
    chemin = tmp_path / "live_ranking.json"
    monkeypatch.setattr(live_ranker, "RANKING_PATH", str(chemin))
    chemin.write_text(
        json.dumps({
            "updated_at": HORODATAGE,
            "ranking": [{"ticker": "SNTS", "composite_adj": 10.0}],
        }),
        encoding="utf-8",
    )
    assert live_ranker.load_ranking()["ranking"][0]["composite_adj"] == 10.0
    chemin.unlink()
    assert live_ranker.load_ranking() is None


def test_features_ignore_scores_json(monkeypatch, tmp_path):
    import features
    (tmp_path / "scores_2099.json").write_text(
        json.dumps([{
            "ticker": "VIEUX", "price": 1000, "eps": 100,
            "bvpa": 500, "roe": 10, "composite_adj": 1.0,
        }]),
        encoding="utf-8",
    )
    monkeypatch.setattr(features, "DATA_DIR", str(tmp_path))
    assert features._load_scores() == []


def test_features_prefere_live_ranking(monkeypatch, tmp_path):
    import features
    (tmp_path / "scores_2099.json").write_text(
        json.dumps([{"ticker": "VIEUX", "composite_adj": 1.0, "price": 10}]),
        encoding="utf-8",
    )
    (tmp_path / "live_ranking.json").write_text(
        json.dumps({
            "updated_at": HORODATAGE,
            "ranking": [{
                "ticker": "NEUF", "composite_adj": 70.0,
                "price": 1000, "eps": 100, "bvpa": 500, "roe": 10,
            }],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(features, "DATA_DIR", str(tmp_path))
    rows = features._load_scores()
    assert [r["ticker"] for r in rows] == ["NEUF"]
    assert rows[0]["composite_adj"] == 70.0
    assert rows[0]["updated_at"] == HORODATAGE


def test_backtest_ignore_scores_json(monkeypatch, tmp_path):
    import backtest_previsionnel as bp
    (tmp_path / "scores_2000.json").write_text(
        json.dumps([{"ticker": "VIEUX", "composite_adj": 1.0}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(bp, "DATA_DIR", str(tmp_path))
    assert bp._load_scores() == []


def test_backtest_lit_live_ranking(monkeypatch, tmp_path):
    import backtest_previsionnel as bp
    (tmp_path / "scores_2000.json").write_text(
        json.dumps([{"ticker": "VIEUX", "composite_adj": 1.0}]),
        encoding="utf-8",
    )
    (tmp_path / "live_ranking.json").write_text(
        json.dumps({
            "updated_at": HORODATAGE,
            "ranking": [{"ticker": "NEUF", "composite_adj": 70.0}],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(bp, "DATA_DIR", str(tmp_path))
    rows = bp._load_scores()
    assert rows[0]["ticker"] == "NEUF"
    assert rows[0]["composite_adj"] == 70.0


def test_import_app_ne_demarre_pas_le_scheduler(app_module):
    import auto_scheduler
    assert auto_scheduler.get_scheduler().running is False


def test_routes_accordent_note_conseil_et_horodatage(client, data_dir):
    payload = _payload()
    _ecrire(data_dir, payload)
    attendu = {
        "SNTS": (54.0, 1.2, "SENTINELLE", "LIBELLE-SENTINELLE", HORODATAGE),
        "SGBC": (61.0, 9.9, "AUTRE", "LIBELLE-AUTRE", HORODATAGE),
    }

    scores = client.get("/api/scores")
    assert scores.status_code == 200
    scores_body = scores.get_json()
    assert isinstance(scores_body, list)

    ranking = client.get("/api/live-ranking")
    assert ranking.status_code == 200
    ranking_body = ranking.get_json()
    assert isinstance(ranking_body, dict)
    assert ranking_body["updated_at"] == HORODATAGE

    lives = client.get("/api/live-scores")
    assert lives.status_code == 200
    lives_body = lives.get_json()
    assert lives_body["updated_at"] == HORODATAGE
    assert isinstance(lives_body["scores"], list)
    assert isinstance(lives_body["ranking"], list)

    for ticker, vals in attendu.items():
        assert _champs(_par_ticker(scores_body, ticker)) == vals
        assert _champs(_par_ticker(ranking_body["ranking"], ticker)) == vals
        assert _champs(_par_ticker(lives_body["scores"], ticker)) == vals
        assert _champs(_par_ticker(lives_body["ranking"], ticker)) == vals

        un = client.get("/api/live-score/" + ticker)
        assert un.status_code == 200
        assert _champs(un.get_json()) == vals

        fiche = client.get("/api/stock/" + ticker)
        assert fiche.status_code == 200
        fiche_body = fiche.get_json()
        assert fiche_body["updated_at"] == HORODATAGE
        assert _champs(fiche_body["stock"]) == vals
        assert "price_history" in fiche_body

    recherche = client.get("/api/search?q=SNTS")
    assert recherche.status_code == 200
    assert _champs(_par_ticker(recherche.get_json(), "SNTS")) == attendu["SNTS"]


def test_fichier_absent_503_sans_note_fantome(client, data_dir, monkeypatch):
    chemin = os.path.join(data_dir, "live_ranking.json")
    if os.path.exists(chemin):
        os.remove(chemin)
    live_ranker._last_ranking = {
        "updated_at": "vieux",
        "ranking": [{
            "ticker": "SNTS",
            "composite_adj": 1,
            "note10": 1,
            "conseil": "FANTOME",
            "conseil_libelle": "FANTOME",
        }],
    }
    live_ranker._last_stamp = (0, 0)
    live_ranker._last_updated_at = "vieux"

    appels = []

    def boom(*_a, **_k):
        appels.append(1)
        return [{"ticker": "SNTS", "composite_adj": 99, "conseil": "RECALCULE"}]

    monkeypatch.setattr("live_valuation.compute_all_live_scores", boom)

    urls = (
        "/api/scores",
        "/api/live-ranking",
        "/api/live-scores",
        "/api/live-score/SNTS",
        "/api/stock/SNTS",
        "/api/previsions/signaux",
        "/api/previsions/portfolios",
        "/api/previsions/backtest",
        "/api/rapport-mensuel",
    )
    for url in urls:
        resp = client.get(url)
        assert resp.status_code == 503, url
        corps = resp.get_json()
        assert "indisponible" in corps["error"].lower(), url
        texte = json.dumps(corps)
        assert "FANTOME" not in texte
        assert "RECALCULE" not in texte
    assert appels == []


def test_refresh_public_ne_recalcule_pas(client, data_dir, monkeypatch):
    _ecrire(data_dir, _payload())

    def boom(*_a, **_k):
        raise AssertionError("recalcul public")

    monkeypatch.setattr(live_ranker, "compute_live_ranking", boom)
    resp = client.get("/api/live-ranking?refresh=1")
    assert resp.status_code == 200
    assert resp.get_json()["ranking"][0]["composite_adj"] == 54.0


def test_refresh_admin_declenche_le_calcul(client, data_dir, monkeypatch):
    _ecrire(data_dir, _payload())
    monkeypatch.setenv("ADMIN_TOKEN", "jeton-test")
    appels = []

    def faux(trigger="manual", force=False):
        appels.append(trigger)
        return _payload()

    monkeypatch.setattr(live_ranker, "compute_live_ranking", faux)
    resp = client.get(
        "/api/live-ranking?refresh=1",
        headers={"X-Admin-Token": "jeton-test"},
    )
    assert appels == ["manual"]
    assert resp.status_code == 200
    assert resp.get_json()["updated_at"] == HORODATAGE


def test_ticker_inconnu_reste_404(client, data_dir):
    _ecrire(data_dir, _payload())
    resp = client.get("/api/live-score/ZZZZ")
    assert resp.status_code == 404


def test_json_illisible_503(client, data_dir):
    chemin = os.path.join(data_dir, "live_ranking.json")
    with open(chemin, "w", encoding="utf-8") as f:
        f.write("{")
    _vider()
    resp = client.get("/api/scores")
    assert resp.status_code == 503
    assert "indisponible" in resp.get_json()["error"].lower()


def test_chat_404_et_accueil_200(client):
    assert client.post("/api/chat").status_code == 404
    assert client.get("/").status_code == 200
