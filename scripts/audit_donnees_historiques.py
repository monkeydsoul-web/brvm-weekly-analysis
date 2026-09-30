#!/usr/bin/env python3
"""Audit local des P/E et P/B codés en dur. Ne modifie aucun calcul ni aucun cache.

Lit STOCK_FUNDAMENTALS dans scraper.py. Avec --ranking, rejoue la note du
classement et le contrefactuel où pe_hist / pb_hist deviendraient pe_ref / pb_ref.
Le classement live, lui, calcule pe_ref = cours / BNA et pb_ref = cours / BVPA.
"""

import argparse
import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _lire_constantes():
    """Le dictionnaire, sans importer scraper.py (évite le réseau et BeautifulSoup)."""
    source = (ROOT / "scraper.py").read_text(encoding="utf-8")
    marque = "STOCK_FUNDAMENTALS = "
    debut = source.index(marque)
    i = source.index("{", debut)
    profondeur = 0
    fin = None
    for j, car in enumerate(source[i:], i):
        if car == "{":
            profondeur += 1
        elif car == "}":
            profondeur -= 1
            if profondeur == 0:
                fin = j + 1
                break
    return ast.literal_eval(source[i:fin])


def _mediane(valeurs):
    xs = sorted(valeurs)
    n = len(xs)
    if n == 0:
        return None
    if n % 2:
        return xs[n // 2]
    return (xs[n // 2 - 1] + xs[n // 2]) / 2


def _generique(pe, pb):
    drapeaux = []
    if pe == 14:
        drapeaux.append("P/E 14")
    if pb == 2:
        drapeaux.append("P/B 2")
    return ", ".join(drapeaux) if drapeaux else "non"


def tableau_constantes(fonds):
    par_secteur = {}
    for fiche in fonds.values():
        par_secteur.setdefault(fiche["sector"], []).append(fiche)
    medianes = {}
    for secteur, lignes in par_secteur.items():
        medianes[secteur] = (
            _mediane([l["pe_hist"] for l in lignes]),
            _mediane([l["pb_hist"] for l in lignes]),
            len(lignes),
        )
    lignes = []
    for ticker, fiche in fonds.items():
        pe_med, pb_med, n = medianes[fiche["sector"]]
        lignes.append({
            "ticker": ticker,
            "nom": fiche["name"],
            "secteur": fiche["sector"],
            "pe_hist": fiche["pe_hist"],
            "pb_hist": fiche["pb_hist"],
            "generique": _generique(fiche["pe_hist"], fiche["pb_hist"]),
            "mediane_pe_secteur": pe_med,
            "mediane_pb_secteur": pb_med,
            "n_secteur": n,
            "source": "non documentée dans le dépôt",
        })
    return lignes, medianes


def _note_locale(row):
    """Même assemblage que live_ranker._compute_scores, technique déjà dans la ligne."""
    from valuation import (
        GEO_RISK_PENALTY,
        score_buffett,
        score_dcf,
        score_ddm,
        score_epv,
        score_graham,
        score_relative,
        score_reverse_dcf,
    )
    from verdict import note10

    r = dict(row)
    if r.get("pe_ref") is None:
        r.pop("pe_ref", None)
    if r.get("pb_ref") is None:
        r.pop("pb_ref", None)
    brut = (
        score_graham(r)["score"]
        + score_dcf(r)["score"]
        + score_ddm(r)["score"]
        + score_epv(r)["score"]
        + score_buffett(r)["score"]
        + score_reverse_dcf(r)["score"]
        + score_relative(r)["score"]
    )
    geo = GEO_RISK_PENALTY.get(r.get("country", ""), 0)
    fond = max(0, brut + geo * 7 / 10)
    technique = r.get("score_technique") or 0
    composite = round(min(80, fond + technique), 1)
    return composite, note10(composite)


def contrefactuel(fonds, ranking):
    """Si les constantes remplaçaient le P/E et le P/B de la note."""
    from verdict import conseil

    resultats = []
    for row in ranking:
        ticker = row["ticker"]
        fiche = fonds[ticker]
        actuel_composite, actuel_note = _note_locale(row)
        alt = dict(row)
        alt["pe_ref"] = fiche["pe_hist"]
        alt["pb_ref"] = fiche["pb_hist"]
        composite, note = _note_locale(alt)
        precedent = row.get("conseil")
        statut = row.get("statut") or "cote"
        conseil_alt = conseil(composite, precedent, statut)
        resultats.append({
            "ticker": ticker,
            "composite_rejoue": actuel_composite,
            "composite_fichier": row.get("composite_adj"),
            "note_fichier": row.get("note10"),
            "note_constantes": note,
            "composite_constantes": composite,
            "conseil_fichier": precedent,
            "conseil_constantes": conseil_alt,
            "statut": statut,
        })
    return resultats


def main():
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument(
        "--ranking",
        help="live_ranking.json déjà téléchargé. Sans ce fichier, seules les constantes sont imprimées.",
    )
    args = parseur.parse_args()
    fonds = _lire_constantes()
    lignes, medianes = tableau_constantes(fonds)
    print(f"societes {len(lignes)}")
    print("medianes_secteur")
    for secteur, (pe, pb, n) in sorted(medianes.items()):
        print(f"  {secteur}: n={n} pe={pe} pb={pb}")
    n_pe14 = sum(1 for l in lignes if l["pe_hist"] == 14)
    n_pb2 = sum(1 for l in lignes if l["pb_hist"] == 2)
    print(f"pe_hist_egal_14 {n_pe14}")
    print(f"pb_hist_egal_2 {n_pb2}")
    for ligne in lignes:
        print(
            f"{ligne['ticker']}\t{ligne['pe_hist']}\t{ligne['pb_hist']}\t"
            f"{ligne['generique']}\t{ligne['mediane_pe_secteur']}\t{ligne['mediane_pb_secteur']}"
        )
    if not args.ranking:
        return
    payload = json.loads(pathlib.Path(args.ranking).read_text(encoding="utf-8"))
    ranking = payload["ranking"] if isinstance(payload, dict) else payload
    resultats = contrefactuel(fonds, ranking)
    ecarts = [
        r for r in resultats
        if r["composite_fichier"] is not None
        and abs(r["composite_rejoue"] - r["composite_fichier"]) > 0.15
    ]
    print(f"rejeu_ecarts {len(ecarts)}")
    bascules = [
        r for r in resultats
        if r["conseil_fichier"] and r["conseil_constantes"]
        and r["conseil_fichier"] != r["conseil_constantes"]
    ]
    print(f"conseils_qui_changeraient {len(bascules)}")
    for r in bascules:
        print(
            f"  {r['ticker']} note {r['note_fichier']} -> {r['note_constantes']} "
            f"conseil {r['conseil_fichier']} -> {r['conseil_constantes']}"
        )


if __name__ == "__main__":
    main()
