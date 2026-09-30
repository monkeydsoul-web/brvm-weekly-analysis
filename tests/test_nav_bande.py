# -*- coding: utf-8 -*-
"""Bande de séance : la date affichée vient de /api/status, sans date inventée."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORE = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")


def _fonction():
    debut = CORE.index("function _seanceDepuisStatut")
    fin = CORE.index("\nfunction ", debut + 1)
    return CORE[debut:fin]


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_seance_reelle_depuis_horodatage_statut():
    script = _fonction() + """
    var cas = [
      ['2026-09-26T12:00:00Z', 'ven. 25/09/2026'],
      ['2026-09-25T16:00:00Z', 'ven. 25/09/2026'],
      ['2026-09-28T08:00:00Z', 'ven. 25/09/2026'],
      ['2026-09-30T10:38:00Z', 'mer. 30/09/2026'],
      ['2026-09-30T16:00:00Z', 'mer. 30/09/2026'],
      ['', '']
    ];
    cas.forEach(function(c) {
      var got = _seanceDepuisStatut(c[0]);
      if (got !== c[1]) {
        console.error(c[0] + ' -> ' + got + ' attendu ' + c[1]);
        process.exit(1);
      }
    });
    """
    resultat = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
    assert resultat.returncode == 0, resultat.stderr or resultat.stdout


def test_bande_mobile_ne_comprime_pas_les_pastilles():
    css = (ROOT / "dashboard" / "css" / "app.css").read_text(encoding="utf-8")
    bloc = css[css.index("@media(max-width:768px)"):]
    assert ".index-chips,#index-fx{flex-shrink:0;min-width:auto}" in bloc
    assert "width:24px" in bloc
    assert ".index-band.fondu-gauche::before" in bloc
    assert ".index-band.fondu-droite::after" in bloc
    assert "function _syncFonduBande()" in CORE


def test_echap_ferme_plus_et_apprendre_apres_la_recherche():
    assert "closeGSearch();return;" in CORE
    assert "if(e.key==='Escape' && _fermerMenusEchap(e)) return;" in CORE
    assert CORE.index("closeGSearch();return;") < CORE.index("_fermerMenusEchap(e)")
    assert "function _fermerMenusEchap(e)" in CORE
    assert "topnav-apprendre-btn" in CORE
    assert '#tabbar [data-nav="apprendre"]' in CORE


def test_screener_dans_le_menu_apprendre_mobile():
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    bloc = html[html.index('<div id="tab-plus"'):html.index("<!-- LOADJS-1")]
    assert 'data-nav="screener"' in bloc
    assert ">Screener</button>" in bloc
