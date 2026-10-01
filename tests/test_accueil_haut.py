# -*- coding: utf-8 -*-
"""Haut de l'accueil : héros, indice, chiffres. Aucun cours inventé."""
import re
import shutil
import subprocess
from html.parser import HTMLParser
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


class _TexteVisible(HTMLParser):
    """Texte rendu : ignore les sous-arbres hidden, script et style."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._pile = []
        self._muet = 0
        self.morceaux = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._muet += 1
        cache = any(nom == "hidden" for nom, _valeur in attrs)
        parent = self._pile[-1] if self._pile else False
        self._pile.append(parent or cache)

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._muet:
            self._muet -= 1
        if self._pile:
            self._pile.pop()

    def handle_data(self, data):
        if self._muet or (self._pile and self._pile[-1]):
            return
        self.morceaux.append(data)


def _texte_visible(html):
    parseur = _TexteVisible()
    parseur.feed(html)
    return " ".join(" ".join(parseur.morceaux).split())


def _balise(html, identifiant):
    motif = r'<[^>]*\bid="%s"[^>]*>' % re.escape(identifiant)
    trouve = re.search(motif, html)
    assert trouve, identifiant
    return trouve.group(0)


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


def test_courbe_exemple_masquee_sous_vingt_seances():
    carte = _entre(PAGE, '<article class="accueil-composite"', "</article>")
    visible = _texte_visible(carte)
    assert "BRVM Composite" in visible
    assert "EXEMPLE" not in visible.upper()
    assert "Courbe illustrative" not in visible
    assert "exemple" not in visible.lower()
    for onglet in ("1S", "1M", "YTD", "1A"):
        assert onglet not in visible
    assert "hidden" in _balise(carte, "accueil-courbe")
    assert "hidden" in _balise(carte, "accueil-periodes")
    assert "accueil-composite-val" in carte
    assert "accueil-composite-badge" in carte
    assert "accueil-composite-seance" in carte
    assert "accueil-composite-etat" in carte
    assert ".accueil-courbe-zone[hidden]" in CSS
    assert ".accueil-periodes[hidden]{display:none!important}" in CSS
    assert "align-self:start" in CSS.split(".accueil-composite{")[1].split("}")[0]
    assert "var SEUIL_SEANCES_COURBE = 20;" in JS
    chargeur = JS[JS.index("function _chargerCourbeComposite"):JS.index("function _remplirMontants")]
    assert "/api/index-history" not in chargeur
    assert "fetch(" not in chargeur
    assert "_seancesIndiceConnues() < SEUIL_SEANCES_COURBE" in chargeur
    assert "_masquerCourbeComposite()" in chargeur


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_seuil_vingt_seances_masque_sans_requete():
    debut = JS.index("var SEUIL_SEANCES_COURBE")
    fin = JS.index("function _remplirMontants")
    _node(r"""
function attend(cond, msg) {
  if (!cond) { console.error(msg); process.exit(1); }
}
var window = {};
var fetches = [];
function fetch(url) {
  fetches.push(String(url));
  return Promise.reject(new Error('fetch interdit'));
}
function noeud(id) {
  return { id: id, hidden: false };
}
var nodes = {
  'accueil-courbe': noeud('accueil-courbe'),
  'accueil-periodes': noeud('accueil-periodes')
};
var document = {
  getElementById: function(id) { return nodes[id] || null; }
};
""" + JS[debut:fin] + r"""
function repart() {
  nodes['accueil-courbe'].hidden = false;
  nodes['accueil-periodes'].hidden = false;
  fetches.length = 0;
}
attend(SEUIL_SEANCES_COURBE === 20, 'seuil');
attend(_seancesIndiceConnues() === 0, 'absent');
window.BRVM_INDEX_HISTORY = true;
attend(_seancesIndiceConnues() === 0, 'booleen');
window.BRVM_INDEX_HISTORY = 19;
attend(_seancesIndiceConnues() === 19, 'nombre 19');
window.BRVM_INDEX_HISTORY = { points: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19] };
attend(_seancesIndiceConnues() === 19, 'points 19');
repart();
_chargerCourbeComposite();
attend(nodes['accueil-courbe'].hidden === true, 'courbe 19');
attend(nodes['accueil-periodes'].hidden === true, 'onglets 19');
attend(fetches.length === 0, 'fetch 19');
window.BRVM_INDEX_HISTORY = { series: new Array(20) };
attend(_seancesIndiceConnues() === 20, 'series 20');
repart();
_chargerCourbeComposite();
attend(nodes['accueil-courbe'].hidden === true, 'courbe 20 encore masquee');
attend(nodes['accueil-periodes'].hidden === true, 'onglets 20');
attend(fetches.length === 0, 'fetch 20');
window.BRVM_INDEX_HISTORY = undefined;
repart();
_chargerCourbeComposite();
attend(nodes['accueil-courbe'].hidden === true && fetches.length === 0, 'defaut');
""")


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
