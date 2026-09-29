"""
Construit et maintient data/price_history.json
- Initialise depuis les prix statiques connus (HIST_PRICES annuels)
- Accumule les prix live quotidiennement
"""
import json, os, logging, tempfile
from datetime import datetime, timedelta

from paths import DATA_DIR
HISTORY_PATH = os.path.join(DATA_DIR, "price_history.json")

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
    if not history:
        logger.error("save_history: historique vide, ecriture annulee pour eviter un ecrasement")
        return
    tmp_path = None
    try:
        tmp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=os.path.dirname(HISTORY_PATH), delete=False)
        tmp_path = tmp.name
        with tmp:
            json.dump(history, tmp, ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, HISTORY_PATH)
    except Exception:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

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

def _volume_seance(data):
    if not isinstance(data, dict):
        return None
    volume = data.get("volume")
    if isinstance(volume, bool) or not isinstance(volume, (int, float)):
        return None
    if volume < 0 or volume != volume or volume in (float("inf"), float("-inf")):
        return None
    return int(volume)


def _seance_precedente(points, today):
    """Dernier point de séance avant `today`. Les points annuels ne comptent pas."""
    meilleur = None
    for point in points or []:
        if not isinstance(point, dict) or point.get("source") == "historical":
            continue
        date = point.get("date") or ""
        if not isinstance(date, str) or date >= today:
            continue
        if meilleur is None or date > (meilleur.get("date") or ""):
            meilleur = point
    return meilleur


def _meme_cours(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return False
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return False
    return float(a) == float(b)


def _reproduit_seance_precedente(history, prices, today):
    """True si chaque cours live et son volume recopient la séance précédente.

    TODO: calendrier des jours fériés BRVM. Sans calendrier, un férié en
    semaine republie souvent le dernier cours et le dernier volume pour
    toutes les valeurs : on n'ajoute pas de point ce jour-là. Dès qu'un
    ticker diffère (cours ou volume), c'est une vraie séance.
    """
    vus = 0
    if not isinstance(history, dict):
        return False
    for ticker, data in (prices or {}).items():
        if not isinstance(data, dict) or not data.get("price"):
            continue
        vus += 1
        precedent = _seance_precedente(history.get(ticker), today)
        if precedent is None or not _meme_cours(precedent.get("price"), data.get("price")):
            return False
        if _volume_seance(precedent) != _volume_seance(data):
            return False
    return vus > 0


def append_live_prices():
    """Ajoute les prix live du jour à l'historique."""
    try:
        if datetime.now().weekday() >= 5:  # PHWEEKEND-1 : pas de seance le week-end
            logger.info("append_live_prices: week-end, aucun point ecrit")
            return 0
        from live_data import get_live_data
        live = get_live_data(force_refresh=False)
        prices = live.get("prices", {})
        today = datetime.now().strftime("%Y-%m-%d")
        history = load_history()
        if not history and os.path.exists(HISTORY_PATH) and os.path.getsize(HISTORY_PATH) > 100:
            logger.error("append_live_prices: lecture vide alors qu'un fichier non trivial existe, historique probablement corrompu, ecriture annulee")
            return 0
        if _reproduit_seance_precedente(history, prices, today):
            logger.info(
                "append_live_prices: cours et volumes identiques a la seance precedente, point non ajoute"
            )
            return 0
        updated = []
        for ticker, data in prices.items():
            price = data.get("price")
            if not price:
                continue
            if ticker not in history:
                history[ticker] = []
            # Eviter doublons du même jour
            existing_dates = {p["date"] for p in history[ticker]}
            # Volume de la séance close (job 18h). Absent des points anciens :
            # le Technique le traite comme « pas de volume », pas comme zéro.
            point = {"date": today, "price": price, "source": "live"}
            volume = data.get("volume")
            if isinstance(volume, (int, float)) and not isinstance(volume, bool) and volume >= 0:
                point["volume"] = int(volume)
            if today not in existing_dates:
                history[ticker].append(point)
                updated.append(ticker)
            else:
                # Mettre à jour le prix du jour
                for p in history[ticker]:
                    if p["date"] == today:
                        p["price"] = price
                        p["source"] = "live"
                        if "volume" in point:
                            p["volume"] = point["volume"]
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
