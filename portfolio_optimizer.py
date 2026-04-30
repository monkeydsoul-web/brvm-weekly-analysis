#!/usr/bin/env python3
# portfolio_optimizer.py — Optimisation Markowitz BRVM — Python 3.9
import json, statistics, math, random
from datetime import datetime
from pathlib import Path

CACHE_FILE = Path("portfolio_optimizer_cache.json")

# Rendements annuels historiques 2016-2025 (%)
RETURNS = {
    "SGBC":  [12,18,25,15,-8,22,30,20,15,10],
    "SIBC":  [15,20,18,22,-5,25,28,18,12,8],
    "SNTS":  [8,12,15,10,-3,18,22,15,10,6],
    "CBIBF": [20,25,18,15,-10,28,35,22,18,12],
    "NSBC":  [10,15,12,18,-6,20,25,16,11,7],
    "ORAC":  [5,8,10,12,-15,15,18,12,8,5],
    "BOAB":  [8,10,8,10,-8,12,15,10,7,4],
    "ECOC":  [6,9,7,9,-12,10,13,9,6,3],
    "BICC":  [9,11,9,11,-7,13,16,11,8,5],
    "NTLC":  [7,10,8,10,-5,12,14,10,7,4],
    "STBC":  [11,14,11,13,-9,16,19,13,9,6],
    "UNLC":  [8,10,9,11,-6,13,16,11,8,5],
    "SLBC":  [5,7,6,8,-10,9,11,8,5,3],
    "PALC":  [4,6,5,7,-12,8,10,7,4,2],
    "SPHC":  [3,5,4,6,-8,7,9,6,4,2],
}
RF = 3.0  # Taux sans risque UEMOA

def load_cache():
    if CACHE_FILE.exists():
        try: return json.loads(CACHE_FILE.read_text())
        except: pass
    return {}

def save_cache(data):
    CACHE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def _mean(r): return statistics.mean(r) if r else 0.0
def _std(r): return statistics.stdev(r) if len(r)>1 else 0.0

def _cov(a, b):
    if len(a) != len(b) or len(a) < 2: return 0.0
    ma, mb = _mean(a), _mean(b)
    return sum((x-ma)*(y-mb) for x,y in zip(a,b)) / (len(a)-1)

def _corr(a, b):
    sa, sb = _std(a), _std(b)
    return _cov(a,b)/(sa*sb) if sa and sb else 0.0

def build_cov_matrix(tickers):
    n = len(tickers)
    cov = [[0.0]*n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            cov[i][j] = _cov(RETURNS[tickers[i]], RETURNS[tickers[j]])
    return cov

def portfolio_stats(weights, tickers, cov):
    ret = sum(w * _mean(RETURNS[t]) for w, t in zip(weights, tickers))
    n = len(weights)
    var = sum(weights[i]*weights[j]*cov[i][j] for i in range(n) for j in range(n))
    vol = math.sqrt(max(var, 0))
    sharpe = (ret - RF) / vol if vol > 0 else 0.0
    return round(ret, 3), round(vol, 3), round(sharpe, 3)

def _random_weights(n):
    w = [random.random() for _ in range(n)]
    s = sum(w)
    return [x/s for x in w]

def optimize(tickers=None, n_sim=5000, max_weight=0.35):
    if tickers is None:
        tickers = list(RETURNS.keys())
    n = len(tickers)
    cov = build_cov_matrix(tickers)
    
    best_sharpe = {"sharpe": -999, "weights": None, "ret": 0, "vol": 0}
    best_ret    = {"ret": -999, "weights": None, "sharpe": 0, "vol": 0}
    min_vol     = {"vol": 9999, "weights": None, "ret": 0, "sharpe": 0}
    frontier    = []

    for _ in range(n_sim):
        w = _random_weights(n)
        # Contrainte max_weight
        w = [min(x, max_weight) for x in w]
        s = sum(w); w = [x/s for x in w]
        
        ret, vol, sharpe = portfolio_stats(w, tickers, cov)
        frontier.append({"ret": ret, "vol": vol, "sharpe": sharpe,
                         "weights": {t: round(w[i],4) for i,t in enumerate(tickers)}})
        
        if sharpe > best_sharpe["sharpe"]:
            best_sharpe = {"sharpe": sharpe, "ret": ret, "vol": vol,
                          "weights": {t: round(w[i],4) for i,t in enumerate(tickers)}}
        if ret > best_ret["ret"]:
            best_ret = {"ret": ret, "sharpe": sharpe, "vol": vol,
                       "weights": {t: round(w[i],4) for i,t in enumerate(tickers)}}
        if vol < min_vol["vol"]:
            min_vol = {"vol": vol, "ret": ret, "sharpe": sharpe,
                      "weights": {t: round(w[i],4) for i,t in enumerate(tickers)}}

    # Top 20 frontière efficiente
    frontier_sorted = sorted(frontier, key=lambda x: x["vol"])
    efficient = []
    max_ret_seen = -999
    for p in frontier_sorted:
        if p["ret"] > max_ret_seen:
            efficient.append(p); max_ret_seen = p["ret"]
    efficient = efficient[:20]

    # Corrélation matrix pour affichage
    corr_matrix = {}
    for t1 in tickers:
        corr_matrix[t1] = {}
        for t2 in tickers:
            corr_matrix[t1][t2] = round(_corr(RETURNS[t1], RETURNS[t2]), 3)

    # Rendements et vols individuels
    individual = {t: {"mean_return": round(_mean(RETURNS[t]),2),
                      "volatility": round(_std(RETURNS[t]),2),
                      "sharpe": round((_mean(RETURNS[t])-RF)/_std(RETURNS[t]),3) if _std(RETURNS[t]) else 0}
                  for t in tickers}

    output = {
        "generated_at": datetime.now().isoformat(),
        "tickers": tickers,
        "n_simulations": n_sim,
        "max_weight_pct": max_weight * 100,
        "optimal_sharpe": best_sharpe,
        "optimal_return": best_ret,
        "min_volatility": min_vol,
        "efficient_frontier": efficient,
        "correlation_matrix": corr_matrix,
        "individual_stats": individual,
    }
    save_cache(output)
    return output

def get_optimizer_html():
    cache = load_cache()
    if not cache: return "<p>Optimisation non encore calculée.</p>"
    
    ms = cache.get("optimal_sharpe", {})
    mr = cache.get("optimal_return", {})
    mv = cache.get("min_volatility", {})
    indiv = cache.get("individual_stats", {})
    corr = cache.get("correlation_matrix", {})
    tickers = cache.get("tickers", [])

    def fmt_weights(w):
        if not w: return ""
        top = sorted(w.items(), key=lambda x: x[1], reverse=True)[:6]
        return " ".join(f'<span style="background:#1e3a5f;padding:2px 6px;border-radius:3px;margin:2px;display:inline-block;font-size:11px;color:#93c5fd">{t} {v*100:.0f}%</span>' for t,v in top)

    # Bulle chart frontière (SVG)
    frontier = cache.get("efficient_frontier", [])
    svg_frontier = ""
    if frontier and indiv:
        all_vols = [p["vol"] for p in frontier] + [v["volatility"] for v in indiv.values()]
        all_rets = [p["ret"] for p in frontier] + [v["mean_return"] for v in indiv.values()]
        min_v, max_v = min(all_vols)-1, max(all_vols)+1
        min_r, max_r = min(all_rets)-2, max(all_rets)+2
        W, H, PL, PR, PT, PB = 420, 200, 40, 10, 10, 30
        
        def sx(v): return PL + (v-min_v)/(max_v-min_v)*(W-PL-PR)
        def sy(r): return H-PB - (r-min_r)/(max_r-min_r)*(H-PT-PB)

        dots = ""
        for t, s in indiv.items():
            x, y = sx(s["volatility"]), sy(s["mean_return"])
            dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#334155" stroke="#64748b" stroke-width="1"/>'
            dots += f'<text x="{x+5:.1f}" y="{y+4:.1f}" fill="#64748b" font-size="8">{t}</text>'

        # Points frontière efficiente
        fp = " ".join(f"{sx(p['vol']):.1f},{sy(p['ret']):.1f}" for p in frontier)
        
        # Points optimaux
        sx_s, sy_s = sx(ms.get("vol",0)), sy(ms.get("ret",0))
        sx_r, sy_r = sx(mr.get("vol",0)), sy(mr.get("ret",0))
        sx_v, sy_v = sx(mv.get("vol",0)), sy(mv.get("ret",0))

        svg_frontier = f'''<svg viewBox="0 0 {W} {H}" style="width:100%;height:180px;margin:8px 0">
  <line x1="{PL}" y1="{PT}" x2="{PL}" y2="{H-PB}" stroke="#334155" stroke-width="1"/>
  <line x1="{PL}" y1="{H-PB}" x2="{W-PR}" y2="{H-PB}" stroke="#334155" stroke-width="1"/>
  <text x="2" y="{H//2}" fill="#64748b" font-size="8" transform="rotate(-90,8,{H//2})">Rendement %</text>
  <text x="{W//2-20}" y="{H-2}" fill="#64748b" font-size="8">Volatilité %</text>
  {dots}
  <polyline points="{fp}" fill="none" stroke="#22c55e" stroke-width="2" stroke-dasharray="3,2"/>
  <circle cx="{sx_s:.1f}" cy="{sy_s:.1f}" r="7" fill="#f59e0b" stroke="white" stroke-width="1.5"/>
  <text x="{sx_s+9:.1f}" y="{sy_s+4:.1f}" fill="#f59e0b" font-size="9" font-weight="bold">Max Sharpe</text>
  <circle cx="{sx_v:.1f}" cy="{sy_v:.1f}" r="7" fill="#818cf8" stroke="white" stroke-width="1.5"/>
  <text x="{sx_v+9:.1f}" y="{sy_v+4:.1f}" fill="#818cf8" font-size="9">Min Vol</text>
</svg>'''

    return f'''<div style="background:#1e293b;border-radius:8px;padding:16px;font-family:sans-serif">
<h3 style="color:#e2e8f0;margin:0 0 4px;font-size:14px">⚖️ Optimisation Portefeuille — Markowitz</h3>
<p style="color:#94a3b8;font-size:11px;margin:0 0 12px">{cache.get("n_simulations",0):,} simulations · {len(tickers)} actions · max {cache.get("max_weight_pct",35):.0f}% par action</p>
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px">
  <div style="background:#0f172a;border-radius:6px;padding:10px">
    <div style="color:#f59e0b;font-size:11px;font-weight:600;margin-bottom:4px">⭐ Max Sharpe ({ms.get("sharpe",0):.2f})</div>
    <div style="color:#e2e8f0;font-size:12px">Ret: <b>{ms.get("ret",0):+.1f}%</b> · Vol: {ms.get("vol",0):.1f}%</div>
    <div style="margin-top:6px">{fmt_weights(ms.get("weights",{}))}</div>
  </div>
  <div style="background:#0f172a;border-radius:6px;padding:10px">
    <div style="color:#22c55e;font-size:11px;font-weight:600;margin-bottom:4px">📈 Max Rendement ({mr.get("ret",0):+.1f}%)</div>
    <div style="color:#e2e8f0;font-size:12px">Sharpe: {mr.get("sharpe",0):.2f} · Vol: {mr.get("vol",0):.1f}%</div>
    <div style="margin-top:6px">{fmt_weights(mr.get("weights",{}))}</div>
  </div>
  <div style="background:#0f172a;border-radius:6px;padding:10px">
    <div style="color:#818cf8;font-size:11px;font-weight:600;margin-bottom:4px">🛡️ Min Volatilité ({mv.get("vol",0):.1f}%)</div>
    <div style="color:#e2e8f0;font-size:12px">Ret: {mv.get("ret",0):+.1f}% · Sharpe: {mv.get("sharpe",0):.2f}</div>
    <div style="margin-top:6px">{fmt_weights(mv.get("weights",{}))}</div>
  </div>
</div>
{svg_frontier}
<p style="color:#475569;font-size:10px;margin:4px 0 0;text-align:right">Généré {cache.get("generated_at","")[:10]}</p>
</div>'''

if __name__ == "__main__":
    print("Optimisation Markowitz BRVM...")
    r = optimize(n_sim=5000)
    ms = r["optimal_sharpe"]; mr = r["optimal_return"]; mv = r["min_volatility"]
    print(f"Max Sharpe  : {ms['sharpe']:.2f}  ret:{ms['ret']:+.1f}%  vol:{ms['vol']:.1f}%")
    print(f"Max Ret     : {mr['ret']:+.1f}%  sharpe:{mr['sharpe']:.2f}  vol:{mr['vol']:.1f}%")
    print(f"Min Vol     : {mv['vol']:.1f}%  ret:{mv['ret']:+.1f}%  sharpe:{mv['sharpe']:.2f}")
    print("\nAllocation Max Sharpe:")
    for t, w in sorted(ms["weights"].items(), key=lambda x: x[1], reverse=True):
        if w > 0.01: print(f"  {t:8s} {w*100:5.1f}%")
