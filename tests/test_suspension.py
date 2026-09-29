# -*- coding: utf-8 -*-
"""SUSP-1 : liste manuelle des cotations suspendues, alertes seulement."""
import json
import logging
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import live_ranker
import statuts_cotation
from live_ranker import compute_live_ranking, empreinte_faits
from statuts_cotation import (
    SEANCES_COURS_FIGE,
    appliquer,
    charger_liste,
    detecter_alerte,
    entree_active,
    invalider_cache,
    lire_seances_ticker,
    statut_de,
)
from verdict import conseil as conseil_verdict
from verdict import note10


MOMENT = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
APRES = datetime(2026, 9, 29, 16, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

FOND = {
    "name": "Emetteur",
    "sector": "Banque",
    "country": "Côte d'Ivoire",
    "shares": 1000,
    "pe_hist": 8.0,
    "pb_hist": 1.2,
    "roe": 20,
    "div_hist": 100,
    "debt": "Faible",
    "stable": True,
}


def _seances(cours, volume=0, n=5, debut="2026-09-22"):
    jour = datetime.strptime(debut, "%Y-%m-%d")
    points = []
    for i in range(n):
        prix = cours[i] if isinstance(cours, (list, tuple)) else cours
        point = {
            "date": (jour + timedelta(days=i)).date().isoformat(),
            "price": prix,
            "source": "live",
        }
        if volume is not None:
            vol = volume[i] if isinstance(volume, (list, tuple)) else volume
            point["volume"] = vol
        points.append(point)
    return points


def test_constante_cinq_seances():
    assert SEANCES_COURS_FIGE == 5


def test_liste_reelle_sicc_et_scrc():
    invalider_cache()
    assert statut_de("SICC", MOMENT) == "suspendu"
    assert statut_de("SCRC", MOMENT) == "suspendu"
    sicc = entree_active("SICC", MOMENT)
    assert sicc["depuis"] == "2026-09-17"
    assert sicc["fin"] is None
    assert "agenceecofin.com" in sicc["source"]
    assert statut_de("SONOCO", MOMENT) is None
    assert statut_de("ALPH", MOMENT) is None


def test_fin_passee_ignoree(fixtures_dir):
    invalider_cache()
    chemin = str(fixtures_dir / "susp_fin_passee.json")
    assert statut_de("ZZZZ", MOMENT, chemin) is None
    assert entree_active("ZZZZ", MOMENT, chemin) is None
    # Le jour de la fin, la suspension tient encore.
    jour_fin = datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc)
    assert statut_de("ZZZZ", jour_fin, chemin) == "suspendu"


def test_fixture_active(fixtures_dir):
    invalider_cache()
    chemin = str(fixtures_dir / "susp_actif.json")
    assert statut_de("zzzz", MOMENT, chemin) == "suspendu"
    assert entree_active("ZZZZ", MOMENT, chemin)["depuis"] == "2026-09-01"


def test_fichier_malforme_liste_vide(fixtures_dir, caplog, tmp_path):
    invalider_cache()
    with caplog.at_level(logging.WARNING, logger="statuts_cotation"):
        liste = charger_liste(str(fixtures_dir / "susp_malforme.json"))
    assert liste == {}
    assert any("illisible" in r.message for r in caplog.records)

    caplog.clear()
    tableau = tmp_path / "liste.json"
    tableau.write_text("[1, 2]", encoding="utf-8")
    invalider_cache()
    with caplog.at_level(logging.WARNING, logger="statuts_cotation"):
        assert charger_liste(str(tableau)) == {}
    assert any("mal forme" in r.message for r in caplog.records)


def test_detection_cours_fige_volume_zero():
    points = _seances(8400, volume=0, n=5)
    alerte = detecter_alerte(points, suspendu=False, moment=MOMENT)
    assert alerte["type"] == "cours_fige"
    assert alerte["depuis"] == "2026-09-22"
    assert alerte["seances"] == 5


def test_detection_cinq_seances_sans_volume():
    points = _seances(8400, volume=None, n=5)
    alerte = detecter_alerte(points, suspendu=False, moment=MOMENT)
    assert alerte["type"] == "cours_fige"
    assert alerte["seances"] == 5


def test_detection_quatre_seances_pas_dalerte():
    assert detecter_alerte(_seances(8400, n=4), suspendu=False, moment=MOMENT) is None


def test_detection_volume_positif_pas_fige():
    assert detecter_alerte(_seances(8400, volume=12, n=6), moment=MOMENT) is None


def test_detection_ignore_les_points_annuels():
    points = [
        {"date": "2024-12-31", "price": 8400, "source": "historical"},
        {"date": "2023-12-31", "price": 8400, "source": "historical"},
    ]
    assert detecter_alerte(points, moment=MOMENT) is None


def test_detection_reprise_probable():
    points = _seances([8400, 8400, 8400, 8400, 8500], volume=0, n=5)
    alerte = detecter_alerte(points, suspendu=True, moment=MOMENT)
    assert alerte == {"type": "reprise_probable", "depuis": "2026-09-26", "seances": 1}
    # Le cours reste figé : pas d'alerte de reprise, et pas de cours_fige
    # tant que le titre est sur la liste.
    plat = _seances(8400, volume=0, n=6)
    assert detecter_alerte(plat, suspendu=True, moment=MOMENT) is None


def test_lire_seances_passe_par_load_history(monkeypatch):
    monkeypatch.setattr(
        "price_history_builder.load_history",
        lambda: {"SICC": _seances(8400, volume=0, n=2)},
    )
    seances = lire_seances_ticker("sicc", MOMENT)
    assert [s["date"] for s in seances] == ["2026-09-22", "2026-09-23"]
    assert seances[-1]["price"] == 8400


def test_appliquer_garde_la_note():
    ligne = {
        "ticker": "SICC",
        "statut": "cote",
        "conseil": "Intéressant",
        "conseil_libelle": "Intéressant",
        "conseil_couleur": "vert",
        "note10": 8.0,
        "composite_adj": 64.0,
    }
    alerte = appliquer(ligne, _seances([8400, 8500], n=2), MOMENT)
    assert ligne["statut"] == "suspendu"
    assert ligne["conseil"] is None
    assert ligne["conseil_libelle"] is None
    assert ligne["conseil_couleur"] is None
    assert ligne["note10"] == 8.0
    assert ligne["composite_adj"] == 64.0
    assert ligne["statut_depuis"] == "2026-09-17"
    assert alerte["type"] == "reprise_probable"
    assert ligne["alerte_cotation"] == alerte


def _prix_live(table):
    prices = {}
    for ticker, prix in table.items():
        prices[ticker] = {
            "price": prix,
            "open": prix,
            "change_pct": 0.2,
            "volume": 10,
            "trend": None,
            "source": "brvm.org",
        }
    return {
        "updated_at": "2026-09-29T10:00:00+00:00",
        "market_open": True,
        "prices": prices,
    }


@pytest.fixture
def marche(tmp_path, monkeypatch):
    chemin = tmp_path / "live_ranking.json"
    monkeypatch.setattr(live_ranker, "RANKING_PATH", str(chemin))
    monkeypatch.setattr(live_ranker, "HISTORY_PATH", str(tmp_path / "ranking_history.json"))
    monkeypatch.setattr(live_ranker, "_last_prices", {})
    monkeypatch.setattr(live_ranker, "_last_ranking", None)
    monkeypatch.setattr(live_ranker, "get_reference_prices", lambda ttl=300: {})
    monkeypatch.setattr(live_ranker, "empreinte_faits", lambda chemins=None: "fixe")
    scores = {"SICC": 79.0, "GAMM": 60.0, "BETA": 50.0, "ALPH": 40.0, "DELT": 30.0}

    def faux(row):
        return {
            "composite_adj": scores.get(row.get("ticker"), 10.0),
            "composite_raw": scores.get(row.get("ticker"), 10.0),
        }

    monkeypatch.setattr(live_ranker, "_compute_scores", faux)
    return {"chemin": chemin, "scores": scores}


def _lancer(marche, monkeypatch, hist, tickers):
    fond = dict((t, dict(FOND, name="Emetteur " + t)) for t in tickers)
    monkeypatch.setattr("scraper.STOCK_FUNDAMENTALS", fond)
    monkeypatch.setattr("price_history_builder.load_history", lambda: hist)
    prix = dict((t, 1000) for t in tickers)
    prix["SICC"] = 8500
    monkeypatch.setattr("live_data.get_live_data", lambda force_refresh=False: _prix_live(prix))
    invalider_cache()
    return compute_live_ranking(trigger="scheduler", moment=MOMENT)


def test_sicc_classe_apres_les_cotes(marche, monkeypatch, caplog):
    hist = {
        "ALPH": _seances(1000, volume=20, n=3),
        "BETA": _seances(1000, volume=20, n=3),
        "GAMM": _seances(1000, volume=20, n=3),
        "DELT": _seances(500, volume=0, n=5),
        "SICC": _seances([8400, 8400, 8400, 8400, 8500], volume=0, n=5),
    }
    with caplog.at_level(logging.WARNING, logger="live_ranker"):
        resultat = _lancer(marche, monkeypatch, hist, list(hist))
    lignes = resultat["ranking"]
    sicc = next(l for l in lignes if l["ticker"] == "SICC")
    delt = next(l for l in lignes if l["ticker"] == "DELT")
    assert sicc["statut"] == "suspendu"
    assert sicc["conseil"] is None
    assert sicc["conseil_libelle"] is None
    assert sicc["conseil_couleur"] is None
    assert sicc["statut_depuis"] == "2026-09-17"
    assert sicc["note10"] == note10(79.0)
    assert sicc["composite_adj"] == 79.0
    assert sicc["classe"] is False
    assert sicc["alerte_cotation"]["type"] == "reprise_probable"
    assert sicc["rank"] == len(lignes)
    top = lignes[:3]
    assert [l["ticker"] for l in top] == ["GAMM", "BETA", "ALPH"]
    assert all(l["statut"] == "cote" and l["classe"] is True for l in top)
    assert all(l["ticker"] != "SICC" for l in top)
    assert delt["statut"] == "cote"
    assert delt["alerte_cotation"]["type"] == "cours_fige"
    assert delt["alerte_cotation"]["seances"] == 5
    assert delt["conseil"] == conseil_verdict(30.0, None, "cote")
    assert delt["conseil"] is not None
    messages = " ".join(r.message for r in caplog.records)
    assert "DELT" in messages and "cours_fige" in messages
    assert "SICC" in messages and "reprise_probable" in messages


def test_changement_de_liste_change_lempreinte_et_sapplique_en_seance(tmp_path, monkeypatch):
    liste = tmp_path / "statuts_cotation.json"
    liste.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(statuts_cotation, "CHEMIN_LISTE", str(liste))
    monkeypatch.setattr(live_ranker, "DATA_DIR", str(tmp_path))
    invalider_cache()
    avant = empreinte_faits()
    assert any(c.endswith("statuts_cotation.json") for c in live_ranker.chemins_faits())

    chemin = tmp_path / "live_ranking.json"
    monkeypatch.setattr(live_ranker, "RANKING_PATH", str(chemin))
    monkeypatch.setattr(live_ranker, "HISTORY_PATH", str(tmp_path / "hist.json"))
    monkeypatch.setattr(live_ranker, "_last_prices", {})
    monkeypatch.setattr(live_ranker, "_last_ranking", None)
    monkeypatch.setattr(live_ranker, "get_reference_prices", lambda ttl=300: {})
    monkeypatch.setattr(live_ranker, "empreinte_faits", empreinte_faits)
    monkeypatch.setattr(
        "scraper.STOCK_FUNDAMENTALS",
        {"SICC": dict(FOND, name="Sicor"), "ALPH": dict(FOND, name="Alpha")},
    )
    hist = {
        "SICC": _seances(8400, volume=10, n=3),
        "ALPH": _seances(1000, volume=10, n=3),
    }
    monkeypatch.setattr("price_history_builder.load_history", lambda: hist)
    monkeypatch.setattr(
        "live_data.get_live_data",
        lambda force_refresh=False: _prix_live({"SICC": 8400, "ALPH": 1000}),
    )

    def faux(row):
        score = 70.0 if row.get("ticker") == "SICC" else 40.0
        return {"composite_adj": score, "composite_raw": score}

    monkeypatch.setattr(live_ranker, "_compute_scores", faux)
    premier = compute_live_ranking(trigger="scheduler", moment=MOMENT)
    sicc = next(l for l in premier["ranking"] if l["ticker"] == "SICC")
    assert sicc["statut"] == "cote"
    assert sicc["conseil"] is not None
    assert premier["note_recalculee"] is True

    liste.write_text(
        json.dumps({
            "SICC": {
                "statut": "suspendu",
                "depuis": "2026-09-17",
                "fin": None,
                "source": "liste de test",
            },
        }),
        encoding="utf-8",
    )
    invalider_cache()
    apres = empreinte_faits()
    assert apres != avant
    second = compute_live_ranking(trigger="scheduler", moment=MOMENT)
    assert second["note_recalculee"] is True
    sicc2 = next(l for l in second["ranking"] if l["ticker"] == "SICC")
    assert sicc2["statut"] == "suspendu"
    assert sicc2["conseil"] is None
    assert sicc2["conseil_libelle"] is None
    assert sicc2["statut_depuis"] == "2026-09-17"
    assert sicc2["note10"] == note10(70.0)
    assert sicc2["rank"] == 2
    assert second["ranking"][0]["ticker"] == "ALPH"


def test_liste_malforme_ne_casse_pas_le_classement(marche, monkeypatch, tmp_path, caplog):
    mauvais = tmp_path / "statuts_cotation.json"
    mauvais.write_text("{", encoding="utf-8")
    monkeypatch.setattr(statuts_cotation, "CHEMIN_LISTE", str(mauvais))
    invalider_cache()
    with caplog.at_level(logging.WARNING):
        resultat = _lancer(marche, monkeypatch, {"ALPH": _seances(1000, n=2)}, ["ALPH"])
    assert resultat["ranking"][0]["ticker"] == "ALPH"
    assert resultat["ranking"][0]["statut"] == "cote"
    assert any("illisible" in r.getMessage() or "mal forme" in r.getMessage() for r in caplog.records)


def _scores_mixes():
    return [
        {
            "ticker": "SICC", "name": "Sicor", "statut": "suspendu",
            "composite_adj": 80, "div_yield": 10, "pe_ref": 4, "pb_ref": 1,
            "roe": 20, "price": 8400,
        },
        {
            "ticker": "SCRC", "name": "Sucrivoire", "statut": "suspendu",
            "composite_adj": 75, "div_yield": 9, "pe_ref": 5, "price": 1000,
        },
        {
            "ticker": "NNNN", "name": "Sans note", "statut": "non_note",
            "composite_adj": 70, "div_yield": 8, "pe_ref": 6, "price": 1000,
        },
        {
            "ticker": "ALPH", "name": "Alpha", "statut": "cote",
            "composite_adj": 60, "div_yield": 6, "pe_ref": 8, "pb_ref": 1,
            "roe": 15, "price": 1000,
        },
        {
            "ticker": "VIEUX", "name": "Ancien fichier",
            "composite_adj": 55, "div_yield": 5, "pe_ref": 9, "price": 1000,
        },
    ]


def _hist_long(prix):
    pts = []
    jour = datetime(2024, 1, 2)
    for i in range(30):
        pts.append({
            "date": (jour + timedelta(days=i)).date().isoformat(),
            "price": prix + i,
            "source": "boc",
        })
    return pts


def test_portefeuilles_et_signaux_excluent_les_suspendus():
    import backtest_previsionnel as bp
    scores = _scores_mixes()
    hist = {
        "SICC": _hist_long(100),
        "SCRC": _hist_long(200),
        "NNNN": _hist_long(50),
        "ALPH": _hist_long(80),
        "VIEUX": _hist_long(90),
    }
    ports = bp.generate_portfolios(scores, hist)
    tickers = [st["ticker"] for pf in ports for st in pf["stocks"]]
    assert "SICC" not in tickers
    assert "SCRC" not in tickers
    assert "NNNN" not in tickers
    assert "ALPH" in tickers
    assert "VIEUX" in tickers
    sigs = bp.compute_signals(scores, hist)
    vus = [s["ticker"] for s in sigs]
    assert "SICC" not in vus
    assert "SCRC" not in vus
    assert "NNNN" not in vus
    assert "ALPH" in vus
    assert "VIEUX" in vus


def test_backtest_exclut_les_suspendus(tmp_path, monkeypatch):
    import backtest_previsionnel as bp
    monkeypatch.setattr(bp, "DATA_DIR", str(tmp_path))
    scores = _scores_mixes()
    hist = dict((s["ticker"], _hist_long(100)) for s in scores)
    resultat = bp.compute_backtest_previsionnel(scores, hist)
    brut = json.dumps(resultat)
    assert "SICC" not in brut
    assert "SCRC" not in brut
    assert "NNNN" not in brut
    assert "ALPH" in brut


def test_pdf_top_exclut_le_suspendu(tmp_path, monkeypatch):
    pytest.importorskip("reportlab")
    import backtest_previsionnel as bp
    monkeypatch.setattr(bp, "DATA_DIR", str(tmp_path))
    scores = _scores_mixes()
    hist = dict((s["ticker"], _hist_long(100)) for s in scores)
    pdf = bp.generate_rapport_pdf(scores, hist)
    import io
    from pypdf import PdfReader
    texte = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    assert "SICC" not in texte
    assert "SCRC" not in texte
    assert "ALPH" in texte


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_performances_ignorent_les_suspendus():
    texte = (ROOT / "dashboard" / "performance.js").read_text(encoding="utf-8")
    assert "_chargerSuspendus" in texte
    assert "if (_perfSuspendus.has(ticker)) continue;" in texte
    assert ".filter(([ticker]) => !_perfSuspendus.has(ticker))" in texte
    assert "/api/scores" in texte


def test_badge_suspendu_dans_le_front():
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    debut = html.index("function conseilAffiche")
    fin = html.index("function showChangelog", debut)
    source = html[debut:fin]
    i = html.index("function _genVerdict")
    j = html.index("function _shareStockText", i)
    source += html[i:j]
    script = source + r"""
const document = { documentElement: { dataset: { mode: 'expert' } } };
function attend(cond, msg) {
  if (!cond) { console.error(msg); process.exit(1); }
}
const row = {
  ticker: 'SICC', statut: 'suspendu', statut_depuis: '2026-09-17',
  composite_adj: 80, conseil: 'Intéressant', conseil_libelle: 'Intéressant',
  conseil_couleur: 'vert', pe_ref: 8, div_yield: 6, roe: 20
};
const avis = conseilAffiche(row);
attend(avis.texte === 'Cotation suspendue depuis le 17/09/2026', avis.texte);
attend(avis.css === 'var(--t2)', 'badge gris');
attend(avis.suspendu === true, 'marque suspendu');
const htmlConseil = fmtConseil(row);
attend(htmlConseil.indexOf('Cotation suspendue depuis le 17/09/2026') !== -1, 'fmt');
attend(htmlConseil.indexOf('var(--t2)') !== -1, 'fmt gris');
attend(htmlConseil.indexOf('Intéressant') === -1, 'fmt sans conseil');
const fiche = _genVerdict(row);
attend(fiche.indexOf('Cotation suspendue depuis le 17/09/2026') !== -1, 'fiche badge');
attend(fiche.indexOf('Note ') !== -1, 'note presente');
attend(fiche.indexOf('color:var(--t2)') !== -1, 'note grise');
['ACHETER','ACCUMULER','CONSERVER','SURVEILLER','ALLÉGER','Intéressant','Prudence','À surveiller'].forEach(function (mot) {
  attend(fiche.indexOf(mot) === -1, 'mot interdit ' + mot);
});
document.documentElement.dataset.mode = 'beginner';
const ficheDeb = _genVerdict(row);
attend(ficheDeb.indexOf('Cotation suspendue depuis le 17/09/2026') !== -1, 'mode debutant');
const normal = conseilAffiche({conseil:'acheter'});
attend(normal.texte === '✅ Intéressant', 'repli intact');
"""
    resultat = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultat.returncode == 0, resultat.stderr or resultat.stdout
