#!/usr/bin/env python3
"""
brvm_news_scraper.py
Scrape les annonces officielles BRVM depuis brvm.org.

Sources :
  1. Paiements de dividendes
  2. Convocations AG
  3. Notations financières
  4. Communiqués
  5. Changements de dirigeants
  6. Franchissements de seuil
  7. Avis et publications
  8. Rapports sociétés cotées

Output : data/brvm_announcements.json
Usage  :
  python3 scripts/brvm_news_scraper.py
  python3 scripts/brvm_news_scraper.py --incremental
  python3 scripts/brvm_news_scraper.py --reset
"""

import os, sys, json, re, io, time, logging, datetime, argparse, threading
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    import pdfplumber
    HAS_PDF = True
except ImportError:
    HAS_PDF = False
    logging.warning("pdfplumber non installé — PDFs non lus")

# ── Chemins ───────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent.parent
DATA_DIR        = BASE_DIR / "data"
DOCS_DIR        = DATA_DIR / "brvm_docs"
OUTPUT_PATH     = DATA_DIR / "brvm_announcements.json"
CHECKPOINT_PATH = DATA_DIR / "brvm_news_checkpoint.json"
LOG_DIR         = BASE_DIR / "logs"

# ── Sources ───────────────────────────────────────────────────────────────────
SOURCES = {
    "dividendes": {
        "url":   "https://www.brvm.org/fr/esv/paiement-de-dividendes",
        "label": "Paiements de dividendes",
    },
    "convocations_ag": {
        "url":   "https://www.brvm.org/fr/emetteurs/type-annonces/convocations-assemblees-generales",
        "label": "Convocations AG",
    },
    "notations": {
        "url":   "https://www.brvm.org/fr/emetteurs/type-annonces/notations-financieres",
        "label": "Notations financières",
    },
    "communiques": {
        "url":   "https://www.brvm.org/fr/emetteurs/type-annonces/communiques",
        "label": "Communiqués",
    },
    "dirigeants": {
        "url":   "https://www.brvm.org/fr/emetteurs/type-annonces/changements-de-dirigeants",
        "label": "Changements de dirigeants",
    },
    "franchissements": {
        "url":   "https://www.brvm.org/fr/emetteurs/type-annonces/franchissements-de-seuil",
        "label": "Franchissements de seuil",
    },
    "avis": {
        "url":   "https://www.brvm.org/fr/marche/avis-et-publications/avis",
        "label": "Avis et publications",
    },
    "rapports": {
        "url":   "https://www.brvm.org/fr/rapports-societes-cotees",
        "label": "Rapports sociétés cotées",
    },
}

TICKERS = sorted([
    "ABJC","BICB","BICC","BNBC","BOAB","BOABF","BOAC","BOAM","BOAN","BOAS",
    "CABC","CBIBF","CFAC","CIEC","ECOC","ETIT","FTSC","LNBB","NEIC","NSBC",
    "NTLC","ONTBF","ORAC","ORGT","PALC","PRSC","SAFC","SCRC","SDCC","SDSC",
    "SEMC","SGBC","SHEC","SIBC","SICC","SIVC","SLBC","SMBC","SNTS","SOGC",
    "SPHC","STAC","STBC","TTLC","TTLS","UNLC","UNXC",
])

# ── HTTP ──────────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
RATE_LIMIT  = 1.5
MAX_RETRIES = 3
BRVM_BASE   = "https://www.brvm.org"

_rate_lock = threading.Lock()
_last_req  = 0.0

def _get(url: str, binary: bool = False) -> Optional[requests.Response]:
    global _last_req
    for attempt in range(MAX_RETRIES):
        with _rate_lock:
            wait = RATE_LIMIT - (time.time() - _last_req)
            if wait > 0:
                time.sleep(wait)
            _last_req = time.time()
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r
        except requests.Timeout:
            logging.warning(f"Timeout {url} (tentative {attempt+1})")
            time.sleep(2 ** attempt)
        except requests.HTTPError as e:
            logging.warning(f"HTTP {e.response.status_code} — {url}")
            return None
        except Exception as e:
            logging.warning(f"Erreur {url}: {e} (tentative {attempt+1})")
            time.sleep(2 ** attempt)
    return None

# ── Détection de ticker dans du texte ─────────────────────────────────────────
_TICKER_RE = re.compile(r'\b(' + '|'.join(TICKERS) + r')\b')

def _find_ticker(text: str) -> Optional[str]:
    m = _TICKER_RE.search(text.upper())
    return m.group(1) if m else None

# ── Parsing date ───────────────────────────────────────────────────────────────
_MONTHS_FR = {
    "janvier":1,"février":2,"fevrier":2,"mars":3,"avril":4,"mai":5,"juin":6,
    "juillet":7,"août":8,"aout":8,"septembre":9,"octobre":10,"novembre":11,
    "décembre":12,"decembre":12,
    "jan":1,"fév":2,"fev":2,"mar":3,"avr":4,"jui":6,"jul":7,"aoû":8,"sep":9,"oct":10,"nov":11,"déc":12,"dec":12,
}

def _parse_date(text: str) -> Optional[str]:
    if not text:
        return None
    text = text.strip()
    # ISO: 2024-06-15
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # French: 15 juin 2024 or 15/06/2024 or 15-06-2024
    m = re.search(r'(\d{1,2})[\s/\-](\d{2})[\s/\-](\d{4})', text)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    m = re.search(r'(\d{1,2})\s+([a-zéûôàèî]+)\.?\s+(\d{4})', text, re.I)
    if m:
        day   = int(m.group(1))
        month = _MONTHS_FR.get(m.group(2).lower().rstrip('.'), 0)
        year  = int(m.group(3))
        if month:
            return f"{year}-{month:02d}-{day:02d}"
    return None

# ── Extraction montant dividende ───────────────────────────────────────────────
def _extract_dividend_amount(text: str) -> Optional[int]:
    patterns = [
        r'(\d[\d\s]+)\s*(?:FCFA|XOF|francs?)',
        r'dividende[^:]*:\s*(\d[\d\s]+)',
        r'montant[^:]*:\s*(\d[\d\s]+)',
        r'(\d[\d\s]+)\s*F\b',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            val = re.sub(r'\s', '', m.group(1))
            try:
                v = int(val)
                if 10 <= v <= 100_000_000:
                    return v
            except ValueError:
                pass
    return None

# ── Extraction seuil de franchissement ────────────────────────────────────────
def _extract_threshold_pct(text: str) -> Optional[float]:
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*%', text)
    if m:
        try:
            return float(m.group(1).replace(',', '.'))
        except ValueError:
            pass
    return None

# ── PDF download + lecture ─────────────────────────────────────────────────────
def _download_pdf(url: str, dest_dir: Path, filename: str) -> Optional[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    if dest.exists():
        return dest
    r = _get(url)
    if r is None:
        return None
    if b'%PDF' not in r.content[:10]:
        return None
    dest.write_bytes(r.content)
    return dest

def _read_pdf(path: Path, max_chars: int = 3000) -> str:
    if not HAS_PDF or not path or not path.exists():
        return ""
    try:
        with pdfplumber.open(path) as pdf:
            text = "\n".join(
                (p.extract_text() or "") for p in pdf.pages[:6]
            )
        return text[:max_chars].strip()
    except Exception as e:
        logging.warning(f"PDF lecture {path}: {e}")
        return ""

# ── Parsing liste BRVM (format Drupal) ────────────────────────────────────────
def _parse_list_page(html: str, source_key: str) -> List[Dict[str, Any]]:
    """Extrait les items d'une page de liste BRVM."""
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # Table rows (format dividendes)
    for row in soup.select("table tbody tr, .views-row, article, .node--type-annonce"):
        item = _parse_row_or_node(row, source_key)
        if item:
            items.append(item)

    # Si table vide, essayer les liens de liste génériques
    if not items:
        for link in soup.select("a[href*='/fr/']"):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if not text or len(text) < 10:
                continue
            full_url = urljoin(BRVM_BASE, href)
            items.append({
                "titre": text,
                "date": _parse_date(text),
                "ticker": _find_ticker(text),
                "detail_url": full_url,
                "pdf_url": None,
            })

    return items

def _parse_row_or_node(tag, source_key: str) -> Optional[Dict[str, Any]]:
    text = tag.get_text(" ", strip=True)
    if len(text) < 5:
        return None

    titre = ""
    date_str = None
    ticker = None
    detail_url = None
    pdf_url = None

    # Titre : premier lien ou premier <h*>
    link = tag.select_one("a")
    if link:
        titre = link.get_text(strip=True)
        href = link.get("href", "")
        full = urljoin(BRVM_BASE, href)
        if href.lower().endswith(".pdf"):
            pdf_url = full
        else:
            detail_url = full

    if not titre:
        titre = text[:120]

    # Date : chercher dans toutes les cellules / spans
    for sel in ["time", ".date-display-single", "td:nth-child(1)", ".views-field-field-date"]:
        el = tag.select_one(sel)
        if el:
            d = _parse_date(el.get_text(strip=True) or el.get("datetime", ""))
            if d:
                date_str = d
                break
    if not date_str:
        date_str = _parse_date(text)

    ticker = _find_ticker(titre + " " + text)

    if not titre:
        return None
    return {
        "titre": titre,
        "date": date_str,
        "ticker": ticker,
        "detail_url": detail_url,
        "pdf_url": pdf_url,
    }

def _has_next_page(html: str, page: int) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    # Pager Drupal
    nxt = soup.select_one("li.pager__item--next a, a[rel='next'], .pager-next a")
    if nxt:
        return True
    # Ou présence d'items et page actuelle active
    active = soup.select_one(".pager__item--active, .pager-current")
    if active:
        try:
            cur = int(re.search(r'\d+', active.get_text()).group())
            return cur >= page
        except Exception:
            pass
    return False

# ── Fetch page de détail ───────────────────────────────────────────────────────
def _fetch_detail(url: str) -> Dict[str, str]:
    if not url:
        return {}
    r = _get(url)
    if not r:
        return {}
    soup = BeautifulSoup(r.text, "html.parser")
    # Corps principal
    body = soup.select_one(".field--type-text-with-summary, .node__content, article, main")
    content = body.get_text("\n", strip=True) if body else soup.get_text("\n", strip=True)

    # Lien PDF dans la page de détail
    pdf_link = None
    for a in soup.select("a[href$='.pdf'], a[href*='/sites/default/files/']"):
        pdf_link = urljoin(BRVM_BASE, a["href"])
        break

    return {"contenu": content[:4000], "pdf_url_from_detail": pdf_link}

# ── Enrichissement selon la source ────────────────────────────────────────────
def _enrich(item: Dict, source_key: str, content: str) -> Dict:
    combined = (item.get("titre", "") + " " + content).upper()

    if source_key == "dividendes":
        item["montant_xof"] = _extract_dividend_amount(content)
        # Date de paiement spécifique
        m = re.search(r"(?:paiement|mise en paiement)[^:]*:?\s*(\d{1,2}[^\d]+\d{4})", content, re.I)
        item["date_paiement"] = _parse_date(m.group(1)) if m else None

    elif source_key == "dirigeants":
        for kw in ["nomm", "révoqué", "démission", "président", "directeur"]:
            if kw in content.lower():
                item["type_changement"] = kw
                break

    elif source_key == "notations":
        m = re.search(r"not(?:ation|e)[^:]*:?\s*([A-Z][A-Z0-9+\-]{0,4})", content, re.I)
        item["notation"] = m.group(1) if m else None

    elif source_key == "franchissements":
        item["seuil_pct"] = _extract_threshold_pct(content)

    elif source_key == "rapports":
        m = re.search(r"(?:rapport|exercice|année)\s+(\d{4})", content, re.I)
        item["annee"] = m.group(1) if m else None

    return item

# ── Scraper principal ──────────────────────────────────────────────────────────
def scrape_source(source_key: str, source_cfg: dict, incremental: bool,
                  known_urls: set, checkpoint: dict) -> List[Dict]:
    base_url = source_cfg["url"]
    label    = source_cfg["label"]
    docs_dir = DOCS_DIR / source_key
    results  = []
    page     = 0
    empty_pages = 0

    logging.info(f"\n{'─'*50}")
    logging.info(f"  Source : {label}")
    logging.info(f"{'─'*50}")

    while True:
        page_url = f"{base_url}?page={page}"
        ck_key   = f"{source_key}::p{page}"

        if ck_key in checkpoint and incremental:
            logging.debug(f"  [skip] {page_url} (checkpoint)")
            page += 1
            continue

        r = _get(page_url)
        if r is None:
            logging.info(f"  Page {page} → 404/vide — fin source")
            break

        items = _parse_list_page(r.text, source_key)
        if not items:
            empty_pages += 1
            if empty_pages >= 3:
                logging.info(f"  3 pages vides consécutives — fin source")
                break
            page += 1
            continue
        else:
            empty_pages = 0

        logging.info(f"  Page {page} → {len(items)} items")

        for item in items:
            url_key = item.get("detail_url") or item.get("pdf_url") or item.get("titre", "")
            if incremental and url_key in known_urls:
                continue

            # Fetch détail HTML si pas de PDF direct
            detail = {}
            if item.get("detail_url") and not item.get("pdf_url"):
                detail = _fetch_detail(item["detail_url"])
                if detail.get("pdf_url_from_detail"):
                    item["pdf_url"] = detail["pdf_url_from_detail"]

            content = detail.get("contenu", "")

            # Download + lecture PDF
            pdf_path = None
            pdf_text = ""
            if item.get("pdf_url"):
                ticker_dir = item.get("ticker") or "UNKNOWN"
                pdf_name   = os.path.basename(urlparse(item["pdf_url"]).path) or "doc.pdf"
                dest       = docs_dir / ticker_dir / pdf_name
                dl         = _download_pdf(item["pdf_url"], dest.parent, pdf_name)
                if dl:
                    pdf_path = str(dl.relative_to(BASE_DIR))
                    pdf_text = _read_pdf(dl)
                    if not content:
                        content = pdf_text

            item["contenu"]   = content[:2000] if content else ""
            item["pdf_path"]  = pdf_path
            item["source_url"]= item.get("detail_url") or item.get("pdf_url") or page_url
            item = _enrich(item, source_key, content)

            # Nettoyer les clés internes
            item.pop("detail_url", None)
            item.pop("pdf_url", None)

            results.append(item)
            if url_key:
                known_urls.add(url_key)

        checkpoint[ck_key] = datetime.date.today().isoformat()

        # Sauvegarde checkpoint toutes les 20 pages
        if page > 0 and page % 20 == 0:
            _save_checkpoint(checkpoint)

        if not _has_next_page(r.text, page):
            logging.info(f"  Dernière page ({page}) — fin source")
            break

        page += 1

    logging.info(f"  → {len(results)} nouvelles annonces")
    return results

# ── Checkpoint ────────────────────────────────────────────────────────────────
def _load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        try:
            with open(CHECKPOINT_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_checkpoint(data: dict):
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Scraper annonces officielles BRVM")
    parser.add_argument("--incremental", action="store_true",
                        help="Ne télécharger que les nouvelles annonces")
    parser.add_argument("--reset", action="store_true",
                        help="Réinitialiser checkpoint et données")
    parser.add_argument("--source", default=None,
                        help="Scraper une seule source (ex: dividendes)")
    args = parser.parse_args()

    LOG_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    DOCS_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_DIR / "brvm_news_scraper.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("requests").setLevel(logging.ERROR)

    if args.reset:
        if CHECKPOINT_PATH.exists():
            CHECKPOINT_PATH.unlink()
        if OUTPUT_PATH.exists():
            OUTPUT_PATH.unlink()
        logging.info("Checkpoint et données réinitialisés")

    # Charger données existantes
    existing: Dict[str, List] = {}
    if OUTPUT_PATH.exists() and not args.reset:
        try:
            with open(OUTPUT_PATH) as f:
                existing = json.load(f)
        except Exception:
            pass

    # Index des URLs déjà connues
    known_urls: set = set()
    for key_items in existing.values():
        for item in key_items:
            u = item.get("source_url", "")
            if u:
                known_urls.add(u)

    checkpoint = _load_checkpoint()

    print(f"\n{'━'*60}")
    print(f"  BRVM Annonces Scraper")
    print(f"  Mode : {'incrémental' if args.incremental else 'complet'}")
    print(f"  Annonces existantes : {sum(len(v) for v in existing.values())}")
    print(f"{'━'*60}\n")

    sources_to_run = SOURCES
    if args.source:
        if args.source not in SOURCES:
            print(f"Source inconnue: {args.source}. Disponibles: {list(SOURCES)}")
            sys.exit(1)
        sources_to_run = {args.source: SOURCES[args.source]}

    for key, cfg in sources_to_run.items():
        new_items = scrape_source(key, cfg, args.incremental, known_urls, checkpoint)
        existing.setdefault(key, [])
        # Dédupliquer par source_url
        seen = {i.get("source_url") for i in existing[key]}
        for item in new_items:
            if item.get("source_url") not in seen:
                existing[key].append(item)
                seen.add(item.get("source_url"))

    # Tri par date décroissante
    for key in existing:
        existing[key].sort(key=lambda x: x.get("date") or "0000", reverse=True)

    # Sauvegarde finale
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    _save_checkpoint(checkpoint)

    total = sum(len(v) for v in existing.values())
    print(f"\n{'━'*60}")
    print(f"  Total annonces : {total}")
    for k, v in existing.items():
        print(f"    {k:<20} {len(v):>4}")
    print(f"  Sauvegardé → {OUTPUT_PATH}")
    print(f"{'━'*60}\n")


if __name__ == "__main__":
    main()
