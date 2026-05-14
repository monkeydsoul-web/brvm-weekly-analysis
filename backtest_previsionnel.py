"""
backtest_previsionnel.py — Modèle composite de prévision BRVM
Validation annuelle 2019-2024 + split train/test sur données BOC récentes.
"""
import json
import os
import math
from datetime import datetime, timedelta
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_price_history():
    with open(os.path.join(DATA_DIR, "price_history.json")) as f:
        return json.load(f)


def _load_boc_data():
    path = os.path.join(DATA_DIR, "boc_data.json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _load_analyses():
    path = os.path.join(DATA_DIR, "analyses_summary.json")
    try:
        with open(path) as f:
            d = json.load(f)
            if isinstance(d, list):
                return {x.get("ticker", ""): x for x in d if x.get("ticker")}
            return d
    except Exception:
        return {}


def _load_scores():
    files = sorted(
        [f for f in os.listdir(DATA_DIR) if f.startswith("scores_") and f.endswith(".json")],
        reverse=True,
    )
    if files:
        with open(os.path.join(DATA_DIR, files[0])) as f:
            return json.load(f)
    return []


# ── Math helpers ──────────────────────────────────────────────────────────────

def _volatility(prices, window=30):
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
    if len(prices) < 2:
        return 0.0
    idx = max(0, len(prices) - window)
    start = prices[idx]
    end = prices[-1]
    return round((end - start) / start * 100, 2) if start > 0 else 0.0


def _sharpe(returns, rf=6.5):
    """Annualized Sharpe ratio from list of annual returns (%)."""
    if not returns:
        return 0.0
    n = len(returns)
    mean = sum(returns) / n
    if n < 2:
        return round((mean - rf) / max(abs(mean), 1), 2)
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(var)
    return round((mean - rf) / max(std, 0.1), 2)


def _directional_accuracy(predictions, actuals):
    if not predictions:
        return 0.0
    correct = sum(1 for p, a in zip(predictions, actuals) if (p > 0) == (a > 0))
    return round(correct / len(predictions) * 100, 1)


# ── Composite prediction score ────────────────────────────────────────────────

def _score_prevision(score_adj, div_yield, mom_30d, var_annee):
    """
    Composite prediction score [0..1].
    score_adj : composite_adj / 80 (fondamentaux)
    div_yield  : rendement dividende %
    mom_30d    : momentum 30j %
    var_annee  : variation depuis Jan (%)
    """
    # Normalize each factor to [0, 1]
    f_fondamental = min(1.0, max(0.0, score_adj / 80))         # poids 40%
    f_div = min(1.0, max(0.0, div_yield / 15))                  # poids 20%, cap à 15%
    f_mom30 = min(1.0, max(0.0, (mom_30d + 30) / 60))           # poids 20%, [-30,+30] → [0,1]
    f_var = min(1.0, max(0.0, (var_annee + 30) / 60))           # poids 20%, [-30,+30] → [0,1]
    return round(0.40 * f_fondamental + 0.20 * f_div + 0.20 * f_mom30 + 0.20 * f_var, 4)


def _signal_from_score(sp):
    if sp > 0.65:
        return "ACHETER"
    if sp < 0.35:
        return "ALLÉGER"
    return "CONSERVER"


# ── Yearly backtest validation (2019-2024) ────────────────────────────────────

def _backtest_yearly(price_history, score_map, boc_data):
    """
    Pour chaque année 2019-2024 :
    - Calcule score_prevision au 1er janvier
    - Compare avec la performance annuelle réelle
    - Retourne métriques par année
    """
    years = ["2019", "2020", "2021", "2022", "2023", "2024"]
    yearly_results = {}
    all_returns_model = []   # rendements des portefeuilles simulés par année

    for yr in years:
        preds, actuals, ticker_rows = [], [], []
        for ticker, raw_pts in price_history.items():
            pts = sorted(raw_pts, key=lambda x: x["date"])
            yr_pts = [p for p in pts if p["date"].startswith(yr)]
            if len(yr_pts) < 2:
                continue
            yr_prev = [p for p in pts if p["date"].startswith(str(int(yr) - 1))]

            p_start = yr_pts[0]["price"]
            p_end   = yr_pts[-1]["price"]
            if not p_start or p_start == 0:
                continue
            actual_return = round((p_end - p_start) / p_start * 100, 2)

            # Momentum 30j = 3 derniers points de l'année précédente
            prev_prices = [p["price"] for p in yr_prev if p.get("price")]
            mom_30d = _momentum(prev_prices, min(3, len(prev_prices))) if len(prev_prices) >= 2 else 0.0

            # Fondamentaux = scores live (proxy pour les années historiques)
            sc = score_map.get(ticker, {})
            score_adj = sc.get("composite_adj", 0)
            div_yield = sc.get("div_yield", 0)

            # var_annee = from boc_data (actuel) — proxy historique
            boc = boc_data.get(ticker, {})
            var_annee = boc.get("var_annee", mom_30d * 2)  # fallback: extrapolate

            sp = _score_prevision(score_adj, div_yield, mom_30d, var_annee)
            signal = _signal_from_score(sp)
            preds.append(sp - 0.5)   # centered: >0 = haussier
            actuals.append(actual_return)

            ticker_rows.append({
                "ticker": ticker,
                "score_prevision": sp,
                "signal": signal,
                "score_adj": score_adj,
                "div_yield": div_yield,
                "mom_30d": round(mom_30d, 2),
                "var_annee": round(var_annee, 2),
                "actual_return": actual_return,
                "correct": (sp > 0.5) == (actual_return > 0),
                "p_start": p_start,
                "p_end": p_end,
            })

        if not ticker_rows:
            continue

        dir_acc = _directional_accuracy(preds, actuals)
        # Simulated portfolio: actions with signal ACHETER
        acheter = [r for r in ticker_rows if r["signal"] == "ACHETER"]
        avg_ret_acheter = (
            round(sum(r["actual_return"] for r in acheter) / len(acheter), 2)
            if acheter else None
        )
        avg_ret_all = round(sum(r["actual_return"] for r in ticker_rows) / len(ticker_rows), 2)

        yearly_results[yr] = {
            "year": yr,
            "n_tickers": len(ticker_rows),
            "directional_accuracy": dir_acc,
            "n_acheter": len(acheter),
            "avg_return_acheter": avg_ret_acheter,
            "avg_return_market": avg_ret_all,
            "alpha": round((avg_ret_acheter or avg_ret_all) - avg_ret_all, 2),
            "results": sorted(ticker_rows, key=lambda x: -x["actual_return"])[:15],
        }
        if avg_ret_acheter is not None:
            all_returns_model.append(avg_ret_acheter)

    return yearly_results, all_returns_model


# ── Portfolio generation ──────────────────────────────────────────────────────

def generate_portfolios(scores=None, price_history=None):
    if scores is None:
        scores = _load_scores()
    if price_history is None:
        price_history = _load_price_history()

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
        exp_div  = sum(s.get("div_yield", 0) * w for s, w in zip(stocks, wt))
        exp_price = sum(max(0, s.get("momentum_30d", 0)) * 0.10 * w for s, w in zip(stocks, wt))
        exp_ret  = round(exp_div + exp_price, 1)
        vol      = round(sum(s.get("volatility", 20) * w for s, w in zip(stocks, wt)), 1)
        sharpe   = round((exp_ret - 6.5) / max(vol, 1), 2)
        return {"exp_return": exp_ret, "volatility": vol, "sharpe": sharpe}

    def pack(stocks, weights, name, risk, target_min, target_max, rationale):
        st = stats(stocks, weights)
        return {
            "name": name, "risk": risk,
            "target_min": target_min, "target_max": target_max,
            "rationale": rationale, **st,
            "stocks": [
                {
                    "ticker": s["ticker"], "name": s.get("name", ""),
                    "weight": w, "score": s.get("composite_adj", 0),
                    "div_yield": s.get("div_yield", 0), "pe": s.get("pe_ref"),
                    "pb": s.get("pb_ref"), "roe": s.get("roe"),
                    "momentum": s.get("momentum_30d", 0),
                    "volatility": s.get("volatility", 0),
                    "sector": s.get("sector", ""), "price": s.get("price", 0),
                }
                for s, w in zip(stocks, weights)
            ],
        }

    # Conservateur
    cand_c = sorted(
        [s for s in enriched if s.get("composite_adj", 0) >= 50 and
         s.get("div_yield", 0) >= 4 and (s.get("pe_ref") or 99) < 15],
        key=lambda x: -(x.get("div_yield", 0) + x.get("composite_adj", 0) * 0.05),
    )[:5]
    if len(cand_c) < 3:
        cand_c = sorted([s for s in enriched if s.get("div_yield", 0) >= 3],
                        key=lambda x: -x.get("div_yield", 0))[:5]

    # Équilibré
    cand_b = sorted([s for s in enriched if s.get("composite_adj", 0) >= 58],
                    key=lambda x: -x.get("composite_adj", 0))[:6]
    if len(cand_b) < 3:
        cand_b = sorted(enriched, key=lambda x: -x.get("composite_adj", 0))[:6]

    # Croissance
    cand_g = sorted(
        [s for s in enriched if s.get("composite_adj", 0) >= 48 and s.get("momentum_30d", -999) > 0],
        key=lambda x: -(x.get("momentum_30d", 0) + x.get("composite_adj", 0) * 0.3),
    )[:5]
    if len(cand_g) < 3:
        cand_g = sorted([s for s in enriched if s.get("momentum_30d", -999) > 0],
                        key=lambda x: -x.get("momentum_30d", 0))[:5]

    return [
        pack(cand_c, eq_weights(len(cand_c)), "Conservateur", "Faible", 8, 12,
             "Dividendes élevés + P/E bas + secteurs défensifs. Taux BCEAO 6.5% → préférer div>6%."),
        pack(cand_b, eq_weights(len(cand_b)), "Équilibré", "Modéré", 15, 25,
             "Meilleurs scores composites. Mix dividende + croissance. Pondération égale par défaut."),
        pack(cand_g, eq_weights(len(cand_g)), "Croissance", "Élevé", 25, 40,
             "Momentum positif 30j + score ≥50. Secteurs dynamiques. Horizon 12 mois."),
    ]


# ── Signals ───────────────────────────────────────────────────────────────────

def compute_signals(scores=None, price_history=None):
    if scores is None:
        scores = _load_scores()
    if price_history is None:
        price_history = _load_price_history()
    boc_data = _load_boc_data()

    out = []
    for s in scores:
        ticker = s.get("ticker", "")
        score  = s.get("composite_adj", 0)
        pts    = sorted(price_history.get(ticker, []), key=lambda x: x["date"])
        prices = [p["price"] for p in pts if p.get("price")]
        mom    = _momentum(prices, 30)

        boc       = boc_data.get(ticker, {})
        var_annee = boc.get("var_annee", 0) or 0
        div_yield = s.get("div_yield", 0) or boc.get("div_rdt", 0) or 0

        sp = _score_prevision(score, div_yield, mom, var_annee)

        bullish_models = sum(
            1 for k in ["score_graham", "score_dcf", "score_ddm", "score_epv", "score_buffett"]
            if (s.get(k) or 0) >= 7
        )
        confidence = min(95, int(sp * 100 * 0.8 + bullish_models * 5 + (5 if mom > 0 else 0)))

        if sp > 0.65:
            signal, emoji = "ACHETER", "🟢"
            reasons = [f"Score prévision {sp:.2f}"]
            if div_yield >= 5: reasons.append(f"div {div_yield:.1f}%")
            if (s.get("pe_ref") or 99) < 10: reasons.append(f'P/E {s["pe_ref"]:.1f}×')
            if mom > 0: reasons.append(f"momentum +{mom:.1f}%")
            if var_annee > 5: reasons.append(f"var annuelle +{var_annee:.1f}%")
            raison = ", ".join(reasons)
        elif sp > 0.50:
            signal, emoji = "CONSERVER", "🟡"
            raison = f"Score {score:.0f}/80, prévision {sp:.2f} — fondamentaux corrects"
        elif sp > 0.35:
            signal, emoji = "ALLÉGER", "🔴"
            raison = f"Score {score:.0f}/80, prévision {sp:.2f} — signaux mitigés"
        else:
            signal, emoji = "ÉVITER", "⚫"
            raison = f"Score {score:.0f}/80, prévision {sp:.2f} — risque élevé"

        out.append({
            "ticker": ticker, "name": s.get("name", ""),
            "sector": s.get("sector", ""), "signal": signal,
            "emoji": emoji, "raison": raison,
            "confidence": confidence, "score": score,
            "score_prevision": sp,
            "momentum": mom, "var_annee": var_annee,
            "div_yield": div_yield, "price": s.get("price", 0),
            "updated_at": datetime.now().strftime("%d/%m/%Y"),
        })

    _order = ["ACHETER", "CONSERVER", "ALLÉGER", "ÉVITER"]
    out.sort(key=lambda x: (_order.index(x["signal"]), -x["score"]))
    return out


# ── Main backtest (historique annuel + split récent) ──────────────────────────

def compute_backtest_previsionnel(scores=None, price_history=None):
    if scores is None:
        scores = _load_scores()
    if price_history is None:
        price_history = _load_price_history()
    boc_data  = _load_boc_data()

    score_map = {s["ticker"]: s for s in scores}

    # ── 1. Validation annuelle 2019-2024 ──────────────────────────────────────
    yearly_results, model_returns = _backtest_yearly(price_history, score_map, boc_data)

    # ── 2. Split train/test sur données récentes (BOC 2026) ───────────────────
    preds_recent, actuals_recent, recent_rows = [], [], []
    for ticker, raw_pts in price_history.items():
        pts  = sorted(raw_pts, key=lambda x: x["date"])
        boc  = [p for p in pts if p.get("source") == "boc"] or pts
        if len(boc) < 25:
            continue
        train = boc[:-20]
        test  = boc[-20:]
        tp = [p["price"] for p in train if p.get("price")]
        ap = [p["price"] for p in test  if p.get("price")]
        if len(tp) < 5 or len(ap) < 2:
            continue

        mom_train  = (tp[-1] - tp[-5]) / tp[-5] * 100 if tp[-5] > 0 else 0
        sc         = score_map.get(ticker, {})
        boc_d      = boc_data.get(ticker, {})
        div_yield  = sc.get("div_yield", 0) or boc_d.get("div_rdt", 0) or 0
        var_annee  = boc_d.get("var_annee", 0) or 0
        sp         = _score_prevision(sc.get("composite_adj", 0), div_yield, mom_train, var_annee)
        pred_ret   = (sp - 0.5) * 20   # [-10, +10]%
        actual_ret = (ap[-1] - ap[0]) / ap[0] * 100 if ap[0] > 0 else 0

        preds_recent.append(pred_ret)
        actuals_recent.append(actual_ret)
        recent_rows.append({
            "ticker": ticker,
            "score_prevision": sp,
            "signal": _signal_from_score(sp),
            "score": sc.get("composite_adj", 0),
            "mom_train": round(mom_train, 2),
            "predicted_return": round(pred_ret, 2),
            "actual_return": round(actual_ret, 2),
            "correct": (pred_ret > 0) == (actual_ret > 0),
            "train_start": train[0]["date"] if train else "",
            "train_end": train[-1]["date"] if train else "",
            "test_end": test[-1]["date"] if test else "",
        })

    dir_acc_recent = _directional_accuracy(preds_recent, actuals_recent)
    mae_recent = round(
        sum(abs(a - p) for a, p in zip(actuals_recent, preds_recent)) / max(len(preds_recent), 1), 2
    )

    # ── 3. Métriques globales ──────────────────────────────────────────────────
    all_dir_accs = [v["directional_accuracy"] for v in yearly_results.values()]
    avg_dir_acc  = round(sum(all_dir_accs) / len(all_dir_accs), 1) if all_dir_accs else dir_acc_recent

    all_alpha    = [v["alpha"] for v in yearly_results.values()]
    avg_alpha    = round(sum(all_alpha) / len(all_alpha), 2) if all_alpha else 0

    best_yr  = max(yearly_results.values(), key=lambda x: x.get("avg_return_acheter") or -999, default=None)
    worst_yr = min(yearly_results.values(), key=lambda x: x.get("avg_return_acheter") or 999, default=None)

    sharpe_model = _sharpe(model_returns)

    result = {
        # Global metrics
        "directional_accuracy": avg_dir_acc,
        "directional_accuracy_recent": dir_acc_recent,
        "mae_recent": mae_recent,
        "avg_alpha": avg_alpha,
        "sharpe_model": sharpe_model,
        "best_year": best_yr["year"] if best_yr else None,
        "best_year_return": best_yr.get("avg_return_acheter") if best_yr else None,
        "worst_year": worst_yr["year"] if worst_yr else None,
        "worst_year_return": worst_yr.get("avg_return_acheter") if worst_yr else None,
        "model_description": "Composite 4 facteurs : Fondamentaux 40% + Dividende 20% + Momentum30j 20% + VarAnnée 20%",
        "seuil_acheter": 0.65,
        "seuil_alleger": 0.35,
        # Yearly breakdown
        "yearly_results": yearly_results,
        # Recent split results
        "total_tested": len(recent_rows),
        "train_period": "BOC récent sauf 20 derniers jours",
        "test_period": "20 derniers jours BOC",
        "results": sorted(recent_rows, key=lambda x: -abs(x["actual_return"]))[:25],
        "computed_at": datetime.now().isoformat()[:16],
    }

    out_path = os.path.join(DATA_DIR, "prevision_accuracy.json")
    with open(out_path, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


# ── PDF rapport mensuel ───────────────────────────────────────────────────────

def generate_rapport_pdf(scores=None, price_history=None):
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
    signals    = compute_signals(scores, price_history)
    buy_signals = [s for s in signals if s["signal"] == "ACHETER"]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles    = getSampleStyleSheet()
    title_sty = ParagraphStyle("title", parent=styles["Heading1"],
                               fontSize=18, textColor=colors.HexColor("#1E3A5F"), spaceAfter=6)
    h2   = ParagraphStyle("h2", parent=styles["Heading2"],
                          fontSize=13, textColor=colors.HexColor("#2563EB"), spaceAfter=4)
    body = styles["BodyText"]
    disc = ParagraphStyle("disc", parent=body, fontSize=7, textColor=colors.grey)

    now = datetime.now()
    story = []
    story.append(Paragraph(f"BRVM Dashboard — Rapport mensuel {now.strftime('%B %Y')}", title_sty))
    story.append(Paragraph(f"Généré le {now.strftime('%d/%m/%Y à %H:%M')}", body))
    story.append(Spacer(1, 0.4*cm))

    n_strong = len([s for s in scores if (s.get("composite_adj") or 0) >= 60])
    top3     = sorted(scores, key=lambda x: -(x.get("composite_adj") or 0))[:3]
    story.append(Paragraph("Résumé du marché BRVM", h2))
    t = Table([[
        "Actions analysées", str(len(scores)),
        "Score fort (≥60)", str(n_strong),
        "Signaux ACHAT", str(len(buy_signals)),
    ]], colWidths=[4*cm, 2.5*cm, 4*cm, 2.5*cm, 3.5*cm, 2.5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("Top 3 actions par score composite", h2))
    top_data = [["#", "Ticker", "Score/80", "P/E", "Div%", "Secteur"]]
    for i, s in enumerate(top3, 1):
        top_data.append([
            str(i), s["ticker"],
            f"{s.get('composite_adj', 0):.0f}",
            f"{s.get('pe_ref', 0):.1f}×" if s.get("pe_ref") else "—",
            f"{s.get('div_yield', 0):.1f}%" if s.get("div_yield") else "—",
            (s.get("sector", "—") or "—")[:20],
        ])
    t2 = Table(top_data, colWidths=[1*cm, 2.5*cm, 2.5*cm, 2*cm, 2*cm, 4.5*cm])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
        ("PADDING",    (0, 0), (-1, -1), 5),
    ]))
    story.append(t2)
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("Portefeuilles prévisionnels recommandés", h2))
    for pf in portfolios:
        story.append(Paragraph(
            f"<b>{pf['name']}</b> — Risque {pf['risk']} — Objectif +{pf['target_min']}% à +{pf['target_max']}%",
            body
        ))
        pf_data = [["Ticker", "Poids", "Score", "Div%", "Momentum"]]
        for st in pf.get("stocks", []):
            pf_data.append([
                st["ticker"], f"{st['weight']:.1f}%",
                f"{st['score']:.0f}/80", f"{st.get('div_yield', 0):.1f}%",
                f"{st.get('momentum', 0):+.1f}%",
            ])
        tp = Table(pf_data, colWidths=[2.5*cm, 2*cm, 2.5*cm, 2*cm, 2.5*cm])
        tp.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTSIZE",   (0, 0), (-1, -1), 8),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("PADDING",    (0, 0), (-1, -1), 4),
        ]))
        story.append(tp)
        story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph("Signaux d'achat actifs", h2))
    sig_data = [["Ticker", "Score", "Prévision", "Confiance", "Raison"]]
    for sig in buy_signals[:10]:
        sig_data.append([
            sig["ticker"], f"{sig['score']:.0f}/80",
            f"{sig.get('score_prevision', 0):.2f}",
            f"{sig['confidence']}%", sig["raison"][:45],
        ])
    ts = Table(sig_data, colWidths=[2.2*cm, 2*cm, 2.2*cm, 2*cm, 7.1*cm])
    ts.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#166534")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0FDF4")]),
        ("PADDING",    (0, 0), (-1, -1), 4),
    ]))
    story.append(ts)
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        "Ce rapport est généré automatiquement. Les prévisions sont indicatives et ne constituent pas un conseil en investissement.",
        disc
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()


if __name__ == "__main__":
    print("Computing backtest…")
    r = compute_backtest_previsionnel()
    print(f"Directional accuracy (all years): {r['directional_accuracy']}%")
    print(f"Directional accuracy (recent split): {r['directional_accuracy_recent']}%")
    print(f"MAE recent: {r['mae_recent']}%")
    print(f"Sharpe modèle: {r['sharpe_model']}")
    print(f"Meilleure année: {r['best_year']} ({r['best_year_return']}%)")
    print(f"Pire année: {r['worst_year']} ({r['worst_year_return']}%)")
    print(f"Alpha moyen: {r['avg_alpha']}%")
