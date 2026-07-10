import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

from paths import DATA_DIR
LIVE_RANKING_PATH = os.path.join(DATA_DIR, "live_ranking.json")
RANK_HISTORY_PATH = os.path.join(DATA_DIR, "rank_history.json")


def _load_rank_history():
    if os.path.exists(RANK_HISTORY_PATH):
        try:
            with open(RANK_HISTORY_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_rank_history(entries):
    with open(RANK_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def append_daily_top3():
    if datetime.now().weekday() >= 5:
        logger.info("append_daily_top3: week-end (BRVM fermée), skip")
        return

    if not os.path.exists(LIVE_RANKING_PATH):
        logger.warning("append_daily_top3: live_ranking.json absent")
        return
    try:
        with open(LIVE_RANKING_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"append_daily_top3: live_ranking.json illisible ({e})")
        return

    ranking = data.get("ranking", [])
    if not ranking:
        logger.warning("append_daily_top3: ranking vide")
        return

    top3 = sorted(ranking, key=lambda r: r.get("rank", 999))[:3]
    top3_entry = [
        {"ticker": r.get("ticker"), "rank": r.get("rank"), "note": r.get("note")}
        for r in top3
    ]

    today = datetime.now().strftime("%Y-%m-%d")
    entries = [e for e in _load_rank_history() if e.get("date") != today]
    entries.append({"date": today, "top3": top3_entry})
    entries.sort(key=lambda e: e["date"])
    _save_rank_history(entries)


def compute_top3_constance():
    entries = _load_rank_history()
    if not entries:
        return {"days": 0, "since": None, "podium": []}

    days = len(entries)
    since = entries[0]["date"]
    counts = {}
    for e in entries:
        for t in e.get("top3", []):
            ticker = t.get("ticker")
            if ticker:
                counts[ticker] = counts.get(ticker, 0) + 1

    podium = [
        {"ticker": ticker, "pct": round(count / days * 100, 1), "jours": count}
        for ticker, count in counts.items()
    ]
    podium.sort(key=lambda p: p["pct"], reverse=True)
    return {"days": days, "since": since, "podium": podium[:3]}
