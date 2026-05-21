#!/usr/bin/env python3
"""
analyze_all_reports.py — Analyse IA de tous les rapports de reports_full.json.

Appelle pdf_analyzer.analyze_report() pour chaque rapport avec pdf_url.
Cache par hash URL dans data/pdf_analyses/.
Construit data/analyses_reports.json (index URL-hash → analyse).

Usage :
    python3 scripts/analyze_all_reports.py
    python3 scripts/analyze_all_reports.py --ticker SNTS
    python3 scripts/analyze_all_reports.py --max 5 --force
    python3 scripts/analyze_all_reports.py --dry-run
"""

import json, sys, argparse, hashlib, time, os
from pathlib import Path

BASE_DIR       = Path(__file__).parent.parent
REPORTS_PATH   = BASE_DIR / "data" / "reports_full.json"
CACHE_DIR      = BASE_DIR / "data" / "pdf_analyses"
OUT_INDEX_PATH = BASE_DIR / "data" / "analyses_reports.json"

sys.path.insert(0, str(BASE_DIR))
from pdf_analyzer import analyze_report, _cache_path


def _url_md5(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _is_cached(url: str) -> bool:
    path = Path(_cache_path(url))
    return path.exists() and path.stat().st_size > 100


def build_index() -> dict:
    """Relit tous les fichiers cache et construit l'index par URL hash."""
    index: dict = {}
    if not CACHE_DIR.exists():
        return index
    for f in CACHE_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("status") == "ok" and data.get("url"):
                key = _url_md5(data["url"])
                index[key] = data
        except Exception:
            continue
    return index


def main():
    parser = argparse.ArgumentParser(description="Analyse IA rapports BRVM")
    parser.add_argument("--ticker", default=None, help="Analyser seulement ce ticker")
    parser.add_argument("--max", type=int, default=0, help="Nombre max d'analyses (0=illimité)")
    parser.add_argument("--force", action="store_true", help="Ré-analyser même si déjà en cache")
    parser.add_argument("--dry-run", action="store_true", help="Afficher sans analyser")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("⚠️  ANTHROPIC_API_KEY non défini — analyse IA impossible.")
        print("   Exécutez: export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    if not REPORTS_PATH.exists():
        print(f"reports_full.json introuvable. Lancez d'abord :")
        print(f"  python3 scripts/brvm_reports_full_scraper.py")
        sys.exit(1)

    reports = json.loads(REPORTS_PATH.read_text(encoding="utf-8"))
    if args.ticker:
        reports = [r for r in reports if r.get("ticker", "").upper() == args.ticker.upper()]

    # Filtrer : seulement ceux avec pdf_url
    reports = [r for r in reports if r.get("pdf_url")]

    print(f"\n{'═'*60}")
    print(f"  Analyse IA rapports BRVM")
    print(f"  Rapports avec PDF : {len(reports)}")
    print(f"  Force re-analyse  : {args.force}")
    print(f"{'═'*60}\n")

    # Compteurs
    done = skipped = errors = 0
    limit = args.max or len(reports)

    for r in reports:
        if done + errors >= limit:
            break

        url    = r["pdf_url"]
        ticker = r.get("ticker", "?")
        annee  = r.get("annee", "?")
        type_  = r.get("type", "Document")

        cached = _is_cached(url)
        if cached and not args.force:
            skipped += 1
            continue

        label = f"[{ticker}] {type_} {annee}"
        if args.dry_run:
            print(f"  DRY-RUN: {label}")
            done += 1
            continue

        print(f"  → {label}…", end=" ", flush=True)
        try:
            result = analyze_report(
                url=url,
                ticker=ticker,
                doc_type=type_,
                year=annee if isinstance(annee, int) else None,
                force=args.force,
            )
            if result.get("status") == "ok":
                verdict = result.get("verdict_investisseur", "?")
                print(f"✓ {verdict}")
                done += 1
            else:
                print(f"✗ {result.get('error','?')[:60]}")
                errors += 1
        except Exception as e:
            print(f"✗ {e}")
            errors += 1

        time.sleep(2)  # rate-limit API

    # Reconstruire l'index consolidé
    index = build_index()
    OUT_INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n{'─'*60}")
    print(f"  Nouvelles analyses : {done}")
    print(f"  Déjà en cache     : {skipped}")
    print(f"  Erreurs           : {errors}")
    print(f"  Index total       : {len(index)} analyses")
    print(f"  Sauvegardé → {OUT_INDEX_PATH.name}")
    print(f"{'─'*60}")

    # Coût approximatif (claude-sonnet-4-6 : ~$3/MTok input, ~$15/MTok output)
    cost_est = done * 0.015  # ~$0.015 par analyse (40k tokens input)
    if done > 0:
        print(f"\n  Coût API estimé : ~${cost_est:.2f} USD ({done} analyses)")


if __name__ == "__main__":
    main()
