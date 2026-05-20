#!/usr/bin/env python3
"""
rescore_news.py — Re-score tous les articles brvm_news.json avec news_relevance.

Usage :
    python3 scripts/rescore_news.py
    python3 scripts/rescore_news.py --ticker BOAB
    python3 scripts/rescore_news.py --dry-run
"""

import json, sys, argparse
from pathlib import Path

BASE_DIR   = Path(__file__).parent.parent
NEWS_PATH  = BASE_DIR / "data" / "brvm_news.json"

sys.path.insert(0, str(BASE_DIR))
from scripts.news_relevance import score_article, load_aliases


def main():
    parser = argparse.ArgumentParser(description="Re-score brvm_news.json")
    parser.add_argument("--ticker", default=None, help="Scorer un seul ticker")
    parser.add_argument("--dry-run", action="store_true", help="Afficher sans sauvegarder")
    args = parser.parse_args()

    if not NEWS_PATH.exists():
        print("brvm_news.json introuvable")
        sys.exit(1)

    with open(NEWS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    aliases = load_aliases()
    tickers = [args.ticker.upper()] if args.ticker else list(data.keys())

    total = updated = 0
    for ticker in tickers:
        articles = data.get(ticker, [])
        for a in articles:
            total += 1
            new_rel = score_article(a, ticker, aliases)
            if a.get("relevance") != new_rel:
                a["relevance"] = new_rel
                updated += 1

        # Re-trier par (pertinence DESC, date DESC)
        data[ticker] = sorted(
            articles,
            key=lambda x: (
                x.get("relevance", {}).get("score", 0),
                x.get("date") or "0000",
            ),
            reverse=True
        )

    print(f"Articles traités : {total}  |  mis à jour : {updated}")

    if args.dry_run:
        print("[dry-run] Aucune sauvegarde.")
        return

    with open(NEWS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Sauvegardé → {NEWS_PATH}")


if __name__ == "__main__":
    main()
