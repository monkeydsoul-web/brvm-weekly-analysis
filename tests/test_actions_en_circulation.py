# -*- coding: utf-8 -*-
"""Nombre d'actions en circulation — NTLC, SOGC, PALC, CIEC, ORAC, SDCC.

Valeurs officielles retenues (septembre 2026). Le calcul du BNA n'est pas
modifié : ces tests vérifient seulement le nombre d'actions.

NTLC — 22 070 400
  États financiers 2024 sur brvm.org : capital 5 517 600 000 FCFA, inchangé
  depuis 2023. Fiche BRVM : 1 103 520 actions au 31/12/2015. Fractionnement
  du 8 septembre 2017, 20 actions nouvelles pour 1 ancienne
  (1 103 520 × 20 = 22 070 400). Nominal 250 FCFA
  (5 517 600 000 / 250 = 22 070 400).

SOGC — 21 601 840
  États financiers 2024 sur brvm.org et avis d'AG du 20 mai 2025 : capital
  21 601 840 000 FCFA. Socfin (actionnaire de contrôle), au 31/12/2023 :
  21 601 840 actions, soit un nominal de 1 000 FCFA. Befin détient
  15 803 970 titres, soit 73,16 % de ce total.

PALC — 15 459 316
  Rapport annuel PALMCI 2025 : capital 20 406 297 120 FCFA « divisé en
  15 459 316 actions » au 31/12/2025. Même nombre dans le rapport annuel
  2023 publié sur brvm.org. Nominal 1 320 FCFA.

CIEC — 56 000 000
  Fiche émetteur BRVM : « Nombre total d'actions (au 31/12/2025) :
  56 000 000 ». Capital social 14 000 000 000 FCFA, nominal 250 FCFA.

ORAC — 150 655 350
  Rapport annuel intégré 2022 publié sur brvm.org : total de l'actionnariat
  150 655 350 actions. Capital 6 026 214 000 FCFA (nominal 40 FCFA),
  inchangé dans les états financiers 2025. Dividende brut 2025 :
  150 655 350 × 800 FCFA = 120 524 280 000 FCFA.

SDCC — 9 000 000
  Communiqué des états financiers 2025 sur brvm.org : dividende global de
  4,725 milliards FCFA, soit 525 FCFA brut par action
  (4 725 000 000 / 525 = 9 000 000). Capital 4 500 000 000 FCFA,
  nominal 500 FCFA. La fiche BRVM encore datée du 31/12/2015 (900 000)
  correspond à l'avant-division par 10.
"""
from pathlib import Path

from scraper import STOCK_FUNDAMENTALS

# Anciennes valeurs fausses, à ne plus retrouver pour ces sociétés.
_ANCIENNES = {
    "NTLC": 36_364_848,
    "SOGC": 15_000_000,
    "PALC": 11_021_655,
    "CIEC": 65_536_000,
    "ORAC": 141_174_476,
    "SDCC": 12_000_000,
}

# 15 000 000 et 12 000 000 et 9 000 000 existent aussi pour d'autres sociétés.
# On ne les change pas.
_INCHANGEES = {
    "BOAS": 15_000_000,
    "BOAM": 12_000_000,
    "BICC": 9_000_000,
}

OFFICIELLES = {
    "NTLC": 22_070_400,
    "SOGC": 21_601_840,
    "PALC": 15_459_316,
    "CIEC": 56_000_000,
    "ORAC": 150_655_350,
    "SDCC": 9_000_000,
}


def test_nombre_actions_officiel():
    assert len(STOCK_FUNDAMENTALS) == 47
    for ticker, attendu in OFFICIELLES.items():
        assert STOCK_FUNDAMENTALS[ticker]["shares"] == attendu


def test_anciennes_valeurs_retirees_pour_ces_societes():
    for ticker, ancienne in _ANCIENNES.items():
        assert STOCK_FUNDAMENTALS[ticker]["shares"] != ancienne


def test_autres_societes_au_meme_nombre_ne_bougent_pas():
    for ticker, attendu in _INCHANGEES.items():
        assert STOCK_FUNDAMENTALS[ticker]["shares"] == attendu


def test_pas_de_doublon_des_anciens_nombres_uniques():
    """Les anciens nombres qui n'appartenaient qu'à une société ont disparu."""
    texte = Path(__file__).resolve().parents[1].joinpath("scraper.py").read_text(encoding="utf-8")
    for ancien in (36_364_848, 11_021_655, 65_536_000, 141_174_476):
        assert str(ancien) not in texte
        assert f"{ancien:_}" not in texte
