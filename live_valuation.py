"""
live_valuation.py — Recalcul du score /80 avec prix live brvm.org
Enveloppe valuation.py sans le modifier.
Injecte le prix live dans le row avant appel des 7 modèles + score technique.
"""

import logging
from valuation import (
    score_graham, score_dcf, score_ddm, score_epv,
    score_buffett, score_reverse_dcf, score_relative,
    GEO_RISK_PENALTY,
)

logger = logging.getLogger(__name__)

_score_cache = {}
_CACHE_TTL = 300

def _get_cached(ticker):
    import time
    entry = _score_cache.get(ticker)
    if entry and (time.time() - entry['ts']) < _CACHE_TTL:
        return entry['data']
    return None

def _set_cached(ticker, data):
    import time
    _score_cache[ticker] = {'ts': time.time(), 'data': data}


# ──────────────────────────────────────────────────────────────────────────────
# Score technique /10 — momentum prix live
# ──────────────────────────────────────────────────────────────────────────────
def score_technique_live(row: dict) -> dict:
    """
    Score technique /10 basé sur les données live :
    - Variation jour (change_pct)
    - Momentum vs veille (prix vs prev_close)
    - Volume relatif
    """
    score = 0.0
    details = []

    change_pct  = row.get("change_pct", 0) or 0
    price       = row.get("price") or 0
    prev_close  = row.get("prev_close") or price
    volume      = row.get("volume", 0) or 0

    # Variation du jour
    if change_pct >= 3:
        score += 3.0
        details.append(f"Variation={change_pct:+.1f}% ✓✓")
    elif change_pct >= 1:
        score += 2.0
        details.append(f"Variation={change_pct:+.1f}% ✓")
    elif change_pct >= -1:
        score += 1.0
        details.append(f"Variation={change_pct:+.1f}% neutre")
    elif change_pct >= -3:
        score += 0.0
        details.append(f"Variation={change_pct:+.1f}% ✗")
    else:
        score -= 1.0
        details.append(f"Variation={change_pct:+.1f}% forte baisse ✗✗")

    # Prix au-dessus de la veille = momentum positif
    if prev_close and prev_close > 0:
        above = (price / prev_close - 1) * 100
        if above > 2:
            score += 3.0
            details.append(f"Au-dessus veille +{above:.1f}% ✓✓")
        elif above > 0:
            score += 2.0
            details.append(f"Au-dessus veille +{above:.1f}% ✓")
        elif above > -2:
            score += 1.0
            details.append("En ligne avec veille")
        else:
            details.append(f"En dessous veille {above:.1f}% ✗")

    # Volume : signal de liquidité (bonus si > 0)
    if volume > 10000:
        score += 2.0
        details.append(f"Volume={volume:,} — Liquide ✓✓")
    elif volume > 1000:
        score += 1.0
        details.append(f"Volume={volume:,} — Correct ✓")
    elif volume > 0:
        score += 0.5
        details.append(f"Volume={volume:,} — Faible")
    else:
        details.append("Volume=0 — Pas d'échange ✗")

    # Trend top5/flop5 brvm.org
    trend = row.get("trend")
    if trend == "top":
        score += 2.0
        details.append("Top 5 du jour ✓✓")
    elif trend == "flop":
        score -= 1.0
        details.append("Flop 5 du jour ✗")

    # Variation annuelle BOC — bandes élargies pour performances exceptionnelles
    var_annee = row.get("var_annee") or 0
    if var_annee >= 80:
        score += 3.0
        details.append(f"Perf annuelle +{var_annee:.1f}% ✓✓✓")
    elif var_annee >= 30:
        score += 2.0
        details.append(f"Perf annuelle +{var_annee:.1f}% ✓✓")
    elif var_annee >= 10:
        score += 1.0
        details.append(f"Perf annuelle +{var_annee:.1f}% ✓")
    elif var_annee >= 0:
        score += 0.5
        details.append(f"Perf annuelle +{var_annee:.1f}% stable")
    elif var_annee >= -10:
        score -= 0.5
        details.append(f"Perf annuelle {var_annee:.1f}% ✗")
    else:
        score -= 1.0
        details.append(f"Perf annuelle {var_annee:.1f}% ✗✗")

    # Historique prix — tendance 52 semaines
    try:
        from price_history_builder import get_price_history
        hist = get_price_history(row.get("ticker", ""), weeks=52)
        if hist and len(hist) >= 4:
            prices = [p["price"] for p in hist if p.get("price")]
            if len(prices) >= 4:
                q = len(prices) // 4
                avg_recent = sum(prices[-q:]) / q
                avg_old    = sum(prices[:q]) / q
                if avg_old > 0:
                    trend_pct = (avg_recent - avg_old) / avg_old * 100
                    if trend_pct >= 15:
                        score += 1.5
                        details.append(f"Tendance haussière +{trend_pct:.0f}% ✓✓")
                    elif trend_pct >= 0:
                        score += 0.5
                        details.append(f"Tendance stable +{trend_pct:.0f}% ✓")
                    else:
                        details.append(f"Tendance baissière {trend_pct:.0f}% ✗")
    except Exception:
        pass

    score = min(10.0, max(0.0, score))
    return {"score": round(score, 1), "label": "Technique", "details": " | ".join(details)}


# ──────────────────────────────────────────────────────────────────────────────
# Recalcul P/E et P/B live
# ──────────────────────────────────────────────────────────────────────────────
def _inject_live_price(base_row: dict, live_price: float, live_data: dict) -> dict:
    """
    Crée une copie du row fondamental avec le prix live injecté.
    Recalcule pe_ref et pb_ref si le prix change significativement.
    """
    row = dict(base_row)
    old_price = row.get("price") or live_price

    row["price"]      = live_price
    row["change_pct"] = live_data.get("change_pct", 0)
    row["prev_close"] = live_data.get("prev_close")
    row["volume"]     = live_data.get("volume", 0)
    row["trend"]      = live_data.get("trend")

    # Recalcul P/E et P/B proportionnels au nouveau prix
    if old_price and old_price != live_price:
        ratio = live_price / old_price
        old_pe = row.get("pe_ref") or row.get("pe_hist")
        old_pb = row.get("pb_ref") or row.get("pb_hist")
        if old_pe and old_pe < 990:
            row["pe_ref"] = round(old_pe * ratio, 2)
        if old_pb and old_pb < 990:
            row["pb_ref"] = round(old_pb * ratio, 2)

        # Recalcul div_yield
        old_div_yield = row.get("div_yield") or 0
        if old_div_yield and old_price:
            div_per_share = old_div_yield / 100 * old_price
            row["div_yield"] = round(div_per_share / live_price * 100, 2)
            row["div_per_share"] = div_per_share

    return row


# ──────────────────────────────────────────────────────────────────────────────
# Point d'entrée principal
# ──────────────────────────────────────────────────────────────────────────────
def compute_live_score(ticker: str, base_fundamentals: dict, live_cache: dict) -> dict:
    """
    Calcule le score /80 live pour un ticker.

    Args:
        ticker: ex. "SGBCI"
        base_fundamentals: row fondamental depuis scraper.py (STOCK_FUNDAMENTALS[ticker])
        live_cache: résultat de live_data.get_live_data() — contient ["prices"][ticker]

    Returns:
        dict avec tous les scores + métadonnées live
    """
    # Cache désactivé — score vient de live_ranker.py
    pass
    prices = live_cache.get("prices", {})
    live_data_ticker = prices.get(ticker, {})
    live_price = live_data_ticker.get("price")

    # Si pas de prix live, on utilise le prix fondamental
    if not live_price:
        live_price = base_fundamentals.get("price")
        live_data_ticker = {}
        live_source = "static"
    else:
        live_source = live_data_ticker.get("source", "live")

    if not live_price:
        return {
            "ticker": ticker,
            "error": "Prix indisponible",
            "composite_adj": 0,
            "live_price": None,
            "live_source": "unavailable",
        }

    # Injection du prix live dans le row
    row = _inject_live_price(base_fundamentals, live_price, live_data_ticker)

    # Calcul des 7 modèles fondamentaux
    g   = score_graham(row)
    dcf = score_dcf(row)
    ddm = score_ddm(row)
    epv = score_epv(row)
    buf = score_buffett(row)
    rev = score_reverse_dcf(row)
    rel = score_relative(row)
    tec = score_technique_live(row)

    # Pénalité géopolitique
    geo_penalty = GEO_RISK_PENALTY.get(base_fundamentals.get("country", ""), 0)

    # Score composite /70 fondamental
    composite_raw = (
        g["score"] + dcf["score"] + ddm["score"] + epv["score"]
        + buf["score"] + rev["score"] + rel["score"]
    )
    composite_adj_70 = max(0, composite_raw + geo_penalty * 7 / 10)

    # Score total /80 avec technique
    composite_adj_80 = round(min(80, composite_adj_70 + tec["score"]), 1)

    result = {
        "ticker":           ticker,
        "live_price":       live_price,
        "live_change_pct":  live_data_ticker.get("change_pct", 0),
        "live_source":      live_source,
        "live_updated_at":  live_data_ticker.get("fetched_at"),
        "market_open":      live_cache.get("market_open", False),
        # Scores individuels
        "score_graham":     g["score"],
        "score_dcf":        dcf["score"],
        "score_ddm":        ddm["score"],
        "score_epv":        epv["score"],
        "score_buffett":    buf["score"],
        "score_rev_dcf":    rev["score"],
        "score_relatif":    rel["score"],
        "score_technique":  tec["score"],
        # Détails
        "detail_graham":    g["details"],
        "detail_dcf":       dcf["details"],
        "detail_ddm":       ddm["details"],
        "detail_epv":       epv["details"],
        "detail_buffett":   buf["details"],
        "detail_rev_dcf":   rev["details"],
        "detail_relatif":   rel["details"],
        "detail_technique": tec["details"],
        # Composite
        "geo_penalty":      geo_penalty,
        "composite_raw":    round(composite_raw, 1),
        "composite_adj":    composite_adj_80,
        "pe_ref_live":      row.get("pe_ref") or row.get("pe_hist") or row.get("pe_hist"),
        "pb_ref_live":      row.get("pb_ref") or row.get("pb_hist") or row.get("pb_hist"),
        "div_yield_live":   row.get("div_yield"),
    }
    return result


def compute_all_live_scores(base_fundamentals_dict: dict, live_cache: dict) -> list:
    """
    Recalcule les scores live pour tous les tickers.

    Args:
        base_fundamentals_dict: {ticker: row_dict} depuis STOCK_FUNDAMENTALS
        live_cache: résultat de get_live_data()

    Returns:
        liste de dicts triée par composite_adj décroissant
    """
    results = []
    for ticker, row in base_fundamentals_dict.items():
        try:
            result = compute_live_score(ticker, row, live_cache)
            results.append(result)
        except Exception as e:
            logger.warning(f"Erreur score live {ticker}: {e}")
            results.append({"ticker": ticker, "composite_adj": 0, "error": str(e)})

    results.sort(key=lambda x: x.get("composite_adj", 0), reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    return results
