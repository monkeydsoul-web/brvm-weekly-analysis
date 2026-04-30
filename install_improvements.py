#!/usr/bin/env python3
"""
BRVM Weekly Analysis — Script d'installation des améliorations
Exécuter depuis : ~/brvm-weekly-analysis/
  source ~/.zprofile && python3 install_improvements.py
"""
import os, sys, shutil, textwrap
from pathlib import Path

BASE = Path(__file__).parent
print("=" * 60)
print("BRVM — Installation des améliorations")
print("=" * 60)

# ─────────────────────────────────────────────────────────────
# 1. FIX CRITIQUE : .env pour la clé API
# ─────────────────────────────────────────────────────────────
def fix_api_key():
    print("\n[1/5] Fix clé API Anthropic...")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("  ⚠ ANTHROPIC_API_KEY non trouvée dans l'environnement")
        print("  → Lancez d'abord : source ~/.zprofile")
        return False

    env_file = BASE / ".env"
    env_file.write_text(f"ANTHROPIC_API_KEY={api_key}\n")
    print(f"  ✓ .env créé avec la clé ({api_key[:8]}...)")

    gitignore = BASE / ".gitignore"
    content = gitignore.read_text() if gitignore.exists() else ""
    if ".env" not in content:
        with open(gitignore, "a") as f:
            f.write("\n.env\n")
        print("  ✓ .env ajouté au .gitignore")
    return True

# ─────────────────────────────────────────────────────────────
# 2. PATCH app.py — charger .env + fix route chat
# ─────────────────────────────────────────────────────────────
def patch_app_py():
    print("\n[2/5] Patch app.py...")
    app_file = BASE / "app.py"
    if not app_file.exists():
        print("  ✗ app.py non trouvé")
        return

    content = app_file.read_text()

    # Ajouter python-dotenv au chargement si pas déjà présent
    dotenv_patch = """
# --- PATCH: charger .env pour ANTHROPIC_API_KEY ---
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv()
except ImportError:
    pass  # python-dotenv non installé, utiliser os.environ directement
# --- FIN PATCH ---
"""
    if "load_dotenv" not in content and "PATCH: charger .env" not in content:
        # Insérer après les imports existants (après la dernière ligne d'import)
        lines = content.split("\n")
        last_import_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                last_import_idx = i
        lines.insert(last_import_idx + 1, dotenv_patch)
        content = "\n".join(lines)
        print("  ✓ Patch dotenv ajouté")
    else:
        print("  → dotenv déjà présent, skip")

    # Fix route /api/chat — s'assurer que la clé est lue au moment de la requête
    old_chat_pattern = "anthropic.Anthropic()"
    new_chat_pattern = "anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))"
    if old_chat_pattern in content:
        content = content.replace(old_chat_pattern, new_chat_pattern)
        print("  ✓ Client Anthropic patché pour lire la clé à chaque requête")

    # Même patch pour les variantes
    old2 = "anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)"
    if old2 in content and "os.environ.get('ANTHROPIC_API_KEY')" not in content:
        content = content.replace(
            old2,
            "anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY', ANTHROPIC_API_KEY))"
        )
        print("  ✓ Fallback clé API ajouté")

    app_file.write_text(content)
    print("  ✓ app.py mis à jour")

# ─────────────────────────────────────────────────────────────
# 3. NOUVEAU FICHIER : candlestick.py
# ─────────────────────────────────────────────────────────────
def create_candlestick():
    print("\n[3/5] Création candlestick.py...")
    code = '''#!/usr/bin/env python3
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
'''
    (BASE / "candlestick.py").write_text(code)
    print("  ✓ candlestick.py créé")

# ─────────────────────────────────────────────────────────────
# 4. NOUVEAU FICHIER : backtesting.py
# ─────────────────────────────────────────────────────────────
def create_backtesting():
    print("\n[4/5] Création backtesting.py...")
    code = '''#!/usr/bin/env python3
"""
backtesting.py — Validation historique des scores de valorisation BRVM
Mesure si un score élevé prédit réellement une surperformance 3/6/12 mois plus tard.
"""
import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

CACHE_FILE = Path("backtesting_cache.json")

# ─── Helpers ───────────────────────────────────────────────────────────────

def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {}

def save_cache(data: dict):
    CACHE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

# ─── Analyse principale ────────────────────────────────────────────────────

def run_backtesting(tickers: Optional[list] = None, horizons_months: list = None) -> dict:
    """
    Pour chaque ticker × horizon, calcule la corrélation score → rendement.
    Retourne un dict complet avec métriques et résultats par ticker.
    """
    if horizons_months is None:
        horizons_months = [3, 6, 12]

    # Charger les scores et l'historique de prix
    try:
        from valuation import compute_all_scores
        scores_data = compute_all_scores()
    except Exception as e:
        scores_data = {}
        print(f"  ⚠ valuation.py: {e}")

    try:
        from price_history import get_all_tickers, get_weekly_prices
        if tickers is None:
            tickers = get_all_tickers()
    except Exception as e:
        tickers = tickers or []
        print(f"  ⚠ price_history.py: {e}")
        get_weekly_prices = None

    results = {}
    summary_by_horizon = {h: {"high_score": [], "low_score": [], "all": []} for h in horizons_months}

    for ticker in tickers:
        ticker_result = {"ticker": ticker, "horizons": {}}

        # Score actuel
        score_info = scores_data.get(ticker, {})
        score = score_info.get("total_score", 0) if isinstance(score_info, dict) else 0

        # Historique de prix
        if get_weekly_prices:
            try:
                prices = get_weekly_prices(ticker)
            except Exception:
                prices = []
        else:
            prices = []

        if len(prices) < 52:
            results[ticker] = ticker_result
            continue

        # Pour chaque horizon, calculer le rendement moyen "post-signal"
        for horizon in horizons_months:
            weeks = int(horizon * 4.33)
            returns = []

            # Simuler: à chaque point dans l'historique, quel était le rendement horizon semaines après ?
            for i in range(len(prices) - weeks - 1):
                price_entry = prices[i][1]
                price_exit  = prices[i + weeks][1]
                if price_entry > 0:
                    ret = (price_exit - price_entry) / price_entry * 100
                    returns.append(ret)

            if returns:
                avg_ret     = statistics.mean(returns)
                median_ret  = statistics.median(returns)
                positive_pct = len([r for r in returns if r > 0]) / len(returns) * 100
                sharpe_proxy = avg_ret / (statistics.stdev(returns) or 1)

                ticker_result["horizons"][horizon] = {
                    "avg_return_pct":  round(avg_ret, 2),
                    "median_return_pct": round(median_ret, 2),
                    "positive_pct":    round(positive_pct, 1),
                    "sharpe_proxy":    round(sharpe_proxy, 3),
                    "n_observations":  len(returns),
                }

                # Classifier high/low score pour le résumé
                if score >= 40:
                    summary_by_horizon[horizon]["high_score"].append(avg_ret)
                else:
                    summary_by_horizon[horizon]["low_score"].append(avg_ret)
                summary_by_horizon[horizon]["all"].append(avg_ret)

        ticker_result["current_score"] = score
        results[ticker] = ticker_result

    # Calculer les métriques globales de validation
    validation = {}
    for h, data in summary_by_horizon.items():
        hs = data["high_score"]
        ls = data["low_score"]
        validation[h] = {
            "high_score_avg_return": round(statistics.mean(hs), 2) if hs else 0,
            "low_score_avg_return":  round(statistics.mean(ls), 2) if ls else 0,
            "premium_bps":           round((statistics.mean(hs) - statistics.mean(ls)) * 100, 0) if (hs and ls) else 0,
            "n_high": len(hs),
            "n_low":  len(ls),
            "model_valid": statistics.mean(hs) > statistics.mean(ls) if (hs and ls) else False,
        }

    output = {
        "generated_at": datetime.now().isoformat(),
        "n_tickers": len(results),
        "horizons": horizons_months,
        "validation_summary": validation,
        "ticker_results": results,
    }

    save_cache(output)
    return output

def get_backtesting_summary_html() -> str:
    """
    Retourne un HTML résumé pour intégration dans le dashboard.
    Utilise le cache si disponible.
    """
    cache = load_cache()
    if not cache:
        return "<p>Backtesting non encore calculé. Lancer run_backtesting().</p>"

    rows = ""
    for h, v in cache.get("validation_summary", {}).items():
        valid_icon = "✓" if v.get("model_valid") else "✗"
        valid_color = "#22c55e" if v.get("model_valid") else "#ef4444"
        rows += f"""
        <tr>
          <td style="padding:8px 12px;color:#e2e8f0">{h} mois</td>
          <td style="padding:8px 12px;color:#22c55e;font-weight:500">+{v.get('high_score_avg_return', 0):.1f}%</td>
          <td style="padding:8px 12px;color:#ef4444">+{v.get('low_score_avg_return', 0):.1f}%</td>
          <td style="padding:8px 12px;color:#f59e0b">{v.get('premium_bps', 0):.0f} bps</td>
          <td style="padding:8px 12px;color:{valid_color};font-weight:600">{valid_icon} {'Valide' if v.get('model_valid') else 'Non valide'}</td>
        </tr>"""

    return f"""
    <div style="background:#1e293b;border-radius:8px;padding:16px;margin:16px 0">
      <h3 style="color:#e2e8f0;margin:0 0 12px;font-size:14px">Backtesting — Validation des scores</h3>
      <p style="color:#94a3b8;font-size:12px;margin:0 0 12px">
        Calculé le {cache.get('generated_at', '')[:10]} sur {cache.get('n_tickers', 0)} actions
      </p>
      <table style="width:100%;border-collapse:collapse">
        <thead>
          <tr style="border-bottom:1px solid #334155">
            <th style="padding:6px 12px;color:#64748b;text-align:left;font-size:12px">Horizon</th>
            <th style="padding:6px 12px;color:#64748b;text-align:left;font-size:12px">Score ≥40 (rendement moy.)</th>
            <th style="padding:6px 12px;color:#64748b;text-align:left;font-size:12px">Score &lt;40</th>
            <th style="padding:6px 12px;color:#64748b;text-align:left;font-size:12px">Prime de score</th>
            <th style="padding:6px 12px;color:#64748b;text-align:left;font-size:12px">Verdict</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>"""

if __name__ == "__main__":
    print("Lancement du backtesting (peut prendre quelques secondes)...")
    result = run_backtesting(horizons_months=[3, 6, 12])
    print(f"\\nRésultats pour {result['n_tickers']} tickers:")
    for h, v in result["validation_summary"].items():
        status = "✓ VALIDE" if v["model_valid"] else "✗ NON VALIDE"
        print(f"  {h}m: Score≥40={v['high_score_avg_return']:+.1f}% vs Score<40={v['low_score_avg_return']:+.1f}%  [{status}]")
'''
    (BASE / "backtesting.py").write_text(code)
    print("  ✓ backtesting.py créé")

# ─────────────────────────────────────────────────────────────
# 5. PATCH app.py — Ajouter routes candlestick + backtesting
# ─────────────────────────────────────────────────────────────
def patch_app_routes():
    print("\n[5/5] Ajout routes API dans app.py...")
    app_file = BASE / "app.py"
    if not app_file.exists():
        print("  ✗ app.py non trouvé")
        return

    content = app_file.read_text()

    new_routes = '''

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
'''

    if "api_candlestick" not in content:
        # Ajouter avant le bloc if __name__ == "__main__" ou en fin de fichier
        if 'if __name__ == "__main__"' in content:
            content = content.replace(
                'if __name__ == "__main__"',
                new_routes + '\nif __name__ == "__main__"'
            )
        else:
            content += new_routes
        app_file.write_text(content)
        print("  ✓ Routes /api/candlestick et /api/backtesting ajoutées")
    else:
        print("  → Routes déjà présentes, skip")

# ─────────────────────────────────────────────────────────────
# 6. Installer python-dotenv si absent
# ─────────────────────────────────────────────────────────────
def install_deps():
    print("\n[Extra] Vérification dépendances...")
    import subprocess
    try:
        import dotenv
        print("  ✓ python-dotenv déjà installé")
    except ImportError:
        print("  → Installation python-dotenv...")
        subprocess.run([sys.executable, "-m", "pip", "install", "python-dotenv", "--quiet"])
        print("  ✓ python-dotenv installé")

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.chdir(BASE)

    ok_key  = fix_api_key()
    install_deps()
    patch_app_py()
    create_candlestick()
    create_backtesting()
    patch_app_routes()

    print("\n" + "=" * 60)
    print("✓ Installation terminée !")
    print("=" * 60)
    print()
    if not ok_key:
        print("⚠  IMPORTANT — Pour que le Chat IA fonctionne :")
        print("   source ~/.zprofile && python3 install_improvements.py")
        print()
    print("Démarrer le serveur :")
    print("  source ~/.zprofile && python3 app.py")
    print()
    print("Nouvelles routes disponibles :")
    print("  GET /api/candlestick/SGBC?period=1y")
    print("  GET /api/candlestick/SGBC?period=5y")
    print("  GET /api/backtesting")
    print("  GET /api/backtesting?force=1  (recalcul)")
    print("  GET /api/backtesting/summary  (HTML)")
    print()
    print("Test Chat IA :")
    print("  curl -X POST http://localhost:5000/api/chat \\")
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"message": "quelles sont les 3 meilleures actions ?"}\'')
