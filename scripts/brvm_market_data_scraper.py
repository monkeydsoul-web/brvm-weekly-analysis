#!/usr/bin/env python3
"""
brvm_market_data_scraper.py
Scrape et structure :
  A) Notations financières BRVM → data/brvm_ratings.json
  B) Statistiques de marché    → data/brvm_market_stats.json
  C) Données fondamentales     → data/brvm_fundamentals.json

Sources :
  - data/brvm_docs/notations/ (PDFs déjà téléchargés)
  - https://www.brvm.org/fr/emetteurs/type-annonces/notations-financieres (nouvelles pages)
  - https://www.brvm.org/fr/emetteurs/{slug} (pages emetteurs)
  - live_cache.json + market_cache.json (données locales)
"""
import os, re, sys, json, time, logging, datetime, warnings
from pathlib import Path
from typing import Optional, List, Dict, Any

warnings.filterwarnings("ignore")
import requests
from bs4 import BeautifulSoup

try:
    import pdfplumber
    HAS_PDF = True
except ImportError:
    HAS_PDF = False
    logging.warning("pdfplumber non disponible — skip lecture PDF")

BASE_DIR    = Path(__file__).parent.parent
DATA_DIR    = BASE_DIR / "data"
DOCS_DIR    = DATA_DIR / "brvm_docs"
LOG_DIR     = BASE_DIR / "logs"

RATINGS_PATH     = DATA_DIR / "brvm_ratings.json"
MARKET_PATH      = DATA_DIR / "brvm_market_stats.json"
FUNDAMENT_PATH   = DATA_DIR / "brvm_fundamentals.json"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; BRVMBot/2.0)"})
RATE_LIMIT = 1.5
_last_req  = 0.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_DIR / "brvm_market.log"),
        logging.StreamHandler(sys.stdout),
    ],
)

# ── Mapping nom société → ticker ────────────────────────────────────────────
COMPANY_TO_TICKER: Dict[str, str] = {
    "erium": "STAC", "erium cote d'ivoire": "STAC",
    "societe ivoirienne des tabacs": "STBC", "sitab": "STBC",
    "oragroup": "ORGT",
    "sonatel": "SNTS",
    "sgbc": "SGBC", "societe generale": "SGBC",
    "nsia banque": "NSBC", "nsia": "NSBC",
    "coris bank": "CBIBF",
    "boa benin": "BOAB", "bank of africa benin": "BOAB",
    "boa burkina": "BOABF", "bank of africa burkina": "BOABF",
    "boa cote d'ivoire": "BOAC", "bank of africa ci": "BOAC",
    "boa mali": "BOAM", "bank of africa mali": "BOAM",
    "boa niger": "BOAN", "bank of africa niger": "BOAN",
    "boa senegal": "BOAS", "bank of africa senegal": "BOAS",
    "ecobank": "ECOC", "ecobank ci": "ECOC",
    "ecobank transnational": "ETIT", "eti": "ETIT",
    "orange ci": "ORAC", "orange cote d'ivoire": "ORAC",
    "total ci": "TTLC", "totalenergies ci": "TTLC",
    "total senegal": "TTLS", "totalenergies senegal": "TTLS",
    "nestle ci": "NTLC", "nestle": "NTLC",
    "unilever ci": "UNLC",
    "palmci": "PALC", "palm ci": "PALC",
    "saph": "SPHC",
    "sogb": "SOGC", "caoutchoucs grand bereby": "SOGC",
    "solibra": "SLBC",
    "bicici": "BICC", "bici ci": "BICC",
    "sibc": "SIBC", "societe ivoirienne de banque": "SIBC",
    "sodeci": "SDCC",
    "cie": "CIEC", "compagnie ivoirienne electricite": "CIEC",
    "cfao": "CFAC",
    "onatel": "ONTBF",
    "sicable": "CABC",
    "filtisac": "FTSC",
    "sucrivoire": "SCRC",
    "air burkina": "ABJC",
    "lnbb": "LNBB", "lonab": "LNBB",
    "prsc": "PRSC", "prestige": "PRSC",
    "safc": "SAFC", "safca": "SAFC",
    "sdsc": "SDSC",
    "semc": "SEMC",
    "sicc": "SICC", "sicogi": "SICC",
    "sivc": "SIVC",
    "smbc": "SMBC", "soacii": "SMBC",
    "stac": "STAC", "setaci": "STAC",
    "unxc": "UNXC", "uniwax": "UNXC",
    "neic": "NEIC", "nei ceda": "NEIC",
    "bnbc": "BNBC",
    "bicb": "BICB",
    "cbibf": "CBIBF",
}

RATING_GRADES = {
    "AAA":10,"AA+":9.5,"AA":9,"AA-":8.5,
    "A+":8,"A":7.5,"A-":7,
    "BBB+":6.5,"BBB":6,"BBB-":5.5,
    "BB+":5,"BB":4.5,"BB-":4,
    "B+":3.5,"B":3,"B-":2.5,
    "CCC":2,"CC":1.5,"C":1,"D":0,
}

# ── Helpers réseau ───────────────────────────────────────────────────────────
def _get(url: str, timeout=20) -> Optional[requests.Response]:
    global _last_req
    wait = RATE_LIMIT - (time.time() - _last_req)
    if wait > 0:
        time.sleep(wait)
    _last_req = time.time()
    try:
        r = SESSION.get(url, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        logging.warning(f"GET {url}: {e}")
        return None

def _soup(url: str) -> Optional[BeautifulSoup]:
    r = _get(url)
    if r:
        return BeautifulSoup(r.content, "html.parser")
    return None

# ── Lecture PDF ──────────────────────────────────────────────────────────────
def _read_pdf(path: str) -> str:
    if not HAS_PDF or not os.path.exists(path):
        return ""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join(
                p.extract_text() or "" for p in pdf.pages[:4]
            )[:6000]
    except Exception:
        return ""

# ── Extraire ticker depuis texte ─────────────────────────────────────────────
def _extract_ticker(text: str) -> Optional[str]:
    t = text.lower()
    for name, ticker in COMPANY_TO_TICKER.items():
        if name in t:
            return ticker
    # Chercher un pattern TICKER (4-5 lettres majuscules)
    m = re.search(r'\b([A-Z]{3,5}C|[A-Z]{4,5})\b', text)
    if m:
        candidate = m.group(1)
        if candidate in {v for v in COMPANY_TO_TICKER.values()}:
            return candidate
    return None

# ── Extraire note depuis texte ───────────────────────────────────────────────
def _extract_rating_info(text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {"note": None, "perspective": None, "agence": None}

    # Agence
    agences = [
        ("Bloomfield", "Bloomfield Investment"),
        ("bloomfield", "Bloomfield Investment"),
        ("GCR", "GCR Ratings"),
        ("Moody", "Moody's"),
        ("S&P", "S&P Global"),
        ("Fitch", "Fitch Ratings"),
        ("RAM Ratings", "RAM Ratings"),
        ("Agusto", "Agusto & Co"),
    ]
    for kw, name in agences:
        if kw in text:
            result["agence"] = name
            break

    # Note long terme (ex: BBB, AA+, A-)
    for grade in sorted(RATING_GRADES.keys(), key=len, reverse=True):
        pattern = rf'\b{re.escape(grade)}\b'
        if re.search(pattern, text):
            result["note"] = grade
            result["score_notation"] = RATING_GRADES[grade]
            break

    # Perspective
    if re.search(r'[Ss]table', text):
        result["perspective"] = "Stable"
    elif re.search(r'[Pp]ositiv', text):
        result["perspective"] = "Positive"
    elif re.search(r'[Nn]égatif|[Nn]egatif|[Nn]egative', text):
        result["perspective"] = "Négative"
    elif re.search(r'[Ss]ous surveillance|[Cc]reditwatch', text):
        result["perspective"] = "Surveillance"

    return result

# ═══════════════════════════════════════════════════════════════════════════════
# A) NOTATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def scrape_ratings() -> List[Dict]:
    """Parse PDFs de notations existants + télécharge nouveaux."""
    ratings: Dict[str, Dict] = {}   # keyed by pdf_path

    # 1. Exploiter brvm_announcements.json existant
    annc_path = DATA_DIR / "brvm_announcements.json"
    if annc_path.exists():
        with open(annc_path, encoding="utf-8") as f:
            annc = json.load(f)
        for item in annc.get("notations", []):
            pdf = item.get("pdf_path") or ""
            url = item.get("source_url") or ""
            key = pdf or url
            if not key or key in ratings:
                continue
            # Lire PDF si disponible
            text = _read_pdf(pdf) if pdf and os.path.exists(pdf) else ""
            if not text and item.get("contenu"):
                text = item["contenu"]
            info = _extract_rating_info(text)
            ticker = item.get("ticker")
            if not ticker or ticker == "None":
                ticker = _extract_ticker(text)
            ratings[key] = {
                "ticker": ticker,
                "agence": info.get("agence"),
                "note": info.get("note") or item.get("notation"),
                "score_notation": info.get("score_notation"),
                "perspective": info.get("perspective"),
                "date": item.get("date"),
                "source_url": url,
                "resume": text[:500] if text else "",
            }

    # 2. Scraper nouvelles notations depuis brvm.org
    logging.info("Scraping notations BRVM...")
    for page in range(0, 3):
        url = f"https://www.brvm.org/fr/emetteurs/type-annonces/notations-financieres?page={page}"
        soup = _soup(url)
        if not soup:
            break
        pdf_links = [
            a.get("href", "")
            for a in soup.find_all("a", href=True)
            if ".pdf" in a.get("href", "").lower()
               and "default/files" in a.get("href", "")
        ]
        if not pdf_links:
            break
        for pdf_url in pdf_links:
            if pdf_url in {v.get("source_url","") for v in ratings.values()}:
                continue
            # Télécharger PDF si pas déjà présent
            fname = pdf_url.split("/")[-1]
            local = DOCS_DIR / "notations" / "UNKNOWN" / fname
            local.parent.mkdir(parents=True, exist_ok=True)
            text = ""
            if not local.exists():
                r = _get(pdf_url)
                if r:
                    local.write_bytes(r.content)
                    logging.info(f"  ↓ {fname}")
            text = _read_pdf(str(local))
            info = _extract_rating_info(text)
            ticker = _extract_ticker(text)
            ratings[pdf_url] = {
                "ticker": ticker,
                "agence": info.get("agence"),
                "note": info.get("note"),
                "score_notation": info.get("score_notation"),
                "perspective": info.get("perspective"),
                "date": None,
                "source_url": pdf_url,
                "resume": text[:500] if text else "",
            }
        # Vérifier pagination
        next_links = [a for a in soup.find_all("a", href=True)
                      if f"page={page+1}" in a.get("href","")]
        if not next_links:
            break

    result = list(ratings.values())
    logging.info(f"Notations: {len(result)} entrées")
    return result

# ═══════════════════════════════════════════════════════════════════════════════
# B) STATISTIQUES DE MARCHÉ
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_num(s: str) -> Optional[float]:
    """Convertit '16 101 667 934 513' → 16101667934513.0"""
    s = re.sub(r"[^\d.,]", "", s.replace(" ", ""))
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def scrape_market_stats() -> Dict:
    """Récupère stats de marché depuis brvm.org + market_cache.json local."""
    stats: Dict[str, Any] = {"date": datetime.date.today().isoformat()}

    # 1. Depuis market_cache.json local
    mc_path = DATA_DIR / "market_cache.json"
    if mc_path.exists():
        try:
            with open(mc_path, encoding="utf-8") as f:
                mc = json.load(f)
            stats["brvm_c"]    = mc.get("brvm_c")
            stats["brvm_30"]   = mc.get("brvm_30")
            stats["brvm_pres"] = mc.get("brvm_pres")
        except Exception:
            pass

    # 2. Scraper brvm.org pour données fraîches
    soup = _soup("https://www.brvm.org/fr")
    if soup:
        # Table "Activités du marché"
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
                if len(cells) >= 2:
                    label = cells[0].lower()
                    val   = cells[1] if len(cells) > 1 else ""
                    if "transactions" in label or "volume" in label:
                        v = _parse_num(val)
                        if v:
                            stats["volume_total_fcfa"] = v
                    elif "capitalisation actions" in label or "cap. actions" in label:
                        v = _parse_num(val)
                        if v:
                            stats["capitalisation_actions_fcfa"] = v
                    elif "capitalisation" in label and "oblig" in label:
                        v = _parse_num(val)
                        if v:
                            stats["capitalisation_obligations_fcfa"] = v
                    elif "brvm-c" in label:
                        m = re.search(r"[\d.,]+", val)
                        if m:
                            stats["brvm_c"] = float(m.group().replace(",","."))
                    elif "brvm-30" in label:
                        m = re.search(r"[\d.,]+", val)
                        if m:
                            stats["brvm_30"] = float(m.group().replace(",","."))

    # 3. Indices sectoriels depuis /fr/indices
    soup_idx = _soup("https://www.brvm.org/fr/indices")
    if soup_idx:
        secteur_indices: Dict[str, float] = {}
        tables = soup_idx.find_all("table")
        for table in tables:
            for row in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
                if len(cells) >= 2 and cells[0]:
                    v = _parse_num(cells[1])
                    if v and any(c.isdigit() for c in cells[1]):
                        secteur_indices[cells[0][:40]] = v
        if secteur_indices:
            stats["indices_sectoriels"] = secteur_indices

    logging.info(f"Market stats: {list(stats.keys())}")
    return stats

# ═══════════════════════════════════════════════════════════════════════════════
# C) DONNÉES FONDAMENTALES
# ═══════════════════════════════════════════════════════════════════════════════

TICKER_SLUGS: Dict[str, str] = {
    "ABJC":"air-burkina","BICB":"bic-benin","BICC":"bici-ci","BNBC":"baci",
    "BOAB":"boa-benin","BOABF":"boa-burkina-faso","BOAC":"boa-cote-divoire",
    "BOAM":"boa-mali","BOAN":"boa-niger","BOAS":"boa-senegal",
    "CABC":"sicable-ci","CBIBF":"coris-bank-international","CFAC":"cfao-motors-ci",
    "CIEC":"cie","ECOC":"ecobank-ci","ETIT":"ecobank-transnational",
    "FTSC":"filtisac","LNBB":"lonab","NEIC":"nei-ceda",
    "NSBC":"nsia-banque","NTLC":"nestle-ci","ONTBF":"onatel",
    "ORAC":"orange-ci","ORGT":"oragroup","PALC":"palmci",
    "PRSC":"prestige-ci","SAFC":"safca","SCRC":"sucrivoire",
    "SDCC":"sodeci","SDSC":"sds-ci","SEMC":"setao-ci",
    "SGBC":"sgbc","SHEC":"vivo-energy-ci","SIBC":"sibc",
    "SICC":"sicogi","SIVC":"sivop","SLBC":"solibra",
    "SMBC":"soacii","SNTS":"sonatel","SOGC":"sogb",
    "SPHC":"saph","STAC":"setaci","STBC":"sitab",
    "TTLC":"total-ci","TTLS":"total-senegal",
    "UNLC":"unilever-ci","UNXC":"uniwax",
}

def scrape_emetteur(ticker: str, slug: str) -> Dict[str, Any]:
    """Scrape la page emetteur BRVM pour un ticker."""
    url = f"https://www.brvm.org/fr/emetteurs/{slug}"
    soup = _soup(url)
    result: Dict[str, Any] = {"ticker": ticker, "source_url": url}
    if not soup:
        return result

    text = soup.get_text(" ", strip=True)

    # Capital social
    m = re.search(r"[Cc]apital\s+(?:social)?[^0-9]*([0-9][0-9 .,]+)\s*(?:F\.?C\.?F\.?A|FCFA|CFA|F CFA)", text)
    if m:
        v = _parse_num(m.group(1))
        if v:
            result["capital_social_fcfa"] = v

    # Nombre d'actions
    m = re.search(r"[Nn]ombre\s+d.actions?[^0-9]*([0-9][0-9 .,]+)", text)
    if m:
        v = _parse_num(m.group(1))
        if v:
            result["nb_actions"] = v

    # Date d'introduction
    m = re.search(r"[Ii]ntroduction[^0-9]*(\d{2}/\d{2}/\d{4}|\d{4})", text)
    if m:
        result["date_introduction"] = m.group(1)

    # Flottant
    m = re.search(r"[Ff]lottant[^0-9%]*([0-9,.]+)\s*%?", text)
    if m:
        result["flottant_pct"] = _parse_num(m.group(1))

    # Secteur
    m = re.search(r"[Ss]ecteur[^:]*:\s*([^\n·|<]{5,60})", text)
    if m:
        result["secteur_detail"] = m.group(1).strip()

    # Capitalisation depuis tables
    tables = soup.find_all("table")
    for table in tables:
        for row in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
            if len(cells) >= 2:
                label = cells[0].lower()
                val   = cells[1]
                if "capitalisation" in label:
                    v = _parse_num(val)
                    if v:
                        result["capitalisation_fcfa"] = v
                elif "actions" in label and "nombre" in label:
                    v = _parse_num(val)
                    if v:
                        result["nb_actions"] = v

    return result

def scrape_fundamentals(tickers: Optional[List[str]] = None) -> Dict[str, Dict]:
    """Scrape données fondamentales pour tous les tickers (ou liste fournie)."""
    target = tickers or list(TICKER_SLUGS.keys())
    result: Dict[str, Dict] = {}

    # Charger données existantes pour merge
    if FUNDAMENT_PATH.exists():
        try:
            with open(FUNDAMENT_PATH, encoding="utf-8") as f:
                result = json.load(f)
        except Exception:
            pass

    # Enrichir depuis live_cache (capitalisation si dispo)
    lc_path = DATA_DIR / "live_cache.json"
    if lc_path.exists():
        try:
            with open(lc_path, encoding="utf-8") as f:
                lc = json.load(f)
            for item in lc:
                t = item.get("ticker","")
                if t:
                    if t not in result:
                        result[t] = {"ticker": t}
                    result[t].setdefault("prix_actuel", item.get("price"))
                    result[t].setdefault("variation_pct", item.get("change_pct"))
        except Exception:
            pass

    # Scraper pages emetteurs
    for ticker in target:
        slug = TICKER_SLUGS.get(ticker)
        if not slug:
            continue
        logging.info(f"  Fondamentaux {ticker}...")
        data = scrape_emetteur(ticker, slug)
        # Merge avec existant
        existing = result.get(ticker, {})
        existing.update({k: v for k, v in data.items() if v is not None})
        result[ticker] = existing

    logging.info(f"Fondamentaux: {len(result)} tickers")
    return result

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="BRVM Market Data Scraper")
    parser.add_argument("--ratings-only",     action="store_true")
    parser.add_argument("--market-only",      action="store_true")
    parser.add_argument("--fundamentals-only",action="store_true")
    parser.add_argument("--ticker", default=None, help="Un seul ticker pour --fundamentals-only")
    args = parser.parse_args()

    LOG_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)

    run_all = not (args.ratings_only or args.market_only or args.fundamentals_only)

    if run_all or args.ratings_only:
        print("\n━━━ A) Notations ━━━")
        ratings = scrape_ratings()
        with open(RATINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(ratings, f, ensure_ascii=False, indent=2)
        print(f"  → {RATINGS_PATH} ({len(ratings)} notations)")

    if run_all or args.market_only:
        print("\n━━━ B) Statistiques de marché ━━━")
        stats = scrape_market_stats()
        # Historiser
        history: List[Dict] = []
        if MARKET_PATH.exists():
            try:
                with open(MARKET_PATH, encoding="utf-8") as f:
                    old = json.load(f)
                if isinstance(old, list):
                    history = old
                else:
                    history = [old]
            except Exception:
                pass
        # Ne pas dupliquer si même date
        today = stats["date"]
        history = [h for h in history if h.get("date") != today]
        history.append(stats)
        history = history[-365:]   # garder 1 an max
        with open(MARKET_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        print(f"  → {MARKET_PATH} (today: {today})")

    if run_all or args.fundamentals_only:
        print("\n━━━ C) Données fondamentales ━━━")
        tickers = [args.ticker.upper()] if args.ticker else None
        funds = scrape_fundamentals(tickers)
        with open(FUNDAMENT_PATH, "w", encoding="utf-8") as f:
            json.dump(funds, f, ensure_ascii=False, indent=2)
        print(f"  → {FUNDAMENT_PATH} ({len(funds)} tickers)")

    print("\n✓ Terminé\n")

if __name__ == "__main__":
    main()
