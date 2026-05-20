#!/usr/bin/env python3
"""
google_news_scraper.py
Scrape Google News RSS pour les 47 tickers BRVM.

Output : data/brvm_news.json
  {
    "SIBC": [{"titre", "date", "source", "lien", "resume"}, ...],
    ...
  }

Usage :
  python3 scripts/google_news_scraper.py
  python3 scripts/google_news_scraper.py --ticker SGBC
  python3 scripts/google_news_scraper.py --max-age 7   # articles ≤ 7 jours
"""

import os, sys, json, re, time, logging, datetime, argparse
from pathlib import Path
from typing import Optional, List, Dict, Any
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

# ── Chemins ───────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent.parent
DATA_DIR    = BASE_DIR / "data"
OUTPUT_PATH = DATA_DIR / "brvm_news.json"
LOG_DIR     = BASE_DIR / "logs"

# ── Mapping ticker → noms de recherche ────────────────────────────────────────
TICKER_NAMES: Dict[str, List[str]] = {
    "ABJC": ["Air Burkina", "ABJC"],
    "BICB": ["BIC Bénin", "BICB", "Banque Internationale du Commerce"],
    "BICC": ["BICI CI", "BICC", "Banque Internationale pour le Commerce"],
    "BNBC": ["BACI", "BNBC", "Banque Atlantique"],
    "BOAB": ["BOA Bénin", "BOAB", "Bank of Africa Bénin"],
    "BOABF": ["BOA Burkina", "BOABF", "Bank of Africa Burkina"],
    "BOAC": ["BOA Côte d'Ivoire", "BOAC", "Bank of Africa CI"],
    "BOAM": ["BOA Mali", "BOAM", "Bank of Africa Mali"],
    "BOAN": ["BOA Niger", "BOAN", "Bank of Africa Niger"],
    "BOAS": ["BOA Sénégal", "BOAS", "Bank of Africa Sénégal"],
    "CABC": ["Sicable", "CABC", "Câbles de Côte d'Ivoire"],
    "CBIBF": ["Coris Bank", "CBIBF", "Coris Bank International Burkina"],
    "CFAC": ["CFAO Motors", "CFAC"],
    "CIEC": ["CIE", "CIEC", "Compagnie Ivoirienne d'Électricité"],
    "ECOC": ["Ecobank CI", "ECOC", "Ecobank Côte d'Ivoire"],
    "ETIT": ["Ecobank Transnational", "ETIT", "ETI"],
    "FTSC": ["Filtisac", "FTSC"],
    "LNBB": ["LONAB", "LNBB", "Loterie Nationale Burkina"],
    "NEIC": ["NEI CEDA", "NEIC"],
    "NSBC": ["NSIA Banque", "NSBC", "NSIA Banque CI"],
    "NTLC": ["Nestlé CI", "NTLC", "Nestlé Côte d'Ivoire"],
    "ONTBF": ["ONATEL", "ONTBF", "Office National des Télécommunications Burkina"],
    "ORAC": ["Orange CI", "ORAC", "Orange Côte d'Ivoire"],
    "ORGT": ["ORAGROUP", "ORGT"],
    "PALC": ["PALMCI", "PALC", "Palm Côte d'Ivoire"],
    "PRSC": ["PRESTIGE", "PRSC"],
    "SAFC": ["SAFCA", "SAFC"],
    "SCRC": ["SUCRIVOIRE", "SCRC"],
    "SDCC": ["SODECI", "SDCC", "Société de Distribution d'Eau de Côte d'Ivoire"],
    "SDSC": ["SDS CI", "SDSC"],
    "SEMC": ["SETAO", "SEMC"],
    "SGBC": ["Société Générale CI", "SGBC", "Société Générale Côte d'Ivoire"],
    "SHEC": ["VIVO Energy", "SHEC", "Shell CI"],
    "SIBC": ["Société Ivoirienne de Banque", "SIBC", "SIB"],
    "SICC": ["SICOGI", "SICC"],
    "SIVC": ["SIVOP", "SIVC"],
    "SLBC": ["SOLIBRA", "SLBC", "Société de Limonaderies et Brasseries d'Afrique"],
    "SMBC": ["SOACII", "SMBC"],
    "SNTS": ["Sonatel", "SNTS", "Sonatel Sénégal"],
    "SOGC": ["SOGB", "SOGC", "Société de Caoutchouc de Grand Béréby"],
    "SPHC": ["SAPH", "SPHC", "Société Africaine de Plantations d'Hévéas"],
    "STAC": ["SETACI", "STAC"],
    "STBC": ["STAB", "STBC", "Société de Tabac de Côte d'Ivoire"],
    "TTLC": ["TOTAL CI", "TTLC", "TotalEnergies CI"],
    "TTLS": ["TOTAL SN", "TTLS", "TotalEnergies Sénégal"],
    "UNLC": ["UNILEVER CI", "UNLC", "Unilever Côte d'Ivoire"],
    "UNXC": ["UNIWAX", "UNXC"],
}

# ── Mots-clés de pertinence ────────────────────────────────────────────────────
RELEVANT_KW = [
    "résultat", "bénéfice", "dividende", "chiffre d'affaires", "revenus",
    "bénéfice net", "résultat net", "croissance", "bilan", "assemblée générale",
    "nomination", "directeur général", "président", "conseil d'administration",
    "acquisition", "fusion", "partenariat", "contrat", "accord",
    "notation", "upgrade", "downgrade", "crédit",
    "brvm", "bourse", "action", "cours", "cotation",
    "rapport annuel", "rapport financier", "publication",
    "investissement", "expansion", "filiale",
]

EXCLUDED_KW = [
    "football", "rugby", "basketball", "sport", "match", "tournoi",
    "météo", "élection", "politique", "gouvernement", "militaire", "coup d'état",
    "chanson", "musique", "festival", "cinéma",
]

RATE_LIMIT = 1.2

_last_req = 0.0

def _get_rss(url: str) -> Optional[requests.Response]:
    global _last_req
    wait = RATE_LIMIT - (time.time() - _last_req)
    if wait > 0:
        time.sleep(wait)
    _last_req = time.time()
    try:
        r = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; BRVMBot/1.0; +https://brvm.org)",
            "Accept": "application/rss+xml, application/xml, text/xml",
        }, timeout=20)
        r.raise_for_status()
        return r
    except Exception as e:
        logging.warning(f"RSS fetch {url}: {e}")
        return None

def _parse_date(date_str: str) -> Optional[str]:
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_str)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None

def _is_relevant(title: str, summary: str, ticker: str, names: List[str]) -> bool:
    combined = (title + " " + summary).lower()

    # Exclure si contient des mots-clés hors-sujet
    for kw in EXCLUDED_KW:
        if kw in combined:
            return False

    # Vérifier présence du ticker ou nom société
    ticker_hit = ticker.lower() in combined
    name_hit   = any(n.lower() in combined for n in names if len(n) > 3)
    if not (ticker_hit or name_hit):
        return False

    # Vérifier pertinence financière
    for kw in RELEVANT_KW:
        if kw in combined:
            return True

    # Accepter si ticker/nom trouvé + pas de mots exclus (annonce générique)
    return ticker_hit or name_hit

def _strip_html(text: str) -> str:
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(" ", strip=True)[:500]

def scrape_ticker(ticker: str, names: List[str], max_age_days: int = 90) -> List[Dict]:
    cutoff = (datetime.date.today() - datetime.timedelta(days=max_age_days)).isoformat()
    articles = []

    # Requêtes Google News RSS : une par nom principal + ticker
    queries = [f"{names[0]} BRVM"]
    if len(names) > 1:
        queries.append(f"{ticker} BRVM bourse")

    seen_links: set = set()

    for query in queries:
        encoded = requests.utils.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=fr&gl=SN&ceid=SN:fr"

        r = _get_rss(url)
        if not r:
            continue

        try:
            soup = BeautifulSoup(r.content, "xml")
        except Exception:
            soup = BeautifulSoup(r.content, "html.parser")

        for item in soup.find_all("item"):
            title   = item.find("title")
            link    = item.find("link")
            pub     = item.find("pubDate")
            desc    = item.find("description")
            source  = item.find("source")

            title_text = title.get_text(strip=True) if title else ""
            link_text  = link.get_text(strip=True) if link else (link.get("href", "") if link else "")
            date_str   = _parse_date(pub.get_text(strip=True) if pub else "")
            summary    = _strip_html(desc.get_text(strip=True) if desc else "")
            source_name= source.get_text(strip=True) if source else ""

            if not title_text or not link_text:
                continue
            if link_text in seen_links:
                continue
            if date_str and date_str < cutoff:
                continue
            if not _is_relevant(title_text, summary, ticker, names):
                continue

            seen_links.add(link_text)
            articles.append({
                "titre":  title_text,
                "date":   date_str,
                "source": source_name,
                "lien":   link_text,
                "resume": summary,
            })

    # Tri par date décroissante
    articles.sort(key=lambda x: x.get("date") or "0000", reverse=True)
    return articles[:30]  # max 30 articles par ticker

def main():
    parser = argparse.ArgumentParser(description="Google News scraper BRVM")
    parser.add_argument("--ticker", default=None,
                        help="Scraper un seul ticker (ex: SGBC)")
    parser.add_argument("--max-age", type=int, default=90,
                        help="Articles des N derniers jours (défaut: 90)")
    parser.add_argument("--append", action="store_true",
                        help="Ajouter aux données existantes sans effacer")
    args = parser.parse_args()

    LOG_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_DIR / "google_news.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Charger données existantes si --append
    existing: Dict[str, List] = {}
    if args.append and OUTPUT_PATH.exists():
        try:
            with open(OUTPUT_PATH) as f:
                existing = json.load(f)
        except Exception:
            pass

    tickers_to_run = list(TICKER_NAMES.keys())
    if args.ticker:
        if args.ticker.upper() not in TICKER_NAMES:
            print(f"Ticker inconnu: {args.ticker}")
            sys.exit(1)
        tickers_to_run = [args.ticker.upper()]

    print(f"\n{'━'*60}")
    print(f"  Google News BRVM Scraper")
    print(f"  Tickers : {len(tickers_to_run)}  |  Max-age : {args.max_age}j")
    print(f"{'━'*60}\n")

    total_articles = 0
    for i, ticker in enumerate(tickers_to_run):
        names = TICKER_NAMES[ticker]
        articles = scrape_ticker(ticker, names, args.max_age)

        if args.append and ticker in existing:
            # Fusionner sans doublons (par lien)
            seen = {a["lien"] for a in existing[ticker]}
            added = [a for a in articles if a["lien"] not in seen]
            existing[ticker] = sorted(
                existing[ticker] + added,
                key=lambda x: x.get("date") or "0000",
                reverse=True
            )[:50]
        else:
            existing[ticker] = articles

        n = len(articles)
        total_articles += n
        print(f"  [{i+1:2d}/{len(tickers_to_run)}]  {ticker:<8} → {n:>3} articles")

        # Sauvegarde partielle toutes les 10 tickers
        if (i + 1) % 10 == 0:
            with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

    # Sauvegarde finale
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"\n{'━'*60}")
    print(f"  Total articles : {total_articles}")
    print(f"  Sauvegardé → {OUTPUT_PATH}")
    print(f"{'━'*60}\n")


if __name__ == "__main__":
    main()
