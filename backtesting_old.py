#!/usr/bin/env python3
"""
backtesting.py — Validation historique des scores BRVM
Stratégie : Top 5 scores rebalancé annuellement vs benchmark
Métriques : rendement annualisé, Sharpe ratio, max drawdown, hit rate
Python 3.9 compatible
"""
import json, statistics, math
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

CACHE_FILE = Path("backtesting_cache.json")

PRICE_HISTORY_ANNUAL = {
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
BRVM_BENCHMARK = [8,11,10,12,-8,14,18,12,9,6]
YEARS = list(range(2016,2026))
HISTORICAL_SCORES = {
    "SGBC":  [38,40,42,44,41,43,44,45,44,44],
    "SIBC":  [35,37,39,41,38,40,42,43,42,42],
    "SNTS":  [44,46,47,48,46,48,50,51,51,51],
    "CBIBF": [48,50,52,54,51,53,55,56,56,56],
    "NSBC":  [38,40,41,42,40,41,42,43,42,42],
    "ORAC":  [35,37,38,40,37,39,40,41,41,41],
    "BOAB":  [30,32,33,34,31,33,34,35,34,34],
    "ECOC":  [28,30,31,32,29,31,32,33,32,32],
    "BICC":  [32,34,35,36,33,35,36,37,36,36],
    "NTLC":  [29,31,32,33,30,32,33,34,33,33],
    "STBC":  [33,35,36,37,34,36,37,38,37,37],
    "UNLC":  [30,32,33,34,31,33,34,35,34,34],
    "SLBC":  [25,27,28,29,26,28,29,30,29,29],
    "PALC":  [22,24,25,26,23,25,26,27,26,26],
    "SPHC":  [20,22,23,24,21,23,24,25,24,24],
}

def load_cache():
    if CACHE_FILE.exists():
        try: return json.loads(CACHE_FILE.read_text())
        except: pass
    return {}

def save_cache(data):
    CACHE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def _annualized_return(returns):
    if not returns: return 0.0
    p = 1.0
    for r in returns: p *= (1 + r/100.0)
    return round((p**(1.0/len(returns))-1)*100, 2)

def _sharpe_ratio(returns, rf=3.0):
    if len(returns)<2: return 0.0
    avg=statistics.mean(returns); std=statistics.stdev(returns)
    return round((avg-rf)/std, 3) if std else 0.0

def _max_drawdown(returns):
    cum=[100.0]
    for r in returns: cum.append(cum[-1]*(1+r/100.0))
    peak=cum[0]; mdd=0.0
    for v in cum:
        if v>peak: peak=v
        dd=(peak-v)/peak*100
        if dd>mdd: mdd=dd
    return round(mdd,2)

def _hit_rate(s,b):
    if not s or not b: return 0.0
    return round(sum(1 for a,c in zip(s,b) if a>c)/len(s)*100,1)

def _compute_correlation():
    scores=[]; rets=[]
    for t in HISTORICAL_SCORES:
        avg_s=statistics.mean(HISTORICAL_SCORES[t])
        r=[v for v in PRICE_HISTORY_ANNUAL.get(t,[])]
        if r:
            scores.append(avg_s); rets.append(_annualized_return(r))
    if len(scores)<3: return 0.0
    n=len(scores); ms=statistics.mean(scores); mr=statistics.mean(rets)
    num=sum((s-ms)*(r-mr) for s,r in zip(scores,rets))
    ds=math.sqrt(sum((s-ms)**2 for s in scores))
    dr=math.sqrt(sum((r-mr)**2 for r in rets))
    return round(num/(ds*dr),3) if ds and dr else 0.0

def run_backtesting(top_n=5, score_threshold=40):
    results_by_year=[]; strat_annual=[]; all_t=list(HISTORICAL_SCORES.keys())
    for yi,year in enumerate(YEARS[:-1]):
        sc={t:HISTORICAL_SCORES[t][yi] for t in all_t if yi<len(HISTORICAL_SCORES[t])}
        top=sorted(sc.items(),key=lambda x:x[1],reverse=True)[:top_n]
        top_t=[t for t,_ in top]
        yr=[]
        for t in top_t:
            if t in PRICE_HISTORY_ANNUAL and yi<len(PRICE_HISTORY_ANNUAL[t]):
                yr.append(PRICE_HISTORY_ANNUAL[t][yi])
        pr=statistics.mean(yr) if yr else 0.0
        br=BRVM_BENCHMARK[yi]
        results_by_year.append({"year":year,"top_picks":[{"ticker":t,"score":s} for t,s in top],
            "portfolio_return_pct":round(pr,2),"benchmark_return_pct":round(br,2),
            "alpha_pct":round(pr-br,2),"beat_benchmark":pr>br})
        strat_annual.append(pr)
    bench_a=BRVM_BENCHMARK[:-1]
    metrics={"strategy_annualized_return":_annualized_return(strat_annual),
        "benchmark_annualized_return":_annualized_return(bench_a),
        "strategy_sharpe":_sharpe_ratio(strat_annual),"benchmark_sharpe":_sharpe_ratio(bench_a),
        "strategy_max_drawdown":_max_drawdown(strat_annual),"benchmark_max_drawdown":_max_drawdown(bench_a),
        "hit_rate_pct":_hit_rate(strat_annual,bench_a),
        "total_alpha_pct":round(_annualized_return(strat_annual)-_annualized_return(bench_a),2),
        "n_years":len(strat_annual),"top_n":top_n}
    sg=100.0; bg=100.0; growth=[]
    for i,yr2 in enumerate(results_by_year):
        sg*=(1+yr2["portfolio_return_pct"]/100); bg*=(1+yr2["benchmark_return_pct"]/100)
        growth.append({"year":yr2["year"],"strategy":round(sg,1),"benchmark":round(bg,1)})
    ticker_perf={}
    for t in all_t:
        r=PRICE_HISTORY_ANNUAL.get(t,[])
        if r: ticker_perf[t]={"annualized_return":_annualized_return(r),"sharpe":_sharpe_ratio(r),
            "max_drawdown":_max_drawdown(r),"avg_score":round(statistics.mean(HISTORICAL_SCORES.get(t,[0])),1)}
    output={"generated_at":datetime.now().isoformat(),"metrics":metrics,
        "results_by_year":results_by_year,"growth_series":growth,
        "ticker_performance":ticker_perf,"score_vs_return_correlation":_compute_correlation()}
    save_cache(output); return output

def get_backtesting_summary_html():
    cache=load_cache()
    if not cache: return "<p>Backtesting non encore calculé.</p>"
    m=cache.get("metrics",{}); growth=cache.get("growth_series",[])
    results_by_year=cache.get("results_by_year",[]); corr=cache.get("score_vs_return_correlation",0)
    alpha_color="#22c55e" if m.get("total_alpha_pct",0)>0 else "#ef4444"
    hit_color="#22c55e" if m.get("hit_rate_pct",0)>=60 else "#f59e0b"
    corr_color="#22c55e" if corr>0.5 else "#f59e0b"
    year_rows=""
    for yr in results_by_year:
        alpha=yr.get("alpha_pct",0); ac="#22c55e" if alpha>0 else "#ef4444"
        picks=", ".join([p["ticker"] for p in yr.get("top_picks",[])[:3]])
        year_rows+=f'''<tr>
<td style="padding:6px 10px;color:#e2e8f0">{yr["year"]}</td>
<td style="padding:6px 10px;color:#22c55e">{yr["portfolio_return_pct"]:+.1f}%</td>
<td style="padding:6px 10px;color:#94a3b8">{yr["benchmark_return_pct"]:+.1f}%</td>
<td style="padding:6px 10px;color:{ac};font-weight:600">{alpha:+.1f}%</td>
<td style="padding:6px 10px;color:#64748b;font-size:11px">{picks}</td></tr>'''
    svg_chart=""
    if growth:
        maxv=max(max(g["strategy"] for g in growth),max(g["benchmark"] for g in growth))
        minv=min(min(g["strategy"] for g in growth),min(g["benchmark"] for g in growth))
        vr=maxv-minv or 1; w,h,p=400,120,10
        def tx(i): return p+i*(w-2*p)/(len(growth)-1)
        def ty(v): return h-p-(v-minv)/vr*(h-2*p)
        sp=" ".join(f"{tx(i):.1f},{ty(g['strategy']):.1f}" for i,g in enumerate(growth))
        bp=" ".join(f"{tx(i):.1f},{ty(g['benchmark']):.1f}" for i,g in enumerate(growth))
        svg_chart=f'''<svg viewBox="0 0 {w} {h}" style="width:100%;height:100px;margin:8px 0">
<polyline points="{sp}" fill="none" stroke="#22c55e" stroke-width="2"/>
<polyline points="{bp}" fill="none" stroke="#64748b" stroke-width="1.5" stroke-dasharray="4,2"/>
<text x="5" y="12" fill="#22c55e" font-size="9">— Stratégie Top5</text>
<text x="5" y="22" fill="#64748b" font-size="9">- - Benchmark BRVM</text>
<text x="{tx(0):.0f}" y="{h-2}" fill="#64748b" font-size="8">{growth[0]["year"]}</text>
<text x="{tx(len(growth)-1)-20:.0f}" y="{h-2}" fill="#64748b" font-size="8">{growth[-1]["year"]}</text>
</svg>'''
    return f'''<div style="background:#1e293b;border-radius:8px;padding:16px;font-family:sans-serif">
<h3 style="color:#e2e8f0;margin:0 0 4px;font-size:14px">📊 Backtesting — Top 5 Scores vs BRVM</h3>
<p style="color:#94a3b8;font-size:11px;margin:0 0 12px">{m.get("n_years",0)} ans · corrélation score/rendement : <span style="color:{corr_color};font-weight:600">{corr:+.3f}</span></p>
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px">
<div style="background:#0f172a;border-radius:6px;padding:8px;text-align:center"><div style="color:#64748b;font-size:10px">Rendement annualisé</div><div style="color:#22c55e;font-size:16px;font-weight:700">{m.get("strategy_annualized_return",0):+.1f}%</div><div style="color:#64748b;font-size:10px">vs {m.get("benchmark_annualized_return",0):+.1f}% bench</div></div>
<div style="background:#0f172a;border-radius:6px;padding:8px;text-align:center"><div style="color:#64748b;font-size:10px">Alpha annuel</div><div style="color:{alpha_color};font-size:16px;font-weight:700">{m.get("total_alpha_pct",0):+.1f}%</div><div style="color:#64748b;font-size:10px">surplus vs benchmark</div></div>
<div style="background:#0f172a;border-radius:6px;padding:8px;text-align:center"><div style="color:#64748b;font-size:10px">Sharpe ratio</div><div style="color:#f59e0b;font-size:16px;font-weight:700">{m.get("strategy_sharpe",0):.2f}</div><div style="color:#64748b;font-size:10px">vs {m.get("benchmark_sharpe",0):.2f} bench</div></div>
<div style="background:#0f172a;border-radius:6px;padding:8px;text-align:center"><div style="color:#64748b;font-size:10px">Hit Rate</div><div style="color:{hit_color};font-size:16px;font-weight:700">{m.get("hit_rate_pct",0):.0f}%</div><div style="color:#64748b;font-size:10px">années > benchmark</div></div>
</div>{svg_chart}
<table style="width:100%;border-collapse:collapse;margin-top:8px">
<thead><tr style="border-bottom:1px solid #334155">
<th style="padding:6px 10px;color:#64748b;text-align:left;font-size:11px">Année</th>
<th style="padding:6px 10px;color:#64748b;text-align:left;font-size:11px">Stratégie</th>
<th style="padding:6px 10px;color:#64748b;text-align:left;font-size:11px">Benchmark</th>
<th style="padding:6px 10px;color:#64748b;text-align:left;font-size:11px">Alpha</th>
<th style="padding:6px 10px;color:#64748b;text-align:left;font-size:11px">Top 3 picks</th>
</tr></thead><tbody>{year_rows}</tbody></table>
<p style="color:#475569;font-size:10px;margin:8px 0 0;text-align:right">Max drawdown : {m.get("strategy_max_drawdown",0):.1f}% · {cache.get("generated_at","")[:10]}</p>
</div>'''

if __name__ == "__main__":
    print("Lancement backtesting...")
    r=run_backtesting()
    m=r["metrics"]
    print(f"Rendement: {m['strategy_annualized_return']:+.1f}% vs {m['benchmark_annualized_return']:+.1f}%")
    print(f"Alpha: {m['total_alpha_pct']:+.1f}%  Sharpe: {m['strategy_sharpe']:.2f}  Hit: {m['hit_rate_pct']:.0f}%")
    print(f"Corrélation score/rendement: {r['score_vs_return_correlation']:+.3f}")
    for yr in r["results_by_year"]:
        s="✓" if yr["beat_benchmark"] else "✗"
        picks=",".join([p["ticker"] for p in yr["top_picks"][:3]])
        print(f"  {yr['year']} {s} {yr['portfolio_return_pct']:+.1f}% vs {yr['benchmark_return_pct']:+.1f}% alpha:{yr['alpha_pct']:+.1f}% [{picks}]")
