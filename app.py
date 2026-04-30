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
from flask_cors import CORS

app = Flask(__name__, static_folder="dashboard", static_url_path="")
CORS(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

DATA_DIR = "data"
REPORTS_DIR = "reports"

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_latest_scores():
    files = sorted(glob.glob(os.path.join(DATA_DIR, "scores_*.json")))
    if not files:
        return []
    try:
        with open(files[-1]) as f:
            return json.load(f)
    except Exception:
        return []


def load_price_history():
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
    app.run(debug=False, port=port, host="127.0.0.1")
