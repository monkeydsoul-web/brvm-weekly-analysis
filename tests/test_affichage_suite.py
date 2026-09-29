# -*- coding: utf-8 -*-
"""Affichage seulement : fiche SICOR, paliers du score live, glossaire, tris.

Aucune note ni aucun conseil du serveur n'est recalculé.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")


def _node(script):
    resultat = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultat.returncode == 0, resultat.stderr or resultat.stdout


def test_fiche_sicc_decrit_sicor_et_ecrase_sicable(data_dir):
    fiche = json.loads((ROOT / "stories" / "sicc.json").read_text(encoding="utf-8"))
    texte = json.dumps(fiche, ensure_ascii=False).lower()
    assert "sicor" in texte
    assert "coco" in texte
    assert "coprah" in texte
    assert "tourteau" in texte
    assert "sicable" not in texte
    assert "câble" not in texte
    assert "cable" not in texte
    assert fiche["sources"]
    assert any("brvm.org" in s for s in fiche["sources"])

    mauvais = {
        "stories": {
            "SICC": {
                "en_bref": "SICABLE fabrique des câbles électriques.",
                "points_forts": ["Câbles"],
                "points_attention": ["Cuivre"],
                "activites": ["Câbles électriques"],
                "presence": ["🇨🇮 Côte d'Ivoire"],
            },
            "CABC": {"en_bref": "Sicable fabrique des câbles."},
        }
    }
    chemin = Path(data_dir) / "companies_stories.json"
    chemin.write_text(json.dumps(mauvais), encoding="utf-8")

    import app as application

    reponse = application.app.test_client().get("/data/companies_stories.json")
    assert reponse.status_code == 200
    stories = reponse.get_json()["stories"]
    sicc = json.dumps(stories["SICC"], ensure_ascii=False).lower()
    assert "coco" in sicc
    assert "sicable" not in sicc
    assert "câble" not in sicc
    assert "sicable" in stories["CABC"]["en_bref"].lower()


def test_glossaire_exemple_fictif():
    assert "SIBC 8,5/10" not in HTML
    assert "Exemple fictif" in HTML
    assert "« EXEMPLE »" in HTML


def test_screener_trie_comme_le_classement():
    screener = (ROOT / "dashboard" / "screener.js").read_text(encoding="utf-8")
    assert "triCommeClassement" in screener
    assert "_scrSort.col === 'composite_adj'" in screener


def test_secours_badges_met_le_rang_1_devant():
    badges = (ROOT / "dashboard" / "badges.js").read_text(encoding="utf-8")
    assert "(a.rank||999)-(b.rank||999)" in badges
    assert "(b.rank||999)-(a.rank||999)" not in badges


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_tri_screener_et_secours_suivent_le_rang():
    tri = HTML[HTML.index("function triCommeClassement"):HTML.index("function rapportAnnuelTxt")]
    screener = (ROOT / "dashboard" / "screener.js").read_text(encoding="utf-8")
    fonction = screener[screener.index("function _triScreener"):screener.index("function screenerSortBy")]
    _node(tri + fonction + r"""
function attend(cond, msg) { if (!cond) { console.error(msg); process.exit(1); } }
const rows = [
  { ticker: 'SICC', composite_adj: 90, rank: 46 },
  { ticker: 'ALPH', composite_adj: 50, rank: 2 },
  { ticker: 'BRAV', composite_adj: 80, rank: 1 },
  { ticker: 'SEMC', composite_adj: 70, rank: 47 }
];
let _scrSort = { col: 'composite_adj', asc: false };
const ordre = rows.slice().sort(_triScreener).map(function(x){ return x.ticker; });
attend(ordre.join(',') === 'BRAV,ALPH,SICC,SEMC', ordre.join(','));
const secours = rows.slice().sort(function(a, b){ return (a.rank||999)-(b.rank||999); });
attend(secours.map(function(x){ return x.ticker; }).join(',') === 'BRAV,ALPH,SICC,SEMC', 'secours');
""")
