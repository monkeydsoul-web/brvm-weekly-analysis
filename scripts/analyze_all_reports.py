#!/usr/bin/env python3
"""
analyze_all_reports.py — Analyse IA de tous les rapports.

Sources : data/reports_full.json (nouveau pipeline) +
          data/reports_cache.json (legacy rapports_scraper)

Cache par hash URL dans data/pdf_analyses/.
Construit data/analyses_reports.json (index URL-hash → analyse).

Usage :
    python3 scripts/analyze_all_reports.py
    python3 scripts/analyze_all_reports.py --types "Rapport annuel"
    python3 scripts/analyze_all_reports.py --types "Rapport annuel,Etats financiers"
    python3 scripts/analyze_all_reports.py --max-cost 3.0 --dry-run
    python3 scripts/analyze_all_reports.py --ticker SNTS
"""

import json, sys, argparse, hashlib, time, os
from pathlib import Path

BASE_DIR       = Path(__file__).parent.parent
REPORTS_PATH   = BASE_DIR / "data" / "reports_full.json"
LEGACY_PATH    = BASE_DIR / "data" / "reports_cache.json"
CACHE_DIR      = BASE_DIR / "data" / "pdf_analyses"
OUT_INDEX_PATH = BASE_DIR / "data" / "analyses_reports.json"

sys.path.insert(0, str(BASE_DIR))
from pdf_analyzer import analyze_report, _cache_path


def _url_md5(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _is_cached(url: str) -> bool:
    path = Path(_cache_path(url))
    return path.exists() and path.stat().st_size > 100


def _load_all_reports() -> list:
    """Fusionne reports_full.json + reports_cache.json (legacy), normalisé."""
    reports = []

    # Source 1 : reports_full.json
    if REPORTS_PATH.exists():
        for r in json.loads(REPORTS_PATH.read_text(encoding="utf-8")):
            if not r.get("pdf_url"):
                continue
            reports.append({
                "ticker": r.get("ticker") or "?",
                "annee": r.get("annee"),
                "type": r.get("type", "Document"),
                "titre": r.get("titre", ""),
                "pdf_url": r["pdf_url"],
                "source": "full",
            })

    # Source 2 : reports_cache.json (legacy)
    if LEGACY_PATH.exists():
        legacy = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))
        reps = legacy.get("reports", {})
        seen_urls = {r["pdf_url"] for r in reports}
        for ticker, items in reps.items():
            for r in items:
                url = r.get("url") or r.get("pdf_url")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                # Normalize type: legacy uses "Rapport annuel", "Rapport S1", etc.
                rtype = r.get("type", "Document")
                # Map legacy variants to canonical names
                type_map = {
                    "Rapport activite": "Rapport annuel",
                }
                rtype = type_map.get(rtype, rtype)
                reports.append({
                    "ticker": r.get("ticker") or ticker,
                    "annee": r.get("annee"),
                    "type": rtype,
                    "titre": r.get("title") or r.get("titre") or "",
                    "pdf_url": url,
                    "source": "legacy",
                })

    return reports


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
    parser.add_argument("--types", default=None,
                        help='Types à analyser, séparés par virgule : "Rapport annuel,Etats financiers"')
    parser.add_argument("--max", type=int, default=0, help="Nombre max d'analyses (0=illimité)")
    parser.add_argument("--max-cost", type=float, default=10.0,
                        help="Arrêter si coût estimé dépasse ce montant USD")
    parser.add_argument("--force", action="store_true", help="Ré-analyser même si déjà en cache")
    parser.add_argument("--dry-run", action="store_true", help="Afficher sans analyser")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("⚠️  ANTHROPIC_API_KEY non défini — analyse IA impossible.")
        print("   Exécutez: export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    reports = _load_all_reports()

    # Filtres
    if args.ticker:
        reports = [r for r in reports if r.get("ticker", "").upper() == args.ticker.upper()]
    if args.types:
        types_filter = [t.strip() for t in args.types.split(",")]
        reports = [r for r in reports if r.get("type") in types_filter]

    # Filtrer déjà en cache (sauf --force)
    if not args.force:
        pending = [r for r in reports if not _is_cached(r["pdf_url"])]
        cached_count = len(reports) - len(pending)
    else:
        pending = reports
        cached_count = 0

    # Estimation coût (approx 0.015 $ / rapport — 40k tokens input)
    est_cost = len(pending) * 0.015

    print(f"\n{'═'*60}")
    print(f"  Analyse IA rapports BRVM")
    print(f"  Total dans les sources  : {len(reports)}")
    if args.types:
        print(f"  Filtre types            : {args.types}")
    print(f"  Déjà en cache           : {cached_count}")
    print(f"  À analyser              : {len(pending)}")
    print(f"  Coût estimé             : ~${est_cost:.2f} USD")
    print(f"  Budget max              : ${args.max_cost:.2f} USD")
    print(f"{'═'*60}\n")

    if args.dry_run:
        print("  [dry-run] Rapports à analyser :")
        for r in pending:
            print(f"    [{r['ticker']}] {r['type']} {r.get('annee','?')} — {r['titre'][:50]}")
        print(f"\n  Total : {len(pending)} rapports · ~${est_cost:.2f}")
        return

    if est_cost > args.max_cost:
        print(f"❌ Coût estimé ${est_cost:.2f} dépasse le budget de ${args.max_cost:.2f}")
        print(f"   Réduisez le scope avec --types ou --ticker, ou augmentez --max-cost")
        sys.exit(1)

    if pending:
        try:
            input(f"⚠️  Continuer avec {len(pending)} analyses (~${est_cost:.2f}) ? "
                  f"[Enter pour confirmer / Ctrl-C pour annuler] ")
        except KeyboardInterrupt:
            print("\nAnnulé.")
            sys.exit(0)

    # Compteurs
    done = skipped = errors = 0
    limit = args.max or len(pending)

    for r in pending:
        if done + errors >= limit:
            break

        url    = r["pdf_url"]
        ticker = r.get("ticker", "?")
        annee  = r.get("annee", "?")
        type_  = r.get("type", "Document")
        label  = f"[{ticker}] {type_} {annee}"

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

        time.sleep(2)

    # Reconstruire l'index consolidé
    index = build_index()
    OUT_INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Distribution des verdicts
    verdicts = {}
    for v in index.values():
        verd = (v.get("verdict_investisseur") or "?").lower()
        verdicts[verd] = verdicts.get(verd, 0) + 1
    tickers_done = list({v.get("ticker") for v in index.values() if v.get("ticker")})

    print(f"\n{'─'*60}")
    print(f"  Nouvelles analyses : {done}")
    print(f"  Erreurs            : {errors}")
    print(f"  Cache total        : {len(index)} analyses")
    print(f"  Sociétés couvertes : {', '.join(sorted(tickers_done))}")
    if verdicts:
        dist = " · ".join(f"{k}={n}" for k,n in sorted(verdicts.items()))
        print(f"  Verdicts           : {dist}")
    print(f"  Sauvegardé → {OUT_INDEX_PATH.name}")
    print(f"{'─'*60}")

    cost_est = done * 0.015
    if done > 0:
        print(f"\n  Coût API estimé : ~${cost_est:.2f} USD ({done} analyses)")


if __name__ == "__main__":
    main()
