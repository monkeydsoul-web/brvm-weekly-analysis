"""
bulk_analyzer.py — Analyse IA en masse des 47 sociétés BRVM
Lance : python3 bulk_analyzer.py
       python3 bulk_analyzer.py SNTS SGBC ORAC  (tickers spécifiques)
       python3 bulk_analyzer.py --status          (voir état du cache)
"""

import os
import json
import time
import logging
import sys
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
SUMMARY_PATH  = os.path.join(BASE_DIR, "data", "analyses_summary.json")
DELAY_BETWEEN = 2.0   # secondes entre chaque analyse (respect brvm.org)
MAX_PER_TICKER = 2    # max rapports analysés par société


def load_summary():
    if os.path.exists(SUMMARY_PATH):
        try:
            with open(SUMMARY_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_summary(summary):
    os.makedirs(os.path.dirname(SUMMARY_PATH), exist_ok=True)
    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def print_status():
    """Affiche l'état du cache d'analyses."""
    summary = load_summary()
    if not summary:
        print("Aucune analyse en cache.")
        return

    print(f"\n{'Ticker':8s} {'Verdict':10s} {'CA (MFCFA)':12s} {'RN (MFCFA)':12s} {'ROE':6s} {'Année':6s} {'Analysé le'}")
    print("-" * 80)
    for ticker, data in sorted(summary.items()):
        if data.get("status") != "ok":
            print(f"{ticker:8s} ERREUR")
            continue
        kpis = data.get("kpis", {})
        ca   = kpis.get("chiffre_affaires", {})
        rn   = kpis.get("resultat_net", {})
        roe  = kpis.get("roe", {})
        print(
            f"{ticker:8s} "
            f"{data.get('verdict_investisseur','?'):10s} "
            f"{str(ca.get('valeur','?')):12s} "
            f"{str(rn.get('valeur','?')):12s} "
            f"{str(roe.get('valeur','?')):6s} "
            f"{str(data.get('year','?')):6s} "
            f"{(data.get('analyzed_at','?')[:10])}"
        )
    positif = sum(1 for d in summary.values() if d.get("verdict_investisseur") == "POSITIF")
    neutre  = sum(1 for d in summary.values() if d.get("verdict_investisseur") == "NEUTRE")
    negatif = sum(1 for d in summary.values() if d.get("verdict_investisseur") == "NEGATIF")
    print(f"\nTotal: {len(summary)} | POSITIF: {positif} | NEUTRE: {neutre} | NEGATIF: {negatif}")


def run_bulk_analysis(tickers=None, force=False):
    """
    Lance l'analyse IA pour tous les tickers (ou une liste).
    Met à jour le summary JSON après chaque ticker.
    """
    from reports_scraper import get_reports, TICKER_SLUG
    from pdf_analyzer    import analyze_report

    if tickers is None:
        tickers = list(TICKER_SLUG.keys())

    summary = load_summary()
    total   = len(tickers)
    ok = err = skip = 0

    print(f"\nAnalyse IA BRVM — {total} sociétés")
    print(f"Force refresh: {force}")
    print("=" * 60)

    for i, ticker in enumerate(tickers):
        print(f"\n[{i+1}/{total}] {ticker}", end=" ", flush=True)

        # Récupérer les rapports disponibles
        try:
            reports = get_reports(ticker)
        except Exception as e:
            print(f"— ERREUR scrape: {e}")
            err += 1
            continue

        if not reports:
            print(f"— aucun rapport")
            skip += 1
            continue

        # Trier : états financiers > rapport annuel > autres
        priority = {"Etats financiers": 0, "Rapport annuel": 1}
        sorted_reports = sorted(
            reports,
            key=lambda r: (priority.get(r.get("type", ""), 2), -(r.get("year") or 0))
        )[:MAX_PER_TICKER]

        best_result = None
        for report in sorted_reports:
            print(f"\n  → {report['type']} {report.get('year','?')}", end=" ", flush=True)
            try:
                result = analyze_report(
                    url=report["url"],
                    ticker=ticker,
                    doc_type=report.get("type", "Document"),
                    year=report.get("year"),
                    force=force,
                )
                if result.get("status") == "ok":
                    print(f"✓ {result.get('verdict_investisseur','?')}", end="")
                    if best_result is None:
                        best_result = result
                    ok += 1
                else:
                    print(f"✗ {result.get('error','?')[:40]}", end="")
                    err += 1
                time.sleep(DELAY_BETWEEN)
            except Exception as e:
                print(f"✗ {str(e)[:40]}", end="")
                err += 1

        # Sauvegarder le meilleur résultat pour ce ticker
        if best_result:
            summary[ticker] = best_result
            save_summary(summary)

    print(f"\n\n{'='*60}")
    print(f"Terminé — OK: {ok} | Erreurs: {err} | Sans rapport: {skip}")
    print(f"Summary: {SUMMARY_PATH}")
    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,  # Moins verbeux en mode batch
        format="%(asctime)s %(levelname)s %(message)s"
    )

    args = sys.argv[1:]

    if "--status" in args:
        print_status()
    elif args:
        tickers = [a.upper() for a in args if not a.startswith("--")]
        force   = "--force" in args
        run_bulk_analysis(tickers, force=force)
    else:
        force = "--force" in args
        run_bulk_analysis(force=force)
