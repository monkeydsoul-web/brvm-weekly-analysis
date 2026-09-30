# -*- coding: utf-8 -*-
"""Finitions d'interface : libellé du menu Plus, fondu des indices, Échap."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_menu_plus_mobile_dit_methode():
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    bloc = html[html.index('<div id="tab-plus"'):html.index("<!-- LOADJS-1")]
    assert ">Méthode</button>" in bloc
    assert "Méthodologie" not in bloc
    barre = html[html.index('id="topnav-links"'):html.index('id="topnav-more"')]
    assert ">Méthode</button>" in barre


def test_fondu_indices_accessible():
    css = (ROOT / "dashboard" / "css" / "accueil.css").read_text(encoding="utf-8")
    assert ".accueil-indices-cadre.fondu-droite:not(.fondu-gauche) .accueil-indices" in css
    assert ".accueil-indices-cadre.fondu-gauche:not(.fondu-droite) .accueil-indices" in css
    assert ".accueil-indices-cadre.fondu-gauche.fondu-droite .accueil-indices" in css
    assert "mask-image:linear-gradient" in css
    js = (ROOT / "dashboard" / "welcome_v2.js").read_text(encoding="utf-8")
    assert "Faites défiler horizontalement pour voir tous les indices." in js
    assert "box.tabIndex = 0" in js
    assert "cadre.classList.toggle('fondu-gauche'" in js
    assert "cadre.classList.toggle('fondu-droite'" in js


def test_echap_ferme_le_menu_plus():
    js = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
    assert "if(e.key==='Escape' && _fermerPlusEchap(e)) return;" in js
    assert "function _fermerPlusEchap(e)" in js
    assert "_fermerPlusHaut();" in js
    assert "plus.classList.remove('open');" in js
