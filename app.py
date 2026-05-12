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


def fetch_commodity_prices():
    """Récupère les prix des commodités depuis Yahoo Finance (via yfinance si dispo)"""
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
        for name, info in commodities.items():
            try:
                ticker = yf.Ticker(info["symbol"])
                hist = ticker.history(period="5d")
                if not hist.empty:
                    last = float(hist["Close"].iloc[-1])
                    prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last
                    change = (last / prev - 1) * 100
                    prices[name] = {
                        "price": round(last, 2),
                        "change_pct": round(change, 2),
                        "unit": info["unit"],
                        "symbol": info["symbol"],
                    }
            except Exception:
                pass
    except ImportError:
        # yfinance non installé — utiliser données statiques de démonstration
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

    return prices


# ── Routes API ────────────────────────────────────────────────────────────────


@app.route("/simulator.js")
def serve_simulator():
    return send_from_directory("dashboard", "simulator.js",
                               mimetype="application/javascript")

@app.route("/")
def index():
    from flask import Response
    import json as _json
    try:
        # Injecter price_history minimal (30 derniers BOC) dans le HTML
        ph_path = os.path.join(DATA_DIR, "price_history.json")
        ph = {}
        if os.path.exists(ph_path):
            with open(ph_path) as f:
                raw = _json.load(f)
            # Garder seulement les 30 derniers points BOC par ticker
            for ticker, pts in raw.items():
                boc = [p for p in pts if p.get("source")=="boc"][-30:]
                if boc:
                    ph[ticker] = boc
        
        with open(os.path.join("dashboard","index.html"), encoding="utf-8") as f:
            html = f.read()
        
        inject = f"<script>window._priceHistory={_json.dumps(ph)};</script>"
        html = html.replace("<body", inject + "<body", 1)
        return Response(html, mimetype="text/html")
    except Exception as e:
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

@app.route("/compare_analysis.js")
def serve_compare_analysis_js():
    return send_from_directory("dashboard", "compare_analysis.js", mimetype="application/javascript")

@app.route("/performance.js")
def serve_performance_js():
    return send_from_directory("dashboard", "performance.js", mimetype="application/javascript")

@app.route("/sectors.js")
def serve_sectors_js():
    return send_from_directory("dashboard", "sectors.js", mimetype="application/javascript")


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

@app.route("/api/price-history")
def api_price_history():
    """Historique de prix pour le graphique performances."""
    try:
        from price_history_builder import load_history
        return jsonify(load_history())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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

if __name__ == "__main__":
    import socket
    import os as _os
    try:
        from dotenv import load_dotenv as _ldenv
        _ldenv()
    except ImportError:
        pass
    port = 5000
    for p in range(5000, 5010):
        try:
            s = socket.socket(); s.bind(("127.0.0.1", p)); s.close(); port = p; break
        except:
            pass
    print("\n" + "="*50)
    print(f"  BRVM Dashboard — http://localhost:{port}")
    print("="*50 + "\n")
    try:
        from auto_scheduler import start_scheduler as _start_auto
        _sched = _start_auto()
        logger.info(f"Auto-scheduler démarré — {len(_sched.get_jobs())} jobs")
    except Exception as e:
        logger.warning(f"Scheduler non démarré: {e}")
    app.run(debug=False, port=port, host="127.0.0.1")

