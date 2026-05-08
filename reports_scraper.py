"""
reports_scraper.py — Scrape les rapports annuels depuis brvm.org
URL pattern : https://www.brvm.org/fr/rapports-societe-cotes/{slug}
PDFs        : https://www.brvm.org/sites/default/files/{fichier}.pdf
Cache JSON  : data/reports_cache.json
"""

import json
import os
import time
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "data", "reports_cache.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# ── Mapping ticker → slug brvm.org ────────────────────────────────────────────
TICKER_SLUG = {
    "SGBC":  "societe-generale-ci",
    "SIBC":  "societe-ivoirienne-de-banque",
    "SNTS":  "sonatel",
    "NSBC":  "nsia-banque-ci",
    "CBIBF": "coris-bank-international",
    "BOAB":  "bank-africa-bn",
    "BOABF": "bank-africa-bf",
    "BOAC":  "bank-africa-ci",
    "BOAM":  "bank-africa-ml",
    "BOAN":  "bank-africa-ng",
    "BOAS":  "bank-africa-sn",
    "ETIT":  "ecobank-tg",
    "ECOC":  "ecobank-ci",
    "ORAC":  "orange-ci",
    "ONTBF": "onatel",
    "NTLC":  "nestle-ci",
    "SLBC":  "solibra",
    "SMBC":  "smb",
    "PALC":  "palm-ci",
    "SPHC":  "saph",
    "SOGC":  "sogb",
    "SCRC":  "sucrivoire",
    "TTLC":  "total-ci",
    "TTLS":  "total-senegal",
    "SHEC":  "vivo-energy-ci",
    "CIEC":  "cie-ci",
    "SDCC":  "sodeci",
    "STBC":  "sitab",
    "UNLC":  "unilever-ci",
    "FTSC":  "filtisac-ci",
    "ABJC":  "air-liquide-ci",
    "CFAC":  "cfao-motors-ci",
    "LNBB":  "lnb",
    "PRSC":  "tractafric-motors-ci",
    "SVOC":  "sivoa",
    "SICC":  "sicable",
    "NEIC":  "nei-ceda",
    "CABC":  "crrh",
    "ORGT":  "oragroup",
    "SEMC":  "crown-siem-ci",
    "STAC":  "setao",
    "BICC":  "bici-ci",
    "BOLLORE": "bollore-transport-logistics",
}

# Types de rapports (field_type_rapport_tid)
REPORT_TYPES = {
    "58": "Rapport annuel",
    "57": "Etats financiers",
    "59": "Rapport semestriel",
    "60": "Rapport trimestriel",
    "56": "Commentaire activite",
}


def fetch_reports_for_ticker(ticker, slug, type_tid="All", max_docs=10):
    """
    Scrape les rapports d'une société depuis brvm.org.
    Retourne une liste de dicts {title, url, date, type, year}.
    """
    if type_tid == "All":
        url = f"https://www.brvm.org/fr/rapports-societe-cotes/{slug}"
    else:
        url = f"https://www.brvm.org/fr/rapports-societe-cotes/{slug}?field_type_rapport_tid={type_tid}"

    reports = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            logger.warning(f"{ticker}: HTTP {r.status_code} pour {url}")
            return reports

        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.find_all("a", href=True)

        for link in links:
            href = link["href"]
            if "/sites/default/files/" not in href:
                continue

            # Extraire le nom du fichier
            filename = href.split("/")[-1]
            if not filename.endswith(".pdf"):
                continue

            # Extraire la date depuis le nom du fichier (format YYYYMMDD_)
            year = None
            date_str = None
            if len(filename) >= 8 and filename[:8].isdigit():
                raw_date = filename[:8]
                try:
                    year = int(raw_date[:4])
                    date_str = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
                except Exception:
                    pass

            # Detecter le type depuis le nom du fichier
            fname_lower = filename.lower()
            doc_type = "Document"
            if "rapport_annuel" in fname_lower or "rapport_dactivites_annuel" in fname_lower:
                doc_type = "Rapport annuel"
            elif "etats_financiers" in fname_lower or "resultats_financiers" in fname_lower or "resultats_consolides" in fname_lower:
                doc_type = "Etats financiers"
            elif "rapport_dactivites" in fname_lower or "rapport_activite" in fname_lower:
                if "1er_semestre" in fname_lower or "1er_sem" in fname_lower or "semestre" in fname_lower:
                    doc_type = "Rapport S1"
                elif "3eme_trimestre" in fname_lower or "3eme_trim" in fname_lower:
                    doc_type = "Rapport T3"
                elif "trimestre" in fname_lower:
                    doc_type = "Rapport trimestriel"
                else:
                    doc_type = "Rapport activite"
            elif "rse" in fname_lower:
                doc_type = "Rapport RSE"

            # URL absolue
            full_url = href if href.startswith("http") else f"https://www.brvm.org{href}"

            # Titre lisible depuis le nom de fichier
            title = filename.replace("_", " ").replace(".pdf", "")
            title = " ".join(w.capitalize() for w in title.split()[:8])

            reports.append({
                "ticker":   ticker,
                "title":    title,
                "url":      full_url,
                "filename": filename,
                "type":     doc_type,
                "year":     year,
                "date":     date_str,
            })

            if len(reports) >= max_docs:
                break

    except Exception as e:
        logger.warning(f"{ticker} ({slug}): erreur scrape — {e}")

    return reports


def fetch_all_reports(tickers=None, delay=0.5):
    """
    Scrape les rapports pour tous les tickers (ou une liste).
    Retourne un dict {ticker: [reports]}.
    """
    if tickers is None:
        tickers = list(TICKER_SLUG.keys())

    all_reports = {}
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        slug = TICKER_SLUG.get(ticker)
        if not slug:
            logger.warning(f"{ticker}: slug manquant, ignoré")
            all_reports[ticker] = []
            continue

        logger.info(f"[{i+1}/{total}] {ticker} ({slug})")
        reports = fetch_reports_for_ticker(ticker, slug, max_docs=15)
        all_reports[ticker] = reports
        logger.info(f"  → {len(reports)} documents")
        time.sleep(delay)

    return all_reports


def save_reports_cache(all_reports):
    """Sauvegarde le cache JSON."""
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total_tickers": len(all_reports),
        "total_docs": sum(len(v) for v in all_reports.values()),
        "reports": all_reports,
    }
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"Cache sauvegarde: {CACHE_PATH}")
    return payload


def load_reports_cache():
    """Charge le cache JSON."""
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_reports(ticker, force_refresh=False):
    """
    Point d'entree principal — cache < 24h ou re-fetch.
    Retourne la liste des rapports pour un ticker.
    """
    cache = load_reports_cache()
    if cache and not force_refresh:
        try:
            updated = datetime.fromisoformat(cache["updated_at"])
            age_h = (datetime.now(timezone.utc) - updated).total_seconds() / 3600
            if age_h < 24:
                return cache["reports"].get(ticker, [])
        except Exception:
            pass

    # Re-fetch pour ce ticker uniquement
    slug = TICKER_SLUG.get(ticker)
    if not slug:
        return []
    reports = fetch_reports_for_ticker(ticker, slug, max_docs=15)

    # Mettre a jour le cache partiel
    if cache:
        cache["reports"][ticker] = reports
        cache["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

    return reports


def get_latest_annual_report(ticker):
    """Retourne le rapport annuel le plus recent pour un ticker."""
    reports = get_reports(ticker)
    annuels = [r for r in reports if r["type"] in ("Rapport annuel", "Etats financiers")]
    if not annuels:
        return None
    annuels.sort(key=lambda r: r.get("year") or 0, reverse=True)
    return annuels[0]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    import sys
    tickers_arg = sys.argv[1:] if len(sys.argv) > 1 else None

    if tickers_arg:
        # Test sur tickers specifiques
        for ticker in tickers_arg:
            slug = TICKER_SLUG.get(ticker.upper())
            if not slug:
                print(f"{ticker}: slug inconnu")
                continue
            reports = fetch_reports_for_ticker(ticker.upper(), slug, max_docs=20)
            print(f"\n{ticker} — {len(reports)} documents:")
            for r in reports:
                print(f"  [{r['type']:20s}] {r['year'] or '?':4} | {r['url'][-80:]}")
    else:
        # Fetch complet
        print("Fetch rapports pour tous les tickers...")
        all_reports = fetch_all_reports(delay=0.8)
        cache = save_reports_cache(all_reports)
        print(f"\nTotal: {cache['total_docs']} documents pour {cache['total_tickers']} societes")
        print(f"Cache: {CACHE_PATH}")
