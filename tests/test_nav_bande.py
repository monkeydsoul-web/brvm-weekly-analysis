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
