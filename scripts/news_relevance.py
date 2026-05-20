#!/usr/bin/env python3
"""
news_relevance.py — Scoring de pertinence des articles Google News BRVM.

Usage (module) :
    from scripts.news_relevance import score_article, load_aliases

Usage (CLI) :
    python3 scripts/news_relevance.py --ticker BOAB
"""

import re
import json
import os
from pathlib import Path
from typing import Optional

BASE_DIR    = Path(__file__).parent.parent
ALIASES_PATH = BASE_DIR / "data" / "ticker_aliases.json"

TRUSTED_SOURCES = {
    "Sika Finance", "Dabafinance", "Financial Afrik",
    "Africtelegraph", "Zonebourse", "Agence Ecofin",
    "Leral", "Seneplus", "Apa News", "Reuters Afrique",
}

_DIVIDEND_RE   = re.compile(r'dividende|coupon|distribution|versement', re.I)
_RESULTS_RE    = re.compile(r'r[ée]sultat|b[ée]n[ée]fice|chiffre.d.affaires|pnb\b|ca\s+\d|revenus', re.I)
_AG_RE         = re.compile(r'assembl[ée]e\s+g[ée]n[ée]rale|assembl[ée]e\s+extraordinaire|\bag[eo]\b|\bage\b', re.I)
_NOMINATION_RE = re.compile(r'nomination|nouveau\s+directeur|directeur.g[ée]n[ée]ral|administrateur|d[ée]mission|pr[ée]sident', re.I)
_COURS_RE      = re.compile(r'\bcours\b|\bcotation\b|hausse|baisse|rebond|correction|plus\s+haut|plus\s+bas', re.I)

_aliases_cache: Optional[dict] = None


def load_aliases() -> dict:
    global _aliases_cache
    if _aliases_cache is not None:
        return _aliases_cache
    try:
        with open(ALIASES_PATH, encoding="utf-8") as f:
            _aliases_cache = json.load(f)
    except Exception:
        _aliases_cache = {}
    return _aliases_cache


def _detect_category(text: str) -> str:
    if _DIVIDEND_RE.search(text):
        return "dividende"
    if _RESULTS_RE.search(text):
        return "resultats"
    if _AG_RE.search(text):
        return "ag"
    if _NOMINATION_RE.search(text):
        return "nomination"
    if _COURS_RE.search(text):
        return "cours"
    return "generique"


def score_article(article: dict, ticker: str, aliases_map: Optional[dict] = None) -> dict:
    """
    Returns {
        'score': int 0-100,
        'category': str,
        'matched_alias': str|None,
        'is_relevant': bool  # score >= 30
    }
    """
    if aliases_map is None:
        aliases_map = load_aliases()

    text = (
        (article.get("titre") or "") + " " +
        (article.get("resume") or "")
    ).lower()

    ticker_data = aliases_map.get(ticker.upper(), {})
    aliases = ticker_data.get("aliases", [ticker])

    # Alias match (longest first to prefer specific matches)
    matched: Optional[str] = None
    for alias in sorted(aliases, key=len, reverse=True):
        if alias.lower() in text:
            matched = alias
            break

    category = _detect_category(text)

    score = 0
    if matched:
        score += 60
    if category != "generique":
        score += 30
    source = article.get("source", "") or ""
    if any(src.lower() in source.lower() for src in TRUSTED_SOURCES):
        score += 10

    score = min(score, 100)

    return {
        "score": score,
        "category": category,
        "matched_alias": matched,
        "is_relevant": score >= 30,
    }


if __name__ == "__main__":
    import argparse, sys
    parser = argparse.ArgumentParser(description="Test scoring article BRVM")
    parser.add_argument("--ticker", required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(BASE_DIR))
    aliases = load_aliases()

    news_path = BASE_DIR / "data" / "brvm_news.json"
    if not news_path.exists():
        print("brvm_news.json introuvable")
        sys.exit(1)

    with open(news_path, encoding="utf-8") as f:
        data = json.load(f)

    ticker = args.ticker.upper()
    articles = data.get(ticker, [])
    if not articles:
        print(f"Aucun article pour {ticker}")
        sys.exit(0)

    print(f"\n{'═'*60}")
    print(f"  Scoring articles {ticker}")
    print(f"{'═'*60}\n")
    for a in articles:
        r = score_article(a, ticker, aliases)
        print(f"  [{r['score']:3d}] [{r['category']:10s}] alias:{r['matched_alias'] or '—':25s}")
        print(f"        {a.get('titre','')[:80]}")
        print()
