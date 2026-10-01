# -*- coding: utf-8 -*-
"""Bas de l'accueil : mieux notées, séance, débuter, pied de page."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "welcome_v2.js").read_text(encoding="utf-8")
CORE = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
CSS = (ROOT / "dashboard" / "css" / "accueil.css").read_text(encoding="utf-8")
APP = (ROOT / "dashboard" / "css" / "app.css").read_text(encoding="utf-8")


def _entre(source, debut, fin):
    i = source.index(debut)
    j = source.index(fin, i)
    return source[i:j]


def _accueil():
    i = HTML.index('<div class="accueil" id="accueil">')
    j = HTML.index("<!-- METHODOLOGIE -->", i)
    return HTML[i:j]


def test_blocs_du_bas_dans_l_ordre_sans_tableau():
    page = _accueil()
    assert "Top du moment" not in page
    assert "Écart cible" not in page
    titres = [
        "Les mieux notées",
        "Note /10 · méthode publiée · mise à jour après chaque séance",
        "Tout le classement →",
        "Séance du jour",
        "Heatmap complète →",
        "Débuter à la BRVM",
        "3 minutes pour comprendre l'essentiel",
        "La BRVM c'est quoi ?",
        "Ouvrir un compte via une SGI",
        "Lire une note sur 10",
        "Dernières actualités",
    ]
    places = [page.index(t) for t in titres]
    assert places == sorted(places)
    assert page.index('onclick="nav(\'glossaire\')"') < page.index('onclick="nav(\'methodo\')"')
    sgi = page[page.index("Ouvrir un compte via une SGI"):page.index("Lire une note sur 10")]
    assert "allerCommentInvestir" in sgi
    assert "nav('glossaire')" in sgi
    assert page.index("accueil-debuter-titre") < page.index("accueil-actus-titre")
    assert 'id="accueil-top"' in page
    assert "accueil-avertissement" not in page
    pied = HTML[HTML.index('<footer id="app-footer">'):HTML.index("</footer>")]
    assert "Pas un conseil en investissement" in pied
    assert 'onclick="showChangelog()"' in pied
    assert "Changelog" in pied
    assert "Acheter" not in page


def test_styles_carrousel_seance_et_pied_dans_le_flux():
    assert "scroll-snap-type:x mandatory" in CSS
    assert "repeat(4,minmax(0,1fr))" in CSS
    assert ".accueil-seance-grille" in CSS
    assert ".accueil-seance-ligne.is-inerte" in CSS
    assert ".app-footer-log" in APP
    assert ".accueil-lecons" in CSS
    assert "position:static" in APP[APP.index("/* ══ Footer"):APP.index("/* ══ Misc")]
    assert "position:fixed" not in APP[APP.rindex("@media(min-width:769px)"):]


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_quatre_cartes_par_note_et_conseil_existant():
    source = _entre(CORE, "function note10num", "function rapportAnnuelTxt")
    source += _entre(CORE, "function _baseXof", "function toggleMobMenu")
    source += _entre(CORE, "function conseilAffiche", "function showChangelog")
    source += JS
    script = source + r"""
function attend(cond, msg) { if (!cond) { console.error(msg); process.exit(1); } }
var XOF_PAR_EUR = 655.957;
global.window = { _currency: 'XOF', _xofParUsd: null, _rates: { EUR: null, USD: null } };
const rows = [
  { ticker: 'BAS', name: 'Bas Societe', sector: 'Banque', note10: 4.2, price: 1000, change_pct: -1.5, rank: 30,
    conseil: 'eviter', conseil_libelle: 'Prudence', conseil_couleur: 'rouge', statut: 'cote' },
  { ticker: 'SNTS', name: 'Sonatel Senegal', sector: 'Télécoms', note10: 7.3, price: 44995, change_pct: 4.65, rank: 3,
    conseil: 'attendre', conseil_libelle: 'À surveiller', conseil_couleur: 'orange', statut: 'cote' },
  { ticker: 'ETIT', name: 'Ecobank Transnational', sector: 'Banque', note10: 7.3, price: 20, change_pct: 0, rank: 9,
    conseil: 'acheter', conseil_libelle: 'Intéressant', conseil_couleur: 'vert', statut: 'cote' },
  { ticker: 'SMBC', name: 'SMB CI', sector: 'Industriel', note10: 8.4, price: 16500, change_pct: 0, rank: 20,
    conseil: 'Intéressant', conseil_libelle: 'Intéressant', conseil_couleur: 'vert', statut: 'cote' },
  { ticker: 'BICC', name: 'BICI CI', sector: 'Banque', note10: 7.7, price: 32510, change_pct: -6.83, rank: 15,
    conseil: 'Intéressant', conseil_libelle: 'Intéressant', conseil_couleur: 'vert', statut: 'cote' },
  { ticker: 'SICC', name: 'Sicor CI', sector: 'Industriel', note10: 9.1, price: 100, change_pct: 1,
    conseil: 'Intéressant', conseil_libelle: 'Intéressant', conseil_couleur: 'vert', statut: 'suspendu' },
  { ticker: 'ORGT', name: 'Oragroup Togo', sector: 'Banque', note10: 6.6, price: 500, change_pct: 0.2,
    conseil: 'À surveiller', conseil_libelle: 'À surveiller', conseil_couleur: 'orange', statut: 'cote' }
];
window.scores = rows;
const top = _mieuxNotees(rows).map(function(x){ return x.ticker; });
attend(top.join(',') === 'SMBC,BICC,SNTS,ETIT', 'note puis rang ' + top.join(','));
const html = top.map(function(t){ return _htmlCarteNote(rows.filter(function(x){ return x.ticker===t; })[0]); }).join('\n');
attend(html.indexOf('Acheter') === -1, 'pas le mot interdit');
attend(html.indexOf('>Intéressant<') !== -1, 'badge interessant');
attend(html.indexOf('>À surveiller<') !== -1, 'badge a surveiller');
attend(html.indexOf('SICC') === -1, 'suspendu hors des quatre');
attend(html.indexOf('accueil-anneau is-interessant') !== -1, 'anneau vert');
const snts = _htmlCarteNote(rows[1]);
attend(snts.indexOf('accueil-anneau is-surveiller') !== -1, 'anneau selon le conseil');
attend(snts.indexOf('Sonatel Senegal · Télécoms') !== -1, 'nom et secteur');
attend(snts.indexOf('XOF') !== -1, 'cours en XOF');
attend(snts.indexOf('FCFA') === -1, 'pas de FCFA en dur');
attend(snts.indexOf('SS') !== -1, 'initiales');
attend(snts.indexOf('<img') === -1, 'pas de logo');
const etit = _htmlCarteNote(rows[2]);
attend(etit.indexOf('>Intéressant<') !== -1, 'repli acheter vers interessant');
attend(etit.indexOf('Acheter') === -1, 'repli sans ancien mot');
const seance = {
  updated_at: '2026-09-30T10:48:51+00:00',
  top5: [
    { ticker: 'BBGC', price: 9675, change: 7.5 },
    { ticker: 'SNTS', price: 44995, change: 4.65 },
    { ticker: 'NSBC', price: 22500, change: 4.65 },
    { ticker: 'BICB', price: 8940, change: 4.44 },
    { ticker: 'BOAB', price: 9800, change: 4.26 },
    { ticker: 'XXXX', price: 1, change: 9 }
  ],
  flop5: [
    { ticker: 'BICC', price: 32510, change: -6.83 },
    { ticker: 'SIVC', price: 2005, change: -6.31 }
  ]
};
attend(_sousTitreSeance(seance) === 'Plus fortes variations', 'updated_at ignore');
attend(_sousTitreSeance({ session_date: '2026-09-29', updated_at: seance.updated_at }) === 'Plus fortes variations · 29 septembre 2026', 'session_date marche');
attend(_sousTitreSeance({ updated_at: seance.updated_at }, { session_date: '2026-09-28' }) === 'Plus fortes variations · 28 septembre 2026', 'session_date statut');
attend(_sousTitreSeance(null, { updated_at: seance.updated_at, market_open: false }) === 'Plus fortes variations', 'statut sans session_date');
const colH = _htmlColonneSeance('▲ Hausses', 'is-up', seance.top5);
const colB = _htmlColonneSeance('▼ Baisses', 'is-down', seance.flop5);
attend((colH.match(/accueil-seance-ligne/g) || []).length === 5, 'cinq hausses');
attend(colH.indexOf('XXXX') === -1, 'sixieme ignoree');
attend(colH.replace(/\s/g, '').indexOf('9675') !== -1, 'cours hausse');
attend(colH.indexOf('XOF') !== -1, 'seance en XOF');
attend(colH.indexOf('FCFA') === -1, 'seance sans FCFA');
attend(colH.indexOf('+7,50') !== -1, 'variation hausse');
attend(colH.indexOf('data-ticker="BBGC"') === -1, 'bggc sans lien');
attend(colH.indexOf('is-inerte') !== -1, 'ligne hors classement inerte');
attend(colH.indexOf('<button type="button" class="accueil-seance-ligne" data-ticker="SNTS">') !== -1, 'snts cliquable');
attend((colB.match(/accueil-seance-ligne/g) || []).length === 2, 'baisses presentes');
attend(colB.indexOf('is-down') !== -1, 'etiquette baisse');
attend(colB.indexOf('data-ticker="BICC"') !== -1, 'bicc cliquable');
attend(colB.indexOf('data-ticker="SIVC"') === -1, 'sivc hors classement');
attend(_sousTitreSeance(null) === 'Plus fortes variations', 'sans date inventee');
window._currency = 'EUR';
const eur = _fmtCours(65596);
attend(eur.indexOf('€') !== -1, 'suit EUR ' + eur);
attend(eur.indexOf('FCFA') === -1 && eur.indexOf('XOF') === -1, 'EUR sans XOF');
window._currency = 'XOF';
attend(_htmlCarteNote({ ticker: 'VIDE', name: 'Sans', sector: 'Banque', note10: 1, price: null, change_pct: null }).indexOf('—') !== -1, 'cours absent');
"""
    resultat = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
    assert resultat.returncode == 0, resultat.stderr or resultat.stdout
