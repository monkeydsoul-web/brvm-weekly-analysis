"""
BRVM Price History & Technical Momentum — Phase 2
Stocke les cours semaine par semaine.
Calcule : RSI · Momentum 4/13/26 semaines · Écart MM · Volume relatif
Produit un 8ème score de valorisation : score_technique /10
"""

import os
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

HISTORY_FILE = "data/price_history.json"
MIN_WEEKS_FOR_SIGNALS = 4   # Minimum de semaines pour calculer les signaux


def load_history() -> dict:
    """Charge l'historique des prix depuis le fichier JSON"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Erreur chargement historique: {e}")
    return {}


def save_history(history: dict):
    """Sauvegarde l'historique des prix"""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    logger.info(f"Historique sauvegardé: {HISTORY_FILE}")


def update_history(df_current: pd.DataFrame) -> dict:
    """
    Met à jour l'historique avec les cours de cette semaine.
    df_current doit contenir: ticker, price, change_pct, market_cap_xof
    """
    history = load_history()
    week_key = datetime.now().strftime("%Y-W%W")
    date_str = datetime.now().strftime("%Y-%m-%d")

    for _, row in df_current.iterrows():
        ticker = row.get("ticker", "")
        price = row.get("price")
        if not ticker or not price:
            continue

        if ticker not in history:
            history[ticker] = []

        # Éviter les doublons pour la même semaine
        existing_weeks = [e.get("week") for e in history[ticker]]
        if week_key not in existing_weeks:
            history[ticker].append({
                "week": week_key,
                "date": date_str,
                "price": float(price),
                "change_pct": float(row.get("change_pct", 0) or 0),
                "market_cap": float(row.get("market_cap_xof", 0) or 0),
            })
            # Garder seulement les 104 dernières semaines (2 ans)
            history[ticker] = history[ticker][-104:]

    save_history(history)
    logger.info(f"Historique mis à jour: {len(history)} actions")
    return history


def compute_rsi(prices: list[float], period: int = 14) -> object:
    """Calcule le RSI sur une série de prix"""
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [max(d, 0) for d in deltas[-period:]]
    losses = [abs(min(d, 0)) for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def compute_technical_score(ticker: str, history: dict) -> dict:
    """
    Calcule le score technique /10 pour une action.
    Basé sur: RSI, momentum 4/13/26 semaines, écart à la MM, tendance
    """
    score = 5.0  # Score neutre par défaut si pas assez d'historique
    details = []
    signals = {}

    records = history.get(ticker, [])
    if len(records) < MIN_WEEKS_FOR_SIGNALS:
        return {
            "score": score,
            "label": "Technique",
            "details": f"Historique insuffisant ({len(records)} semaines, min {MIN_WEEKS_FOR_SIGNALS})",
            "signals": {},
            "data_weeks": len(records),
        }

    prices = [r["price"] for r in records]
    current_price = prices[-1]
    score = 5.0  # Repart de neutre avec données suffisantes

    # ── 1. RSI ────────────────────────────────────────────────────────────────
    rsi = compute_rsi(prices, period=min(14, len(prices) - 1))
    if rsi is not None:
        signals["rsi"] = rsi
        if rsi < 30:
            score += 2.5
            details.append(f"RSI={rsi:.0f} — Survendu ✓✓ (signal achat fort)")
        elif rsi < 45:
            score += 1.5
            details.append(f"RSI={rsi:.0f} — Zone valeur ✓")
        elif rsi < 55:
            score += 0.5
            details.append(f"RSI={rsi:.0f} — Neutre")
        elif rsi < 70:
            score -= 0.5
            details.append(f"RSI={rsi:.0f} — Zone prudence")
        else:
            score -= 2.0
            details.append(f"RSI={rsi:.0f} — Suracheté ✗ (signal vente)")

    # ── 2. Momentum 4 semaines ────────────────────────────────────────────────
    if len(prices) >= 4:
        mom_4w = (current_price / prices[-4] - 1) * 100
        signals["momentum_4w"] = round(mom_4w, 1)
        if mom_4w > 15:
            score -= 1.0  # Trop chaud à court terme
            details.append(f"Momentum 4s=+{mom_4w:.1f}% — Surachat court terme ✗")
        elif mom_4w > 5:
            score += 0.5
            details.append(f"Momentum 4s=+{mom_4w:.1f}% — Tendance positive ✓")
        elif mom_4w > -5:
            score += 0.3
            details.append(f"Momentum 4s={mom_4w:.1f}% — Stable")
        elif mom_4w > -15:
            score += 1.0
            details.append(f"Momentum 4s={mom_4w:.1f}% — Repli modéré — Opportunité ✓")
        else:
            score += 1.5
            details.append(f"Momentum 4s={mom_4w:.1f}% — Forte baisse — Potentiel rebond ✓✓")

    # ── 3. Momentum 13 semaines (1 trimestre) ────────────────────────────────
    if len(prices) >= 13:
        mom_13w = (current_price / prices[-13] - 1) * 100
        signals["momentum_13w"] = round(mom_13w, 1)
        if mom_13w > 30:
            score -= 0.5
            details.append(f"Momentum 13s=+{mom_13w:.1f}% — Possible essoufflement")
        elif mom_13w > 10:
            score += 0.5
            details.append(f"Momentum 13s=+{mom_13w:.1f}% — Tendance haussière ✓")
        elif mom_13w < -20:
            score += 1.5
            details.append(f"Momentum 13s={mom_13w:.1f}% — Fort repli — Possible valeur ✓✓")
        elif mom_13w < -10:
            score += 1.0
            details.append(f"Momentum 13s={mom_13w:.1f}% — Repli — Opportunité ✓")

    # ── 4. Écart à la moyenne mobile 26 semaines ─────────────────────────────
    if len(prices) >= 26:
        mm_26 = sum(prices[-26:]) / 26
        ecart_mm = (current_price / mm_26 - 1) * 100
        signals["mm_26w"] = round(mm_26, 0)
        signals["ecart_mm_26w"] = round(ecart_mm, 1)
        if ecart_mm < -15:
            score += 2.0
            details.append(f"Cours {ecart_mm:.1f}% sous MM26 — Sous-évalué technique ✓✓")
        elif ecart_mm < -5:
            score += 1.0
            details.append(f"Cours {ecart_mm:.1f}% sous MM26 ✓")
        elif ecart_mm > 20:
            score -= 1.5
            details.append(f"Cours {ecart_mm:.1f}% au-dessus MM26 — Surachat ✗")
        elif ecart_mm > 10:
            score -= 0.5
            details.append(f"Cours {ecart_mm:.1f}% au-dessus MM26")

    # ── 5. Tendance long terme (52 semaines) ─────────────────────────────────
    if len(prices) >= 52:
        perf_52w = (current_price / prices[-52] - 1) * 100
        signals["perf_52w"] = round(perf_52w, 1)
        # Plus haut/bas 52 semaines
        high_52 = max(prices[-52:])
        low_52 = min(prices[-52:])
        pct_from_low = (current_price / low_52 - 1) * 100
        pct_from_high = (current_price / high_52 - 1) * 100
        signals["pct_from_52w_low"] = round(pct_from_low, 1)
        signals["pct_from_52w_high"] = round(pct_from_high, 1)
        if pct_from_low < 10:
            score += 1.5
            details.append(f"Proche du plus bas 52s (+{pct_from_low:.1f}%) — Zone d'achat ✓✓")
        if pct_from_high < -30:
            score += 1.0
            details.append(f"À {pct_from_high:.1f}% du plus haut — Repli significatif ✓")
    elif len(prices) >= 26:
        perf_26w = (current_price / prices[-26] - 1) * 100
        signals["perf_26w"] = round(perf_26w, 1)

    score = min(10.0, max(0.0, score))
    return {
        "score": round(score, 1),
        "label": "Technique",
        "details": " | ".join(details) if details else "Signaux techniques neutres",
        "signals": signals,
        "data_weeks": len(records),
    }


def compute_all_technical_scores(df: pd.DataFrame, history: dict = None) -> pd.DataFrame:
    """Ajoute le score technique à chaque action du DataFrame"""
    if history is None:
        history = load_history()

    tech_scores = []
    tech_details = []
    tech_signals = []
    tech_weeks = []

    for _, row in df.iterrows():
        result = compute_technical_score(row["ticker"], history)
        tech_scores.append(result["score"])
        tech_details.append(result["details"])
        tech_signals.append(result["signals"])
        tech_weeks.append(result["data_weeks"])

    df = df.copy()
    df["score_technique"] = tech_scores
    df["detail_technique"] = tech_details
    df["technical_signals"] = tech_signals
    df["data_weeks"] = tech_weeks

    # Recalculer le composite avec le 8ème score
    df["composite_raw"] = df["composite_raw"] + df["score_technique"]
    df["composite_adj"] = df["composite_adj"] + df["score_technique"]

    return df


def get_history_summary(history: dict) -> dict:
    """Retourne un résumé de l'historique pour le rapport"""
    total_tickers = len(history)
    total_records = sum(len(v) for v in history.values())
    avg_weeks = total_records / total_tickers if total_tickers > 0 else 0

    # Top performers de la semaine
    weekly_changes = []
    for ticker, records in history.items():
        if len(records) >= 2:
            last = records[-1]["price"]
            prev = records[-2]["price"]
            change = (last / prev - 1) * 100
            weekly_changes.append((ticker, round(change, 1)))

    weekly_changes.sort(key=lambda x: x[1], reverse=True)

    return {
        "total_tickers_tracked": total_tickers,
        "total_data_points": total_records,
        "avg_weeks_per_ticker": round(avg_weeks, 1),
        "top_gainers": weekly_changes[:5],
        "top_losers": weekly_changes[-5:][::-1],
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=== TEST HISTORIQUE PRIX ===")
    history = load_history()
    print(f"Tickers en historique: {len(history)}")
    if history:
        summary = get_history_summary(history)
        print(f"Résumé: {summary}")
