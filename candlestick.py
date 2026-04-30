#!/usr/bin/env python3
"""
candlestick.py — Générateur de données OHLC hebdomadaires pour graphiques bougies
Données synthétiques basées sur price_history.py (pas de librairie externe)
"""
import json
import random
from datetime import datetime, timedelta

def generate_ohlc_from_weekly_prices(ticker: str, weekly_prices: list) -> list:
    """
    Convertit une liste de prix de clôture hebdomadaires en données OHLC.
    weekly_prices: liste de (date_str, close_price)
    Retourne: liste de dicts {date, open, high, low, close, volume}
    """
    ohlc = []
    for i, (date_str, close) in enumerate(weekly_prices):
        if i == 0:
            open_price = close * random.uniform(0.98, 1.02)
        else:
            open_price = weekly_prices[i-1][1] * random.uniform(0.995, 1.005)

        volatility = close * 0.025
        high = max(open_price, close) + abs(random.gauss(0, volatility))
        low  = min(open_price, close) - abs(random.gauss(0, volatility))
        volume = int(random.gauss(50000, 20000))

        ohlc.append({
            "date":   date_str,
            "open":   round(open_price, 2),
            "high":   round(high, 2),
            "low":    round(low, 2),
            "close":  round(close, 2),
            "volume": max(1000, volume)
        })
    return ohlc

def get_ohlc_svg(ohlc_data: list, width: int = 800, height: int = 300,
                 ticker: str = "", title: str = "") -> str:
    """
    Génère un graphique SVG candlestick à partir de données OHLC.
    Retourne une chaîne SVG pure, compatible avec le dashboard.
    """
    if not ohlc_data:
        return '<svg viewBox="0 0 800 300"><text x="400" y="150" text-anchor="middle">Pas de données</text></svg>'

    prices = [c["close"] for c in ohlc_data] + [c["high"] for c in ohlc_data] + [c["low"] for c in ohlc_data]
    min_p = min(prices) * 0.995
    max_p = max(prices) * 1.005
    price_range = max_p - min_p or 1

    margin_l, margin_r, margin_t, margin_b = 60, 20, 30, 40
    chart_w = width - margin_l - margin_r
    chart_h = height - margin_t - margin_b

    n = len(ohlc_data)
    candle_w = max(4, chart_w / n * 0.6)

    def px(price):
        return margin_t + chart_h * (1 - (price - min_p) / price_range)
    def x_pos(i):
        return margin_l + (i + 0.5) * chart_w / n

    # Grille de prix (5 niveaux)
    grid_lines = ""
    y_labels = ""
    for k in range(5):
        p = min_p + price_range * k / 4
        y = px(p)
        grid_lines += f'<line x1="{margin_l}" y1="{y:.1f}" x2="{width - margin_r}" y2="{y:.1f}" stroke="#334155" stroke-width="0.5" stroke-dasharray="3,3"/>'
        y_labels += f'<text x="{margin_l - 5}" y="{y + 4:.1f}" text-anchor="end" font-size="10" fill="#94a3b8">{p:.0f}</text>'

    # Bougies
    candles = ""
    for i, c in enumerate(ohlc_data):
        xc = x_pos(i)
        is_bull = c["close"] >= c["open"]
        color = "#22c55e" if is_bull else "#ef4444"

        body_top    = min(px(c["open"]), px(c["close"]))
        body_bottom = max(px(c["open"]), px(c["close"]))
        body_h = max(1, body_bottom - body_top)

        candles += (
            f'<line x1="{xc:.1f}" y1="{px(c["high"]):.1f}" x2="{xc:.1f}" y2="{px(c["low"]):.1f}" stroke="{color}" stroke-width="1"/>'
            f'<rect x="{xc - candle_w/2:.1f}" y="{body_top:.1f}" width="{candle_w:.1f}" height="{body_h:.1f}" fill="{color}" opacity="0.85"/>'
        )

    # Labels X (1 sur 4 pour éviter chevauchement)
    x_labels = ""
    step = max(1, n // 8)
    for i in range(0, n, step):
        d = ohlc_data[i]["date"]
        # Afficher seulement mois/année
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            label = dt.strftime("%b %y")
        except Exception:
            label = d[:7]
        x_labels += f'<text x="{x_pos(i):.1f}" y="{height - 5}" text-anchor="middle" font-size="9" fill="#64748b">{label}</text>'

    title_el = f'<text x="{width/2}" y="18" text-anchor="middle" font-size="12" font-weight="500" fill="#e2e8f0">{title or ticker}</text>' if title or ticker else ""

    last = ohlc_data[-1]
    is_bull_last = last["close"] >= last["open"]
    price_color = "#22c55e" if is_bull_last else "#ef4444"
    price_tag = f'<text x="{width - margin_r}" y="18" text-anchor="end" font-size="12" font-weight="500" fill="{price_color}">{last["close"]:.0f} FCFA</text>'

    return f"""<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="background:#0f172a;border-radius:8px">
  <rect width="{width}" height="{height}" fill="#0f172a" rx="8"/>
  {title_el}
  {price_tag}
  {grid_lines}
  {y_labels}
  {candles}
  {x_labels}
</svg>"""

def get_candlestick_data_for_ticker(ticker: str) -> dict:
    """
    Récupère les données OHLC pour un ticker depuis price_history.
    Retourne dict avec 'ohlc', 'ticker', 'svg_1y', 'svg_5y'
    """
    try:
        from price_history import get_weekly_prices
        prices = get_weekly_prices(ticker)
    except Exception:
        # Fallback: données synthétiques si price_history indisponible
        base = 5000
        prices = []
        current = datetime.now()
        for i in range(260, 0, -1):
            d = current - timedelta(weeks=i)
            base *= random.uniform(0.97, 1.03)
            prices.append((d.strftime("%Y-%m-%d"), round(base, 2)))

    ohlc = generate_ohlc_from_weekly_prices(ticker, prices)

    # 1 an = ~52 semaines, 5 ans = ~260 semaines
    ohlc_1y = ohlc[-52:] if len(ohlc) >= 52 else ohlc
    ohlc_5y = ohlc[-260:] if len(ohlc) >= 260 else ohlc

    return {
        "ticker": ticker,
        "ohlc":   ohlc,
        "ohlc_1y": ohlc_1y,
        "ohlc_5y": ohlc_5y,
        "svg_1y":  get_ohlc_svg(ohlc_1y, ticker=ticker, title=f"{ticker} — 1 an"),
        "svg_5y":  get_ohlc_svg(ohlc_5y, ticker=ticker, title=f"{ticker} — 5 ans"),
    }

if __name__ == "__main__":
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "SGBC"
    data = get_candlestick_data_for_ticker(ticker)
    print(f"OHLC {ticker}: {len(data['ohlc'])} semaines")
    print(f"Dernière bougie: {data['ohlc'][-1]}")
    # Écrire SVG de test
    Path(f"test_{ticker}_candlestick.svg").write_text(data["svg_1y"])
    print(f"SVG écrit: test_{ticker}_candlestick.svg")
