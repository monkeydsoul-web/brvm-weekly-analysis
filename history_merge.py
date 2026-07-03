import json
import os

from price_history_builder import load_history

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXTENDED_PATH = os.path.join(BASE_DIR, "data", "price_history_extended.json")


def _load_extended():
    try:
        with open(EXTENDED_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_full_history(ticker):
    ticker = ticker.upper()
    extended = sorted(_load_extended().get(ticker, []), key=lambda p: p["date"])
    live = load_history().get(ticker, [])

    last_extended_date = extended[-1]["date"] if extended else None
    live_points = [
        {"date": p["date"], "close": p["price"], "volume": 0}
        for p in live
        if last_extended_date is None or p["date"] > last_extended_date
    ]

    merged = {p["date"]: p for p in extended}
    for p in live_points:
        merged.setdefault(p["date"], p)  # extended prioritaire en cas de collision

    return sorted(merged.values(), key=lambda p: p["date"])
