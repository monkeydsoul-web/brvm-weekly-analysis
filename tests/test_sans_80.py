# -*- coding: utf-8 -*-
"""FRONT-VERITE-2 : plus aucun /80 visible, PDF et Partager alignes sur /10.

Aucun appel reseau, aucun appel au modele payant.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")

FICHIERS_FRONT = (
    "dashboard/index.html",
    "dashboard/compare_analysis.js",
    "dashboard/backtest.js",
    "dashboard/markowitz.js",
)


def _entre(texte, debut, fin):
    i = texte.index(debut)
    j = texte.index(fin, i)
    return texte[i:j]


def _visible(src):
    """Enleve commentaires et calculs internes, pour ne garder que le texte affiche."""
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"(?m)^\s*//.*$", "", src)
    src = re.sub(r"/\s*80\s*\*\s*10\b", "", src)
    src = re.sub(r"/\s*80\s*\*\s*100\b", "", src)
    return src


def test_aucun_slash_80_visible_dans_les_fichiers_front():
    for rel in FICHIERS_FRONT:
        brut = (ROOT / rel).read_text(encoding="utf-8")
        visible = _visible(brut)
        assert "/80" not in visible, rel
        assert "/ 80" not in visible, rel


def test_app_ne_contient_plus_de_score_sur_80():
    assert "/80" not in APP
    assert "/ 80" not in APP
    assert "Verdict IA" not in APP


def test_methodo_glossaire_fiche_et_partage():
    assert "60/80" not in HTML
    assert "40/80" not in HTML
    assert "68/80" not in HTML
    assert "est Note" not in HTML
    methodo = _entre(HTML, "Comment naît la note", "Fréquences de mise à jour")
    assert "7,5/10" in methodo
    assert "Intéressant" in methodo
    assert "À surveiller" in methodo
    assert "Prudence" in methodo
    assert "Acheter" not in methodo
    fiche = _entre(HTML, "Résumé rapide", "Points forts")
    assert "cette société obtient" in fiche
    assert "/10" in fiche
    assert "est Note" not in fiche
    partage = _entre(HTML, "function _shareStockText", "function _addToSSOHistory")
    assert "Verdict IA" not in partage
    assert "Rapport annuel" in partage
    assert "Pas de conseil" in partage
    assert "Copié !" in partage
    assert "/10" in partage
    commodites = _entre(HTML, "function renderComm", "function _stockTab")
    assert "note10txt" in commodites
    assert "note10num" in commodites
    assert "'/10'" in commodites
    legende = _entre(HTML, 'id="rank-counter"', 'id="rank-table-wrap"')
    assert "≥ 7,5 = Intéressant" in legende
    assert "≥ 5 et &lt; 7,5 = À surveiller" in legende
    assert "&lt; 5 = Prudence" in legende
    assert "Excellent" not in legende
    assert "Correct" not in legende
    assert "À éviter" not in legende
    assert "5-7.5 = correct" not in HTML
    assert "Note ≥ 7.5 = Excellent" not in HTML
    screener = _entre(HTML, 'data-col="composite_adj"', "Score /10")
    assert "Intéressant" in screener
    assert "À surveiller" in screener
    assert "Prudence" in screener
    glossaire = _entre(HTML, "const _glossTerms", "let _glossFiltered")
    assert "÷ 8" not in glossaire
    assert "Résultat de l" not in glossaire
    assert "term:'Verdict'" in glossaire
    assert "Intéressant" in glossaire
    assert "À surveiller" in glossaire
    assert "Prudence" in glossaire
    prev = (ROOT / "dashboard" / "previsions.js").read_text(encoding="utf-8")
    assert prev.count("note10txt(s)") == 2
    ecran = (ROOT / "dashboard" / "screener.js").read_text(encoding="utf-8")
    assert "note10num(x).toFixed(1)" in ecran
    assert "note10txt(x)" not in ecran
    assert "/80*10" not in ecran
    aide = _entre(HTML, "🚀 Pour commencer", "function closeHelpDrawer")
    assert "≥ 7,5/10" in aide
    assert "Intéressant" in aide
    assert "À surveiller" in aide
    assert "Prudence" in aide
    assert "bonne opportunité" not in aide
    assert "Acheter" not in aide
    assert "issu de l" not in aide
    signaux = _entre(HTML, "function renderSignauxParSociete", "function toggleRankAdv")
    assert "≥7.5 excellent" not in signaux
    assert "≥ 7,5 = Intéressant" in signaux
    for rel in ("dashboard/compare_analysis.js", "dashboard/backtest.js", "dashboard/markowitz.js"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "note10txt" in src
        assert "/10" in src


def _ligne_pdf(**extra):
    row = {
        "ticker": "SNTS",
        "name": "Sonatel",
        "sector": "Telecoms",
        "price": 28500,
        "change_pct": 1.25,
        "rank": 3,
        "composite_adj": 54.0,
        "note10": 6.8,
        "conseil_libelle": "À surveiller",
        "pdf_verdict": "POSITIF",
        "pe_ref": 8.2,
        "pb_ref": 1.4,
        "roe": 20.0,
        "div_yield": 6.0,
        "eps": 1500,
        "bvpa": 8000,
        "score_graham": 7,
        "score_dcf": 6,
        "score_ddm": 5,
        "score_epv": 6,
        "score_buffett": 8,
        "score_rev_dcf": 5,
        "score_relatif": 7,
        "score_technique": 6,
    }
    row.update(extra)
    return row


def _vider_classement(data_dir):
    import live_ranker

    live_ranker._last_ranking = None
    live_ranker._last_stamp = None
    live_ranker._last_updated_at = None
    for nom in ("live_ranking.json", "analyses_summary.json"):
        chemin = os.path.join(data_dir, nom)
        if os.path.exists(chemin):
            os.remove(chemin)


def _ecrire_classement(data_dir, rows):
    import live_ranker

    chemin = os.path.join(data_dir, "live_ranking.json")
    payload = {
        "updated_at": "2026-09-29T12:00:00+00:00",
        "ranking": rows,
    }
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    live_ranker._last_ranking = None
    live_ranker._last_stamp = None
    live_ranker._last_updated_at = None
    return chemin


@pytest.fixture
def classement_temporaire(data_dir):
    _vider_classement(data_dir)
    yield data_dir
    _vider_classement(data_dir)


def _texte_pdf(contenu):
    from pypdf import PdfReader
    import io

    reader = PdfReader(io.BytesIO(contenu))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    titre = ""
    auteur = ""
    if reader.metadata:
        titre = reader.metadata.title or ""
        auteur = reader.metadata.author or ""
    return "\n".join(pages), str(titre), str(auteur)


@pytest.fixture
def client():
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    import app as application

    return application.app.test_client()


def test_pdf_note_dix_conseil_et_titre(client, classement_temporaire):
    data_dir = classement_temporaire
    _ecrire_classement(data_dir, [_ligne_pdf()])
    rep = client.get("/api/rapport/SNTS")
    assert rep.status_code == 200, rep.get_data(as_text=True)
    assert rep.mimetype == "application/pdf"
    texte, titre, auteur = _texte_pdf(rep.data)
    assert "/10" in texte
    assert "6,8/10" in texte
    assert "À surveiller" in texte
    assert "Rapport annuel" in texte
    assert "positif" in texte
    assert "/ 80" not in texte
    assert "/80" not in texte
    assert "Verdict IA" not in texte
    assert "Score composite" not in texte
    assert "(anonymous)" not in titre
    assert "Sonatel" in titre
    assert "SNTS" in titre
    assert "BRVM Analyzer" in titre
    assert auteur == "BRVM Analyzer"


def test_pdf_sans_conseil(client, classement_temporaire):
    data_dir = classement_temporaire
    _ecrire_classement(data_dir, [_ligne_pdf(
        ticker="SCRC",
        name="Sucrivoire",
        composite_adj=7.0,
        note10=0.9,
        conseil_libelle=None,
        pdf_verdict=None,
    )])
    rep = client.get("/api/rapport/SCRC")
    assert rep.status_code == 200, rep.get_data(as_text=True)
    texte, titre, _auteur = _texte_pdf(rep.data)
    assert "0,9/10" in texte
    assert "Pas de conseil" in texte
    assert "7,0/10" not in texte
    assert "/ 80" not in texte
    assert "Verdict IA" not in texte
    assert "(anonymous)" not in titre
    assert "SCRC" in titre


def test_prompts_parlent_en_note_dix():
    os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
    import app as application

    secteur = application.contexte_prompt_secteur(
        {
            "ticker": "SCRC",
            "country": "CI",
            "composite_adj": 7,
            "note10": 0.9,
            "conseil_libelle": "Prudence",
            "pe_ref": 12,
            "roe": 4,
            "div_yield": 1.5,
        },
        {"verdict_investisseur": "NEUTRE", "kpis": {}},
    )
    assert "0,9/10" in secteur
    assert "Prudence" in secteur
    assert "/80" not in secteur
    assert "/ 80" not in secteur
    assert "Verdict IA" not in secteur

    # note10 du serveur prime sur le composite interne
    sentinelle = application.contexte_prompt_comparaison(
        {
            "ticker": "SNTS",
            "name": "Sonatel",
            "sector": "Telecoms",
            "country": "Senegal",
            "price": 28500,
            "rank": 3,
            "composite_adj": 54,
            "note10": 1.2,
            "conseil_libelle": "Intéressant",
            "div_yield": 6,
        },
        {"verdict_investisseur": "POSITIF", "kpis": {}, "points_cles": [], "risques": []},
        {},
    )
    assert "1,2/10" in sentinelle
    assert "Intéressant" in sentinelle
    assert "6,8/10" not in sentinelle
    assert "/80" not in sentinelle
    assert "Verdict IA" not in sentinelle
    assert "Rapport annuel" in sentinelle

    # sans note10 : repli composite / 8, pas un score brut sur 80
    repli = application.contexte_prompt_secteur(
        {
            "ticker": "SCRC",
            "country": "CI",
            "composite_adj": 7,
            "pe_ref": 12,
            "roe": 4,
            "div_yield": 0,
        },
        {},
    )
    assert "0,9/10" in repli
    assert "Pas de conseil" in repli
    assert "/80" not in repli
    assert "7/80" not in repli


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_navigateur_note10_partage_et_commodites():
    source = _entre(HTML, "function bcls10", "function fmt(")
    source += _entre(HTML, "function svgBar", "function svgDonut")
    source += _entre(HTML, "function conseilAffiche", "function fmtConseil")
    source += _entre(HTML, "function renderComm", "function _stockTab")
    source += _entre(HTML, "function _shareStockText", "function _addToSSOHistory")
    script = source + r"""
function attend(cond, msg) {
  if (!cond) { console.error(msg); process.exit(1); }
}
var _els = {};
function _el(id) {
  if (!_els[id]) {
    _els[id] = { id: id, innerHTML: '', style: { display: '' }, textContent: '', setAttribute: function(){} };
  }
  return _els[id];
}
_el('commPrices');
_el('cCommDiv');
_el('commTable');
var document = {
  getElementById: function(id) { return _els[id] || null; },
  createElement: function() {
    return { id: '', style: { cssText: '', display: '' }, textContent: '', setAttribute: function(){} };
  },
  body: { appendChild: function(el) { if (el.id) _els[el.id] = el; } }
};
var copied = null;
function prompt(msg, texte) { copied = texte; }
var COMM_PROD = {
  SCRC: { prod: 'Sucre', com: ['Sucre'], exp: 'Forte', col: '#F9A8D4' },
  SNTS: { prod: 'Telecom', com: ['Petrole'], exp: 'Moderee', col: '#60A5FA' }
};
var comms = {};
var scores = [
  { ticker: 'SCRC', composite_adj: 7, note10: 0.9, name: 'Sucrivoire' },
  { ticker: 'SNTS', composite_adj: 54, note10: 6.8, name: 'Sonatel',
    conseil_libelle: 'À surveiller', conseil_couleur: 'orange', pdf_verdict: 'POSITIF',
    price: 28500, change_pct: 1.2, pe_ref: 8.2, div_yield: 6, roe: 20 }
];
var window = { scores: scores };

attend(note10txt({ note10: 1.2, composite_adj: 54 }) === '1,2', 'note10 serveur');
attend(note10txt({ composite_adj: 7 }) === '0,9', 'repli v10fmt');
attend(note10txt({ composite_adj: 54 }) === '6,8', 'repli 54');
attend(note10txt({ score: 54 }) === '6,8', 'repli score');
attend(note10txt({ note10: 6.8, score: 7 }) === '6,8', 'note10 prime');
attend(note10num({ note10: 0.9, composite_adj: 7 }) === 0.9, 'nombre barre');

renderComm();
var graphe = _els.cCommDiv.innerHTML;
var table = _els.commTable.innerHTML;
attend(graphe.indexOf('0,9/10') !== -1, 'SCRC graphe /10');
attend(graphe.indexOf('6,8/10') !== -1, 'SNTS graphe /10');
attend(graphe.indexOf('7.0') === -1, 'plus de 7.0');
attend(graphe.indexOf('NaN') === -1, 'largeur numerique');
attend(graphe.indexOf('/80') === -1, 'graphe sans /80');
attend(table.indexOf('0,9/10') !== -1, 'table SCRC');
attend(table.indexOf('6,8/10') !== -1, 'table SNTS');
attend(table.indexOf('/80') === -1, 'table sans /80');

var texte = _shareStockText('SNTS');
attend(texte.indexOf('6,8/10') !== -1, 'partage note');
attend(texte.indexOf('À surveiller') !== -1, 'partage conseil');
attend(texte.indexOf('Rapport annuel : positif') !== -1, 'partage rapport');
attend(texte.indexOf('Verdict IA') === -1, 'partage sans verdict ia');
_shareConfirme();
attend(_els['share-copie-banner'].textContent === 'Copié !', 'confirmation copie');

scores = [{ ticker: 'SCRC', name: 'Sucrivoire', composite_adj: 7, note10: 0.9,
  conseil_libelle: null, pdf_verdict: null, price: 1000, change_pct: 0 }];
window.scores = scores;
var vide = _shareStockText('SCRC');
attend(vide.indexOf('0,9/10') !== -1, 'partage repli note');
attend(vide.indexOf('Pas de conseil') !== -1, 'partage sans conseil');
attend(vide.indexOf('Verdict IA') === -1, 'partage vide sans verdict ia');
"""
    resultat = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultat.returncode == 0, resultat.stderr or resultat.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_csv_screener_autant_de_cellules_que_d_en_tetes():
    """Une note 7.3 ne doit pas couper la ligne CSV sur la virgule."""
    helpers = _entre(HTML, "function note10num", "function rapportAnnuelTxt")
    export = _entre(
        (ROOT / "dashboard" / "screener.js").read_text(encoding="utf-8"),
        "function screenerExportCSV",
        "async function screenerAnalyseAI",
    )
    script = helpers + export + r"""
var csvTexte = null;
function Blob(parts) { csvTexte = parts.join(''); }
var URL = { createObjectURL: function() { return 'blob:x'; }, revokeObjectURL: function() {} };
var document = { createElement: function() { return { click: function() {} }; } };
var _scrResults = [
  { ticker: 'SNTS', name: 'Societe, Test', sector: 'Banque', note10: 7.3,
    composite_adj: 58, pe_ref: 8.25, pb_ref: 1.1, div_yield: 6.5, roe: 12.4,
    change_pct: -1.25, price: 15000, pdf_verdict: 'POSITIF',
    score_graham: 7.1, score_dcf: 6, score_ddm: 5, score_epv: 4, score_buffett: 8 },
  { ticker: 'SCRC', name: 'Sucrivoire', sector: 'Agro', composite_adj: 7,
    pe_ref: null, pb_ref: null, div_yield: 0, roe: null, change_pct: null,
    price: null, pdf_verdict: '', score_graham: 0, score_dcf: 0, score_ddm: 0,
    score_epv: 0, score_buffett: 0 }
];
screenerExportCSV();
if (!csvTexte) { console.error('csv vide'); process.exit(1); }
var brut = csvTexte.replace(/^\uFEFF/, '');
var lignes = brut.split('\n').filter(function(l) { return l.length; });
var n = lignes[0].split(',').length;
if (n !== 16) { console.error('en-tetes ' + n); process.exit(1); }
lignes.forEach(function(l, i) {
  var cells = l.split(',');
  if (cells.length !== n) {
    console.error('ligne ' + i + ' : ' + cells.length + ' cellules / ' + n + ' : ' + l);
    process.exit(1);
  }
});
if (lignes[1].split(',')[3] !== '7.3') {
  console.error('score ' + lignes[1].split(',')[3]);
  process.exit(1);
}
if (brut.indexOf('7,3') !== -1) { console.error('virgule dans le csv'); process.exit(1); }
if (lignes[2].split(',')[3] !== '0.9') {
  console.error('repli ' + lignes[2].split(',')[3]);
  process.exit(1);
}
"""
    resultat = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultat.returncode == 0, resultat.stderr or resultat.stdout
