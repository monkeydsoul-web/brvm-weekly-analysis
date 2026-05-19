#!/usr/bin/env python3
"""
fetch_historical_prices.py
Scrape les cours historiques BRVM depuis les BOC PDF (brvm.org).

Source : https://www.brvm.org/sites/default/files/boc_{YYYYMMDD}_2.pdf
         (fallback sans suffixe pour les années antérieures à 2022)

Output :
  data/price_history_extended.json
  data/price_history_extended_summary.txt

Usage :
  python3 scripts/fetch_historical_prices.py
  python3 scripts/fetch_historical_prices.py --start 2020-01-01
  python3 scripts/fetch_historical_prices.py --reset-checkpoint
"""

import os, sys, json, re, io, time, logging, datetime, argparse, threading
from pathlib import Path
from typing import Optional, List, Dict

import requests
import pdfplumber

# ─── Chemins ───────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent.parent
DATA_DIR       = BASE_DIR / "data"
LOG_DIR        = BASE_DIR / "logs"
OUTPUT_PATH    = DATA_DIR / "price_history_extended.json"
SUMMARY_PATH   = DATA_DIR / "price_history_extended_summary.txt"
CHECKPOINT_PATH= DATA_DIR / "price_history_checkpoint.json"

# ─── Tickers BRVM connus ───────────────────────────────────────────────────────
TICKERS = sorted([
    "ABJC","BICB","BICC","BNBC","BOAB","BOABF","BOAC","BOAM","BOAN","BOAS",
    "CABC","CBIBF","CFAC","CIEC","ECOC","ETIT","FTSC","LNBB","NEIC","NSBC",
    "NTLC","ONTBF","ORAC","ORGT","PALC","PRSC","SAFC","SCRC","SDCC","SDSC",
    "SEMC","SGBC","SHEC","SIBC","SICC","SIVC","SLBC","SMBC","SNTS","SOGC",
    "SPHC","STAC","STBC","TTLC","TTLS","UNLC","UNXC",
])
TICKER_SET = set(TICKERS)

# Codes sectoriels dans le BOC (format post-2022)
SECTOR_CODES = {"AGR","AUT","DIS","FIN","IND","SPU","TRP"}

# ─── HTTP ──────────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
RATE_LIMIT = 1.0     # secondes entre requêtes
MAX_RETRIES = 3

_rate_lock = threading.Lock()
_last_req   = 0.0

def _get(url: str):
    """GET avec rate limiting (1 req/sec) et retry x3."""
    global _last_req
    for attempt in range(MAX_RETRIES):
        with _rate_lock:
            wait = RATE_LIMIT - (time.time() - _last_req)
            if wait > 0:
                time.sleep(wait)
            _last_req = time.time()
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            if r.status_code == 404:
                return None          # jour non-ouvré
            r.raise_for_status()
            return r
        except requests.Timeout:
            logging.warning(f"Timeout {url} (tentative {attempt+1})")
            time.sleep(2 ** attempt)
        except requests.HTTPError:
            return None
        except Exception as e:
            logging.warning(f"Erreur {url}: {e} (tentative {attempt+1})")
            time.sleep(2 ** attempt)
    return None

# ─── Parsing PDF ───────────────────────────────────────────────────────────────

def _parse_num(s):
    """Convertit '6 875' ou '6,875' → float. Renvoie None si impossible."""
    if not s or s in ("NC","SP","Val-T","Ex-d","Ex-c","Ex-coupon","","Moy."):
        return None
    try:
        return float(str(s).replace(" ","").replace(",","."))
    except ValueError:
        return None

def _extract_date_from_pdf(pdf) -> Optional[str]:
    """Extrait la date de séance depuis la première page du PDF."""
    MONTHS = {
        "janvier":1,"février":2,"fevrier":2,"mars":3,"avril":4,"mai":5,"juin":6,
        "juillet":7,"août":8,"aout":8,"septembre":9,"octobre":10,"novembre":11,
        "décembre":12,"decembre":12,
    }
    try:
        text = pdf.pages[0].extract_text() or ""
        m = re.search(
            r"(\d{1,2})\s+(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|"
            r"septembre|octobre|novembre|décembre|decembre)\s+(\d{4})",
            text, re.IGNORECASE
        )
        if m:
            day   = int(m.group(1))
            month = MONTHS.get(m.group(2).lower(), 0)
            year  = int(m.group(3))
            if month:
                return f"{year}-{month:02d}-{day:02d}"
    except Exception:
        pass
    return None

def parse_boc_pdf(content: bytes, fallback_date: str) -> dict:
    """
    Parse un PDF BOC et retourne {ticker: {close, volume, date}}.
    Gère deux formats :
      - Format A (2020-2022) : [TICKER, NAME, '', PREV, OUV, CLOT, VAR%, VOL, VAL, REF]
      - Format B (2023+)     : [SECT, TICKER, NAME, '', PREV, OUV, CLOT, VAR%, VOL, VAL, REF, ...]
    """
    results = {}
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            date_str = _extract_date_from_pdf(pdf) or fallback_date

            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or len(row) < 6:
                            continue

                        col0 = (row[0] or "").strip()
                        col1 = (row[1] or "").strip()

                        # Détecter le format
                        if col0 in SECTOR_CODES:
                            # Format B : SECT TICKER NAME '' PREV OUV CLOT VAR% VOL VAL REF
                            ticker = col1
                            if ticker not in TICKER_SET:
                                continue
                            prev = _parse_num(row[4]) if len(row) > 4 else None
                            ouv  = row[5] if len(row) > 5 else None
                            clot = row[6] if len(row) > 6 else None
                            vol  = _parse_num(row[8]) if len(row) > 8 else None
                            ref  = _parse_num(row[10]) if len(row) > 10 else None
                        elif col0 in TICKER_SET:
                            # Format A : TICKER NAME '' PREV OUV CLOT VAR% VOL VAL REF
                            ticker = col0
                            prev = _parse_num(row[3]) if len(row) > 3 else None
                            ouv  = row[4] if len(row) > 4 else None
                            clot = row[5] if len(row) > 5 else None
                            vol  = _parse_num(row[7]) if len(row) > 7 else None
                            ref  = _parse_num(row[9]) if len(row) > 9 else None
                        else:
                            continue

                        # Résoudre le cours de clôture
                        close = _parse_num(clot)
                        if close is None:
                            # NC/SP : utiliser cours de référence ou cours précédent
                            close = ref if ref else prev
                        if not close or close <= 0:
                            continue

                        results[ticker] = {
                            "close":  int(round(close)),
                            "volume": int(vol) if vol else 0,
                            "date":   date_str,
                        }
    except Exception as e:
        logging.error(f"Erreur parsing PDF {fallback_date}: {e}")
    return results

# ─── URL BOC ───────────────────────────────────────────────────────────────────

def boc_url(date: datetime.date) -> List[str]:
    """Retourne les URLs candidates pour un BOC PDF (priorité décroissante)."""
    d = date.strftime("%Y%m%d")
    base = "https://www.brvm.org/sites/default/files"
    # Suffixe _2 dominant depuis ~2022 ; sans suffixe pour 2020-2021
    return [
        f"{base}/boc_{d}_2.pdf",
        f"{base}/boc_{d}.pdf",
        f"{base}/boc_{d}_1.pdf",
    ]

# ─── Dates ─────────────────────────────────────────────────────────────────────

def trading_dates(start: datetime.date, end: datetime.date) -> List[datetime.date]:
    """Renvoie tous les jours ouvrés (lun-ven) entre start et end."""
    dates, d = [], start
    while d <= end:
        if d.weekday() < 5:
            dates.append(d)
        d += datetime.timedelta(days=1)
    return dates

# ─── Checkpoint ────────────────────────────────────────────────────────────────

def load_checkpoint() -> set:
    if CHECKPOINT_PATH.exists():
        with open(CHECKPOINT_PATH) as f:
            return set(json.load(f))
    return set()

def save_checkpoint(done: set):
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump(sorted(done), f)

# ─── Résumé ────────────────────────────────────────────────────────────────────

def generate_summary(history: dict) -> str:
    lines = [
        "BRVM — Historique cours étendu",
        "=" * 50,
        f"Généré le {datetime.date.today().isoformat()}",
        "",
    ]
    total_pts = sum(len(v) for v in history.values())
    tickers_with_data = [t for t in TICKERS if history.get(t)]
    lines.append(f"Tickers avec données : {len(tickers_with_data)}/{len(TICKERS)}")
    lines.append(f"Total points         : {total_pts:,}")
    lines.append("")
    lines.append(f"{'Ticker':<10} {'Points':>6}  {'Début':>12}  {'Fin':>12}")
    lines.append("-" * 46)
    insufficient = []
    for t in TICKERS:
        pts = history.get(t, [])
        n = len(pts)
        if n == 0:
            lines.append(f"  {t:<8}  {n:>5}  {'—':>12}  {'—':>12}")
            insufficient.append(t)
        else:
            dates = sorted(p["date"] for p in pts)
            lines.append(f"  {t:<8}  {n:>5}  {dates[0]:>12}  {dates[-1]:>12}")
            if n < 30:
                insufficient.append(t)
    lines.append("")
    lines.append(f"Tickers < 30 points ({len(insufficient)}) :")
    lines.append("  " + (", ".join(insufficient) if insufficient else "aucun"))
    return "\n".join(lines)

# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape BRVM historical prices via BOC PDFs")
    parser.add_argument("--start", default="2023-01-02",
                        help="Date de début (défaut: 2023-01-02)")
    parser.add_argument("--end", default=datetime.date.today().isoformat(),
                        help="Date de fin (défaut: aujourd'hui)")
    parser.add_argument("--reset-checkpoint", action="store_true",
                        help="Ignorer le checkpoint existant et tout re-télécharger")
    args = parser.parse_args()

    # Logging
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_DIR / "fetch_historical.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Réduire la verbosité de pdfplumber
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    logging.getLogger("pdfplumber").setLevel(logging.ERROR)

    start = datetime.date.fromisoformat(args.start)
    end   = datetime.date.fromisoformat(args.end)

    # Charger données existantes
    history = {}  # type: Dict[str, list]
    if OUTPUT_PATH.exists():
        with open(OUTPUT_PATH) as f:
            history = json.load(f)
        n_pts = sum(len(v) for v in history.values())
        logging.info(f"Données existantes chargées : {n_pts:,} points sur {len(history)} tickers")

    # Checkpoint
    processed = set() if args.reset_checkpoint else load_checkpoint()

    # Liste des dates à traiter
    all_dates = trading_dates(start, end)
    pending   = [d for d in all_dates if d.isoformat() not in processed]

    print(f"\n{'━'*62}")
    print(f"  BRVM Historical Price Scraper")
    print(f"  Période : {start} → {end}  ({len(all_dates)} jours ouvrés)")
    print(f"  Déjà traités : {len(processed)}  |  À traiter : {len(pending)}")
    est = len(pending) * (RATE_LIMIT + 0.8)
    print(f"  Durée estimée : ~{est/60:.0f} min  (1 req/sec)")
    print(f"{'━'*62}\n")

    if not pending:
        logging.info("Aucune nouvelle date à traiter.")
    else:
        success = skip = errors = 0

        for idx, date in enumerate(pending):
            date_str = date.isoformat()

            # Tenter les URLs candidates
            day_data = None
            for url in boc_url(date):
                resp = _get(url)
                if resp is not None:
                    day_data = parse_boc_pdf(resp.content, date_str)
                    if day_data:
                        break

            if not day_data:
                skip += 1
                status = "—  (jour non-ouvré)"
            else:
                # Fusionner dans history
                seen_dates: dict[str, set] = {}
                for ticker in history:
                    seen_dates[ticker] = {p["date"] for p in history[ticker]}

                added = 0
                for ticker, data in day_data.items():
                    if ticker not in history:
                        history[ticker] = []
                        seen_dates[ticker] = set()
                    if date_str not in seen_dates[ticker]:
                        history[ticker].append({
                            "date":   date_str,
                            "close":  data["close"],
                            "volume": data["volume"],
                        })
                        seen_dates[ticker].add(date_str)
                        added += 1

                success += 1
                status = f"✓  {len(day_data)} tickers  (+{added} points)"

            print(f"  [{idx+1:4d}/{len(pending)}]  {date_str}  {status}")

            processed.add(date_str)

            # Sauvegarde partielle toutes les 10 PDFs réussis
            if success % 10 == 0 and success > 0:
                _save_all(history, processed)

        logging.info(f"\nTerminé — succès:{success}  ignorés:{skip}  erreurs:{errors}")

    # Sauvegarde finale
    _save_all(history, processed)

    # Résumé
    summary = generate_summary(history)
    with open(SUMMARY_PATH, "w") as f:
        f.write(summary)
    print(f"\n{summary}")
    print(f"\n  Données → {OUTPUT_PATH}")
    print(f"  Résumé  → {SUMMARY_PATH}")


def _save_all(history: dict, processed: set):
    """Tri + sauvegarde JSON + checkpoint."""
    for ticker in history:
        history[ticker].sort(key=lambda x: x["date"])
    with open(OUTPUT_PATH, "w") as f:
        json.dump(history, f, ensure_ascii=False, separators=(",", ":"))
    save_checkpoint(processed)


if __name__ == "__main__":
    main()
