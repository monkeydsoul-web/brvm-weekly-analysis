# -*- coding: utf-8 -*-
"""Affichage seulement : note du serveur avec une virgule, ordre du classement, libelles.

Aucun recalcul de note ni de conseil. Les fonctions sont extraites du front
et executees avec node.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")


def _entre(texte, debut, fin):
    i = texte.index(debut)
    j = texte.index(fin, i)
    return texte[i:j]


def _node(script):
    resultat = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultat.returncode == 0, resultat.stderr or resultat.stdout


def test_sources_lisent_la_note_du_serveur():
    screener = (ROOT / "dashboard" / "screener.js").read_text(encoding="utf-8")
    assert "note10txt(x)" in screener
    assert "v10fmt(sc)" not in screener
    assert "'Conseil'" in screener
    assert "Verdict IA" not in screener
    assert "x.conseil_libelle" in screener

    live = (ROOT / "dashboard" / "live_score.js").read_text(encoding="utf-8")
    assert "note10:          r.note10" in live
    assert "note10txt(d)" in live
    assert "'Fort'" in live and "'Modéré'" in live and "'Faible'" in live and "'Très faible'" in live
    assert "n10>=7.1" in live and "n10>=5" in live and "n10>=2.9" in live
    assert "'Prudence'" not in live
    assert "'FORT'" not in live and "'MODERE'" not in live and "'FAIBLE'" not in live

    badges = (ROOT / "dashboard" / "badges.js").read_text(encoding="utf-8")
    assert "note10txt(entry)" in badges
    assert "v10fmt(entry.composite_adj" not in badges
    assert "Cotation suspendue" in badges

    assert "note10txt(x)" in _entre(HTML, "function renderHeatmap", "function sparkline")
    assert "v10fmt(sc)" not in _entre(HTML, "function renderHeatmap", "function sparkline")
    assert "note10txt(" in _entre(HTML, "function renderTargets", "function loadCustomScores")
    assert "v10fmt(t.score" not in HTML

    compare = (ROOT / "dashboard" / "compare.js").read_text(encoding="utf-8")
    assert "note10txt(x)" in compare
    assert "triCommeClassement" in compare
    ranking = (ROOT / "dashboard" / "ranking.js").read_text(encoding="utf-8")
    assert "note10txt(x)" in ranking
    simulateur = (ROOT / "dashboard" / "simulator.js").read_text(encoding="utf-8")
    assert "note10txt(sc)" in simulateur
    assert "v10fmt(score)" not in simulateur


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_tri_suit_le_rang_du_serveur():
    for rel in (
        "dashboard/markowitz.js",
        "dashboard/backtest.js",
        "dashboard/compare_analysis.js",
        "dashboard/compare.js",
    ):
        assert "triCommeClassement" in (ROOT / rel).read_text(encoding="utf-8")
    assert "triCommeClassement" in _entre(HTML, "function _renderMarketPage", "function _syncMktHeatmap")
    source = _entre(HTML, "function triCommeClassement", "function rapportAnnuelTxt")
    source += _entre(HTML, "function note10num", "function note10txt")
    _node(source + r"""
function attend(cond, msg) { if (!cond) { console.error(msg); process.exit(1); } }
const rows = [
  { ticker: 'SICC', composite_adj: 90, note10: 9.9, rank: 46, statut: 'suspendu' },
  { ticker: 'ALPH', composite_adj: 50, note10: 6.3, rank: 2, statut: 'cote' },
  { ticker: 'BRAV', composite_adj: 80, note10: 7.2, rank: 1, statut: 'cote' },
  { ticker: 'SEMC', composite_adj: 70, note10: 8.8, rank: 47, statut: 'suspendu' }
];
const ordre = rows.slice().sort(triCommeClassement).map(function(x){ return x.ticker; });
attend(ordre.join(',') === 'BRAV,ALPH,SICC,SEMC', ordre.join(','));
const top3 = rows.slice().sort(triCommeClassement).slice(0, 3).map(function(x){ return x.ticker; });
attend(top3.join(',') === 'BRAV,ALPH,SICC', top3.join(','));
""")


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_verdict_expert_utilise_le_conseil_serveur():
    source = _entre(HTML, "function conseilAffiche", "function showChangelog")
    source += _entre(HTML, "function _genVerdict", "function _shareStockText")
    _node(source + r"""
const document = { documentElement: { dataset: { mode: 'expert' } } };
function attend(cond, msg) { if (!cond) { console.error(msg); process.exit(1); } }
const fiche = _genVerdict({
  ticker: 'ALPH', composite_adj: 70,
  conseil: 'Intéressant', conseil_libelle: 'Intéressant', conseil_couleur: 'vert'
});
attend(fiche.indexOf('Intéressant') !== -1, fiche);
['ACHETER','ACCUMULER','CONSERVER','ALLÉGER','SURVEILLER'].forEach(function(mot){
  attend(fiche.indexOf(mot) === -1, mot);
});
const hysteresis = _genVerdict({
  ticker: 'BETA', composite_adj: 70,
  conseil_libelle: 'À surveiller', conseil_couleur: 'orange'
});
attend(hysteresis.indexOf('À surveiller') !== -1, hysteresis);
attend(hysteresis.indexOf('ACHETER') === -1, 'pas acheter');
""")


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_en_tete_suspendu_sans_badge_ni_rang():
    source = (ROOT / "dashboard" / "badges.js").read_text(encoding="utf-8")
    debut = source.index("function renderLiveRankBadge")
    fin = source.index("function renderSidebarScores")
    _node(r"""
function getRankBadge(){ return ''; }
function note10num(row){ return Number(row.note10); }
function note10txt(row){ return note10num(row).toFixed(1).replace('.',','); }
const scores = [
  { ticker: 'SICC', statut: 'suspendu', statut_depuis: '2026-09-16', rank: 46,
    composite_adj: 79, note10: 6.8, pdf_verdict: 'POSITIF' },
  { ticker: 'SEMC', statut: 'suspendu', rank: 47, composite_adj: 60, note10: 7.5, pdf_verdict: 'POSITIF' }
];
const window = { scores: scores };
let html = '';
const document = { getElementById: function(){ return { set innerHTML(v){ html = v; }, get innerHTML(){ return html; } }; } };
""" + source[debut:fin] + r"""
function attend(cond, msg) { if (!cond) { console.error(msg); process.exit(1); } }
renderLiveRankBadge('SICC');
attend(html.indexOf('Cotation suspendue depuis le 16/09/2026') !== -1, html);
attend(html.indexOf('Rang') === -1, 'rang');
attend(html.indexOf('POSITIF') === -1, 'positif');
attend(html.indexOf('6,8') === -1, 'pas de note coloree');
attend(html.indexOf('#46') === -1, 'numero');
renderLiveRankBadge('SEMC');
attend(html.indexOf('Cotation suspendue') !== -1, html);
attend(html.indexOf('Rang') === -1, 'rang semc');
attend(html.indexOf('POSITIF') === -1, 'positif semc');
""")


def test_en_bref_sicc_vient_de_la_fiche_sans_texte_en_dur():
    assert "function texteEnBref" not in HTML
    assert "SICABLE fabrique" not in HTML
    assert "escapeHtml(story.en_bref)" in HTML


def test_libelles_flux_et_csv():
    assert "Reflux (vente)" not in HTML
    assert "Reflux par action (vente)" not in HTML
    assert "Argent qui sort, par action" in HTML
    screener = (ROOT / "dashboard" / "screener.js").read_text(encoding="utf-8")
    assert "Verdict IA" not in screener
    assert "'Conseil'" in screener
