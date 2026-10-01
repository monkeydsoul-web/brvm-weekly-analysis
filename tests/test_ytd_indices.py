# -*- coding: utf-8 -*-
"""YTD des indices : clôture du 31/12/2025, pas la colonne figée de brvm.org."""
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ["BRVM_DISABLE_SCHEDULER"] = "1"

import market_data


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "data" / "indices_reference_2025.json"
SOURCE_BOC_249 = "https://bfin.brvm.org/boc/BOC_JOUR/BOC_20251231.pdf"

# Variation annuelle du BOC n° 185 du 30/09/2026.
# Composite 548,38 / 345,75 − 1 = +58,61 %. BRVM 30 266,08 / 166,24 − 1 = +60,06 %.
_CAS = (
    ("BRVM - COMPOSITE", 548.38, 345.75, 58.61),
    ("BRVM-30", 266.08, 166.24, 60.06),
)


@pytest.fixture
def md():
    market_data._memoire = None
    market_data._en_cours = False
    market_data._dernier_essai = 0.0
    market_data._dernier_fil = None
    market_data._references_2025 = None
    if os.path.exists(market_data.CACHE_PATH):
        os.remove(market_data.CACHE_PATH)
    yield market_data
    fil = market_data._dernier_fil
    if fil is not None and fil.is_alive():
        fil.join(3)
    market_data._memoire = None
    market_data._en_cours = False
    market_data._dernier_essai = 0.0
    market_data._dernier_fil = None
    market_data._references_2025 = None
    if os.path.exists(market_data.CACHE_PATH):
        os.remove(market_data.CACHE_PATH)


def test_reference_boc_249():
    brut = json.loads(REFERENCE.read_text(encoding="utf-8"))
    assert brut["source"] == SOURCE_BOC_249
    assert brut["date"] == "2025-12-31"
    assert brut["closes"] == {
        "BRVM Composite": 345.75,
        "BRVM 30": 166.24,
        "Prestige": 144.25,
        "Principal": 217.65,
    }


def test_variation_annuelle_boc_185():
    """548,38 / 345,75 − 1 = +58,61 %, variation annuelle du BOC n° 185."""
    ratio = market_data.ytd_depuis_cloture(548.38, 345.75)
    assert ratio == pytest.approx(548.38 / 345.75 - 1)
    assert round(ratio * 100, 2) == 58.61


def test_deuxieme_valeur_brvm30_boc_185():
    ratio = market_data.ytd_depuis_cloture(266.08, 166.24)
    assert ratio == pytest.approx(266.08 / 166.24 - 1)
    assert round(ratio * 100, 2) == 60.06


def test_colonne_figee_ignoree_et_secteur_sans_reference():
    data = {
        "indices": [{
            "name": "BRVM - COMPOSITE",
            "current": 548.38,
            "ytd": 1.70,
        }],
        "sector_indices": [{
            "name": "BRVM - SERVICES FINANCIERS",
            "current": 247.54,
            "ytd": 0.56,
        }],
    }
    out = market_data.appliquer_ytd_reference(data)
    assert round(out["indices"][0]["ytd"] * 100, 2) == 58.61
    assert out["indices"][0]["ytd"] != 1.70
    assert out["sector_indices"][0]["ytd"] is None
    assert data["indices"][0]["ytd"] == 1.70


def test_api_market_calcule_deux_ytd(md, monkeypatch):
    maintenant = datetime(2026, 9, 30, 16, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(md, "_maintenant", lambda: maintenant)
    payload = {
        "updated_at": (maintenant - timedelta(seconds=10)).isoformat(),
        "market_activity": {},
        "top5": [],
        "flop5": [],
        "indices": [
            {"name": nom, "prev": 100.0, "current": cours, "change": 0.1, "ytd": 1.70}
            for nom, cours, _cloture, _pct in _CAS
        ],
        "sector_indices": [{
            "name": "BRVM - INDUSTRIELS",
            "prev": 222.90,
            "current": 219.19,
            "change": -1.66,
            "ytd": 0.12,
        }],
        "total_return": {},
    }
    md._ecrire(payload)
    md._memoire = None
    monkeypatch.setattr(md, "fetch_market_data", lambda: (_ for _ in ()).throw(AssertionError("scrape")))

    import app as application
    corps = application.app.test_client().get("/api/market").get_json()
    assert set(corps) == {
        "updated_at", "market_activity", "top5", "flop5",
        "indices", "sector_indices", "total_return",
    }
    recus = {item["name"]: item["ytd"] for item in corps["indices"]}
    for nom, cours, cloture, pct in _CAS:
        assert recus[nom] == pytest.approx(cours / cloture - 1)
        assert round(recus[nom] * 100, 2) == pct
        assert recus[nom] != 1.70
    assert corps["sector_indices"][0]["ytd"] is None


def test_aucun_ytd_fige_dans_les_sources():
    interdits = ("+1,7%", "YTD +1,70", "cols[4]")
    fichiers = (
        ROOT / "market_data.py",
        ROOT / "dashboard" / "index.html",
        ROOT / "dashboard" / "js" / "core.js",
        ROOT / "dashboard" / "welcome_v2.js",
    )
    for chemin in fichiers:
        texte = chemin.read_text(encoding="utf-8")
        for mot in interdits:
            assert mot not in texte, f"{mot} dans {chemin.name}"
    macro = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
    bloc = macro[macro.index("function renderMacroPage"):macro.index("let _anncCurrentTab")]
    assert "change_pct" not in bloc
    assert "avgChg" not in bloc
    assert "_texteMacroYtd" in bloc
    assert "demanderMarche(false)" in bloc
    assert "fetch('/api/market'" not in bloc


def _fonctions_accueil():
    js = (ROOT / "dashboard" / "welcome_v2.js").read_text(encoding="utf-8")
    debut = js.index("function _nombreAccueil")
    fin = js.index("function _comptesConseil")
    return js[debut:fin]


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_accueil_et_macro_affichent_le_calcul():
    script = _fonctions_accueil() + r"""
function attend(cond, msg) {
  if (!cond) { console.error(msg); process.exit(1); }
}
function plat(s) { return String(s).replace(/\u202f|\u00a0/g, ' '); }

var cas = [
  { cours: 548.38, cloture: 345.75, texte: '+58,61 %' },
  { cours: 266.08, cloture: 166.24, texte: '+60,06 %' }
];
cas.forEach(function(c) {
  var ratio = c.cours / c.cloture - 1;
  var home = plat(_ligneSeanceIndice({ current: c.cours, prev: c.cours - 1, change: 0, ytd: ratio }));
  var macro = plat(_texteMacroYtd({ indices: [{ name: 'BRVM - COMPOSITE', current: c.cours, ytd: ratio }] }));
  attend(home.indexOf('YTD ' + c.texte) >= 0, home + ' != ' + c.texte);
  attend(macro === c.texte, macro + ' != ' + c.texte);
  attend(home.indexOf(c.texte) >= 0 && macro === c.texte, 'accueil et macro');
});
attend(_texteMacroYtd({ indices: [{ name: 'BRVM - INDUSTRIELS', ytd: null }] }) === '—', 'secteur');
attend(_texteYtdIndice(null) === '—', 'ratio nul');
attend(plat(_ligneSeanceIndice({ current: 200, prev: 190, ytd: null })).indexOf('YTD —') >= 0, 'sans reference');
"""
    resultat = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultat.returncode == 0, resultat.stderr or resultat.stdout
