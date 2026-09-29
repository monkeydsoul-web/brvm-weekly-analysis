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

import os, json, logging, csv, io
from datetime import datetime
from flask import jsonify, request, Response

logger = logging.getLogger(__name__)

from paths import DATA_DIR
from live_ranker import cle_tri_note, nombre_note

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
    """Lignes de live_ranking.json. Aucun repli sur scores_*.json."""
    from live_ranker import lire_lignes
    return lire_lignes(os.path.join(DATA_DIR, "live_ranking.json"))

# ── Custom scoring ─────────────────────────────────────────────────────────
def apply_custom_weights(scores: list, weights: dict) -> list:
    result = []
    total_w = sum(weights.values()) or 8
    norm = 8 / total_w  # normalise to keep /80 scale
    for s in scores:
        custom = (
            (nombre_note(s.get("score_graham"))  * weights.get("graham",1) +
             nombre_note(s.get("score_dcf"))     * weights.get("dcf",1) +
             nombre_note(s.get("score_ddm"))     * weights.get("ddm",1) +
             nombre_note(s.get("score_epv"))     * weights.get("epv",1) +
             nombre_note(s.get("score_buffett")) * weights.get("buffett",1) +
             nombre_note(s.get("score_rev_dcf")) * weights.get("rev_dcf",1) +
             nombre_note(s.get("score_relatif")) * weights.get("relatif",1) +
             nombre_note(s.get("score_technique"))* weights.get("technique",1))
            * norm
        )
        row = dict(s)
        row["composite_custom"] = round(custom, 1)
        result.append(row)
    result.sort(key=lambda x: x["composite_custom"], reverse=True)
    for i,r in enumerate(result): r["custom_rank"] = i+1
    return result

# ── Dividend simulator ─────────────────────────────────────────────────────
def simulate_dividends(investment_xof: float, years: int = 5, reinvest: bool = True) -> dict:
    scores = _load_scores()
    top = sorted(scores, key=cle_tri_note, reverse=True)[:10]
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
    """Même prix, même écart, même libellé que le classement (prix_cible.py)."""
    from prix_cible import estimer_prix_cible

    scores = _load_scores()
    targets = []
    for s in scores:
        price = s.get("price")
        if not price:
            continue
        estimation = estimer_prix_cible(s)
        if estimation["incertain"]:
            logger.warning(
                "[price_targets] %s: upside=%.1f%% (%d modèle(s)) — cible marquée incertaine",
                s.get("ticker", "?"), estimation["ecart_pct"], estimation["n_modeles"],
            )
        targets.append({
            "ticker": s["ticker"], "name": s.get("name", ""),
            "current_price": price, "score": nombre_note(s.get("composite_adj")),
            "epv_target": estimation["epv"],
            "graham_target": estimation["graham"],
            "pb_target": estimation["pb"],
            "avg_target": estimation["prix_cible"],
            "upside_pct": estimation["ecart_pct"],
            "verdict": estimation["libelle"],
            "n_models": estimation["n_modeles"],
            "target_unreliable": estimation["incertain"],
            "div_is_exceptional": estimation["dividende_exceptionnel"],
            "div_confidence": s.get("div_confidence", "inconnue"),
            "div_flag": s.get("div_flag", ""),
            "prix_cible": estimation["prix_cible"],
            "ecart_pct": estimation["ecart_pct"],
            "libelle_valeur": estimation["libelle"],
            "pe_secteur": estimation["pe_secteur"],
            "pb_secteur": estimation["pb_secteur"],
            "facteur_roe": estimation["facteur_roe"],
            "roe_secteur": estimation["roe_secteur"],
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
    for s in sorted(scores, key=cle_tri_note, reverse=True):
        w.writerow(s)
    return buf.getvalue()

# ── AI Chat ────────────────────────────────────────────────────────────────
def chat_with_ai(message, history):
    import requests as _req
    _key = os.environ.get("ANTHROPIC_API_KEY", "")
    _scores = _load_scores()
    _top = sorted(_scores, key=cle_tri_note, reverse=True)[:5]
    _ctx = "Tu es analyste BRVM. Top actions: " + ", ".join(s["ticker"] for s in _top)
    _msgs = [{"role":"user","content":message}]
    import sys
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

    @app.route("/api/chat", methods=["GET", "POST"])
    def api_chat():
        # Route retiree (SEC-1). Sans cette reponse, un POST etait avale par
        # la route statique Flask et renvoyait 405 au lieu de 404.
        return jsonify({"error": "not found"}), 404

    @app.route("/api/search")
    def api_search():
        q = request.args.get("q","").upper()
        scores = _load_scores()
        if not q: return jsonify(scores)
        results = [s for s in scores if q in s.get("ticker","").upper() or q in s.get("name","").upper() or q in s.get("sector","").upper()]
        return jsonify(results)

    logger.info("Features routes registered")