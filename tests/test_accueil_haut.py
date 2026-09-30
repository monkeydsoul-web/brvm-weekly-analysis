# -*- coding: utf-8 -*-
"""Haut de l'accueil : héros, indice, chiffres. Aucun cours inventé."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "welcome_v2.js").read_text(encoding="utf-8")
CSS = (ROOT / "dashboard" / "css" / "accueil.css").read_text(encoding="utf-8")


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
    return resultat.stdout


def _fonctions():
    debut = JS.index("function _nombreAccueil")
    fin = JS.index("function _comptesConseil")
    return JS[debut:fin]


def test_hero_textes_et_ancrage_glossaire():
    haut = _entre(PAGE, 'id="accueil"', 'id="accueil-cartes"')
    assert "BOURSE RÉGIONALE UEMOA" in haut
    assert "Comprendre la BRVM, une note sur 10 à la fois." in haut
    assert "sociétés notées avec 8 modèles de valorisation publics." in haut
    assert "Une méthode transparente pour les investisseurs débutants — pas un conseil en investissement." in haut
    assert "Voir le classement →" in haut
    assert "Comment investir ?" in haut
    assert "allerCommentInvestir()" in haut
    assert 'id="glossaire-investir"' in PAGE
    assert "Comment investir concrètement ?" in PAGE
    assert "540,78" not in haut
    assert "9,15" not in haut
    assert "1,70" not in haut
    assert re.search(r"\b47 sociétés notées", haut) is None


def test_courbe_illustrative_et_onglets_desactives():
    haut = _entre(PAGE, 'id="accueil-composite-titre"', 'id="accueil-chiffres"')
    assert "Courbe illustrative · EXEMPLE · valeur et variation réelles" in haut
    assert 'data-accroche="index-history"' in haut
    assert haut.count("disabled") >= 4
    assert "1S" in haut and "1M" in haut and "YTD" in haut and "1A" in haut
    assert "function _accueilHistoriqueIndice" in JS
    assert "/api/index-history" in JS


def test_quatre_chiffres_et_compteurs_compacts():
    assert "BRVM-30" in PAGE
    assert "Hausses / Baisses" in PAGE
    assert "Valeur échangée" in PAGE
    assert "Capitalisation actions" in PAGE
    assert 'id="accueil-cartes"' in PAGE
    assert "Intéressant" in JS and "À surveiller" in JS and "Prudence" in JS
    assert ".accueil-carte-s{display:none}" in CSS
    assert "grid-template-columns:1fr 1fr" in CSS
    assert "repeat(4,minmax(0,1fr))" in CSS


def test_actions_masquees_seulement_sur_accueil():
    assert "body:has(#page-welcome.on) .sb{display:none!important}" in CSS
    assert ".sb{display:none" not in CSS.split("page-welcome")[0]


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_montants_points_et_largeur_viennent_des_donnees():
    _node(_fonctions() + r"""
function attend(cond, msg) {
  if (!cond) { console.error(msg); process.exit(1); }
}
function plat(s) { return String(s).replace(/\u202f|\u00a0/g, ' '); }

attend(_montantVersMd('10 234 567 890 123') === 10234.567890123, 'cap fcfa');
attend(plat(_mdFcfa(_montantVersMd('10 234 567 890 123'))) === '10 234,57 Md FCFA', plat(_mdFcfa(_montantVersMd('10 234 567 890 123'))));
attend(plat(_mdFcfa(_montantVersMd('1 250 000 000'))) === '1,25 Md FCFA', 'echange');
attend(plat(_mdFcfa(_montantVersMd('850 millions'))) === '0,85 Md FCFA', 'millions');
attend(plat(_mdFcfa(_montantVersMd('12,5 milliards'))) === '12,50 Md FCFA', 'milliards');
attend(plat(_mdFcfa(_montantVersMd('1 234,56 Md FCFA'))) === '1 234,56 Md FCFA', 'deja md');
attend(_montantVersMd('—') === null, 'tiret');
attend(_mdFcfa(null) === '—', 'md nul');

var act = {
  'Capitalisation globale': '999',
  'Capitalisation Obligations': '111',
  'Capitalisation Actions': '10 234 567 890 123',
  'Valeur transigée Obligations': '5',
  'Valeur transigée': '1 250 000 000',
  'Valeur échangée Actions': '2 000 000 000'
};
attend(_choisirTexteActivite(act, 'cap') === '10 234 567 890 123', 'cle cap');
attend(_choisirTexteActivite(act, 'echange') === '2 000 000 000', 'cle echange actions');
attend(_choisirTexteActivite({}, 'cap') === '', 'cap absente');

var ligne = _ligneSeanceIndice({ current: 540.78, prev: 531.63, change: 1.72, ytd: 1.7 });
attend(plat(ligne) === '+9,15 pts sur la séance · YTD +1,70 %', JSON.stringify(ligne));
attend(_ligneSeanceIndice(null) === '—', 'seance vide');
attend(_ligneSeanceIndice({ current: 10 }) === '—', 'sans veille ni ytd');

var largeur = _compterLargeur({
  A: { price: 10, change_pct: 1.2 },
  B: { price: 10, change_pct: -0.4 },
  C: { price: 10, change_pct: 0 },
  D: { price: null, change_pct: 0 },
  E: { change_pct: 3 }
});
attend(largeur.hausses === 1 && largeur.baisses === 1 && largeur.stables === 1 && largeur.total === 3, JSON.stringify(largeur));

attend(_pointsHistorique(null) === null, 'hist nul');
attend(_pointsHistorique({ series: [1] }) === null, 'un seul point');
var pts = _pointsHistorique({ points: [{ v: 10 }, { value: 12 }, 11] });
attend(pts && pts.length === 3 && pts[0] === 10 && pts[1] === 12 && pts[2] === 11, JSON.stringify(pts));
var chemin = _cheminCourbe([10, 12, 11]);
attend(chemin.indexOf('M') === 0 && chemin.indexOf('L') > 0, chemin);
""")
