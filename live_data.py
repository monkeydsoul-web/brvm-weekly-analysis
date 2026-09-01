"""
live_data.py — Données live BRVM
Source : brvm.org Table 3
"""
import json, logging, os, tempfile, time, threading
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
from paths import DATA_DIR
CACHE_PATH = os.path.join(DATA_DIR, "live_cache.json")
_FETCH_LOCK = threading.Lock()
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def is_market_open():
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5: return False
    if now.hour < 9: return False
    if now.hour > 15: return False
    if now.hour == 15 and now.minute >= 30: return False
    return True

def fetch_brvm_org():
    results = {}
    try:
        r = requests.get("https://www.brvm.org/fr/cours-actions/0/appm", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        tables = soup.find_all("table")
        if len(tables) < 4:
            logger.warning(f"brvm.org: {len(tables)} tables seulement")
            return results
        for row in tables[3].find_all("tr")[1:]:
            cols = row.find_all(["td","th"])
            if len(cols) < 7: continue
            try:
                ticker = cols[0].get_text(strip=True).upper()
                def clean(s): return s.get_text(strip=True).replace(" ","").replace("\u202f","").replace(",",".")
                close  = float(clean(cols[5])) if clean(cols[5]) else None
                change = float(clean(cols[6]).replace("%","")) if clean(cols[6]) else 0.0
                open_price = float(clean(cols[3])) if clean(cols[3]) else None
                vol    = clean(cols[2])
                try: volume = int(vol)
                except: volume = 0
                if ticker and close and close > 0:
                    results[ticker] = {"price": close, "open": open_price, "change_pct": change,
                                       "volume": volume, "source": "brvm.org",
                                       "fetched_at": datetime.now(timezone.utc).isoformat()}
            except: continue
        # Tags top/flop
        for i, label in [(0,"top"),(1,"flop")]:
            for row in tables[i].find_all("tr")[1:]:
                cols = row.find_all(["td","th"])
                if cols:
                    t = cols[0].get_text(strip=True).upper()
                    if t in results: results[t]["trend"] = label
        logger.info(f"brvm.org: {len(results)} tickers")
    except Exception as e:
        logger.warning(f"brvm.org erreur: {e}")
    return results

def fetch_live_prices(all_tickers=None):
    if all_tickers is None:
        try:
            from scraper import STOCK_FUNDAMENTALS
            all_tickers = list(STOCK_FUNDAMENTALS.keys())
        except: all_tickers = []
    start = time.time()
    results = fetch_brvm_org()
    for t in all_tickers:
        if t not in results:
            results[t] = {"price": None, "change_pct": 0.0, "source": "unavailable", "fetched_at": None}
    n_ok = len([v for v in results.values() if v.get("price")])
    logger.info(f"Fetch {round(time.time()-start,1)}s — {n_ok}/{len(results)} prix")
    return results

def save_cache(prices_dict):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    sources = {}
    for v in prices_dict.values():
        s = v.get("source","unavailable"); sources[s] = sources.get(s,0)+1
    try:
        from scraper import STOCK_FUNDAMENTALS
        _inconnus = sorted(set(prices_dict.keys()) - set(STOCK_FUNDAMENTALS.keys()))
    except Exception:
        _inconnus = None
    if _inconnus:
        logger.warning("save_cache: %d ticker(s) cote(s) hors perimetre : %s", len(_inconnus), ", ".join(_inconnus))
    payload = {"updated_at": datetime.now(timezone.utc).isoformat(), "market_open": is_market_open(),
               "prices": prices_dict, "stats": {"total": len(prices_dict),
               "with_price": len([v for v in prices_dict.values() if v.get("price")]), "sources": sources,
               "unknown_tickers": _inconnus}}
    n_ok = payload["stats"]["with_price"]
    if n_ok == 0:
        ancien = load_cache()
        if ancien and ancien.get("stats", {}).get("with_price", 0) > 0:
            logger.error("save_cache: 0 prix valide, ecriture annulee pour ne pas ecraser un cache existant")
            return ancien
    tmp_path = None
    try:
        tmp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=os.path.dirname(CACHE_PATH), delete=False)
        tmp_path = tmp.name
        with tmp:
            json.dump(payload, tmp, indent=2, ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, CACHE_PATH)
    except Exception:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    return payload

def load_cache():
    if not os.path.exists(CACHE_PATH): return None
    try:
        with open(CACHE_PATH) as f: return json.load(f)
    except: return None

def get_live_data(force_refresh=False):
    cache = load_cache()
    if cache and not force_refresh:
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(cache["updated_at"])).total_seconds()
            if age < 360: return cache
        except: pass
    if not _FETCH_LOCK.acquire(blocking=False):
        if cache:
            logger.info("get_live_data: recuperation deja en cours, cache existant servi")
            return cache
        _FETCH_LOCK.acquire()
    try:
        return save_cache(fetch_live_prices())
    finally:
        _FETCH_LOCK.release()

def start_scheduler():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        def job():
            if is_market_open(): get_live_data(force_refresh=True)
        s = BackgroundScheduler(daemon=True)
        s.add_job(job, "interval", minutes=5, id="live_refresh", replace_existing=True)
        s.start()
        logger.info("APScheduler démarré")
        threading.Thread(target=lambda: get_live_data(force_refresh=True), daemon=True).start()
        return s
    except ImportError:
        threading.Thread(target=lambda: get_live_data(force_refresh=True), daemon=True).start()
        return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    data = get_live_data(force_refresh=True)
    stats = data.get("stats",{})
    prices = data.get("prices",{})
    print(f"\nTotal : {stats.get('with_price')}/{stats.get('total')} prix")
    print(f"Sources : {stats.get('sources')}")
    print(f"Marché : {'OUVERT' if data.get('market_open') else 'FERME'}")
    print("\nSample:")
    for t,v in list(prices.items())[:10]:
        if v.get("price"):
            print(f"  {t:8s} {v['price']:>10,.0f} FCFA  {v.get('change_pct',0):+.2f}%  [{v['source']}]")
