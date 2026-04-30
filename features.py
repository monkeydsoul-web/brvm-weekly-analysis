import os
import os as _os_fix
try:
    from dotenv import load_dotenv as _ld; _ld()
except ImportError:
    pass

"""
BRVM Features — Modules additionnels
Portfolio · Alertes prix · Score personnalisé · Export · Chat IA · Prévisions
"""

import os, json, glob, logging, csv, io
from datetime import datetime
from flask import jsonify, request, Response

logger = logging.getLogger(__name__)

DATA_DIR = "data"
PORTFOLIO_FILE = os.path.join(DATA_DIR, "portfolio.json")
ALERTS_FILE    = os.path.join(DATA_DIR, "alerts.json")
PREFS_FILE     = os.path.join(DATA_DIR, "preferences.json")
FAVORITES_FILE = os.path.join(DATA_DIR, "favorites.json")
TRANSACTIONS_FILE = os.path.join(DATA_DIR, "transactions.json")

# ── Default score weights ──────────────────────────────────────────────────
DEFAULT_WEIGHTS = {
    "graham": 1.0, "dcf": 1.0, "ddm": 1.0, "epv": 1.0,
    "buffett": 1.0, "rev_dcf": 1.0, "relatif": 1.0, "technique": 1.0
}

PROFILES = {
    "value":    {"graham":2.0,"dcf":1.5,"ddm":1.0,"epv":2.0,"buffett":1.0,"rev_dcf":1.5,"relatif":1.5,"technique":0.5},
    "income":   {"graham":1.5,"dcf":1.0,"ddm":2.5,"epv":1.0,"buffett":1.0,"rev_dcf":1.0,"relatif":1.0,"technique":0.5},
    "quality":  {"graham":0.5,"dcf":1.5,"ddm":1.0,"epv":1.5,"buffett":3.0,"rev_dcf":1.5,"relatif":1.0,"technique":0.5},
    "growth":   {"graham":0.5,"dcf":2.0,"ddm":0.5,"epv":1.0,"buffett":2.0,"rev_dcf":2.0,"relatif":1.0,"technique":1.0},
    "balanced": DEFAULT_WEIGHTS,
}

# ── Helpers ────────────────────────────────────────────────────────────────
def _load(path, default):
    if os.path.exists(path):
        try: return json.load(open(path))
        except: pass
    return default

def _save(path, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    json.dump(data, open(path,"w"), ensure_ascii=False, indent=2)

def _load_scores():
    files = sorted(glob.glob(os.path.join(DATA_DIR,"scores_*.json")))
    return json.load(open(files[-1])) if files else []

# ── Custom scoring ─────────────────────────────────────────────────────────
def apply_custom_weights(scores: list, weights: dict) -> list:
    result = []
    total_w = sum(weights.values()) or 8
    norm = 8 / total_w  # normalise to keep /80 scale
    for s in scores:
        custom = (
            (s.get("score_graham",0)  * weights.get("graham",1) +
             s.get("score_dcf",0)     * weights.get("dcf",1) +
             s.get("score_ddm",0)     * weights.get("ddm",1) +
             s.get("score_epv",0)     * weights.get("epv",1) +
             s.get("score_buffett",0) * weights.get("buffett",1) +
             s.get("score_rev_dcf",0) * weights.get("rev_dcf",1) +
             s.get("score_relatif",0) * weights.get("relatif",1) +
             s.get("score_technique",0)* weights.get("technique",1))
            * norm
        )
        row = dict(s)
        row["composite_custom"] = round(custom, 1)
        result.append(row)
    result.sort(key=lambda x: x["composite_custom"], reverse=True)
    for i,r in enumerate(result): r["custom_rank"] = i+1
    return result

# ── Portfolio ──────────────────────────────────────────────────────────────
def get_portfolio():
    return _load(PORTFOLIO_FILE, {})

def update_portfolio(ticker: str, shares: float, avg_price: float):
    p = get_portfolio()
    if shares <= 0:
        p.pop(ticker, None)
    else:
        p[ticker] = {"shares": shares, "avg_price": avg_price, "added": datetime.now().isoformat()}
    _save(PORTFOLIO_FILE, p)
    return p

def get_portfolio_summary():
    p = get_portfolio()
    if not p: return {"positions":[], "total_value":0, "total_cost":0, "total_gain":0, "total_gain_pct":0, "annual_div":0}
    scores = {s["ticker"]:s for s in _load_scores()}
    positions, total_value, total_cost, annual_div = [], 0, 0, 0
    for ticker, pos in p.items():
        s = scores.get(ticker, {})
        price = s.get("price") or pos["avg_price"]
        shares = pos["shares"]
        cost = shares * pos["avg_price"]
        value = shares * price
        gain = value - cost
        gain_pct = (gain/cost*100) if cost else 0
        div_income = shares * (s.get("div_per_share") or 0)
        total_value += value; total_cost += cost; annual_div += div_income
        positions.append({
            "ticker": ticker, "name": s.get("name",""), "sector": s.get("sector",""),
            "shares": shares, "avg_price": pos["avg_price"], "current_price": price,
            "cost": round(cost), "value": round(value),
            "gain": round(gain), "gain_pct": round(gain_pct,1),
            "div_yield": s.get("div_yield",0), "annual_div": round(div_income),
            "score": s.get("composite_adj",0), "weight_pct": 0,
        })
    positions.sort(key=lambda x: x["value"], reverse=True)
    if total_value:
        for pos in positions: pos["weight_pct"] = round(pos["value"]/total_value*100,1)
    total_gain = total_value - total_cost
    return {
        "positions": positions,
        "total_value": round(total_value), "total_cost": round(total_cost),
        "total_gain": round(total_gain),
        "total_gain_pct": round((total_gain/total_cost*100) if total_cost else 0, 1),
        "annual_div": round(annual_div),
        "div_yield_on_cost": round((annual_div/total_cost*100) if total_cost else 0, 2),
    }

# ── Transactions ───────────────────────────────────────────────────────────
def add_transaction(ticker, action, shares, price, date=None):
    t = _load(TRANSACTIONS_FILE, [])
    t.append({"ticker":ticker,"action":action,"shares":shares,"price":price,
               "date": date or datetime.now().strftime("%Y-%m-%d"),
               "total": round(shares*price)})
    _save(TRANSACTIONS_FILE, t)
    # Update portfolio
    p = get_portfolio()
    existing = p.get(ticker, {"shares":0,"avg_price":price})
    if action == "buy":
        total_shares = existing["shares"] + shares
        total_cost = existing["shares"]*existing["avg_price"] + shares*price
        p[ticker] = {"shares":total_shares, "avg_price":round(total_cost/total_shares,0), "added":datetime.now().isoformat()}
    elif action == "sell":
        new_shares = existing["shares"] - shares
        if new_shares <= 0: p.pop(ticker, None)
        else: p[ticker] = {"shares":new_shares, "avg_price":existing["avg_price"], "added":existing.get("added","")}
    _save(PORTFOLIO_FILE, p)
    return t

# ── Alerts ─────────────────────────────────────────────────────────────────
def get_alerts():
    return _load(ALERTS_FILE, [])

def add_alert(ticker, alert_type, threshold, direction="above"):
    alerts = get_alerts()
    alert = {"id": len(alerts)+1, "ticker":ticker, "type":alert_type,
              "threshold":threshold, "direction":direction,
              "active":True, "created":datetime.now().isoformat(), "triggered":None}
    alerts.append(alert)
    _save(ALERTS_FILE, alerts)
    return alert

def check_alerts():
    alerts = get_alerts()
    scores = {s["ticker"]:s for s in _load_scores()}
    triggered = []
    for alert in alerts:
        if not alert.get("active"): continue
        s = scores.get(alert["ticker"], {})
        val = s.get("price") if alert["type"]=="price" else s.get("composite_adj",0)
        if val is None: continue
        hit = (alert["direction"]=="above" and val >= alert["threshold"]) or \
              (alert["direction"]=="below" and val <= alert["threshold"])
        if hit:
            alert["triggered"] = datetime.now().isoformat()
            alert["active"] = False
            triggered.append({**alert, "current_value": val})
    _save(ALERTS_FILE, alerts)
    return triggered

def delete_alert(alert_id):
    alerts = [a for a in get_alerts() if a["id"] != alert_id]
    _save(ALERTS_FILE, alerts)

# ── Favorites ──────────────────────────────────────────────────────────────
def get_favorites():
    return _load(FAVORITES_FILE, [])

def toggle_favorite(ticker):
    favs = get_favorites()
    if ticker in favs: favs.remove(ticker)
    else: favs.append(ticker)
    _save(FAVORITES_FILE, favs)
    return favs

# ── Dividend simulator ─────────────────────────────────────────────────────
def simulate_dividends(investment_xof: float, years: int = 5, reinvest: bool = True) -> dict:
    scores = _load_scores()
    top = sorted(scores, key=lambda x: (x.get("composite_adj",0)), reverse=True)[:10]
    # Equal weight portfolio from top 10
    per_stock = investment_xof / len(top) if top else 0
    results = []
    for s in top:
        price = s.get("price") or 1
        div = s.get("div_per_share") or 0
        div_yield = s.get("div_yield") or 0
        if not price or not div: continue
        shares = per_stock / price
        annual_div = shares * div
        # Project with 5% annual dividend growth
        total_divs, value = 0, per_stock
        yearly = []
        g = 0.05
        for y in range(1, years+1):
            annual = shares * div * ((1+g)**y)
            total_divs += annual
            if reinvest:
                new_shares = annual / price
                shares += new_shares
                value = shares * price
            yearly.append(round(annual))
        results.append({"ticker":s["ticker"],"name":s.get("name",""),"div_yield":div_yield,
                         "annual_div_yr1":round(shares*div),"total_divs":round(total_divs),
                         "yearly":yearly})
    total_annual = sum(r["annual_div_yr1"] for r in results)
    total_over_period = sum(r["total_divs"] for r in results)
    return {"positions":results, "total_annual_yr1":round(total_annual),
            "total_over_period":round(total_over_period),
            "investment":round(investment_xof), "years":years, "reinvest":reinvest}

# ── Price targets & forecasts ──────────────────────────────────────────────
def get_price_targets() -> list:
    scores = _load_scores()
    targets = []
    for s in scores:
        price = s.get("price")
        eps = s.get("eps_est")
        bv = s.get("book_value_per_share")
        roe = s.get("roe", 0)
        pe = s.get("pe_ref", 15)
        if not price: continue
        # EPV target: normalised EPS / cost of capital
        epv_target = round(eps / 0.10) if eps else None
        # Graham target: sqrt(22.5 * EPS * BV)
        graham_target = round((22.5 * eps * bv) ** 0.5) if eps and bv else None
        # Warranted P/B: ROE / cost of equity
        warranted_pb = roe / 10.0 if roe else None
        pb_target = round(bv * warranted_pb) if bv and warranted_pb else None
        # Average of available targets
        available = [t for t in [epv_target, graham_target, pb_target] if t]
        avg_target = round(sum(available)/len(available)) if available else None
        upside = round((avg_target/price-1)*100, 1) if avg_target and price else None
        targets.append({
            "ticker": s["ticker"], "name": s.get("name",""),
            "current_price": price, "score": s.get("composite_adj",0),
            "epv_target": epv_target, "graham_target": graham_target,
            "pb_target": pb_target, "avg_target": avg_target,
            "upside_pct": upside,
            "verdict": "Fort potentiel" if (upside or 0)>30 else ("Potentiel modéré" if (upside or 0)>10 else "Proche valeur juste"),
        })
    targets.sort(key=lambda x: x.get("upside_pct") or -999, reverse=True)
    return targets

# ── Export ─────────────────────────────────────────────────────────────────
def export_csv() -> str:
    scores = _load_scores()
    buf = io.StringIO()
    if not scores: return ""
    fields = ["ticker","name","sector","country","price","change_pct","div_yield",
              "div_per_share","pe_ref","pb_ref","roe","eps_est",
              "composite_adj","score_graham","score_dcf","score_ddm","score_epv",
              "score_buffett","score_rev_dcf","score_relatif","score_technique",
              "ex_div_date","pay_div_date"]
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for s in sorted(scores, key=lambda x: x.get("composite_adj",0), reverse=True):
        w.writerow(s)
    return buf.getvalue()

# ── AI Chat ────────────────────────────────────────────────────────────────
def chat_with_ai(message, history):
    import requests as _req
    _key = os.environ.get("ANTHROPIC_API_KEY", "")
    _scores = _load_scores()
    _top = sorted(_scores, key=lambda x: x.get("composite_adj",0), reverse=True)[:5]
    _ctx = "Tu es analyste BRVM. Top actions: " + ", ".join(s["ticker"] for s in _top)
    _msgs = [{"role":"user","content":message}]
    import sys
    open("/tmp/brvm_chat_debug.log","a").write("CHAT_CALLED key=" + _key[:15] + "\n")
    try:
        _r = _req.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key":_key,"anthropic-version":"2023-06-01","content-type":"application/json"},
            json={"model":"claude-haiku-4-5-20251001","max_tokens":600,"system":_ctx,"messages":_msgs},
            timeout=30)
        print("CHAT_STATUS=" + str(_r.status_code), file=sys.stderr, flush=True)
        print("CHAT_RESP=" + _r.text[:100], file=sys.stderr, flush=True)
        _r.raise_for_status()
        return _r.json()["content"][0]["text"]
    except Exception as _e:
        print("CHAT_ERROR:", str(_e), file=sys.stderr, flush=True)
        return "Erreur: " + str(_e)

def register_routes(app):
    """Enregistre toutes les routes additionnelles sur l'app Flask"""

    @app.route("/api/scores/custom", methods=["POST"])
    def api_custom_scores():
        weights = request.json or {}
        scores = _load_scores()
        return jsonify(apply_custom_weights(scores, {**DEFAULT_WEIGHTS, **weights}))

    @app.route("/api/profiles")
    def api_profiles():
        return jsonify(PROFILES)

    @app.route("/api/portfolio", methods=["GET"])
    def api_portfolio_get():
        return jsonify(get_portfolio_summary())

    @app.route("/api/portfolio", methods=["POST"])
    def api_portfolio_post():
        d = request.json or {}
        update_portfolio(d["ticker"], float(d["shares"]), float(d["avg_price"]))
        return jsonify(get_portfolio_summary())

    @app.route("/api/portfolio/<ticker>", methods=["DELETE"])
    def api_portfolio_delete(ticker):
        update_portfolio(ticker, 0, 0)
        return jsonify(get_portfolio_summary())

    @app.route("/api/transactions", methods=["GET"])
    def api_transactions_get():
        return jsonify(_load(TRANSACTIONS_FILE, []))

    @app.route("/api/transactions", methods=["POST"])
    def api_transactions_post():
        d = request.json or {}
        t = add_transaction(d["ticker"], d["action"], float(d["shares"]), float(d["price"]), d.get("date"))
        return jsonify({"transactions": t, "portfolio": get_portfolio_summary()})

    @app.route("/api/favorites", methods=["GET"])
    def api_favorites_get():
        favs = get_favorites()
        scores = {s["ticker"]:s for s in _load_scores()}
        return jsonify([scores[f] for f in favs if f in scores])

    @app.route("/api/favorites/<ticker>", methods=["POST"])
    def api_favorites_toggle(ticker):
        return jsonify(toggle_favorite(ticker))

    @app.route("/api/alerts", methods=["GET"])
    def api_alerts_get():
        return jsonify(get_alerts())

    @app.route("/api/alerts", methods=["POST"])
    def api_alerts_post():
        d = request.json or {}
        return jsonify(add_alert(d["ticker"], d.get("type","price"), float(d["threshold"]), d.get("direction","above")))

    @app.route("/api/alerts/<int:alert_id>", methods=["DELETE"])
    def api_alerts_delete(alert_id):
        delete_alert(alert_id)
        return jsonify({"ok": True})

    @app.route("/api/alerts/check")
    def api_alerts_check():
        return jsonify(check_alerts())

    @app.route("/api/simulate/dividends")
    def api_sim_div():
        inv = float(request.args.get("investment", 1000000))
        years = int(request.args.get("years", 5))
        reinvest = request.args.get("reinvest","true").lower()=="true"
        return jsonify(simulate_dividends(inv, years, reinvest))

    @app.route("/api/targets")
    def api_targets():
        return jsonify(get_price_targets())

    @app.route("/api/export/csv")
    def api_export_csv():
        csv_data = export_csv()
        return Response(csv_data, mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename=BRVM_scores_{datetime.now().strftime('%Y%m%d')}.csv"})

    @app.route("/api/chat", methods=["POST"])
    def api_chat():
        import requests as _r2
        d = request.json or {}
        msg = d.get("message","")
        _k = os.environ.get("ANTHROPIC_API_KEY", "")
        try:
            _resp = _r2.post("https://api.anthropic.com/v1/messages",
                headers={"x-api-key":_k,"anthropic-version":"2023-06-01","content-type":"application/json"},
                json={"model":"claude-haiku-4-5-20251001","max_tokens":600,
                      "system":"Tu es analyste BRVM. Réponds en français.",
                      "messages":[{"role":"user","content":msg}]},
                timeout=30)
            _resp.raise_for_status()
            return jsonify({"reply": _resp.json()["content"][0]["text"]})
        except Exception as _ex:
            return jsonify({"reply": "Erreur: " + str(_ex)})

    @app.route("/api/search")
    def api_search():
        q = request.args.get("q","").upper()
        scores = _load_scores()
        if not q: return jsonify(scores)
        results = [s for s in scores if q in s.get("ticker","").upper() or q in s.get("name","").upper() or q in s.get("sector","").upper()]
        return jsonify(results)

    logger.info("Features routes registered")