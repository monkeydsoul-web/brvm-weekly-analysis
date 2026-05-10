"""
Construit et maintient data/price_history.json
- Initialise depuis les prix statiques connus (HIST_PRICES annuels)
- Accumule les prix live quotidiennement
"""
import json, os, logging
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_PATH = os.path.join(BASE_DIR, "data", "price_history.json")

logger = logging.getLogger(__name__)

# Prix annuels historiques connus (2016-2025) — source: rapports BRVM
HIST_PRICES_ANNUAL = {
    "SGBC":  [3500,3800,5200,5670,7760,9120,11090,19435,33000,34995],
    "SIBC":  [843,900,1100,1350,2000,2500,2700,3300,4800,6950],
    "SNTS":  [14000,15000,17000,18500,15000,16000,18000,19000,25000,28500],
    "CBIBF": [8000,8500,9000,9800,9900,9885,9900,10000,13500,16490],
    "NSBC":  [5000,5200,5350,5400,5350,5350,5500,7500,9000,13900],
    "BICC":  [12000,13000,14500,16000,14000,16000,18000,20000,22000,25000],
    "NTLC":  [4500,5000,5500,6000,5500,6000,7000,8000,9000,11000],
    "BOAC":  [3000,3200,3500,3800,3500,4000,4500,5000,6000,8500],
    "ETIT":  [10,12,14,16,15,18,20,22,25,28],
    "ECOC":  [8000,8500,9000,9500,9000,10000,11000,12000,14000,16000],
}
YEARS = [2016,2017,2018,2019,2020,2021,2022,2023,2024,2025]

def load_history():
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_history(history):
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False)

def init_history():
    """Initialise price_history.json depuis les données annuelles statiques."""
    history = load_history()
    changed = False
    for ticker, prices in HIST_PRICES_ANNUAL.items():
        if ticker not in history:
            history[ticker] = []
            for i, (year, price) in enumerate(zip(YEARS, prices)):
                history[ticker].append({
                    "date": f"{year}-12-31",
                    "price": price,
                    "source": "historical"
                })
            changed = True
            logger.info(f"Initialisé historique {ticker}: {len(prices)} points")
    if changed:
        save_history(history)
    return history

def append_live_prices():
    """Ajoute les prix live du jour à l'historique."""
    try:
        from live_data import get_live_data
        live = get_live_data(force_refresh=False)
        prices = live.get("prices", {})
        today = datetime.now().strftime("%Y-%m-%d")
        history = load_history()
        updated = []
        for ticker, data in prices.items():
            price = data.get("price")
            if not price:
                continue
            if ticker not in history:
                history[ticker] = []
            # Eviter doublons du même jour
            existing_dates = {p["date"] for p in history[ticker]}
            if today not in existing_dates:
                history[ticker].append({
                    "date": today,
                    "price": price,
                    "source": "live"
                })
                updated.append(ticker)
            else:
                # Mettre à jour le prix du jour
                for p in history[ticker]:
                    if p["date"] == today:
                        p["price"] = price
                        break
        save_history(history)
        logger.info(f"Historique mis à jour: {len(updated)} tickers")
        return len(updated)
    except Exception as e:
        logger.error(f"Erreur append_live_prices: {e}")
        return 0

def get_price_history(ticker, weeks=52):
    """Retourne l'historique de prix pour un ticker."""
    history = load_history()
    data = history.get(ticker.upper(), [])
    # Trier par date
    data.sort(key=lambda x: x.get("date", ""))
    return data[-weeks:]

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Initialisation de price_history.json...")
    h = init_history()
    print(f"Tickers initialisés: {len(h)}")
    print("Ajout des prix live...")
    n = append_live_prices()
    print(f"Mis à jour: {n} tickers")
    # Stats
    h = load_history()
    print(f"\nHistorique total: {len(h)} tickers")
    for t, pts in list(h.items())[:5]:
        print(f"  {t}: {len(pts)} points ({pts[0]['date']} → {pts[-1]['date']})")
