"""
backtest_previsionnel.py — Validation des modèles prévisionnels BRVM
Split train/test sur données historiques BOC. Génère 3 portefeuilles IA.
"""
import json
import os
import math
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_price_history():
    path = os.path.join(DATA_DIR, "price_history.json")
    with open(path) as f:
        return json.load(f)


def _load_scores():
    # Find most recent scores file
    files = sorted(
        [f for f in os.listdir(DATA_DIR) if f.startswith("scores_") and f.endswith(".json")],
        reverse=True,
    )
    if files:
        with open(os.path.join(DATA_DIR, files[0])) as f:
            return json.load(f)
    return []


def _volatility(prices, window=30):
    """Annualized volatility (%) from daily price list."""
    p = prices[-window:] if len(prices) >= window else prices
    if len(p) < 2:
        return 25.0
    rets = [(p[i] - p[i-1]) / p[i-1] for i in range(1, len(p)) if p[i-1] > 0]
    if not rets:
        return 25.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return round(math.sqrt(var) * math.sqrt(252) * 100, 1)


def _momentum(prices, window=30):
    """Momentum (%) over last `window` days."""
    if len(prices) < 2:
        return 0.0
    start = prices[max(0, len(prices) - window)]
    end = prices[-1]
    return round((end - start) / start * 100, 2) if start > 0 else 0.0


def _directional_accuracy(predictions, actuals):
    """% of times predicted direction matches actual direction."""
    if not predictions:
        return 0.0
    correct = sum(1 for p, a in zip(predictions, actuals) if (p > 0) == (a > 0))
    return round(correct / len(predictions) * 100, 1)


# ── Portfolio generation ──────────────────────────────────────────────────────

def generate_portfolios(scores=None, price_history=None):
    """Return list of 3 dicts: Conservateur, Équilibré, Croissance."""
    if scores is None:
        scores = _load_scores()
    if price_history is None:
        price_history = _load_price_history()

    score_map = {s["ticker"]: s for s in scores}

    # Enrich scores with technicals
    enriched = []
    for s in scores:
        ticker = s.get("ticker", "")
        pts = sorted(price_history.get(ticker, []), key=lambda x: x["date"])
        prices = [p["price"] for p in pts if p.get("price")]
        vol = _volatility(prices)
        mom = _momentum(prices, 30)
        enriched.append({**s, "volatility": vol, "momentum_30d": mom})

    def eq_weights(n):
        return [round(100 / n, 1)] * n if n else []

    def stats(stocks, weights):
        if not stocks:
            return {"exp_return": 0, "volatility": 0, "sharpe": 0}
        wt = [w / 100 for w in weights]
        exp_div = sum(s.get("div_yield", 0) * w for s, w in zip(stocks, wt))
        # Conservative price appreciation: 20% of annualized momentum
        exp_price = sum(
            max(0, s.get("momentum_30d", 0)) * (12 / 1) * 0.10 * w
            for s, w in zip(stocks, wt)
        )
        exp_ret = round(exp_div + exp_price, 1)
        vol = round(sum(s.get("volatility", 20) * w for s, w in zip(stocks, wt)), 1)
        sharpe = round((exp_ret - 6.5) / max(vol, 1), 2)
        return {"exp_return": exp_ret, "volatility": vol, "sharpe": sharpe}

    def pack(stocks, weights, name, risk, target_min, target_max, rationale):
        st = stats(stocks, weights)
        return {
            "name": name,
            "risk": risk,
            "target_min": target_min,
            "target_max": target_max,
            "rationale": rationale,
            **st,
            "stocks": [
                {
                    "ticker": s["ticker"],
                    "name": s.get("name", ""),
                    "weight": w,
                    "score": s.get("composite_adj", 0),
                    "div_yield": s.get("div_yield", 0),
                    "pe": s.get("pe_ref"),
                    "pb": s.get("pb_ref"),
                    "roe": s.get("roe"),
                    "momentum": s.get("momentum_30d", 0),
                    "volatility": s.get("volatility", 0),
                    "sector": s.get("sector", ""),
                    "price": s.get("price", 0),
                }
                for s, w in zip(stocks, weights)
            ],
        }

    DEFENSIVE_SECTORS = {"Banque", "Telecom", "Télécoms", "Distribution", "Assurance", "Eau"}

    # ── Conservateur ────────────────────────────────────────────────────────
    cand_c = sorted(
        [s for s in enriched if
         s.get("composite_adj", 0) >= 50 and
         s.get("div_yield", 0) >= 4 and
         (s.get("pe_ref") or 99) < 15],
        key=lambda x: -(x.get("div_yield", 0) + x.get("composite_adj", 0) * 0.05),
    )[:5]
    if len(cand_c) < 3:
        cand_c = sorted(
            [s for s in enriched if s.get("div_yield", 0) >= 3],
            key=lambda x: -x.get("div_yield", 0),
        )[:5]
    w_c = eq_weights(len(cand_c))

    # ── Équilibré ────────────────────────────────────────────────────────────
    cand_b = sorted(
        [s for s in enriched if s.get("composite_adj", 0) >= 58],
        key=lambda x: -x.get("composite_adj", 0),
    )[:6]
    if len(cand_b) < 3:
        cand_b = sorted(enriched, key=lambda x: -x.get("composite_adj", 0))[:6]
    w_b = eq_weights(len(cand_b))

    # ── Croissance ───────────────────────────────────────────────────────────
    cand_g = sorted(
        [s for s in enriched if
         s.get("composite_adj", 0) >= 48 and
         s.get("momentum_30d", -999) > 0],
        key=lambda x: -(x.get("momentum_30d", 0) + x.get("composite_adj", 0) * 0.3),
    )[:5]
    if len(cand_g) < 3:
        cand_g = sorted(
            [s for s in enriched if s.get("momentum_30d", -999) > 0],
            key=lambda x: -x.get("momentum_30d", 0),
        )[:5]
    w_g = eq_weights(len(cand_g))

    return [
        pack(cand_c, w_c, "Conservateur", "Faible", 8, 12,
             "Dividendes élevés + P/E bas + secteurs défensifs. Taux BCEAO 6.5% → préférer div>6%."),
        pack(cand_b, w_b, "Équilibré", "Modéré", 15, 25,
             "Meilleurs scores composites. Mix dividende + croissance. Pondération égale par défaut."),
        pack(cand_g, w_g, "Croissance", "Élevé", 25, 40,
             "Momentum positif 30j + score ≥50. Secteurs dynamiques. Horizon 12 mois."),
    ]


# ── Signals ───────────────────────────────────────────────────────────────────

def compute_signals(scores=None, price_history=None):
    """Return buy/sell/hold signals for every ticker."""
    if scores is None:
        scores = _load_scores()
    if price_history is None:
        price_history = _load_price_history()

    out = []
    for s in scores:
        ticker = s.get("ticker", "")
        score = s.get("composite_adj", 0)
        pts = sorted(price_history.get(ticker, []), key=lambda x: x["date"])
        prices = [p["price"] for p in pts if p.get("price")]
        mom = _momentum(prices, 30)

        bullish_models = sum(
            1 for k in ["score_graham", "score_dcf", "score_ddm", "score_epv", "score_buffett"]
            if (s.get(k) or 0) >= 7
        )
        confidence = min(95, bullish_models * 19 + (5 if mom > 0 else 0))

        if score >= 60 and mom >= 0:
            signal, emoji = "ACHETER", "🟢"
            reasons = [f"Score {score:.0f}/80"]
            if s.get("div_yield", 0) >= 5:
                reasons.append(f'div {s["div_yield"]:.1f}%')
            if (s.get("pe_ref") or 99) < 10:
                reasons.append(f'P/E {s["pe_ref"]:.1f}×')
            if mom > 0:
                reasons.append(f'momentum +{mom:.1f}%')
            raison = ", ".join(reasons)
        elif score >= 45:
            signal, emoji = "CONSERVER", "🟡"
            raison = f"Score {score:.0f}/80, fondamentaux corrects"
        elif score >= 30:
            signal, emoji = "ALLÉGER", "🔴"
            raison = f"Score {score:.0f}/80 sous la moyenne"
        else:
            signal, emoji = "ÉVITER", "⚫"
            raison = f"Score {score:.0f}/80, risque élevé"

        out.append({
            "ticker": ticker,
            "name": s.get("name", ""),
            "sector": s.get("sector", ""),
            "signal": signal,
            "emoji": emoji,
            "raison": raison,
            "confidence": confidence,
            "score": score,
            "momentum": mom,
            "div_yield": s.get("div_yield", 0),
            "price": s.get("price", 0),
            "updated_at": datetime.now().strftime("%d/%m/%Y"),
        })

    _order = ["ACHETER", "CONSERVER", "ALLÉGER", "ÉVITER"]
    out.sort(key=lambda x: (_order.index(x["signal"]), -x["score"]))
    return out


# ── Backtest validation ───────────────────────────────────────────────────────

def compute_backtest_previsionnel(scores=None, price_history=None):
    """
    Train/test split sur données BOC (80 jours).
    60 premiers jours = entraînement (prédiction par momentum).
    20 derniers jours = test (performance réelle).
    Métriques : précision directionnelle + MAE.
    """
    if scores is None:
        scores = _load_scores()
    if price_history is None:
        price_history = _load_price_history()

    score_map = {s["ticker"]: s for s in scores}

    predictions, actuals = [], []
    ticker_results = []

    for ticker, raw_pts in price_history.items():
        pts = sorted(raw_pts, key=lambda x: x["date"])
        boc = [p for p in pts if p.get("source") == "boc"] or pts
        if len(boc) < 25:
            continue

        train = boc[:-20]
        test = boc[-20:]

        train_prices = [p["price"] for p in train if p.get("price")]
        test_prices = [p["price"] for p in test if p.get("price")]

        if len(train_prices) < 5 or len(test_prices) < 2:
            continue

        # Prediction: 5-day momentum at end of training
        mom_train = (train_prices[-1] - train_prices[-5]) / train_prices[-5] * 100 if train_prices[-5] > 0 else 0
        predicted_return = mom_train * 0.25  # conservative scaling

        actual_return = (test_prices[-1] - test_prices[0]) / test_prices[0] * 100 if test_prices[0] > 0 else 0

        predictions.append(predicted_return)
        actuals.append(actual_return)

        sc = score_map.get(ticker, {})
        ticker_results.append({
            "ticker": ticker,
            "score": sc.get("composite_adj", 0),
            "train_momentum": round(mom_train, 2),
            "predicted_return": round(predicted_return, 2),
            "predicted": "hausse" if predicted_return > 0 else "baisse",
            "actual_return": round(actual_return, 2),
            "actual": "hausse" if actual_return > 0 else "baisse",
            "correct": (predicted_return > 0) == (actual_return > 0),
            "train_start": train[0]["date"] if train else "",
            "train_end": train[-1]["date"] if train else "",
            "test_end": test[-1]["date"] if test else "",
        })

    dir_acc = _directional_accuracy(predictions, actuals)
    mae = round(
        sum(abs(a - p) for a, p in zip(actuals, predictions)) / len(predictions), 2
    ) if predictions else 0

    result = {
        "directional_accuracy": dir_acc,
        "mae": mae,
        "total_tested": len(ticker_results),
        "train_period": "60 jours BOC",
        "test_period": "20 derniers jours BOC",
        "results": sorted(ticker_results, key=lambda x: -abs(x["actual_return"]))[:25],
        "computed_at": datetime.now().isoformat()[:16],
    }

    # Persist
    out_path = os.path.join(DATA_DIR, "prevision_accuracy.json")
    with open(out_path, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


# ── PDF rapport mensuel ───────────────────────────────────────────────────────

def generate_rapport_pdf(scores=None, price_history=None):
    """Generate monthly PDF report. Returns bytes."""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    import io

    if scores is None:
        scores = _load_scores()
    if price_history is None:
        price_history = _load_price_history()

    portfolios = generate_portfolios(scores, price_history)
    signals = compute_signals(scores, price_history)
    buy_signals = [s for s in signals if s["signal"] == "ACHETER"]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Heading1"],
                                 fontSize=18, textColor=colors.HexColor("#1E3A5F"),
                                 spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"],
                         fontSize=13, textColor=colors.HexColor("#2563EB"), spaceAfter=4)
    body = styles["BodyText"]

    now = datetime.now().strftime("%B %Y")
    story = []

    story.append(Paragraph(f"BRVM Dashboard — Rapport mensuel {now}", title_style))
    story.append(Paragraph(f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}", body))
    story.append(Spacer(1, 0.4*cm))

    # Summary KPIs
    n_strong = len([s for s in scores if (s.get("composite_adj") or 0) >= 60])
    top = sorted(scores, key=lambda x: -(x.get("composite_adj") or 0))[:3]
    story.append(Paragraph("Résumé du marché BRVM", h2))
    kpi_data = [
        ["Actions analysées", str(len(scores)),
         "Score fort (≥60)", str(n_strong),
         "Signaux ACHAT", str(len(buy_signals))],
    ]
    t = Table(kpi_data, colWidths=[4*cm, 2.5*cm, 4*cm, 2.5*cm, 3.5*cm, 2.5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.3*cm))

    # Top 3
    story.append(Paragraph("Top 3 actions par score composite", h2))
    top_data = [["#", "Ticker", "Score/80", "P/E", "Div%", "Secteur"]]
    for i, s in enumerate(top, 1):
        top_data.append([
            str(i), s["ticker"],
            f"{s.get('composite_adj', 0):.0f}",
            f"{s.get('pe_ref', 0):.1f}×" if s.get("pe_ref") else "—",
            f"{s.get('div_yield', 0):.1f}%" if s.get("div_yield") else "—",
            s.get("sector", "—")[:20],
        ])
    t2 = Table(top_data, colWidths=[1*cm, 2.5*cm, 2.5*cm, 2*cm, 2*cm, 4.5*cm])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t2)
    story.append(Spacer(1, 0.3*cm))

    # Portfolios
    story.append(Paragraph("Portefeuilles prévisionnels recommandés", h2))
    for pf in portfolios:
        story.append(Paragraph(
            f"<b>{pf['name']}</b> — Risque {pf['risk']} — Objectif +{pf['target_min']}% à +{pf['target_max']}%",
            body
        ))
        pf_data = [["Ticker", "Poids", "Score", "Div%", "Momentum"]]
        for st in pf.get("stocks", []):
            pf_data.append([
                st["ticker"],
                f"{st['weight']:.1f}%",
                f"{st['score']:.0f}/80",
                f"{st.get('div_yield', 0):.1f}%",
                f"{st.get('momentum', 0):+.1f}%",
            ])
        tp = Table(pf_data, colWidths=[2.5*cm, 2*cm, 2.5*cm, 2*cm, 2.5*cm])
        tp.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(tp)
        story.append(Spacer(1, 0.2*cm))

    # Signals ACHAT
    story.append(Paragraph("Signaux d'achat actifs", h2))
    sig_data = [["Ticker", "Score", "Confiance", "Raison"]]
    for sig in buy_signals[:10]:
        sig_data.append([
            sig["ticker"],
            f"{sig['score']:.0f}/80",
            f"{sig['confidence']}%",
            sig["raison"][:50],
        ])
    ts = Table(sig_data, colWidths=[2.5*cm, 2*cm, 2.5*cm, 8*cm])
    ts.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#166534")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0FDF4")]),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(ts)

    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        "Ce rapport est généré automatiquement. Les prévisions sont indicatives et ne constituent pas un conseil en investissement.",
        ParagraphStyle("disclaimer", parent=body, fontSize=7, textColor=colors.grey)
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()


if __name__ == "__main__":
    print("Computing backtest…")
    r = compute_backtest_previsionnel()
    print(f"Directional accuracy: {r['directional_accuracy']}% on {r['total_tested']} tickers")
    print(f"MAE: {r['mae']}%")
