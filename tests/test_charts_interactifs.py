# -*- coding: utf-8 -*-
"""CHARTS-1 : périodes couvertes par les séances réelles, sans point inventé."""
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "dashboard" / "js" / "charts_interactifs.js").read_text(encoding="utf-8")
PAGE = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
CORE = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
STOCK = (ROOT / "dashboard" / "stock_chart.js").read_text(encoding="utf-8")
ACCUEIL = (ROOT / "dashboard" / "welcome_v2.js").read_text(encoding="utf-8")


def test_branchements_fiche_et_marche_seulement():
    assert 'src="/js/charts_interactifs.js?v={{ASSET_V}}"' in PAGE
    assert PAGE.index('src="/stock_chart.js?v={{ASSET_V}}"') < PAGE.index('src="/js/charts_interactifs.js?v={{ASSET_V}}"')
    assert 'hote.addEventListener("pointerdown"' in JS
    assert 'addEventListener("brvm:zoom"' in JS
    assert "periodeDuVisible" in JS
    assert "precedente(container, labels, prices, ticker)" in JS
    assert "function drawPriceChart" in STOCK
    assert "peindreAppel" in STOCK
    assert 'data-ci-indice="BRVM-C"' in PAGE
    assert 'data-ci-indice="BRVM-30"' in PAGE
    assert 'id="mkt-courbe-brvm-c"' in PAGE
    assert 'id="mkt-courbe-brvm-30"' in PAGE
    assert CORE.count('if (typeof brancherCourbesMarche === "function") brancherCourbesMarche();') == 1
    assert "chargerCourbeSociete" in STOCK
    assert "onmouseleave" not in STOCK
    assert "onmousemove" not in STOCK
    assert "accueil-courbe" not in JS
    assert "openBacktest" not in JS
    assert "/api/index-history" in JS
    assert "/api/price-history" in JS
    assert "price-history-extended" not in JS
    assert 'SEUIL_COURS_FIABLE = "2026-05-19"' in JS
    assert "openCompareModal" not in JS
    assert "var SEUIL_SEANCES_COURBE = 20;" in ACCUEIL
    chargeur = ACCUEIL[ACCUEIL.index("function _chargerCourbeComposite"):ACCUEIL.index("function _remplirMontants")]
    assert "/api/index-history" not in chargeur


@pytest.mark.skipif(subprocess.call(["node", "-e", "0"]) != 0, reason="node absent")
def test_periodes_sans_extrapolation():
    script = JS + r"""
function attend(cond, msg) {
  if (!cond) { console.error(msg); process.exit(1); }
}
attend(decalerMoisIso('2026-10-02', -1) === '2026-09-02', '1 mois');
attend(decalerMoisIso('2026-10-02', -3) === '2026-07-02', '3 mois');
attend(decalerMoisIso('2026-10-02', -6) === '2026-04-02', '6 mois');
attend(decalerMoisIso('2026-10-02', -12) === '2025-10-02', '1 an');
attend(decalerMoisIso('2026-03-31', -1) === '2026-02-28', 'fin fevrier');
attend(decalerMoisIso('2026-01-15', -1) === '2025-12-15', 'janvier');

var serie = [
  { date: '2026-05-04', close: 100 },
  { date: '2026-05-10', close: 0 },
  { date: '2026-05-11', close: 101, source: 'synthetic' },
  { date: '2026-07-01', value: 110 },
  { date: '2026-09-03', price: 120 },
  { date: '2026-10-02', close: 130 }
];
var ids = periodesCouvertes(serie);
attend(ids.join(',') === '1M,3M,Tout', 'periodes ' + ids.join(','));
var unMois = filtrerPeriode(serie, '1M');
attend(unMois.length === 2, 'deux seances ' + unMois.length);
attend(unMois[0].date === '2026-09-03', 'pas de 2 septembre invente ' + unMois[0].date);
attend(unMois[1].date === '2026-10-02', 'fin');
var sources = {};
normaliserPoints(serie).forEach(function(p) { sources[p.date] = 1; });
unMois.forEach(function(p) { attend(sources[p.date] === 1, 'point hors serie ' + p.date); });
attend(normaliserPoints(serie).map(function(p){return p.date;}).join(',') === '2026-05-04,2026-07-01,2026-09-03,2026-10-02', 'filtre');
attend(periodesCouvertes([{ date: '2026-10-01', close: 10 }]).length === 0, 'une seance');
var court = periodesCouvertes([
  { date: '2026-09-03', close: 10 },
  { date: '2026-10-02', close: 11 }
]);
attend(court.join(',') === 'Tout', 'moins d un mois ' + court.join(','));
var pile = periodesCouvertes([
  { date: '2026-09-02', close: 10 },
  { date: '2026-10-02', close: 12 }
]);
attend(pile.join(',') === '1M,Tout', 'pile un mois ' + pile.join(','));
var paires = normaliserPoints([['2026-10-02', 210.5], ['2026-05-04', 200]]);
attend(paires.length === 2 && paires[0].date === '2026-05-04' && paires[1].value === 210.5, 'paires indice');
var doublon = normaliserPoints([
  { date: '2026-05-04', close: 1 },
  { date: '2026-05-04', close: 4 },
  { date: '2026-05-05', close: 5 }
]);
attend(doublon.length === 2 && doublon[0].value === 4, 'doublon');
var tout = filtrerPeriode(serie, 'Tout');
attend(tout.length === 4, 'tout garde les seances reelles');
var unMois = filtrerPeriode(serie, '1M');
attend(periodeDuVisible(serie, serie, 'Tout') === 'Tout', 'tout visible');
attend(periodeDuVisible(serie, unMois, '1M') === '1M', '1M choisi');
attend(periodeDuVisible(serie, unMois, 'Tout') === '1M', 'zoom pile sur 1M');
var custom = serieZoom(serie, 0, 1);
attend(custom.length === 2 && custom[0].date === '2026-05-04', 'fenetre zoom');
attend(periodeDuVisible(serie, custom, 'Tout') === '', 'zoom libre ' + periodeDuVisible(serie, custom, 'Tout'));
attend(periodeDuVisible(serie, unMois, '3M') === '3M', '3M garde le choix si meme fenetre');
attend(unitesEtiquette(346) * 346 / 640 >= 10, '10 px a 346');
attend(unitesEtiquette(0) * 346 / 640 >= 10, 'repli mobile');
attend(unitesEtiquette(900) === 11, 'ecran large');
var brut = [
  { date: '2025-06-03', close: 16000 },
  { date: '2026-05-18', price: 15050 },
  { date: '2026-05-20', price: 15790 },
  { date: '2026-10-02', close: 20605 }
];
var fiable = pointsFiables(brut);
attend(fiable.length === 2, 'deux seances fiables ' + fiable.length);
attend(fiable[0].date === '2026-05-20' && fiable[0].value === 15790, 'premier fiable');
attend(fiable[1].date === '2026-10-02' && fiable[1].value === 20605, 'dernier fiable');
attend(fiable.every(function(p) { return p.date >= '2026-05-19'; }), 'rien avant le 19 mai');
var couvert = periodesCouvertes(fiable);
attend(couvert.join(',') === 'Tout', 'moins de trois mois ' + couvert.join(','));
var longFiable = pointsFiables(serie);
attend(longFiable[0].date === '2026-07-01', 'mai retire ' + longFiable[0].date);
attend(periodesCouvertes(longFiable).join(',') === '1M,3M,Tout', 'periodes sur serie fiable ' + periodesCouvertes(longFiable).join(','));
"""
    resultat = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
    assert resultat.returncode == 0, resultat.stderr or resultat.stdout
