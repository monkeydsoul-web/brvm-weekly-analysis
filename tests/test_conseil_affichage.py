# -*- coding: utf-8 -*-
"""Affichage du conseil serveur (Classement, Par societe, fiche).

Execute les fonctions extraites de dashboard/index.html.
Le verdict PDF (fmtVerdict) et les filtres ne sont pas concernes.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

HTML = (Path(__file__).resolve().parents[1] / "dashboard" / "index.html").read_text(
    encoding="utf-8"
)


def _entre(debut, fin):
    i = HTML.index(debut)
    j = HTML.index(fin, i)
    return HTML[i:j]


def test_fmt_verdict_pdf_est_une_tendance():
    assert (
        "function fmtVerdict(v){return v==='POSITIF'?'Tendance positive'"
        ":v==='NEGATIF'?'Tendance négative':v==='NEUTRE'?'Tendance neutre':v||'—';}"
    ) in HTML


def test_colonnes_passent_la_ligne_entiere():
    assert HTML.count("${fmtConseil(x)}") == 2
    assert "${fmtConseil(x.conseil)}" not in HTML


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_conseil_affiche_serveur_et_repli():
    source = _entre("function conseilAffiche", "function showChangelog")
    source += _entre("function _genVerdict", "function _shareStockText")
    script = source + r"""
const document = { documentElement: { dataset: { mode: 'beginner' } } };
function attend(cond, msg) { if (!cond) { console.error(msg); process.exit(1); } }

const nouveau = conseilAffiche({
  conseil: 'Intéressant', conseil_libelle: 'Intéressant', conseil_couleur: 'vert'
});
attend(nouveau.texte === '✅ Intéressant', 'libelle serveur');
attend(nouveau.css === 'var(--green)', 'couleur vert');

const orange = conseilAffiche({
  conseil_libelle: 'Intéressant', conseil_couleur: 'orange'
});
attend(orange.texte === '✅ Intéressant' && orange.css === 'var(--amber)', 'couleur orange du serveur');

const prudence = conseilAffiche({
  conseil_libelle: 'Prudence', conseil_couleur: 'rouge'
});
attend(prudence.texte === '⚠️ Prudence' && prudence.css === 'var(--red)', 'prudence');

const milieu = conseilAffiche({
  conseil_libelle: 'À surveiller', conseil_couleur: 'orange'
});
attend(milieu.texte === '⏳ À surveiller' && milieu.css === 'var(--amber)', 'a surveiller');

attend(conseilAffiche({conseil:'acheter'}).texte === '✅ Intéressant', 'repli acheter');
attend(conseilAffiche('acheter').css === 'var(--green)', 'repli acheter couleur');
attend(conseilAffiche({conseil:'attendre'}).texte === '⏳ À surveiller', 'repli attendre');
attend(conseilAffiche({conseil:'eviter'}).css === 'var(--red)', 'repli eviter');

attend(conseilAffiche({conseil:null, conseil_libelle:null}) === null, 'sans conseil');
attend(conseilAffiche({}) === null, 'ligne vide');
const htmlVide = fmtConseil({conseil:null});
attend(htmlVide.indexOf('—') !== -1, 'tiret quarantaine');
attend(htmlVide.indexOf('Acheter') === -1, 'pas d ancien mot');

const html = fmtConseil({conseil:'acheter'});
attend(html.indexOf('Intéressant') !== -1, 'fmtConseil repli');
attend(html.indexOf('var(--green)') !== -1, 'fmtConseil couleur');
attend(html.indexOf('Acheter') === -1, 'fmtConseil sans Acheter');

const fiche = _genVerdict({ticker:'ALPH', composite_adj:70, conseil:'eviter'});
attend(fiche.indexOf('⚠️ Prudence') !== -1, 'fiche repli eviter');
attend(fiche.indexOf('✅ Acheter') === -1, 'fiche ne derive pas du score brut');

const ficheServeur = _genVerdict({
  ticker:'ALPH', composite_adj:30,
  conseil_libelle:'À surveiller', conseil_couleur:'orange'
});
attend(ficheServeur.indexOf('⏳ À surveiller') !== -1, 'fiche libelle serveur');
attend(ficheServeur.indexOf('var(--amber)') !== -1, 'fiche couleur serveur');

const ficheVide = _genVerdict({ticker:'ALPH', composite_adj:70});
attend(ficheVide.indexOf('>—</span>') !== -1 || ficheVide.indexOf('>—<') !== -1, 'fiche sans conseil');
attend(ficheVide.indexOf('Acheter') === -1, 'fiche vide sans Acheter');
"""
    resultat = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultat.returncode == 0, resultat.stderr or resultat.stdout
