# -*- coding: utf-8 -*-
"""Note principale colorée d'après le conseil, pas d'après la note brute.

L'amortisseur du serveur peut laisser un conseil qui ne suit plus les seuils
7,5 / 5 de la note. Les quatre cas de production :
ETIT 7,3 Intéressant (vert), SOGC 4,9 À surveiller (ambre),
TTLS et ORAC 5,1 Prudence (rouge). SICC et SEMC, suspendues, restent grises.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORE = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
CSS = (ROOT / "dashboard" / "css" / "app.css").read_text(encoding="utf-8")
BADGES = (ROOT / "dashboard" / "badges.js").read_text(encoding="utf-8")
COMPARE = (ROOT / "dashboard" / "compare.js").read_text(encoding="utf-8")
LIVE = (ROOT / "dashboard" / "live_score.js").read_text(encoding="utf-8")


def _entre(source, debut, fin):
    i = source.index(debut)
    j = source.index(fin, i)
    return source[i:j]


def _node(script):
    resultat = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultat.returncode == 0, resultat.stderr or resultat.stdout


def test_sources_separent_note_principale_et_scores_propres():
    assert "function couleurPrincipale" in CORE
    assert "function classePrincipale" in CORE
    assert 'const _colFiche=couleurPrincipale(s)' in CORE
    assert "color:${_colFiche}" in CORE
    assert CORE.count("classePrincipale(") >= 8
    assert "bcls10(" not in CORE.split("function bcls10", 1)[1]
    rang = _entre(CORE, "function renderRank()", "function renderRankLive")
    assert "classePrincipale(x)" in rang
    assert "couleurNote(sv)" in rang
    assert "couleurPrincipale" not in LIVE
    assert "couleurNote(sv)" in LIVE
    assert "couleurPrincipale" in COMPARE
    assert "couleurPrincipale" in (ROOT / "dashboard" / "ranking.js").read_text(encoding="utf-8")
    assert "couleurPrincipale" in (ROOT / "dashboard" / "screener.js").read_text(encoding="utf-8")
    kpi_badges = BADGES[BADGES.index("function buildKpiCards"):]
    assert "div && div > 5" in kpi_badges
    assert "couleurDividende" not in kpi_badges
    assert "var(--exc-ink)" in CORE
    assert "🔶 Exceptionnel" in CORE
    assert ".bx{background:rgba(148,163,184,.18);color:var(--note-muted)}" in CSS
    assert "--note-muted:#b1bac4" in CSS
    assert "--note-muted:#57606a" in CSS
    assert "--exc-ink:#fbbf24" in CSS
    assert "--exc-ink:#6b4200" in CSS
    assert "if((s.div_yield||0)>=6)" in CORE
    assert "else if((s.div_yield||0)>=3)" in CORE
    assert "Math.round(Number(v)/8*10)/10" in CORE
    assert "['Par action',_amtCell,'var(--note-amber)']" in CORE
    assert "col: 'var(--note-muted)'" in LIVE


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_amortisseur_colore_la_note_principale_selon_le_conseil():
    source = _entre(CORE, "function col(v)", "function triCommeClassement")
    source += _entre(CORE, "function triCommeClassement", "function rapportAnnuelTxt")
    source += _entre(CORE, "function conseilAffiche", "function showChangelog")
    source += _entre(CORE, "function renderRank()", "function renderRankLive")
    source += _entre(CORE, "function loadSidebar()", "function filterSidebar")
    source += _entre(BADGES, "function renderLiveRankBadge", "function renderSidebarScores")
    source += _entre(COMPARE, "function renderCompare()", "function createCompareModal")
    source += _entre(CORE, "function _genVerdict", "function _shareStockText")
    source += _entre(LIVE, "function _palierScoreLive", "function _renderLiveScore")
    script = source + r"""
function attend(cond, msg) { if (!cond) { console.error(msg); process.exit(1); } }
function el() {
  return {
    innerHTML: '',
    textContent: '',
    style: {},
    value: '',
    classList: { add: function(){}, remove: function(){} },
    querySelector: function(sel) {
      this._kids = this._kids || {};
      if (!this._kids[sel]) this._kids[sel] = el();
      return this._kids[sel];
    }
  };
}
const nodes = {};
const document = {
  getElementById: function(id) {
    if (!nodes[id]) nodes[id] = el();
    return nodes[id];
  },
  createElement: function() { return el(); },
  body: { appendChild: function(){} },
  documentElement: { dataset: { mode: 'beginner' } }
};
function getRankBadge() { return ''; }
global.window = { SEUIL_NOTE_HAUT: 7.5, SEUIL_NOTE_BAS: 5, _favOnly: false, _priceHistory: {}, _extSparklines: {} };
let favorites = [];
let _cmpSelected = null;
let _rankAdvMode = false;
let compareList = ['ETIT', 'SOGC', 'TTLS', 'ORAC', 'SICC', 'SEMC'];

const lignes = [
  { ticker: 'ETIT', name: 'Ecobank TI', note10: 7.3, composite_adj: 58.4, rank: 1,
    conseil: 'acheter', conseil_libelle: 'Intéressant', conseil_couleur: 'vert',
    score_graham: 7.3, div_yield: 4.0, price: 20, sector: 'Banque', pdf_verdict: 'NEUTRE' },
  { ticker: 'SOGC', name: 'SOGB', note10: 4.9, composite_adj: 39.2, rank: 2,
    conseil: 'attendre', conseil_libelle: 'À surveiller', conseil_couleur: 'orange',
    score_graham: 4.9, div_yield: 2.0, price: 20, sector: 'Agriculture', pdf_verdict: 'NEUTRE' },
  { ticker: 'TTLS', name: 'Total SN', note10: 5.1, composite_adj: 40.8, rank: 3,
    conseil: 'eviter', conseil_libelle: 'Prudence', conseil_couleur: 'rouge',
    score_graham: 5.1, div_yield: 3.0, price: 20, sector: 'Distribution', pdf_verdict: 'NEUTRE' },
  { ticker: 'ORAC', name: 'Orange CI', note10: 5.1, composite_adj: 40.8, rank: 4,
    conseil: 'eviter', conseil_libelle: 'Prudence', conseil_couleur: 'rouge',
    score_graham: 5.1, div_yield: 6.0, price: 20, sector: 'Télécommunications', pdf_verdict: 'NEUTRE' },
  { ticker: 'SICC', name: 'SICOR', note10: 6.8, composite_adj: 54.4, rank: 46,
    statut: 'suspendu', statut_depuis: '2024-03-01', score_graham: 6.8, price: 0 },
  { ticker: 'SEMC', name: 'SEMC', note10: 5.0, composite_adj: 40, rank: 47,
    statut: 'suspendu', score_graham: 5.0, price: 0 }
];
let scores = lignes;
window.scores = lignes;

function ligne(ticker) {
  const html = nodes.rankBody.innerHTML;
  const i = html.indexOf('rank-row-' + ticker);
  attend(i !== -1, 'ligne ' + ticker);
  return html.slice(i, html.indexOf('</tr>', i));
}
function a(classe, extrait) {
  return 'class="b ' + classe + '"' in extrait || extrait.indexOf('class="b ' + classe + '"') !== -1;
}

attend(couleurNote(7.3).indexOf('amber') !== -1, '7,3 brut serait ambre');
attend(couleurNote(4.9).indexOf('red') !== -1, '4,9 brut serait rouge');
attend(couleurNote(5.1).indexOf('amber') !== -1, '5,1 brut serait ambre');
attend(couleurPrincipale(lignes[0]).indexOf('note-green') !== -1, 'ETIT vert');
attend(classePrincipale(lignes[0]) === 'bg', 'ETIT classe');
attend(couleurPrincipale(lignes[1]).indexOf('note-amber') !== -1, 'SOGC ambre');
attend(classePrincipale(lignes[1]) === 'ba', 'SOGC classe');
attend(couleurPrincipale(lignes[2]).indexOf('note-red') !== -1, 'TTLS rouge');
attend(classePrincipale(lignes[2]) === 'br', 'TTLS classe');
attend(couleurPrincipale(lignes[3]).indexOf('note-red') !== -1, 'ORAC rouge');
attend(classePrincipale(lignes[3]) === 'br', 'ORAC classe');
attend(couleurPrincipale(lignes[4]) === 'var(--t2)' && classePrincipale(lignes[4]) === 'bx', 'SICC gris');
attend(couleurPrincipale(lignes[5]) === 'var(--t2)' && classePrincipale(lignes[5]) === 'bx', 'SEMC gris');

renderRank();
const etit = ligne('ETIT');
const sogc = ligne('SOGC');
const ttls = ligne('TTLS');
const orac = ligne('ORAC');
const sicc = ligne('SICC');
const semc = ligne('SEMC');
attend(etit.indexOf('class="b bg"') !== -1 && etit.indexOf('7,3') !== -1, 'classement ETIT vert ' + etit);
attend(sogc.indexOf('class="b ba"') !== -1 && sogc.indexOf('4,9') !== -1, 'classement SOGC ambre');
attend(ttls.indexOf('class="b br"') !== -1 && ttls.indexOf('5,1') !== -1, 'classement TTLS rouge');
attend(orac.indexOf('class="b br"') !== -1 && orac.indexOf('5,1') !== -1, 'classement ORAC rouge');
attend(sicc.indexOf('class="b bx"') !== -1, 'classement SICC gris');
attend(semc.indexOf('class="b bx"') !== -1, 'classement SEMC gris');
const graham = etit.split('adv-col')[1];
attend(graham.indexOf('note-amber') !== -1 && graham.indexOf('7.3') !== -1, 'barre Graham reste sur la note');

loadSidebar();
const side = nodes.tlItems.innerHTML;
attend(side.indexOf('color:var(--note-green)">7,3') !== -1, 'sidebar ETIT');
attend(side.indexOf('color:var(--note-amber)">4,9') !== -1, 'sidebar SOGC');
attend(side.indexOf('color:var(--note-red)">5,1') !== -1, 'sidebar TTLS et ORAC');
attend(side.indexOf('color:var(--t2)">6,8') !== -1, 'sidebar SICC');
attend(side.indexOf('color:var(--t2)">5,0') !== -1, 'sidebar SEMC');

renderCompare();
const cmp = nodes['compare-modal'].querySelector('#compare-content').innerHTML;
attend(cmp.indexOf('color:var(--note-green)">7,3/10') !== -1, 'comparer ETIT');
attend(cmp.indexOf('color:var(--note-amber)">4,9/10') !== -1, 'comparer SOGC');
function compte(texte, mot) {
  let n = 0, p = 0;
  while ((p = texte.indexOf(mot, p)) !== -1) { n += 1; p += mot.length; }
  return n;
}
attend(compte(cmp, 'color:var(--note-red)">5,1/10') === 2, 'comparer TTLS et ORAC');
attend(cmp.indexOf('color:var(--t2)">6,8/10') !== -1, 'comparer SICC');
attend(cmp.indexOf('color:var(--t2)">5,0/10') !== -1, 'comparer SEMC');

renderLiveRankBadge('ETIT');
const fiche = nodes['live-rank-badge'].innerHTML;
attend(fiche.indexOf('color:var(--note-green)">7,3/10') !== -1, 'fiche ETIT');
renderLiveRankBadge('SOGC');
attend(nodes['live-rank-badge'].innerHTML.indexOf('color:var(--note-amber)">4,9/10') !== -1, 'fiche SOGC');
renderLiveRankBadge('TTLS');
attend(nodes['live-rank-badge'].innerHTML.indexOf('color:var(--note-red)">5,1/10') !== -1, 'fiche TTLS');
renderLiveRankBadge('ORAC');
attend(nodes['live-rank-badge'].innerHTML.indexOf('color:var(--note-red)">5,1/10') !== -1, 'fiche ORAC');
renderLiveRankBadge('SICC');
const ficheSicc = nodes['live-rank-badge'].innerHTML;
attend(ficheSicc.indexOf('Cotation suspendue') !== -1 && ficheSicc.indexOf('var(--note-muted)') !== -1, 'fiche SICC grise');
attend(ficheSicc.indexOf('note-green') === -1 && ficheSicc.indexOf('note-amber') === -1, 'fiche SICC sans couleur de note');

function resume(s) {
  const _colFiche = couleurPrincipale(s);
  const _noteFiche = note10txt(s);
  return '<strong style="color:' + _colFiche + '">' + _noteFiche + '/10</strong>';
}
attend(resume(lignes[0]).indexOf('note-green') !== -1 && resume(lignes[0]).indexOf('7,3/10') !== -1, 'resume ETIT');
attend(resume(lignes[1]).indexOf('note-amber') !== -1, 'resume SOGC');
attend(resume(lignes[2]).indexOf('note-red') !== -1 && resume(lignes[3]).indexOf('note-red') !== -1, 'resume TTLS ORAC');

const verdict = _genVerdict(lignes[0]);
attend(verdict.indexOf('note-green') !== -1 && verdict.indexOf('Intéressant') !== -1, 'verdict ETIT');
const divHaut = _genVerdict(Object.assign({}, lignes[0], { div_yield: 6 }));
const divMilieu = _genVerdict(Object.assign({}, lignes[0], { div_yield: 5.9 }));
const divBas = _genVerdict(Object.assign({}, lignes[0], { div_yield: 3 }));
const divFaible = _genVerdict(Object.assign({}, lignes[0], { div_yield: 2.9 }));
attend(divHaut.indexOf('Dividende élevé') !== -1, '6 % élevé');
attend(divMilieu.indexOf('Dividende élevé') === -1 && divMilieu.indexOf('Dividende présent') !== -1, '5,9 % présent');
attend(divBas.indexOf('Dividende présent') !== -1 && divBas.indexOf('Dividende élevé') === -1, '3 % présent');
attend(divFaible.indexOf('Dividende élevé') === -1 && divFaible.indexOf('Dividende présent') === -1, '2,9 % rien');

attend(col(59.6).indexOf('green') !== -1 && bcls(59.6) === 'bg', 'arrondi 7,5 vert');
attend(col(59.2).indexOf('amber') !== -1 && bcls(59.2) === 'ba', '7,4 ambre');
attend(classeNote(7.45) === 'ba', 'sans arrondi 7,45 reste ambre');

const palier = _palierScoreLive(7.3);
attend(palier.tier === 'Modéré' && palier.col.indexOf('amber') !== -1, 'score live 7,3 reste sur la note');
attend(_palierScoreLive(5.1).tier === 'Modéré', 'score live 5,1');
attend(_palierScoreLive(4.9).tier === 'Très faible', 'score live 4,9');
attend(_palierScoreLive(6.8, 'suspendu').col.indexOf('--note-muted') !== -1, 'score live suspendu gris');
attend(etit.indexOf('color:var(--note-green)') !== -1 && etit.indexOf('Intéressant') !== -1, 'mot ETIT');
attend(sogc.indexOf('color:var(--note-amber)') !== -1 && sogc.indexOf('À surveiller') !== -1, 'mot SOGC');
attend(ttls.indexOf('color:var(--note-red)') !== -1 && ttls.indexOf('Prudence') !== -1, 'mot TTLS');
attend(orac.indexOf('color:var(--note-red)') !== -1 && orac.indexOf('Prudence') !== -1, 'mot ORAC');
attend(sicc.indexOf('color:var(--note-muted)') !== -1 && sicc.indexOf('Cotation suspendue') !== -1, 'mot SICC');
"""
    _node(script)
