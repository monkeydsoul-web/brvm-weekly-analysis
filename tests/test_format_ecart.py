# -*- coding: utf-8 -*-
"""Affichage de l'écart au prix cible : virgule française, valeur inchangée."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _node(script):
    resultat = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultat.returncode == 0, resultat.stderr or resultat.stdout
    return resultat.stdout


def _fonction():
    source = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
    debut = source.index("function fmtEcartPct")
    fin = source.index("\n// ── Convertisseur", debut)
    return source[debut:fin]


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_fmt_ecart_pct_virgule_et_espace_insecable():
    """94,2 reste 94,2. Seuls la virgule, le signe et l'espace devant % changent."""
    _node(_fonction() + r"""
function attend(cond, msg) {
  if (!cond) { console.error(msg); process.exit(1); }
}
var plus = fmtEcartPct(94.2);
attend(plus === '+94,2\u00a0%', JSON.stringify(plus));
attend(fmtEcartPct(-75.2) === '-75,2\u00a0%', JSON.stringify(fmtEcartPct(-75.2)));
attend(fmtEcartPct(0) === '0,0\u00a0%', JSON.stringify(fmtEcartPct(0)));
attend(fmtEcartPct(162.8) === '+162,8\u00a0%', JSON.stringify(fmtEcartPct(162.8)));
attend(fmtEcartPct(null) === '\u2014', 'nul');
attend(fmtEcartPct(94.2).indexOf('.') === -1, 'pas de point');
""")


def test_toutes_les_vues_passent_par_fmt_ecart():
    core = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
    screener = (ROOT / "dashboard" / "screener.js").read_text(encoding="utf-8")
    alertes = (ROOT / "dashboard" / "alerts.js").read_text(encoding="utf-8")
    assert "function fmtEcartPct" in core
    assert "fmtEcartPct(up)" in core
    assert "fmtEcartPct(s.ecart_pct)" in core
    assert "fmtEcartPct(fi.upside_pct)" in core
    assert "up.toFixed(1)" not in core
    assert "fmtEcartPct(ecart)" in screener
    assert "ecart + '%'" not in screener
    assert "fmtEcartPct(s.ecart_pct)" in alertes
    assert "s.ecart_pct} %" not in alertes


def test_barre_live_suit_la_note_sur_10():
    live = (ROOT / "dashboard" / "live_score.js").read_text(encoding="utf-8")
    assert "sc/80" not in live
    assert "n10*10" in live
    assert "note10txt(d)" in live


def test_liste_laterale_vise_le_conteneur_reel():
    badges = (ROOT / "dashboard" / "badges.js").read_text(encoding="utf-8")
    assert "sidebarList" not in badges
    assert "function renderSidebarScores" in badges
    assert "loadSidebar()" in badges
