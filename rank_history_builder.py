import json
import logging
import os
import tempfile
from datetime import datetime

logger = logging.getLogger(__name__)

from paths import DATA_DIR
LIVE_RANKING_PATH = os.path.join(DATA_DIR, "live_ranking.json")
RANK_HISTORY_PATH = os.path.join(DATA_DIR, "rank_history.json")


def _load_rank_history(strict=False):
    if not os.path.exists(RANK_HISTORY_PATH):
        return []
    try:
        with open(RANK_HISTORY_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        if strict:
            raise
        logger.warning("_load_rank_history: rank_history.json illisible, historique ignore")
        return []


def _save_rank_history(entries):
    tmp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=os.path.dirname(RANK_HISTORY_PATH), delete=False)
    tmp_path = tmp.name
    try:
        with tmp:
            json.dump(entries, tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, RANK_HISTORY_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


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
    try:
        history = _load_rank_history(strict=True)
    except Exception as exc:
        logger.error(f"append_daily_top3: rank_history.json illisible ({exc}) - ecriture annulee pour ne pas effacer l historique")
        return
    entries = [e for e in history if e.get("date") != today]
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
