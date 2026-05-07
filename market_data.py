"""
market_data.py — Données marché BRVM depuis brvm.org/fr/resume
Indices, capitalisations, top/flop, secteurs
Refresh automatique intégré au scheduler live_data
"""
import json, logging, os, time
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "data", "market_cache.json")
HEADERS    = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def clean(s):
    return s.replace("\u202f","").replace("\xa0","").replace(" ","").replace(",",".").strip()

def fetch_market_data():
    """Scrape brvm.org/fr/resume — 6 tables de données marché"""
    result = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "market_activity": {},
        "top5": [],
        "flop5": [],
        "indices": [],
        "sector_indices": [],
        "total_return": {},
    }
    try:
        r = requests.get("https://www.brvm.org/fr/resume", headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        tables = soup.find_all("table")

        # Table 0 : Activités du marché
        if len(tables) > 0:
            for row in tables[0].find_all("tr")[1:]:
                cols = row.find_all(["td","th"])
                if len(cols) >= 2:
                    label = cols[0].get_text(strip=True)
                    value = cols[1].get_text(strip=True)
                    result["market_activity"][label] = value

        # Table 1 : Top 5
        if len(tables) > 1:
            for row in tables[1].find_all("tr")[1:]:
                cols = row.find_all(["td","th"])
                if len(cols) >= 3:
                    try:
                        result["top5"].append({
                            "ticker": cols[0].get_text(strip=True).upper(),
                            "price":  float(clean(cols[1].get_text(strip=True))),
                            "change": float(clean(cols[2].get_text(strip=True)).replace("%","")),
                        })
                    except: pass

        # Table 2 : Flop 5
        if len(tables) > 2:
            for row in tables[2].find_all("tr")[1:]:
                cols = row.find_all(["td","th"])
                if len(cols) >= 3:
                    try:
                        result["flop5"].append({
                            "ticker": cols[0].get_text(strip=True).upper(),
                            "price":  float(clean(cols[1].get_text(strip=True))),
                            "change": float(clean(cols[2].get_text(strip=True)).replace("%","")),
                        })
                    except: pass

        # Table 3 : Indices BRVM
        if len(tables) > 3:
            for row in tables[3].find_all("tr")[1:]:
                cols = row.find_all(["td","th"])
                if len(cols) >= 4:
                    try:
                        result["indices"].append({
                            "name":    cols[0].get_text(strip=True),
                            "prev":    float(clean(cols[1].get_text(strip=True))),
                            "current": float(clean(cols[2].get_text(strip=True))),
                            "change":  float(clean(cols[3].get_text(strip=True)).replace("%","")),
                            "ytd":     float(clean(cols[4].get_text(strip=True)).replace("%","")) if len(cols)>4 else 0,
                        })
                    except: pass

        # Table 4 : Indices sectoriels
        if len(tables) > 4:
            for row in tables[4].find_all("tr")[1:]:
                cols = row.find_all(["td","th"])
                if len(cols) >= 4:
                    try:
                        result["sector_indices"].append({
                            "name":    cols[0].get_text(strip=True).replace("BRVM – ",""),
                            "prev":    float(clean(cols[1].get_text(strip=True))),
                            "current": float(clean(cols[2].get_text(strip=True))),
                            "change":  float(clean(cols[3].get_text(strip=True)).replace("%","")),
                            "ytd":     float(clean(cols[4].get_text(strip=True)).replace("%","")) if len(cols)>4 else 0,
                        })
                    except: pass

        # Table 5 : Total return
        if len(tables) > 5:
            for row in tables[5].find_all("tr")[1:]:
                cols = row.find_all(["td","th"])
                if len(cols) >= 3:
                    try:
                        result["total_return"] = {
                            "name":    cols[0].get_text(strip=True),
                            "prev":    float(clean(cols[1].get_text(strip=True))),
                            "current": float(clean(cols[2].get_text(strip=True))),
                            "change":  float(clean(cols[3].get_text(strip=True)).replace("%","")) if len(cols)>3 else 0,
                        }
                    except: pass

        logger.info(f"market_data: top5={len(result['top5'])} flop5={len(result['flop5'])} indices={len(result['indices'])}")
    except Exception as e:
        logger.warning(f"market_data erreur: {e}")
    return result

def save_market_cache(data):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return data

def load_market_cache():
    if not os.path.exists(CACHE_PATH): return None
    try:
        with open(CACHE_PATH) as f: return json.load(f)
    except: return None

def get_market_data(force_refresh=False):
    cache = load_market_cache()
    if cache and not force_refresh:
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(cache["updated_at"])).total_seconds()
            if age < 360: return cache
        except: pass
    return save_market_cache(fetch_market_data())

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    d = get_market_data(force_refresh=True)
    print(f"\nActivités: {d['market_activity']}")
    print(f"Top 5: {d['top5']}")
    print(f"Flop 5: {d['flop5']}")
    print(f"Indices: {d['indices']}")
    print(f"Secteurs: {d['sector_indices']}")
