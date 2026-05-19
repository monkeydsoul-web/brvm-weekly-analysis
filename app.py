"""
BRVM Dashboard — Serveur Flask local
API backend pour l'application interactive Mac
Lance avec: python3 app.py
Ouvre: http://localhost:5000
"""

import os
import json
import glob
import logging
import threading
import subprocess
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory
try:
    from auto_scheduler import start_scheduler, get_scheduler_status
except Exception as _e:
    print(f"auto_scheduler import error: {_e}")
    def start_scheduler(): pass
    def get_scheduler_status(): return {}
from flask_cors import CORS
from live_valuation import compute_live_score, compute_all_live_scores
from live_data import get_live_data
try:
    from scraper import STOCK_FUNDAMENTALS
    print(f"STOCK_FUNDAMENTALS charge: {len(STOCK_FUNDAMENTALS)} tickers")
except ImportError:
    STOCK_FUNDAMENTALS = {}
    print("WARN: scraper.py introuvable")
try:
    from live_data import get_live_data, start_scheduler, is_market_open
    LIVE_DATA_OK = True
except ImportError:
    LIVE_DATA_OK = False

app = Flask(__name__, static_folder="dashboard", static_url_path="")
CORS(app)
logging.basicConfig(level=logging.INFO)
if LIVE_DATA_OK:
    start_scheduler()
logger = logging.getLogger("app")

DATA_DIR = "data"
REPORTS_DIR = "reports"

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_latest_scores():
    # Priorité 1 : live_ranking.json (reclassement automatique temps réel)
    live_path = os.path.join(DATA_DIR, "live_ranking.json")
    if os.path.exists(live_path):
        try:
            with open(live_path, encoding="utf-8") as f:
                data = json.load(f)
            ranking = data.get("ranking", [])
            if ranking:
                # Convertir au format attendu par le dashboard
                for r in ranking:
                    r.setdefault("composite_adj", r.get("composite_adj", 0))
                return ranking
        except Exception as e:
            logger.warning(f"live_ranking.json erreur: {e}")
    # Fallback : fichier scores_*.json statique
    files = sorted(glob.glob(os.path.join(DATA_DIR, "scores_*.json")))
    if not files:
        return []
    try:
        with open(files[-1]) as f:
            return json.load(f)
    except Exception:
        return []


def load_price_history():
    from price_history_builder import append_live_prices, get_price_history, load_history
    try:
        append_live_prices()
    except Exception:
        pass
    return load_history()

def _load_price_history_legacy():
    path = os.path.join(DATA_DIR, "price_history.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def load_news_cache():
    path = os.path.join(DATA_DIR, "news_cache.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def load_macro_cache():
    path = os.path.join(DATA_DIR, "macro_cache.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


# ── Données commodités (prix internationaux) ─────────────────────────────────

COMMODITY_IMPACT = {
    "SGBC":  {"commodities": [], "impact": "Indirect — taux d'intérêt BCEAO"},
    "SIBC":  {"commodities": [], "impact": "Indirect — taux BCEAO, crédit entreprises"},
    "SNTS":  {"commodities": ["Pétrole"], "impact": "Coûts énergétiques data centers et antennes"},
    "NSBC":  {"commodities": [], "impact": "Indirect — activité économique CI"},
    "CBIBF": {"commodities": [], "impact": "Indirect — économie Burkina Faso"},
    "BOAB":  {"commodities": ["Coton", "Cacao"], "impact": "Crédit aux exportateurs agricoles Bénin"},
    "BOABF": {"commodities": ["Or", "Coton"], "impact": "Financement mines d'or Burkina Faso"},
    "NTLC":  {"commodities": ["Cacao", "Café", "Lait", "Blé"], "impact": "Coûts matières premières production"},
    "SLBC":  {"commodities": ["Orge", "Houblon", "Sucre"], "impact": "Matières premières brasserie"},
    "SMBC":  {"commodities": ["Pétrole", "Bitume"], "impact": "Prix du bitume = prix de revient direct"},
    "PALC":  {"commodities": ["Huile de palme"], "impact": "Prix de vente directement lié au marché mondial"},
    "SPHC":  {"commodities": ["Caoutchouc"], "impact": "Prix de vente = cours mondial du caoutchouc"},
    "SOGC":  {"commodities": ["Caoutchouc"], "impact": "Même exposition que SAPH"},
    "SCRC":  {"commodities": ["Sucre"], "impact": "Prix de vente lié au cours mondial du sucre"},
    "TTLC":  {"commodities": ["Pétrole brut", "Produits raffinés"], "impact": "Marges de distribution liées au prix du pétrole"},
    "TTLS":  {"commodities": ["Pétrole brut"], "impact": "Distribution carburants Sénégal"},
    "SHEC":  {"commodities": ["Pétrole brut"], "impact": "Distribution Shell/Vivo Energy"},
    "ORAC":  {"commodities": ["Pétrole"], "impact": "Coûts réseau et énergie"},
    "ONTBF": {"commodities": ["Pétrole"], "impact": "Énergie pour infrastructure telecom"},
    "CIEC":  {"commodities": ["Gaz naturel", "Pétrole"], "impact": "Production électricité thermique CI"},
    "SDCC":  {"commodities": ["Pétrole", "Chlore"], "impact": "Pompage et traitement eau"},
    "STBC":  {"commodities": ["Tabac brut"], "impact": "Approvisionnement tabac importé"},
    "UNLC":  {"commodities": ["Huile palme", "Soja", "Pétrole"], "impact": "Matières premières produits ménagers"},
    "FTSC":  {"commodities": ["Pétrole", "Polypropylène"], "impact": "Matière première sacs plastique/jute"},
    "ABJC":  {"commodities": ["Pétrole", "Alimentation"], "impact": "Catering aérien — carburant + food cost"},
    "BOAC":  {"commodities": ["Cacao", "Café"], "impact": "Crédit filière cacao/café CI"},
    "ECOC":  {"commodities": ["Cacao", "Pétrole"], "impact": "Financement agro-industrie et énergie"},
    "ETIT":  {"commodities": ["Pétrole", "Or", "Cacao"], "impact": "Pan-africain — exposé à toutes les matières"},
}

COMMODITY_COLORS = {
    "Cacao":             "#5D3A1A",
    "Café":              "#8B4513",
    "Huile de palme":    "#FF8C00",
    "Caoutchouc":        "#2E8B57",
    "Pétrole brut":      "#1C1C1C",
    "Pétrole":           "#333333",
    "Or":                "#DAA520",
    "Coton":             "#87CEEB",
    "Sucre":             "#FFB6C1",
    "Blé":               "#F5DEB3",
    "Gaz naturel":       "#87CEEB",
    "Bitume":            "#696969",
    "Polypropylène":     "#9370DB",
    "Soja":              "#6B8E23",
    "Tabac brut":        "#A0522D",
    "Lait":              "#FFFACD",
    "Orge":              "#DEB887",
    "Houblon":           "#9ACD32",
    "Alimentation":      "#FF6347",
    "Chlore":            "#20B2AA",
}


_COMM_CACHE = {"data": {}, "ts": 0.0}
_COMM_TTL   = 300  # 5 minutes

def fetch_commodity_prices():
    """Récupère les prix des commodités (cache 5 min, fetches parallèles, timeout 3s/ticker)."""
    import time
    now = time.time()
    if _COMM_CACHE["data"] and now - _COMM_CACHE["ts"] < _COMM_TTL:
        return _COMM_CACHE["data"]

    commodities = {
        "Cacao":        {"symbol": "CC=F",  "unit": "USD/tonne"},
        "Café":         {"symbol": "KC=F",  "unit": "USD/livre"},
        "Huile palme":  {"symbol": "PGFF",  "unit": "USD/tonne"},
        "Caoutchouc":   {"symbol": "RUBBF", "unit": "USD/kg"},
        "Pétrole Brent":{"symbol": "BZ=F",  "unit": "USD/baril"},
        "Or":           {"symbol": "GC=F",  "unit": "USD/once"},
        "Coton":        {"symbol": "CT=F",  "unit": "USD/livre"},
        "Sucre":        {"symbol": "SB=F",  "unit": "USD/livre"},
        "Blé":          {"symbol": "ZW=F",  "unit": "USD/boisseau"},
        "Gaz naturel":  {"symbol": "NG=F",  "unit": "USD/MMBtu"},
    }

    prices = {}
    try:
        import yfinance as yf
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch_one(name, info):
            try:
                ticker = yf.Ticker(info["symbol"])
                hist = ticker.history(period="5d", timeout=3)
                if not hist.empty:
                    last = float(hist["Close"].iloc[-1])
                    prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last
                    change = (last / prev - 1) * 100
                    return name, {
                        "price": round(last, 2),
                        "change_pct": round(change, 2),
                        "unit": info["unit"],
                        "symbol": info["symbol"],
                    }
            except Exception:
                pass
            return name, None

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {pool.submit(_fetch_one, n, i): n for n, i in commodities.items()}
            for fut in as_completed(futures, timeout=8):
                try:
                    name, result = fut.result()
                    if result:
                        prices[name] = result
                except Exception:
                    pass

    except ImportError:
        prices = {
            "Cacao":         {"price": 7842, "change_pct": -1.2, "unit": "USD/tonne"},
            "Café Arabica":  {"price": 3.15, "change_pct": +0.8, "unit": "USD/livre"},
            "Huile palme":   {"price": 1050, "change_pct": +2.1, "unit": "USD/tonne"},
            "Caoutchouc":    {"price": 1.82, "change_pct": -0.5, "unit": "USD/kg"},
            "Pétrole Brent": {"price": 74.3, "change_pct": +1.4, "unit": "USD/baril"},
            "Or":            {"price": 3320, "change_pct": +0.3, "unit": "USD/once"},
            "Coton":         {"price": 0.68, "change_pct": -1.8, "unit": "USD/livre"},
            "Sucre":         {"price": 0.19, "change_pct": +0.6, "unit": "USD/livre"},
            "Blé":           {"price": 5.42, "change_pct": -0.9, "unit": "USD/boisseau"},
            "Gaz naturel":   {"price": 3.85, "change_pct": +2.3, "unit": "USD/MMBtu"},
        }

    if prices:
        _COMM_CACHE["data"] = prices
        _COMM_CACHE["ts"]   = now
    elif _COMM_CACHE["data"]:
        return _COMM_CACHE["data"]

    return prices


# ── Routes API ────────────────────────────────────────────────────────────────


@app.route("/simulator.js")
def serve_simulator():
    return send_from_directory("dashboard", "simulator.js",
                               mimetype="application/javascript")

@app.route("/")
def index():
    return send_from_directory("dashboard", "index.html")


@app.route("/api/scores")
def api_scores():
    scores = load_latest_scores()
    return jsonify(scores)


@app.route("/api/stock/<ticker>")
def api_stock(ticker):
    scores = load_latest_scores()
    stock = next((s for s in scores if s.get("ticker") == ticker.upper()), None)
    if not stock:
        return jsonify({"error": "Ticker non trouvé"}), 404

    # Historique des prix
    history = load_price_history()
    price_history = history.get(ticker.upper(), [])

    # News liées
    all_news = load_news_cache()
    stock_news = [n for n in all_news if ticker.upper() in n.get("tickers", [])]

    # Impact commodités
    commodity_info = COMMODITY_IMPACT.get(ticker.upper(), {"commodities": [], "impact": "Non évalué"})
    commodity_prices = fetch_commodity_prices()

    relevant_commodities = {}
    for c in commodity_info.get("commodities", []):
        for key, val in commodity_prices.items():
            if c.lower() in key.lower() or key.lower() in c.lower():
                relevant_commodities[c] = val

    return jsonify({
        "stock": stock,
        "price_history": price_history[-52:],  # 52 semaines max
        "news": stock_news[:10],
        "commodity_impact": commodity_info["impact"],
        "commodities": commodity_info.get("commodities", []),
        "commodity_prices": relevant_commodities,
    })


@app.route("/api/top_performers")
def api_top_performers():
    """Top performers — sociétés avec meilleure variation sur 52 semaines."""
    try:
        scores = load_latest_scores()
        from price_history_builder import load_history
        history = load_history()
        performers = []
        for s in scores:
            ticker = s.get("ticker")
            hist = history.get(ticker, [])
            if len(hist) >= 2:
                hist_sorted = sorted(hist, key=lambda x: x.get("date",""))
                first = hist_sorted[0].get("price", 0)
                last  = hist_sorted[-1].get("price", 0)
                if first and first > 0:
                    perf = round((last - first) / first * 100, 1)
                    performers.append({
                        "ticker": ticker,
                        "name": s.get("name",""),
                        "sector": s.get("sector",""),
                        "perf_1y": perf,
                        "price": last,
                        "composite_adj": s.get("composite_adj", 0)
                    })
        performers.sort(key=lambda x: x.get("perf_1y", 0), reverse=True)
        return jsonify(performers[:10])
    except Exception as e:
        return jsonify([])

@app.route("/api/news")
def api_news():
    ticker = request.args.get("ticker", "")
    all_news = load_news_cache()
    if ticker:
        news = [n for n in all_news if ticker.upper() in n.get("tickers", [])]
    else:
        news = all_news
    return jsonify(news[:50])


@app.route("/api/commodities")
def api_commodities():
    prices = fetch_commodity_prices()
    return jsonify(prices)


@app.route("/api/macro")
def api_macro():
    macro = load_macro_cache()
    return jsonify(macro)


@app.route("/api/history/<ticker>")
def api_history(ticker):
    history = load_price_history()
    data = history.get(ticker.upper(), [])
    return jsonify(data)


@app.route("/api/sector/<sector>")
def api_sector(sector):
    scores = load_latest_scores()
    stocks = [s for s in scores if s.get("sector", "").lower() == sector.lower()]
    return jsonify(stocks)


@app.route("/api/top/<int:n>")
def api_top(n):
    scores = load_latest_scores()
    sorted_scores = sorted(scores, key=lambda x: x.get("composite_adj", 0), reverse=True)
    return jsonify(sorted_scores[:n])


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Lance une mise à jour des données en arrière-plan"""
    def run_update():
        try:
            subprocess.run(
                ["python3", "main.py", "--no-github", "--no-email"],
                timeout=300,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            # Sauvegarder les news dans le cache
            _cache_news()
        except Exception as e:
            logger.error(f"Refresh: {e}")

    thread = threading.Thread(target=run_update, daemon=True)
    thread.start()
    return jsonify({"status": "started", "message": "Mise à jour lancée en arrière-plan (~2 min)"})


@app.route("/api/refresh/status")
def api_refresh_status():
    files = sorted(glob.glob(os.path.join(DATA_DIR, "scores_*.json")))
    if files:
        mtime = os.path.getmtime(files[-1])
        last_update = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y à %H:%M")
        age_minutes = (datetime.now().timestamp() - mtime) / 60
        return jsonify({
            "last_update": last_update,
            "age_minutes": round(age_minutes),
            "fresh": age_minutes < 60 * 24 * 7,
        })
    return jsonify({"last_update": "Jamais", "age_minutes": 9999, "fresh": False})


def _cache_news():
    """Cache les news dans un fichier JSON pour l'app"""
    try:
        from news_scraper import fetch_all_news
        news = fetch_all_news()
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, "news_cache.json"), "w") as f:
            json.dump(news, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Cache news: {e}")


def _cache_macro():
    """Cache le contexte macro"""
    try:
        from news_scraper import fetch_macro_context
        macro = fetch_macro_context()
        with open(os.path.join(DATA_DIR, "macro_cache.json"), "w") as f:
            json.dump(macro, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Cache macro: {e}")



try:
    from features import register_routes
    register_routes(app)
    print('Features OK')
except Exception as e:
    print(f'Features error: {e}')



# ─── ROUTES AJOUTÉES PAR install_improvements.py ─────────────────────────────

@app.route("/api/candlestick/<ticker>")
def api_candlestick(ticker):
    """Données OHLC + SVG candlestick pour un ticker."""
    try:
        from candlestick import get_candlestick_data_for_ticker
        data = get_candlestick_data_for_ticker(ticker.upper())
        period = request.args.get("period", "1y")
        return jsonify({
            "ticker": data["ticker"],
            "ohlc":   data.get(f"ohlc_{period}", data["ohlc_1y"]),
            "svg":    data.get(f"svg_{period}",  data["svg_1y"]),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/backtesting")
def api_backtesting():
    """Lance ou retourne le backtesting des scores."""
    from pathlib import Path
    import json
    cache_file = Path("backtesting_cache.json")
    force = request.args.get("force", "0") == "1"

    if not force and cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            data["from_cache"] = True
            return jsonify(data)
        except Exception:
            pass

    try:
        from backtesting import run_backtesting
        result = run_backtesting()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/backtesting/summary")
def api_backtesting_summary():
    """HTML résumé du backtesting pour le dashboard."""
    try:
        from backtesting import get_backtesting_summary_html
        return get_backtesting_summary_html(), 200, {"Content-Type": "text/html"}
    except Exception as e:
        return f"<p>Erreur: {e}</p>", 500

# ─── FIN ROUTES AJOUTÉES ──────────────────────────────────────────────────────


@app.route("/api/portfolio/optimize")
def api_portfolio_optimize():
    from portfolio_optimizer import optimize, load_cache
    import json
    force = request.args.get("force", "false").lower() == "true"
    cache = load_cache()
    if cache and not force:
        cache["from_cache"] = True
        return jsonify(cache)
    result = optimize(n_sim=5000)
    return jsonify(result)

@app.route("/api/portfolio/optimize/summary")
def api_portfolio_optimize_summary():
    from portfolio_optimizer import get_optimizer_html, optimize, load_cache
    cache = load_cache()
    if not cache:
        optimize(n_sim=3000)
    return get_optimizer_html()



@app.route("/api/market")
def api_market():
    """Donnees marche BRVM — indices, top5, flop5, secteurs"""
    try:
        from market_data import get_market_data
        force = request.args.get("force","false").lower() == "true"
        data = get_market_data(force_refresh=force)
        # Si top5 vide, forcer refresh
        if not data.get("top5") and not force:
            data = get_market_data(force_refresh=True)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/live")
def api_live():
    """Cours live BRVM depuis brvm.org — cache 5 min"""
    try:
        force = request.args.get("force", "false").lower() == "true"
        data = get_live_data(force_refresh=force)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/live/<ticker>")
def api_live_ticker(ticker):
    """Cours live pour un ticker specifique"""
    try:
        data = get_live_data()
        prices = data.get("prices", {})
        t = ticker.upper()
        if t not in prices:
            return jsonify({"error": f"{t} non trouve"}), 404
        return jsonify({"ticker": t, **prices[t], "updated_at": data.get("updated_at")})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/status")
def api_status():
    """Statut du marche et du cache live"""
    try:
        data = get_live_data()
        stats = data.get("stats", {})
        return jsonify({
            "market_open": data.get("market_open", False),
            "updated_at":  data.get("updated_at"),
            "total":       stats.get("total", 0),
            "with_price":  stats.get("with_price", 0),
            "sources":     stats.get("sources", {}),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/company/<ticker>")
def api_company(ticker):
    """Fiche société enrichie : activité, produits, marchés, rapports"""
    try:
        from company_data import get_company
        import anthropic, os
        t = ticker.upper()
        company = get_company(t)

        # Récupère le prix live
        live = {}
        try:
            cache = get_live_data()
            live = cache.get("prices", {}).get(t, {})
        except Exception:
            pass

        # Enrichissement IA — résumé activité + perspectives
        ai_summary = ""
        try:
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            prompt = f"""Tu es un analyste financier spécialisé sur la BRVM (Bourse Régionale des Valeurs Mobilières d'Afrique de l'Ouest).

Société : {company.get('name')} ({t})
Secteur : {company.get('sector')} | Pays : {company.get('country')}
Fondée : {company.get('founded', 'N/D')}
Description : {company.get('description', '')}
Produits/Services : {', '.join(company.get('products', []))}
Marchés : {', '.join(company.get('markets', []))}

Donne en 3-4 phrases courtes :
1. Le positionnement stratégique de cette société sur la BRVM
2. Les principaux moteurs de croissance ou risques en 2025-2026
3. Une perspective sur l'attractivité du titre pour un investisseur long terme

Réponds en français, de façon factuelle et concise."""
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            ai_summary = resp.content[0].text
        except Exception as e:
            ai_summary = ""

        return jsonify({
            "ticker": t,
            "company": company,
            "live": live,
            "ai_summary": ai_summary,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/api/live-score/<ticker>")
def api_live_score_ticker(ticker):
    ticker = ticker.upper()
    if ticker not in STOCK_FUNDAMENTALS:
        return jsonify({"error": f"Ticker {ticker} inconnu"}), 404
    try:
        from live_ranker import load_ranking
        ranking_data = load_ranking()
        if ranking_data and "ranking" in ranking_data:
            entry = next((r for r in ranking_data["ranking"] if r.get("ticker") == ticker), None)
            if entry:
                return jsonify(entry)
    except Exception as e:
        print(f"[live-score] fallback live_valuation: {e}")
    # Fallback calcul a la volee
    force = request.args.get("refresh", "0") == "1"
    try:
        live_cache = get_live_data(force_refresh=force)
        result = compute_live_score(ticker, STOCK_FUNDAMENTALS[ticker], live_cache)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/live-scores")
def api_live_scores_all():
    try:
        from live_ranker import load_ranking
        ranking_data = load_ranking()
        if ranking_data and "ranking" in ranking_data:
            r = ranking_data["ranking"]
            return jsonify({
                "scores":     r,
                "ranking":    r,
                "updated_at": ranking_data.get("updated_at"),
                "market_open": ranking_data.get("market_open"),
                "total":      len(r)
            })
    except Exception as e:
        print(f"[live-scores] fallback compute_all: {e}")
    # Fallback
    force = request.args.get("refresh", "0") == "1"
    try:
        live_cache = get_live_data(force_refresh=force)
        results = compute_all_live_scores(STOCK_FUNDAMENTALS, live_cache)
        return jsonify({"scores": results, "updated_at": live_cache.get("updated_at"), "market_open": live_cache.get("market_open"), "total": len(results)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/live_score.js")
def serve_live_score_js():
    return send_from_directory("dashboard", "live_score.js", mimetype="application/javascript")

@app.route("/ranking.js")
def serve_ranking_js():
    return send_from_directory("dashboard", "ranking.js", mimetype="application/javascript")

@app.route("/stock_chart.js")
def serve_stock_chart_js():
    return send_from_directory("dashboard", "stock_chart.js", mimetype="application/javascript")

@app.route("/badges.js")
def serve_badges_js():
    return send_from_directory("dashboard", "badges.js", mimetype="application/javascript")

@app.route("/compare.js")
def serve_compare_js():
    return send_from_directory("dashboard", "compare.js", mimetype="application/javascript")

@app.route("/alerts.js")
def serve_alerts_js():
    return send_from_directory("dashboard", "alerts.js", mimetype="application/javascript")

@app.route("/markowitz.js")
def serve_markowitz_js():
    return send_from_directory("dashboard", "markowitz.js", mimetype="application/javascript")

@app.route("/backtest.js")
def serve_backtest_js():
    return send_from_directory("dashboard", "backtest.js", mimetype="application/javascript")

@app.route("/compare_analysis.js")
def serve_compare_analysis_js():
    return send_from_directory("dashboard", "compare_analysis.js", mimetype="application/javascript")

@app.route("/performance.js")
def serve_performance_js():
    return send_from_directory("dashboard", "performance.js", mimetype="application/javascript")

@app.route("/sectors.js")
def serve_sectors_js():
    return send_from_directory("dashboard", "sectors.js", mimetype="application/javascript")

@app.route("/screener.js")
def serve_screener_js():
    return send_from_directory("dashboard", "screener.js", mimetype="application/javascript")

@app.route("/previsions.js")
def serve_previsions_js():
    return send_from_directory("dashboard", "previsions.js", mimetype="application/javascript")


@app.route("/api/reports/<ticker>")
def api_reports(ticker):
    ticker = ticker.upper()
    force = request.args.get("refresh", "0") == "1"
    try:
        from reports_scraper import get_reports
        reports = get_reports(ticker, force_refresh=force)
        return jsonify({"ticker": ticker, "reports": reports, "total": len(reports)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyze-report", methods=["POST"])
def api_analyze_report():
    data = request.get_json() or {}
    url      = data.get("url")
    ticker   = (data.get("ticker") or "").upper()
    doc_type = data.get("doc_type", "Document")
    year     = data.get("year")
    force    = data.get("force", False)
    if not url or not ticker:
        return jsonify({"error": "url et ticker requis"}), 400
    try:
        from pdf_analyzer import analyze_report
        result = analyze_report(url, ticker, doc_type, year, force=force)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/analyze-ticker/<ticker>")
def api_analyze_ticker(ticker):
    ticker = ticker.upper()
    force  = request.args.get("force", "0") == "1"
    try:
        from reports_scraper import get_reports
        from pdf_analyzer    import get_analyses_for_ticker
        reports = get_reports(ticker)
        if not reports:
            return jsonify({"error": f"Aucun rapport pour {ticker}"}), 404
        results = get_analyses_for_ticker(ticker, reports, max_reports=2, force=force)
        return jsonify({"ticker": ticker, "analyses": results, "total": len(results)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/live-ranking")
def api_live_ranking():
    force = request.args.get("refresh", "0") == "1"
    try:
        from live_ranker import compute_live_ranking, load_ranking
        result = compute_live_ranking(trigger="manual") if force else (load_ranking() or compute_live_ranking(trigger="manual"))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/live-ranking/changes")
def api_live_ranking_changes():
    try:
        from live_ranker import get_ranking_changes
        return jsonify(get_ranking_changes())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/sector-analysis", methods=["POST"])
def api_sector_analysis():
    """Analyse IA d'un secteur BRVM complet."""
    try:
        data = request.json or {}
        sector = data.get("sector", "Banque")
        
        import anthropic, os
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY",""))
        
        scores = load_latest_scores()
        analyses = json.load(open(os.path.join(DATA_DIR, "analyses_summary.json"), encoding="utf-8"))
        sector_indices = {}
        si_path = os.path.join(DATA_DIR, "sector_indices.json")
        if os.path.exists(si_path):
            sector_indices = json.load(open(si_path)).get("indices", {})
        
        # Sociétés du secteur
        sector_stocks = [s for s in scores if s.get("sector") == sector]
        sector_stocks.sort(key=lambda x: x.get("composite_adj", 0), reverse=True)
        
        if not sector_stocks:
            return jsonify({"error": f"Secteur {sector} non trouvé"}), 404
        
        # Contexte sectoriel
        idx_key = next((k for k in sector_indices if sector.lower() in k.lower() or k.lower() in sector.lower()), None)
        idx_data = sector_indices.get(idx_key, {}) if idx_key else {}
        
        companies_ctx = []
        for s in sector_stocks:
            a = analyses.get(s["ticker"], {})
            kpis = a.get("kpis", {})
            def kv(k): return (kpis.get(k) or {}).get("valeur")
            ctx = f"• {s['ticker']} ({s.get('country','')}) — Score {s.get('composite_adj',0):.0f}/80 | P/E {s.get('pe_ref','?')} | ROE {s.get('roe','?')}% | Div {s.get('div_yield',0):.1f}% | Verdict: {a.get('verdict_investisseur','N/D')} | CA: {kv('chiffre_affaires')} MFCFA | RN: {kv('resultat_net')} MFCFA"
            companies_ctx.append(ctx)
        
        idx_ctx = f"Indice BRVM {sector}: {idx_data.get('current','N/D')} ({idx_data.get('change',0):+.2f}% jour, YTD {idx_data.get('ytd',0):+.2f}%)" if idx_data else ""
        
        prompt = f"""Tu es un analyste sectoriel expert de la BRVM (Bourse Régionale des Valeurs Mobilières d'Afrique de l'Ouest).

SECTEUR: {sector} ({len(sector_stocks)} sociétés cotées)
{idx_ctx}

SOCIÉTÉS DU SECTEUR:
{chr(10).join(companies_ctx)}

Effectue une analyse sectorielle complète et structurée:

1. **Vue d'ensemble du secteur** — Dynamiques, tendances, environnement macro UEMOA
2. **Classement et champions** — Top 3 et pourquoi, sociétés à éviter
3. **Comparaison valorisation** — P/E et P/B moyens vs normes sectorielles mondiales  
4. **Dividendes sectoriels** — Généreux vs avares, tendances de distribution
5. **Risques sectoriels communs** — Taux, réglementation, concurrence, géopolitique
6. **Opportunités 2026** — Catalyseurs de croissance identifiés
7. **Recommandation de portefeuille sectoriel** — Pondération suggérée entre les sociétés

Sois précis, data-driven et pratique. Réponds en français."""

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return jsonify({
            "analysis": response.content[0].text,
            "sector": sector,
            "nb_stocks": len(sector_stocks),
            "generated_at": __import__("datetime").datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"sector-analysis: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/compare-analysis", methods=["POST"])
def api_compare_analysis():
    """Analyse comparative IA de plusieurs sociétés BRVM."""
    try:
        data = request.json or {}
        tickers = data.get("tickers", [])[:6]  # max 6
        question = data.get("question", "")
        
        if not tickers:
            return jsonify({"error": "Aucun ticker fourni"}), 400
        
        import anthropic, os
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY",""))
        
        scores = load_latest_scores()
        analyses = json.load(open(os.path.join(DATA_DIR, "analyses_summary.json"), encoding="utf-8"))
        boc = {}
        boc_path = os.path.join(DATA_DIR, "boc_data.json")
        if os.path.exists(boc_path):
            boc = json.load(open(boc_path))
        
        # Construire contexte enrichi pour chaque société
        companies_ctx = []
        for ticker in tickers:
            stock = next((s for s in scores if s.get("ticker") == ticker), {})
            analysis = analyses.get(ticker, {})
            boc_data = boc.get(ticker, {})
            kpis = analysis.get("kpis", {})
            
            def kv(k): return (kpis.get(k) or {}).get("valeur")
            
            ctx = f"""
=== {ticker} — {stock.get("name", "")} ({stock.get("sector", "")} · {stock.get("country", "")}) ===
Score global: {stock.get("composite_adj", 0):.1f}/80 | Rang: #{stock.get("rank", "?")}
Cours: {stock.get("price", 0):,} XOF | Var annuelle: {boc_data.get("var_annee", "?")}%
P/E: {stock.get("pe_ref", "?")} | P/B: {stock.get("pb_ref", "?")} | ROE: {stock.get("roe", "?")}%
BNA: {stock.get("eps", "?")} XOF | BVPA: {stock.get("bvpa", "?")} XOF
Dividende: {stock.get("div_per_share", 0)} XOF ({stock.get("div_yield", 0):.1f}%) | Ex-div: {stock.get("ex_div_date", "N/D")}
Scores modèles: Graham={stock.get("score_graham", 0):.0f} DCF={stock.get("score_dcf", 0):.0f} DDM={stock.get("score_ddm", 0):.0f} EPV={stock.get("score_epv", 0):.0f} Buffett={stock.get("score_buffett", 0):.0f} RevDCF={stock.get("score_rev_dcf", 0):.0f} Relatif={stock.get("score_relatif", 0):.0f} Tech={stock.get("score_technique", 0):.0f}
CA: {kv("chiffre_affaires")} MFCFA | RN: {kv("resultat_net")} MFCFA | EBITDA: {kv("ebitda")} MFCFA
Capitaux propres: {kv("capitaux_propres")} MFCFA | Dette nette: {kv("dette_nette")} MFCFA
Verdict IA: {analysis.get("verdict_investisseur", "N/D")}
Points clés: {" | ".join((analysis.get("points_cles") or [])[:3])}
Risques: {" | ".join((analysis.get("risques") or [])[:2])}
Perspectives: {analysis.get("perspectives", "")[:200] if analysis.get("perspectives") else "N/D"}
"""
            companies_ctx.append(ctx)
        
        question_part = ("\n\nQuestion spécifique: " + question) if question else ""
        
        prompt = f"""Tu es un analyste financier expert de la BRVM (Bourse Régionale des Valeurs Mobilières d'Afrique de l'Ouest).

Voici les données détaillées des sociétés à analyser comparativement:

{"".join(companies_ctx)}

Effectue une analyse comparative approfondie et structurée:{question_part}

Ta réponse doit inclure:
1. **Synthèse comparative** — Points forts/faibles de chaque société
2. **Classement recommandé** — De la plus à la moins attractive pour un investisseur
3. **Valorisation relative** — Quelle est la mieux valorisée (P/E, P/B, DDM)
4. **Dividendes** — Comparaison rendements et régularité
5. **Risques spécifiques** — Par société et sectoriels
6. **Recommandation finale** — Avec justification claire

Utilise les données chiffrées. Sois précis, concis et pratique. Réponds en français."""

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        analysis_text = response.content[0].text
        return jsonify({
            "analysis": analysis_text,
            "tickers": tickers,
            "generated_at": __import__("datetime").datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"compare-analysis: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/markowitz", methods=["POST"])
def api_markowitz():
    """Optimisation portefeuille Markowitz - frontière efficiente BRVM."""
    try:
        data = request.json or {}
        tickers = data.get("tickers", [])
        n_portfolios = data.get("n_portfolios", 3000)
        risk_free = data.get("risk_free", 0.06)  # BCEAO taux ~6%
        
        if len(tickers) < 2:
            return jsonify({"error": "Minimum 2 actifs"}), 400
        
        import json as _json, numpy as np
        ph_path = os.path.join(DATA_DIR, "price_history.json")
        with open(ph_path) as f:
            history = _json.load(f)
        
        # Extraire séries de prix (BOC seulement - quotidien)
        price_series = {}
        for ticker in tickers:
            pts = sorted([p for p in history.get(ticker, []) 
                         if p.get("source") == "boc"], key=lambda x: x["date"])
            if len(pts) >= 20:
                price_series[ticker] = {p["date"]: p["price"] for p in pts}
        
        valid_tickers = list(price_series.keys())
        if len(valid_tickers) < 2:
            return jsonify({"error": "Données insuffisantes (min 20 points BOC)"}), 400
        
        # Aligner les dates communes
        all_dates = sorted(set.intersection(*[set(ps.keys()) for ps in price_series.values()]))
        if len(all_dates) < 10:
            # Si peu de dates communes, utiliser union avec forward-fill
            all_dates = sorted(set.union(*[set(ps.keys()) for ps in price_series.values()]))
        
        # Construire matrice de prix
        prices = {}
        for ticker in valid_tickers:
            ps = price_series[ticker]
            last_price = None
            ticker_prices = []
            for d in all_dates:
                if d in ps:
                    last_price = ps[d]
                ticker_prices.append(last_price)
            prices[ticker] = ticker_prices
        
        # Retours journaliers
        returns = {}
        for ticker in valid_tickers:
            p = [x for x in prices[ticker] if x is not None]
            if len(p) < 2:
                continue
            ret = [(p[i]-p[i-1])/p[i-1] for i in range(1, len(p))]
            returns[ticker] = ret
        
        valid_tickers = [t for t in valid_tickers if t in returns and len(returns[t]) >= 10]
        if len(valid_tickers) < 2:
            return jsonify({"error": "Retours insuffisants"}), 400
        
        # Matrice de retours
        min_len = min(len(returns[t]) for t in valid_tickers)
        R = np.array([[returns[t][i] for t in valid_tickers] for i in range(min_len)])
        
        # Statistiques
        mean_returns = R.mean(axis=0) * 252  # annualisé
        cov_matrix = np.cov(R.T) * 252
        
        # Simulation Monte Carlo
        results = []
        np.random.seed(42)
        for _ in range(n_portfolios):
            w = np.random.dirichlet(np.ones(len(valid_tickers)))
            port_ret = float(np.dot(w, mean_returns))
            port_vol = float(np.sqrt(w @ cov_matrix @ w))
            sharpe = (port_ret - risk_free) / port_vol if port_vol > 0 else 0
            results.append({
                "weights": {valid_tickers[i]: round(float(w[i]), 4) for i in range(len(valid_tickers))},
                "return": round(port_ret * 100, 2),
                "volatility": round(port_vol * 100, 2),
                "sharpe": round(sharpe, 3)
            })
        
        # Trouver les portefeuilles optimaux
        max_sharpe = max(results, key=lambda x: x["sharpe"])
        min_vol = min(results, key=lambda x: x["volatility"])
        max_ret = max(results, key=lambda x: x["return"])
        
        # Frontière efficiente (top 200 points)
        frontier = sorted(results, key=lambda x: x["volatility"])
        efficient = []
        max_ret_seen = -999
        for p in frontier:
            if p["return"] > max_ret_seen:
                max_ret_seen = p["return"]
                efficient.append(p)
        
        # Stats individuelles
        individual = {}
        for i, ticker in enumerate(valid_tickers):
            individual[ticker] = {
                "annual_return": round(float(mean_returns[i]) * 100, 2),
                "annual_vol": round(float(np.sqrt(cov_matrix[i,i])) * 100, 2),
                "sharpe": round((float(mean_returns[i]) - risk_free) / float(np.sqrt(cov_matrix[i,i])), 3) if cov_matrix[i,i] > 0 else 0
            }
        
        # Nuage de points (échantillon 500)
        import random
        cloud = random.sample(results, min(500, len(results)))
        
        return jsonify({
            "tickers": valid_tickers,
            "max_sharpe": max_sharpe,
            "min_volatility": min_vol,
            "max_return": max_ret,
            "frontier": efficient[:100],
            "cloud": cloud,
            "individual": individual,
            "n_simulated": len(results),
            "risk_free": risk_free * 100,
        })
    except ImportError:
        return jsonify({"error": "numpy non disponible"}), 500
    except Exception as e:
        logger.error(f"markowitz: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/backtest", methods=["POST"])
def api_backtest():
    """Backtesting portefeuille BRVM sur historique de prix."""
    try:
        data = request.json or {}
        tickers = data.get("tickers", [])
        weights = data.get("weights", {})  # {ticker: poids}
        period = data.get("period", "1an")  # 1an, 3ans, 5ans, tout
        initial_capital = data.get("capital", 1000000)  # FCFA
        
        if not tickers:
            return jsonify({"error": "Aucun ticker"}), 400
        
        import json as _json
        ph_path = os.path.join(DATA_DIR, "price_history.json")
        if not os.path.exists(ph_path):
            return jsonify({"error": "Historique non disponible"}), 404
        
        with open(ph_path) as f:
            history = _json.load(f)
        
        from datetime import datetime, timedelta
        now = datetime.now()
        period_map = {"1an": 365, "3ans": 1095, "5ans": 1825, "tout": 3650}
        days = period_map.get(period, 365)
        cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        
        # Pondérations égales si non fournies
        n = len(tickers)
        equal_w = 1.0 / n
        
        # Calculer performance par ticker
        results = {}
        portfolio_data = {}
        
        for ticker in tickers:
            pts = sorted([p for p in history.get(ticker, []) if p.get("date", "") >= cutoff], 
                        key=lambda x: x["date"])
            if len(pts) < 2:
                continue
            
            first_price = pts[0]["price"]
            last_price = pts[-1]["price"]
            if first_price <= 0:
                continue
            
            perf_pct = (last_price - first_price) / first_price * 100
            w = weights.get(ticker, equal_w)
            
            results[ticker] = {
                "ticker": ticker,
                "start_price": first_price,
                "end_price": last_price,
                "perf_pct": round(perf_pct, 2),
                "weight": round(w, 4),
                "start_date": pts[0]["date"],
                "end_date": pts[-1]["date"],
                "nb_points": len(pts),
                "contribution": round(perf_pct * w, 2),
            }
            
            # Série temporelle normalisée base 100
            portfolio_data[ticker] = [
                {"date": p["date"], "value": round((p["price"] / first_price) * 100, 2)}
                for p in pts
            ]
        
        if not results:
            return jsonify({"error": "Données insuffisantes pour la période"}), 404
        
        # Performance globale du portefeuille (moyenne pondérée)
        total_contrib = sum(r["contribution"] for r in results.values())
        total_weight = sum(r["weight"] for r in results.values())
        portfolio_perf = total_contrib / total_weight if total_weight > 0 else 0
        
        # Valeur finale du portefeuille
        final_value = initial_capital * (1 + portfolio_perf / 100)
        gain = final_value - initial_capital
        
        # Top performers dans le portefeuille
        sorted_results = sorted(results.values(), key=lambda x: x["perf_pct"], reverse=True)
        
        # Série portefeuille agrégée
        all_dates = sorted(set(d["date"] for pts in portfolio_data.values() for d in pts))
        portfolio_series = []
        for date in all_dates:
            weighted_val = 0
            total_w = 0
            for ticker, pts in portfolio_data.items():
                pt = next((p for p in pts if p["date"] == date), None)
                if pt:
                    w = results[ticker]["weight"]
                    weighted_val += pt["value"] * w
                    total_w += w
            if total_w > 0:
                portfolio_series.append({"date": date, "value": round(weighted_val / total_w, 2)})
        
        return jsonify({
            "period": period,
            "initial_capital": initial_capital,
            "final_value": round(final_value),
            "gain": round(gain),
            "portfolio_perf_pct": round(portfolio_perf, 2),
            "nb_tickers": len(results),
            "results": sorted_results,
            "portfolio_series": portfolio_series[-60:],  # max 60 points
            "ticker_series": {t: pts[-60:] for t, pts in portfolio_data.items()},
        })
        
    except Exception as e:
        logger.error(f"backtest: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/sector-indices")
def api_sector_indices():
    try:
        from brvm_data_scraper import get_sector_indices, scrape_sector_indices
        force = request.args.get("force","false").lower() == "true"
        data = scrape_sector_indices() if force else get_sector_indices()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/announcements")
def api_announcements():
    try:
        from brvm_data_scraper import get_announcements
        return jsonify(get_announcements())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/dividends")
def api_dividends():
    """Calendrier ex-div et rendements pour la page Dividendes."""
    scores = load_latest_scores()
    fields = ["ticker","name","div_yield","div_per_share","ex_div_date",
              "eps","pe_ref","sector","pdf_verdict","composite_adj"]
    result = []
    for s in scores:
        dy = s.get("div_yield") or 0
        if dy > 0:
            result.append({f: s.get(f) for f in fields})
    result.sort(key=lambda x: x.get("div_yield") or 0, reverse=True)
    return jsonify(result)

@app.route("/api/price-history")
def api_price_history():
    """Historique de prix pour le graphique performances.
    Enrichit avec des points synthétiques boc_data pour les tickers sans historique."""
    try:
        import datetime as _dt
        from price_history_builder import load_history
        history = load_history()

        boc_path = os.path.join(DATA_DIR, "boc_data.json")
        if os.path.exists(boc_path):
            with open(boc_path) as _f:
                boc = json.load(_f)
            _today = _dt.date.today().isoformat()
            _yesterday = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
            _year_start = f"{_dt.date.today().year}-01-01"

            for ticker, entry in boc.items():
                if not isinstance(entry, dict):
                    continue
                close = entry.get("cours_clot") or 0
                prev  = entry.get("cours_prev") or close
                var_a = entry.get("var_annee") or 0
                if close <= 0 or var_a == -100:
                    continue
                real_pts = sorted(history.get(ticker, []), key=lambda x: x["date"])
                # Enrichir si pas d'historique remontant avant février (que des pts live récents)
                _feb = f"{_dt.date.today().year}-02-01"
                if real_pts and real_pts[0]["date"] < _feb:
                    continue
                year_price = round(close / (1 + var_a / 100), 2)
                synthetic = [
                    {"date": _year_start, "price": float(year_price), "source": "synthetic"},
                    {"date": _yesterday,  "price": float(prev),       "source": "boc"},
                    {"date": _today,      "price": float(close),      "source": "boc"},
                ]
                skip = {_year_start, _yesterday, _today}
                merged = synthetic + [p for p in real_pts if p["date"] not in skip]
                merged.sort(key=lambda x: x["date"])
                history[ticker] = merged

        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Historique étendu (BOC PDFs 2023→) ──────────────────────────────────────

_EXTENDED_HISTORY_CACHE = None
_EXTENDED_HISTORY_MTIME = 0.0

def _load_extended_history():
    global _EXTENDED_HISTORY_CACHE, _EXTENDED_HISTORY_MTIME
    path = os.path.join(DATA_DIR, "price_history_extended.json")
    try:
        mtime = os.path.getmtime(path)
        if _EXTENDED_HISTORY_CACHE is None or mtime != _EXTENDED_HISTORY_MTIME:
            with open(path) as f:
                _EXTENDED_HISTORY_CACHE = json.load(f)
            _EXTENDED_HISTORY_MTIME = mtime
    except Exception:
        _EXTENDED_HISTORY_CACHE = _EXTENDED_HISTORY_CACHE or {}
    return _EXTENDED_HISTORY_CACHE


def _filter_by_period(points, period):
    """Filtre une liste [{date, close, volume}] selon period (6m|1an|3ans|tout)."""
    import datetime as _dt
    if not points or period == "tout":
        return points
    today = _dt.date.today()
    if period == "6m":
        cutoff = (today - _dt.timedelta(days=183)).isoformat()
    elif period == "1an":
        cutoff = (today - _dt.timedelta(days=365)).isoformat()
    elif period == "3ans":
        cutoff = (today - _dt.timedelta(days=3 * 365)).isoformat()
    else:
        return points
    return [p for p in points if p["date"] >= cutoff]


@app.route("/api/price-history-extended/<ticker>")
def api_price_history_extended(ticker):
    ticker = ticker.upper()
    period = request.args.get("period", "1an")
    history = _load_extended_history()
    raw = sorted(history.get(ticker, []), key=lambda x: x["date"])
    points = _filter_by_period(raw, period)
    return jsonify({"ticker": ticker, "period": period, "points": points, "count": len(points)})


@app.route("/api/price-history-extended/top-performers")
def api_price_history_extended_top():
    try:
        n = int(request.args.get("n", 5))
        period = request.args.get("period", "1an")
        history = _load_extended_history()
        results = []
        for ticker, raw in history.items():
            points = _filter_by_period(sorted(raw, key=lambda x: x["date"]), period)
            if len(points) < 5:
                continue
            first_close = points[0]["close"]
            last_close  = points[-1]["close"]
            if first_close and first_close > 0:
                perf = round((last_close - first_close) / first_close * 100, 2)
                results.append({
                    "ticker": ticker,
                    "perf_pct": perf,
                    "first_close": first_close,
                    "last_close": last_close,
                    "first_date": points[0]["date"],
                    "last_date": points[-1]["date"],
                    "count": len(points),
                })
        results.sort(key=lambda x: x["perf_pct"], reverse=True)
        return jsonify(results[:n])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sparklines")
def api_sparklines():
    """Retourne les 30 derniers jours de cotation pour toutes les actions (sparklines légères)."""
    import datetime as _dt
    history = _load_extended_history()
    cutoff = (_dt.date.today() - _dt.timedelta(days=50)).isoformat()
    result = {}
    for ticker, points in history.items():
        recent = sorted([p for p in points if p["date"] >= cutoff], key=lambda x: x["date"])[-30:]
        if len(recent) >= 3:
            result[ticker] = [{"date": p["date"], "close": p["close"]} for p in recent]
    return jsonify(result)


@app.route("/api/analyses/<ticker>")
def api_analyses_ticker(ticker):
    """Analyse IA complète depuis analyses_summary.json pour un ticker."""
    ticker = ticker.upper()
    try:
        path = os.path.join(os.path.dirname(__file__), "data", "analyses_summary.json")
        if not os.path.exists(path):
            return jsonify({"error": "analyses_summary.json introuvable"}), 404
        with open(path) as f:
            data = json.load(f)
        entry = data.get(ticker)
        if not entry:
            return jsonify({"error": f"Aucune analyse pour {ticker}"}), 404
        return jsonify(entry)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/calendar")
def api_calendar():
    """Événements calendrier : ex-div + AG + résultats depuis dividends + announcements."""
    from datetime import datetime

    def _to_iso(raw):
        if not raw or raw == "N/D":
            return None
        s = str(raw).strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    events = []
    try:
        from valuation import STOCK_FUNDAMENTALS
        for ticker, row in STOCK_FUNDAMENTALS.items():
            exd = _to_iso(row.get("ex_div_date") or row.get("ex_div"))
            if exd:
                div = row.get("div_per_share")
                events.append({
                    "type": "ex-div",
                    "ticker": ticker,
                    "date": exd,
                    "label": f"Ex-dividende {ticker}" + (f" ({div} XOF)" if div else ""),
                    "color": "#4ADE80",
                })
    except Exception:
        pass
    try:
        ann_path = os.path.join(os.path.dirname(__file__), "data", "announcements.json")
        if os.path.exists(ann_path):
            with open(ann_path) as f:
                anns = json.load(f)
            for a in (anns if isinstance(anns, list) else []):
                iso = _to_iso(a.get("date"))
                if not iso:
                    continue
                t = a.get("type", "").lower()
                color = "#60A5FA" if ("ag" in t or "assembl" in t) else "#FBBF24"
                events.append({
                    "type": t or "evenement",
                    "ticker": a.get("ticker", ""),
                    "date": iso,
                    "label": a.get("title") or a.get("label") or t,
                    "color": color,
                })
    except Exception:
        pass
    events.sort(key=lambda x: x.get("date", ""))
    return jsonify(events)

@app.route("/api/scheduler/status")
def api_scheduler_status():
    try:
        return jsonify(get_scheduler_status())
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/scheduler/run/<job_id>", methods=["POST"])
def api_scheduler_run(job_id):
    jobs = {
        "news":    lambda: __import__("company_scraper").run_company_scraper(),
        "ranking": lambda: __import__("live_ranker").compute_live_ranking(trigger="manual"),
        "history": lambda: __import__("price_history_builder").append_live_prices(),
    }
    if job_id not in jobs:
        return jsonify({"error": "Job inconnu"}), 404
    try:
        result = jobs[job_id]()
        return jsonify({"status": "ok", "job": job_id, "result": str(result)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/sw.js")
def serve_sw():
    from flask import Response
    with open(os.path.join(os.path.dirname(__file__), "dashboard", "sw.js")) as f:
        content = f.read()
    return Response(content, mimetype="application/javascript",
                    headers={"Service-Worker-Allowed": "/"})


@app.route("/api/rapport/<ticker>")
def api_rapport_pdf(ticker):
    """Génère un rapport PDF pour une société."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        import io

        # Récupérer les données du ticker
        ranking_path = os.path.join(os.path.dirname(__file__), "data", "live_ranking.json")
        row = {}
        if os.path.exists(ranking_path):
            with open(ranking_path) as f:
                data = json.load(f)
            for x in data.get("ranking", []):
                if x.get("ticker") == ticker.upper():
                    row = x
                    break

        if not row:
            return jsonify({"error": f"Ticker {ticker} introuvable"}), 404

        # Résumé IA si dispo
        ai_summary = ""
        ai_paths = [
            os.path.join(os.path.dirname(__file__), "data", "analyses_summary.json"),
            os.path.join(os.path.dirname(__file__), "analyses_summary.json"),
        ]
        for p in ai_paths:
            if os.path.exists(p):
                try:
                    with open(p) as f:
                        summ = json.load(f)
                    ai_summary = summ.get(ticker.upper(), {}).get("summary", "")
                    if not ai_summary:
                        ai_summary = summ.get(ticker.upper(), "")
                    if isinstance(ai_summary, dict):
                        ai_summary = ai_summary.get("summary", "")
                except Exception:
                    pass
                break

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)

        styles = getSampleStyleSheet()
        h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=20, textColor=colors.HexColor("#1E293B"), spaceAfter=4)
        h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=13, textColor=colors.HexColor("#0F4C8C"), spaceBefore=12, spaceAfter=4)
        body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#334155"), leading=15)
        small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748B"))
        green = colors.HexColor("#16A34A"); red = colors.HexColor("#DC2626"); amber = colors.HexColor("#D97706")

        sc = row.get("composite_adj", 0)
        sc_color = green if sc >= 60 else (amber if sc >= 40 else red)
        verdict = row.get("pdf_verdict", "—")

        story = []
        # En-tête
        story.append(Paragraph(f"📈 Rapport BRVM — {ticker.upper()}", h1))
        story.append(Paragraph(row.get("name", ticker.upper()), ParagraphStyle("sub", parent=styles["Normal"], fontSize=12, textColor=colors.HexColor("#64748B"))))
        story.append(Paragraph(f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} — Source : BRVM Dashboard", small))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0"), spaceAfter=10))

        # Score + Cours
        score_data = [
            ["Score composite", f"{sc:.0f} / 80", "Rang", f"#{row.get('rank','?')}"],
            ["Cours", f"{row.get('price', 0):,.0f} XOF".replace(",", " "), "Variation", f"{row.get('change_pct', 0):+.2f}%"],
            ["Verdict IA", verdict, "Secteur", row.get("sector", "—")],
        ]
        ts_score = TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#EFF6FF")),
            ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
            ("FONTSIZE", (0,0), (-1,-1), 10),
            ("FONTNAME", (1,0), (1,0), "Helvetica-Bold"),
            ("TEXTCOLOR", (1,0), (1,0), sc_color),
            ("FONTSIZE", (1,0), (1,0), 16),
            ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.HexColor("#F8FAFC"), colors.HexColor("#FFFFFF")]),
            ("PADDING", (0,0), (-1,-1), 8),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ])
        story.append(Table(score_data, colWidths=[4*cm, 5*cm, 3*cm, 5*cm], style=ts_score))
        story.append(Spacer(1, 12))

        # KPIs
        story.append(Paragraph("Indicateurs financiers clés", h2))
        pe = row.get("pe_ref") or row.get("pe_hist")
        pb = row.get("pb_ref") or row.get("pb_hist")
        kpi_data = [
            ["Indicateur", "Valeur", "Signal", "Seuil"],
            ["P/E (cours/BNA)", f"{pe:.1f}×" if pe else "—",
             "✓ Bon" if pe and pe < 15 else ("~ Correct" if pe and pe < 25 else "✗ Élevé"),
             "≤ 15 Graham"],
            ["P/B (cours/BVPA)", f"{pb:.1f}×" if pb else "—",
             "✓ Bon" if pb and pb < 1.5 else ("~ Correct" if pb and pb < 3 else "✗ Élevé"),
             "≤ 1.5 Graham"],
            ["ROE", f"{row.get('roe',0):.1f}%" if row.get('roe') else "—",
             "✓ Excellent" if (row.get('roe') or 0) > 15 else ("~ Correct" if (row.get('roe') or 0) > 8 else "✗ Faible"),
             "≥ 15%"],
            ["Div. yield", f"{row.get('div_yield',0):.1f}%" if row.get('div_yield') else "—",
             "✓ Bon" if (row.get('div_yield') or 0) > 5 else ("~ Correct" if (row.get('div_yield') or 0) > 2 else "—"),
             "≥ 5% (attrayant)"],
            ["BNA (EPS)", f"{row.get('eps',0):,.0f} XOF".replace(",", " ") if row.get('eps') else "—", "—", "Bénéfice/action"],
            ["BVPA", f"{row.get('bvpa',0):,.0f} XOF".replace(",", " ") if row.get('bvpa') else "—", "—", "Valeur comptable/action"],
        ]
        def kpi_color(sig):
            if "✓" in sig: return green
            if "✗" in sig: return red
            return amber
        ts_kpi = TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1E40AF")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 9),
            ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F8FAFC")]),
            ("PADDING", (0,0), (-1,-1), 7),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ])
        for i, row_d in enumerate(kpi_data[1:], 1):
            ts_kpi.add("TEXTCOLOR", (2,i), (2,i), kpi_color(row_d[2]))
            ts_kpi.add("FONTNAME", (2,i), (2,i), "Helvetica-Bold")
        story.append(Table(kpi_data, colWidths=[4.5*cm, 3.5*cm, 3*cm, 5*cm], style=ts_kpi))
        story.append(Spacer(1, 12))

        # Scores 8 modèles
        story.append(Paragraph("Scores des 8 modèles de valorisation (/10 chacun)", h2))
        models = [
            ("Graham", "score_graham"), ("DCF/FCF", "score_dcf"), ("DDM", "score_ddm"),
            ("EPV", "score_epv"), ("Buffett", "score_buffett"), ("Reverse DCF", "score_rev_dcf"),
            ("Relatif", "score_relatif"), ("Technique", "score_technique"),
        ]
        model_data = [["Modèle", "Score /10", "Évaluation"]]
        for label, key in models:
            v = row.get(key, 0)
            ev = "Excellent" if v >= 8 else ("Bon" if v >= 6 else ("Correct" if v >= 4 else "Faible"))
            model_data.append([label, f"{v:.1f}", ev])
        ts_model = TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0F172A")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 9),
            ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F8FAFC")]),
            ("PADDING", (0,0), (-1,-1), 7),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("ALIGN", (1,0), (1,-1), "CENTER"),
        ])
        for i, (_, key) in enumerate(models, 1):
            v = row.get(key, 0)
            c = green if v >= 7 else (amber if v >= 4 else red)
            ts_model.add("TEXTCOLOR", (1,i), (1,i), c)
            ts_model.add("FONTNAME", (1,i), (1,i), "Helvetica-Bold")
        story.append(Table(model_data, colWidths=[5*cm, 3*cm, 8*cm], style=ts_model))
        story.append(Spacer(1, 12))

        # Résumé IA
        if ai_summary:
            story.append(Paragraph("Analyse IA — Résumé rapport annuel", h2))
            story.append(Paragraph(str(ai_summary)[:2000], body))
            story.append(Spacer(1, 8))

        # Pied de page
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0"), spaceAfter=6))
        story.append(Paragraph("Ce rapport est généré automatiquement à titre informatif. Il ne constitue pas un conseil en investissement.", small))

        doc.build(story)
        buf.seek(0)
        from flask import send_file
        return send_file(buf, mimetype="application/pdf",
                         as_attachment=True,
                         download_name=f"BRVM_{ticker.upper()}_{datetime.now().strftime('%Y%m%d')}.pdf")
    except Exception as e:
        logger.error(f"PDF rapport {ticker}: {e}")
        return jsonify({"error": str(e)}), 500


def _get_live_scores_list():
    """Retourne la liste de scores live (ranking ou calcul à la volée)."""
    try:
        from live_ranker import load_ranking
        rd = load_ranking()
        if rd and rd.get("ranking"):
            return rd["ranking"]
    except Exception:
        pass
    try:
        live_cache = get_live_data()
        return compute_all_live_scores(STOCK_FUNDAMENTALS, live_cache)
    except Exception:
        return []


def _get_price_history_dict():
    ph_path = os.path.join(os.path.dirname(__file__), "data", "price_history.json")
    with open(ph_path) as f:
        return json.load(f)


# ── Prévisions & signaux ──────────────────────────────────────────────────────

@app.route("/api/previsions/portfolios")
def api_prevision_portfolios():
    try:
        from backtest_previsionnel import generate_portfolios
        scores = _get_live_scores_list()
        ph = _get_price_history_dict()
        result = generate_portfolios(scores, ph)
        return jsonify(result)
    except Exception as e:
        logger.error(f"previsions/portfolios: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/previsions/signaux")
def api_prevision_signaux():
    try:
        from backtest_previsionnel import compute_signals
        scores = _get_live_scores_list()
        ph = _get_price_history_dict()
        result = compute_signals(scores, ph)
        return jsonify(result)
    except Exception as e:
        logger.error(f"previsions/signaux: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/previsions/backtest", methods=["GET", "POST"])
def api_prevision_backtest():
    try:
        import importlib, backtest_previsionnel as _bp
        importlib.reload(_bp)
        scores = _get_live_scores_list()
        ph = _get_price_history_dict()
        result = _bp.compute_backtest_previsionnel(scores, ph)
        return jsonify(result)
    except Exception as e:
        logger.error(f"previsions/backtest: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/prevision-accuracy")
def api_prevision_accuracy():
    acc_path = os.path.join(os.path.dirname(__file__), "data", "prevision_accuracy.json")
    if os.path.exists(acc_path):
        with open(acc_path) as f:
            return jsonify(json.load(f))
    return jsonify({"error": "Aucun backtest calculé — lancez /api/previsions/backtest"}), 404


@app.route("/api/rapport-mensuel")
def api_rapport_mensuel():
    try:
        from backtest_previsionnel import generate_rapport_pdf
        scores = _get_live_scores_list()
        ph = _get_price_history_dict()
        pdf_bytes = generate_rapport_pdf(scores, ph)
        from flask import Response
        month = datetime.now().strftime("%Y-%m")
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=BRVM_Rapport_{month}.pdf"}
        )
    except Exception as e:
        logger.error(f"rapport-mensuel: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv as _ldenv
        _ldenv()
    except ImportError:
        pass
    PORT = 5000
    print("\n" + "="*50)
    print(f"  BRVM Dashboard — http://localhost:{PORT}")
    print("="*50 + "\n")
    try:
        from auto_scheduler import start_scheduler as _start_auto
        _sched = _start_auto()
        logger.info(f"Auto-scheduler démarré — {len(_sched.get_jobs())} jobs")
    except Exception as e:
        logger.warning(f"Scheduler non démarré: {e}")
    # Préchauffage du cache commodités en arrière-plan (évite 2.5s au premier appel)
    threading.Thread(target=fetch_commodity_prices, daemon=True).start()
    app.run(host='0.0.0.0', port=PORT, debug=False)

