import os, json, glob, logging, threading, subprocess
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder="dashboard", static_url_path="")
CORS(app)

def load_scores():
    files = sorted(glob.glob("data/scores_*.json"))
    if not files: return []
    return json.load(open(files[-1]))

def load_history():
    p = "data/price_history.json"
    return json.load(open(p)) if os.path.exists(p) else {}

def load_news():
    p = "data/news_cache.json"
    return json.load(open(p)) if os.path.exists(p) else []

def load_macro():
    p = "data/macro_cache.json"
    return json.load(open(p)) if os.path.exists(p) else {}

COMMODITY_MAP = {
    "SGBC":{"c":[],"i":"Indirect — taux BCEAO"},
    "SIBC":{"c":[],"i":"Indirect — activité économique CI"},
    "SNTS":{"c":["Pétrole"],"i":"Coûts énergie data centers et antennes"},
    "NSBC":{"c":[],"i":"Indirect — crédit CI"},
    "CBIBF":{"c":[],"i":"Indirect — économie Burkina Faso"},
    "BOAB":{"c":["Coton","Cacao"],"i":"Crédit exportateurs agricoles Bénin"},
    "BOABF":{"c":["Or","Coton"],"i":"Financement mines d'or Burkina Faso"},
    "BOAC":{"c":["Cacao","Café"],"i":"Crédit filière cacao/café CI"},
    "ECOC":{"c":["Cacao","Pétrole"],"i":"Financement agro-industrie CI"},
    "NTLC":{"c":["Cacao","Lait","Blé"],"i":"Coûts matières premières Nestlé"},
    "SLBC":{"c":["Orge","Sucre"],"i":"Matières premières brasserie"},
    "SMBC":{"c":["Pétrole","Bitume"],"i":"Prix bitume = prix de revient direct"},
    "PALC":{"c":["Huile de palme"],"i":"Prix vente = cours mondial huile de palme"},
    "SPHC":{"c":["Caoutchouc"],"i":"Prix vente = cours mondial caoutchouc"},
    "SOGC":{"c":["Caoutchouc"],"i":"Même exposition que SAPH"},
    "SCRC":{"c":["Sucre"],"i":"Prix vente lié au sucre mondial"},
    "TTLC":{"c":["Pétrole brut"],"i":"Marges distribution carburants CI"},
    "TTLS":{"c":["Pétrole brut"],"i":"Distribution carburants Sénégal"},
    "SHEC":{"c":["Pétrole brut"],"i":"Distribution Vivo Energy CI"},
    "ORAC":{"c":["Pétrole"],"i":"Coûts réseau et énergie Orange CI"},
    "ONTBF":{"c":["Pétrole"],"i":"Énergie infrastructure telecom Burkina"},
    "CIEC":{"c":["Gaz naturel","Pétrole"],"i":"Production électricité thermique CI"},
    "SDCC":{"c":["Pétrole"],"i":"Pompage et traitement eau SODECI"},
    "STBC":{"c":["Tabac brut"],"i":"Approvisionnement tabac importé"},
    "UNLC":{"c":["Huile de palme","Soja","Pétrole"],"i":"Matières produits ménagers Unilever"},
    "FTSC":{"c":["Pétrole","Bitume"],"i":"Matière première sacs et emballages"},
    "ABJC":{"c":["Pétrole"],"i":"Catering aérien — food cost + carburant"},
}

def get_commodity_prices():
    try:
        import yfinance as yf
        symbols = {"Cacao":"CC=F","Café Arabica":"KC=F","Pétrole Brent":"BZ=F",
                   "Or":"GC=F","Caoutchouc":"RUBBF","Coton":"CT=F",
                   "Sucre":"SB=F","Blé":"ZW=F","Gaz naturel":"NG=F"}
        result = {}
        for name, sym in symbols.items():
            try:
                h = yf.Ticker(sym).history(period="5d")
                if not h.empty:
                    last = float(h["Close"].iloc[-1])
                    prev = float(h["Close"].iloc[-2]) if len(h)>1 else last
                    result[name] = {"price":round(last,2),"change_pct":round((last/prev-1)*100,2),"symbol":sym}
            except: pass
        return result if result else _static_commodities()
    except: return _static_commodities()

def _static_commodities():
    return {
        "Cacao":{"price":7842,"change_pct":-1.2,"unit":"USD/tonne"},
        "Café Arabica":{"price":3.15,"change_pct":0.8,"unit":"USD/livre"},
        "Pétrole Brent":{"price":74.3,"change_pct":1.4,"unit":"USD/baril"},
        "Or":{"price":3320,"change_pct":0.3,"unit":"USD/once"},
        "Caoutchouc":{"price":1.82,"change_pct":-0.5,"unit":"USD/kg"},
        "Coton":{"price":0.68,"change_pct":-1.8,"unit":"USD/livre"},
        "Sucre":{"price":0.19,"change_pct":0.6,"unit":"USD/livre"},
        "Blé":{"price":5.42,"change_pct":-0.9,"unit":"USD/boisseau"},
        "Gaz naturel":{"price":3.85,"change_pct":2.3,"unit":"USD/MMBtu"},
        "Huile de palme":{"price":1050,"change_pct":2.1,"unit":"USD/tonne"},
    }

@app.route("/")
def index():
    return send_from_directory("dashboard","index.html")

@app.route("/api/scores")
def api_scores(): return jsonify(load_scores())

@app.route("/api/news")
def api_news():
    ticker = request.args.get("ticker","")
    news = load_news()
    if ticker: news = [n for n in news if ticker.upper() in (n.get("tickers") or [])]
    return jsonify(news[:50])

@app.route("/api/commodities")
def api_commodities(): return jsonify(get_commodity_prices())

@app.route("/api/macro")
def api_macro(): return jsonify(load_macro())

@app.route("/api/history/<ticker>")
def api_history(ticker):
    h = load_history()
    return jsonify(h.get(ticker.upper(),[]))

@app.route("/api/stock/<ticker>")
def api_stock(ticker):
    t = ticker.upper()
    scores = load_scores()
    stock = next((s for s in scores if s.get("ticker")==t), None)
    if not stock: return jsonify({"error":"Ticker non trouvé"}),404
    history = load_history().get(t,[])
    news = [n for n in load_news() if t in (n.get("tickers") or [])]
    cinfo = COMMODITY_MAP.get(t,{"c":[],"i":"Non évalué"})
    prices = get_commodity_prices()
    rel_prices = {}
    for c in cinfo["c"]:
        for k,v in prices.items():
            if c.lower() in k.lower() or k.lower() in c.lower():
                rel_prices[c] = v
    return jsonify({"stock":stock,"price_history":history[-52:],
                    "news":news[:10],"commodity_impact":cinfo["i"],
                    "commodities":cinfo["c"],"commodity_prices":rel_prices})

@app.route("/api/top/<int:n>")
def api_top(n):
    s = sorted(load_scores(),key=lambda x:x.get("composite_adj",0),reverse=True)
    return jsonify(s[:n])

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    def run():
        try:
            subprocess.run(["python3","main.py","--no-github","--no-email"],
                          timeout=300,cwd=os.path.dirname(os.path.abspath(__file__)))
            news = __import__("news_scraper").fetch_all_news()
            json.dump(news,open("data/news_cache.json","w"),ensure_ascii=False)
            macro = __import__("news_scraper").fetch_macro_context()
            json.dump(macro,open("data/macro_cache.json","w"),ensure_ascii=False)
        except Exception as e: print(f"Refresh error: {e}")
    threading.Thread(target=run,daemon=True).start()
    return jsonify({"status":"started","message":"Mise à jour lancée (~2 min)"})

@app.route("/api/refresh/status")
def api_status():
    files = sorted(glob.glob("data/scores_*.json"))
    if not files: return jsonify({"last_update":"Jamais","fresh":False})
    mtime = os.path.getmtime(files[-1])
    last = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y à %H:%M")
    age = (datetime.now().timestamp()-mtime)/60
    return jsonify({"last_update":last,"age_minutes":round(age),"fresh":age<10080})

if __name__=="__main__":
    os.makedirs("dashboard",exist_ok=True)
    os.makedirs("data",exist_ok=True)
    print("\n"+"="*50)
    print("  BRVM Dashboard — http://localhost:5000")
    print("="*50+"\n")
    app.run(debug=False,port=5000,host="127.0.0.1")
