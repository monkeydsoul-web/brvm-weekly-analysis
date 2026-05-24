"""
external_source.py — 3e source externe : african-markets.com
Scrape dividende/action + date de paiement pour les 47 tickers BRVM.

Cache disque : data/external_dividends.json  (refresh 1x/jour, groupé avec BOC 18h30)
Dégradation gracieuse : si le site est down ou change de structure,
le système continue avec BOC+PDF sans jamais planter.
"""
import os, json, re, logging, time
from datetime import datetime, date

logger = logging.getLogger(__name__)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "data", "external_dividends.json")
_BASE_URL  = "https://www.african-markets.com/fr/bourse/brvm/listed-companies/company?code="
_UA        = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
REQUEST_DELAY   = 1.5   # s entre requêtes (rate-limiting poli)
REQUEST_TIMEOUT = 15    # s par requête


# ── Cache ──────────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    try:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning("external_source: lecture cache échouée: %s", e)
    return {}


def _save_cache(data: dict):
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("external_source: écriture cache échouée: %s", e)


# ── Scraper ────────────────────────────────────────────────────────────────

def _scrape_ticker(session, ticker: str):
    """
    Scrape african-markets pour un ticker.
    Retourne (amount_float, paid_date_str) ou (None, None) si échec.
    Le tableau dividendes est le premier tableau dont la 1re cellule
    contient un pattern comme '207.58 XOF'.
    """
    try:
        from bs4 import BeautifulSoup
        r = session.get(_BASE_URL + ticker, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if not rows:
                continue
            first_cells = [c.get_text(strip=True) for c in rows[0].find_all(["td", "th"])]
            if not first_cells:
                continue
            m = re.match(r"([\d\s\.,]+)\s*XOF", first_cells[0])
            if m:
                raw = m.group(1).replace("\xa0", "").replace(" ", "").replace(",", ".")
                try:
                    amount = float(raw)
                except ValueError:
                    continue
                paid_date = first_cells[2].strip() if len(first_cells) > 2 else None
                return amount, paid_date

    except Exception as e:
        logger.debug("external_source: %s scrape échoué: %s", ticker, e)
    return None, None


# ── API publique ────────────────────────────────────────────────────────────

def fetch_all(tickers: list, force_refresh: bool = False) -> dict:
    """
    Fetche/rafraîchit les dividendes externes pour tous les tickers.
    Utilise le cache si les données ont été scrappées aujourd'hui.
    Retourne dict: ticker → {amount, paid_date, scraped_at}
    """
    cache   = _load_cache()
    today   = date.today().isoformat()
    now_str = datetime.utcnow().isoformat()

    to_fetch = [
        t for t in tickers
        if force_refresh or cache.get(t, {}).get("scraped_at", "")[:10] < today
    ]

    if not to_fetch:
        logger.debug("external_source: cache frais, aucun scraping")
        return cache

    logger.info("external_source: scraping %d tickers (african-markets)...", len(to_fetch))

    try:
        import requests as _req
        session = _req.Session()
        session.headers.update({"User-Agent": _UA, "Accept-Language": "fr-FR,fr;q=0.9"})
    except ImportError:
        logger.warning("external_source: requests non disponible — scraping ignoré")
        return cache

    ok_count = 0
    for i, ticker in enumerate(to_fetch):
        if i > 0:
            time.sleep(REQUEST_DELAY)
        try:
            amount, paid_date = _scrape_ticker(session, ticker)
            cache[ticker] = {
                "amount":     amount,
                "paid_date":  paid_date,
                "scraped_at": now_str,
            }
            if amount is not None:
                ok_count += 1
                logger.debug("external_source: %s → %.2f XOF (%s)", ticker, amount, paid_date)
        except Exception as e:
            logger.warning("external_source: erreur inattendue %s: %s", ticker, e)

    _save_cache(cache)
    logger.info(
        "external_source: %d/%d tickers avec données, cache mis à jour",
        ok_count, len(to_fetch),
    )
    return cache


def get_cached_dividends() -> dict:
    """Retourne le cache sans déclencher de scraping (lecture seule)."""
    return _load_cache()
