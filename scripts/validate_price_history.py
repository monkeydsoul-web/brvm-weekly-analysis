#!/usr/bin/env python3
"""
validate_price_history.py — Vérifie la cohérence de price_history_extended.json
                             par rapport aux cours live BRVM.

Usage :
    python3 scripts/validate_price_history.py           # rapport complet
    python3 scripts/validate_price_history.py --fix     # corrige automatiquement
    python3 scripts/validate_price_history.py --ticker SNTS
"""

import json, sys, argparse
from pathlib import Path
from typing import Optional

BASE_DIR  = Path(__file__).parent.parent
HIST_PATH = BASE_DIR / "data" / "price_history_extended.json"
LIVE_PATH = BASE_DIR / "data" / "live_cache.json"


def _live_prices() -> dict:
    """Retourne {ticker: price} depuis live_cache.json."""
    try:
        cache = json.loads(LIVE_PATH.read_text())
        prices = cache.get("prices", {})
        return {t: v.get("price") or v.get("close") for t, v in prices.items() if v}
    except Exception as e:
        print(f"[warn] live_cache.json illisible: {e}")
        return {}


def _detect_corrupted(entries: list, live_price: Optional[float]) -> list:
    """Retourne la liste des entrées suspectes (close divisé par ~1000)."""
    bad = []
    for i, e in enumerate(entries):
        close = e.get("close")
        if close is None:
            continue
        # Détection par rupture brutale (facteur ×10 ou ÷10 par rapport au voisin)
        if i > 0:
            prev = entries[i-1].get("close")
            if prev and prev > 0 and close > 0:
                ratio = max(prev, close) / min(prev, close)
                if ratio > 50:
                    bad.append((i, e["date"], close, "rupture ×50+"))
        # Détection par comparaison avec cours live
        if live_price and live_price > 1000 and close < live_price / 100:
            bad.append((i, e["date"], close, f"vs live {live_price}"))
    return bad


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true", help="Corriger les valeurs suspectes")
    parser.add_argument("--ticker", type=str, default=None, help="Vérifier un seul ticker")
    args = parser.parse_args()

    if not HIST_PATH.exists():
        print("price_history_extended.json introuvable")
        sys.exit(1)

    data = json.loads(HIST_PATH.read_text())
    live = _live_prices()

    tickers_to_check = [args.ticker] if args.ticker else sorted(data.keys())
    issues = {}

    for ticker in tickers_to_check:
        if ticker not in data:
            print(f"[skip] {ticker} absent du fichier")
            continue
        entries = data[ticker]
        live_price = live.get(ticker)
        bad = _detect_corrupted(entries, live_price)
        if bad:
            issues[ticker] = bad

    # Rapport
    print(f"\n{'═'*60}")
    print(f"  Validation price_history_extended.json")
    print(f"  Tickers vérifiés : {len(tickers_to_check)}")
    print(f"  Tickers suspects : {len(issues)}")
    print(f"{'═'*60}")

    total_bad = 0
    for ticker, bad_entries in sorted(issues.items()):
        lp = live.get(ticker)
        print(f"\n  {ticker}  (live={lp})")
        for idx, date, close, reason in bad_entries[:5]:
            print(f"    [{idx:4d}] {date}  close={close:>10,}  — {reason}")
        if len(bad_entries) > 5:
            print(f"    ... et {len(bad_entries)-5} autres")
        total_bad += len(bad_entries)

    print(f"\n  Total entrées suspectes : {total_bad}")

    if not args.fix:
        if issues:
            print("\n  Relancer avec --fix pour corriger automatiquement.")
        print()
        return

    # Correction automatique
    if not issues:
        print("\n  Aucune correction nécessaire.")
        return

    fixed = 0
    for ticker, bad_entries in issues.items():
        entries = data[ticker]
        lp = live.get(ticker)
        for idx, date, close, reason in bad_entries:
            # Correction: multiplier par 1000 si la valeur est clairement trop petite
            if lp and lp > 0 and close > 0:
                factor = round(lp / close)
                if factor in (100, 1000):
                    entries[idx]["close"] = round(close * factor)
                    fixed += 1
            elif "rupture" in reason:
                # Sans cours live, on multiplie par 1000 si ratio ×50+
                entries[idx]["close"] = round(close * 1000)
                fixed += 1

    HIST_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\n  ✓ {fixed} entrées corrigées → {HIST_PATH.name}")


if __name__ == "__main__":
    main()
