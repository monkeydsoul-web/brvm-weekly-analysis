"""
Moteur de valorisation BRVM — 7 modèles combinés
Graham · DCF/FCF · DDM · EPV · Buffett Quality · Reverse DCF · Relatif/EV
"""

import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

# Paramètres globaux
REQUIRED_RETURN = 0.10       # Taux de rendement exigé (10% pour marché frontière)
WACC = 0.10                  # WACC (proxy)
RISK_FREE_RATE = 0.05        # OAT UEMOA ~5%
DIV_YIELD_THRESHOLD = 0.04   # Seuil Graham minimum (4%)
GEO_RISK_PENALTY = {         # Pénalité risque géopolitique (points)
    "Burkina Faso": -1.5,
    "Mali": -1.5,
    "Niger": -2.0,
    "Togo": -0.5,
    "Bénin": 0,
    "Sénégal": 0,
    "Côte d'Ivoire": 0,
}
SECTOR_MEDIAN_EV_EBITDA = {
    "Banque": 5.0,
    "Télécoms": 6.0,
    "Consommation": 8.0,
    "Agriculture": 7.0,
    "Énergie": 6.0,
    "Industriel": 6.0,
    "Utilités": 7.0,
}


# ──────────────────────────────────────────────────────────────────────────────
# 1. GRAHAM
# ──────────────────────────────────────────────────────────────────────────────
def score_graham(row: dict) -> dict:
    """Score Benjamin Graham /10"""
    score = 0.0
    details = []

    pe = row.get("pe_ref", 999)
    pb = row.get("pb_ref", 999)
    div_yield = row.get("div_yield") or 0
    debt = row.get("debt_level", "")
    stable = row.get("earnings_stable", False)

    # P/E ≤ 15 (bonus si ≤ 10)
    if pe <= 10:
        score += 2.5
        details.append(f"P/E={pe}× ≤ 10 ✓✓")
    elif pe <= 15:
        score += 1.5
        details.append(f"P/E={pe}× ≤ 15 ✓")
    else:
        details.append(f"P/E={pe}× > 15 ✗")

    # P/B ≤ 1.5 (bonus si ≤ 1.0)
    if pb <= 1.0:
        score += 2.0
        details.append(f"P/B={pb}× ≤ 1.0 ✓✓")
    elif pb <= 1.5:
        score += 1.0
        details.append(f"P/B={pb}× ≤ 1.5 ✓")
    else:
        details.append(f"P/B={pb}× > 1.5 ✗")

    # P/E × P/B ≤ 22.5 (règle Graham combinée)
    if pe and pb:
        combined = pe * pb
        if combined <= 22.5:
            score += 1.5
            details.append(f"P/E×P/B={combined:.1f} ≤ 22.5 ✓")
        else:
            details.append(f"P/E×P/B={combined:.1f} > 22.5 ✗")

    # Dividende ≥ 4%
    if div_yield >= 6:
        score += 2.0
        details.append(f"Rendement={div_yield:.1f}% ≥ 6% ✓✓")
    elif div_yield >= 4:
        score += 1.0
        details.append(f"Rendement={div_yield:.1f}% ≥ 4% ✓")
    else:
        details.append(f"Rendement={div_yield:.1f}% < 4% ✗")

    # Stabilité des résultats
    if stable:
        score += 1.0
        details.append("Résultats stables ✓")
    else:
        details.append("Résultats instables ✗")

    # Dette faible
    if debt == "Faible":
        score += 1.0
        details.append("Dette faible ✓")
    elif debt == "Modérée":
        score += 0.3
    else:
        details.append("Dette élevée ✗")

    score = min(10.0, max(0.0, score))
    return {"score": round(score, 1), "label": "Graham", "details": " | ".join(details)}


# ──────────────────────────────────────────────────────────────────────────────
# 2. DCF / FREE CASH FLOW YIELD
# ──────────────────────────────────────────────────────────────────────────────
def score_dcf(row: dict) -> dict:
    """Score DCF basé sur le rendement des bénéfices (proxy FCF) /10"""
    score = 0.0
    details = []

    pe = row.get("pe_ref", 999)
    roe = row.get("roe", 0)
    stable = row.get("earnings_stable", False)

    # Rendement des bénéfices = 1/PE
    earnings_yield = (1 / pe * 100) if pe and pe > 0 else 0

    if earnings_yield >= 18:
        score += 4.0
        details.append(f"Rdt bénéfices={earnings_yield:.1f}% ≥ 18% ✓✓✓")
    elif earnings_yield >= 12:
        score += 3.0
        details.append(f"Rdt bénéfices={earnings_yield:.1f}% ≥ 12% ✓✓")
    elif earnings_yield >= 8:
        score += 2.0
        details.append(f"Rdt bénéfices={earnings_yield:.1f}% ≥ 8% ✓")
    elif earnings_yield >= 5:
        score += 1.0
        details.append(f"Rdt bénéfices={earnings_yield:.1f}% ≥ 5%")
    else:
        details.append(f"Rdt bénéfices={earnings_yield:.1f}% < 5% ✗")

    # ROE proxy (qualité des bénéfices)
    if roe >= 25:
        score += 3.0
        details.append(f"ROE={roe}% ≥ 25% ✓✓")
    elif roe >= 15:
        score += 2.0
        details.append(f"ROE={roe}% ≥ 15% ✓")
    elif roe >= 10:
        score += 1.0
        details.append(f"ROE={roe}% ≥ 10%")
    else:
        details.append(f"ROE={roe}% < 10% ✗")

    # Stabilité
    if stable:
        score += 2.0
        details.append("FCF récurrent ✓")
    else:
        score += 0.5
        details.append("FCF volatile ✗")

    # Pénalité dividende nul
    div_yield = row.get("div_yield") or 0
    if div_yield == 0:
        score -= 1.0
        details.append("Pas de dividende ✗")

    score = min(10.0, max(0.0, score))
    return {"score": round(score, 1), "label": "DCF/FCF", "details": " | ".join(details)}


# ──────────────────────────────────────────────────────────────────────────────
# 3. DDM — DIVIDEND DISCOUNT MODEL
# ──────────────────────────────────────────────────────────────────────────────
def score_ddm(row: dict) -> dict:
    """Score DDM Gordon Growth /10"""
    score = 0.0
    details = []

    price = row.get("price")
    div = row.get("div_per_share", 0)
    div_yield = row.get("div_yield") or 0
    roe = row.get("roe", 0)

    if not price or not div or div == 0:
        details.append("Pas de dividende — DDM non applicable ✗")
        return {"score": 0.0, "label": "DDM", "details": " | ".join(details)}

    # Taux de croissance estimé = ROE × taux de rétention (proxy: 30%)
    retention = 0.30
    g_est = min((roe / 100) * retention, 0.12)  # plafond à 12%

    # Valeur DDM = D1 / (r - g)
    d1 = div * (1 + g_est)
    if REQUIRED_RETURN > g_est:
        ddm_value = d1 / (REQUIRED_RETURN - g_est)
        upside = (ddm_value / price - 1) * 100
    else:
        upside = 50  # croissance > taux de rendement = très attractif

    if upside >= 50:
        score += 5.0
        details.append(f"Hausse DDM=+{upside:.0f}% ✓✓✓")
    elif upside >= 25:
        score += 3.5
        details.append(f"Hausse DDM=+{upside:.0f}% ✓✓")
    elif upside >= 10:
        score += 2.0
        details.append(f"Hausse DDM=+{upside:.0f}% ✓")
    elif upside >= 0:
        score += 1.0
        details.append(f"Hausse DDM=+{upside:.0f}%")
    else:
        details.append(f"Surévalué DDM ({upside:.0f}%) ✗")

    # Rendement actuel
    if div_yield >= 8:
        score += 3.0
        details.append(f"Rendement={div_yield:.1f}% ✓✓")
    elif div_yield >= 5:
        score += 2.0
        details.append(f"Rendement={div_yield:.1f}% ✓")
    elif div_yield >= 3:
        score += 1.0
        details.append(f"Rendement={div_yield:.1f}%")
    else:
        details.append(f"Rendement={div_yield:.1f}% faible ✗")

    # Croissance estimée
    if g_est >= 0.07:
        score += 2.0
        details.append(f"Croissance div. estimée={g_est*100:.1f}% ✓")
    elif g_est >= 0.04:
        score += 1.0
        details.append(f"Croissance div. estimée={g_est*100:.1f}%")

    score = min(10.0, max(0.0, score))
    return {"score": round(score, 1), "label": "DDM", "details": " | ".join(details)}


# ──────────────────────────────────────────────────────────────────────────────
# 4. EPV — EARNINGS POWER VALUE (Greenwald)
# ──────────────────────────────────────────────────────────────────────────────
def score_epv(row: dict) -> dict:
    """Score EPV Greenwald /10"""
    score = 0.0
    details = []

    price = row.get("price")
    pe = row.get("pe_ref", 999)
    pb = row.get("pb_ref", 999)
    roe = row.get("roe", 0)
    stable = row.get("earnings_stable", False)

    if not price or not pe:
        return {"score": 0.0, "label": "EPV", "details": "Données insuffisantes"}

    # EPV = Bénéfice normalisé / coût du capital
    # Bénéfice normalisé ≈ prix / PE
    # EPV par action = (prix/PE) / 0.10
    eps_norm = price / pe
    epv_per_share = eps_norm / REQUIRED_RETURN

    epv_ratio = epv_per_share / price  # > 1 = sous-évalué

    if epv_ratio >= 1.5:
        score += 4.0
        details.append(f"EPV/Prix={epv_ratio:.2f} — sous-évalué de {(epv_ratio-1)*100:.0f}% ✓✓✓")
    elif epv_ratio >= 1.2:
        score += 2.5
        details.append(f"EPV/Prix={epv_ratio:.2f} ✓✓")
    elif epv_ratio >= 1.0:
        score += 1.5
        details.append(f"EPV/Prix={epv_ratio:.2f} ✓")
    else:
        details.append(f"EPV/Prix={epv_ratio:.2f} — surévalué ✗")

    # Franchise value: ROE > coût des capitaux propres
    if roe >= 20:
        score += 3.0
        details.append(f"ROE={roe}% — forte valeur de franchise ✓✓")
    elif roe >= 12:
        score += 1.5
        details.append(f"ROE={roe}% — valeur de franchise modérée ✓")
    else:
        details.append(f"ROE={roe}% — franchise faible ✗")

    # Stabilité des bénéfices
    if stable:
        score += 2.0
        details.append("Bénéfices normalisés fiables ✓")
    else:
        score += 0.5
        details.append("Bénéfices volatils — EPV moins fiable ✗")

    # P/B vs ROE (Price-to-EPV)
    fair_pb = roe / (REQUIRED_RETURN * 100)
    pb_discount = fair_pb - pb
    if pb_discount > 0.5:
        score += 1.0
        details.append(f"P/B actuel ({pb}) < P/B juste ({fair_pb:.1f}) ✓")

    score = min(10.0, max(0.0, score))
    return {"score": round(score, 1), "label": "EPV", "details": " | ".join(details)}


# ──────────────────────────────────────────────────────────────────────────────
# 5. BUFFETT QUALITY
# ──────────────────────────────────────────────────────────────────────────────
def score_buffett(row: dict) -> dict:
    """Score qualité style Buffett /10"""
    score = 0.0
    details = []

    roe = row.get("roe", 0)
    stable = row.get("earnings_stable", False)
    sector = row.get("sector", "")
    div = row.get("div_per_share", 0)
    div_yield = row.get("div_yield") or 0
    debt = row.get("debt_level", "")
    pe = row.get("pe_ref", 999)

    # ROE — moteur principal
    if roe >= 30:
        score += 4.0
        details.append(f"ROE={roe}% ≥ 30% — Exceptionnel ✓✓✓")
    elif roe >= 20:
        score += 3.0
        details.append(f"ROE={roe}% ≥ 20% ✓✓")
    elif roe >= 15:
        score += 2.0
        details.append(f"ROE={roe}% ≥ 15% ✓")
    elif roe >= 10:
        score += 1.0
        details.append(f"ROE={roe}% ≥ 10%")
    else:
        details.append(f"ROE={roe}% < 10% ✗")

    # Stabilité des résultats
    if stable:
        score += 2.0
        details.append("Résultats stables sur 5+ ans ✓")
    else:
        details.append("Résultats irréguliers ✗")

    # Fossé concurrentiel (moat) proxy: secteur + stabilité
    MOAT_SECTORS = {"Télécoms", "Banque", "Consommation", "Utilités"}
    if sector in MOAT_SECTORS and stable:
        score += 1.5
        details.append(f"Moat sectoriel ({sector}) ✓")
    elif sector in MOAT_SECTORS:
        score += 0.5

    # Dividende croissant (proxy: div existant + stabilité)
    if div > 0 and stable:
        score += 1.5
        details.append("Dividende régulier et croissant ✓")
    elif div > 0:
        score += 0.5

    # Dette faible = flexibilité financière
    if debt == "Faible":
        score += 1.0
        details.append("Bilan sain ✓")

    # Prix raisonnable (pas de premium excessif)
    if pe <= 15:
        score += 1.0
        details.append(f"P/E={pe}× — Prix raisonnable ✓")
    elif pe <= 25:
        score += 0.5
    else:
        details.append(f"P/E={pe}× — Premium élevé ✗")

    score = min(10.0, max(0.0, score))
    return {"score": round(score, 1), "label": "Buffett", "details": " | ".join(details)}


# ──────────────────────────────────────────────────────────────────────────────
# 6. REVERSE DCF
# ──────────────────────────────────────────────────────────────────────────────
def score_reverse_dcf(row: dict) -> dict:
    """Score Reverse DCF — croissance implicite vs réaliste /10"""
    score = 0.0
    details = []

    price = row.get("price")
    pe = row.get("pe_ref", 999)
    roe = row.get("roe", 0)
    stable = row.get("earnings_stable", False)

    if not price or not pe:
        return {"score": 0.0, "label": "Rev.DCF", "details": "Données insuffisantes"}

    # Croissance implicite g dans: PE = 1/(r-g) → g = r - 1/PE
    g_implied = REQUIRED_RETURN - (1 / pe) if pe > 0 else REQUIRED_RETURN

    # Croissance réaliste = ROE × retention_rate
    g_realistic = min((roe / 100) * 0.35, 0.12) if stable else min((roe / 100) * 0.20, 0.06)

    margin = g_realistic - g_implied  # positif = marché trop pessimiste = opportunité

    if margin >= 0.08:
        score += 5.0
        details.append(f"Croiss. implicite={g_implied*100:.1f}% vs réaliste={g_realistic*100:.1f}% — Marge +{margin*100:.1f}% ✓✓✓")
    elif margin >= 0.04:
        score += 3.5
        details.append(f"Marge +{margin*100:.1f}% ✓✓")
    elif margin >= 0.01:
        score += 2.0
        details.append(f"Marge +{margin*100:.1f}% ✓")
    elif margin >= -0.02:
        score += 1.0
        details.append(f"Marge {margin*100:.1f}% — Équilibre")
    else:
        details.append(f"Marché trop optimiste — Marge {margin*100:.1f}% ✗")

    # Prime à la stabilité
    if stable:
        score += 2.0
        details.append("Croissance réaliste fiable ✓")
    else:
        score += 0.5
        details.append("Incertitude sur la croissance ✗")

    # ROE élevé = croissance soutenable sans dilution
    if roe >= 20:
        score += 3.0
        details.append(f"ROE={roe}% — Croissance auto-financée ✓✓")
    elif roe >= 12:
        score += 1.5
        details.append(f"ROE={roe}% — Croissance modérée ✓")

    score = min(10.0, max(0.0, score))
    return {"score": round(score, 1), "label": "Rev.DCF", "details": " | ".join(details)}


# ──────────────────────────────────────────────────────────────────────────────
# 7. RELATIF / EV
# ──────────────────────────────────────────────────────────────────────────────
def score_relative(row: dict) -> dict:
    """Score valorisation relative sectorielle /10"""
    score = 0.0
    details = []

    pe = row.get("pe_ref", 999)
    pb = row.get("pb_ref", 999)
    sector = row.get("sector", "")
    roe = row.get("roe", 0)
    div_yield = row.get("div_yield") or 0

    sector_median_pe = {
        "Banque": 10, "Télécoms": 13, "Consommation": 16,
        "Agriculture": 14, "Énergie": 12, "Industriel": 13, "Utilités": 12,
    }
    median_pe = sector_median_pe.get(sector, 13)
    pe_discount = (median_pe - pe) / median_pe if median_pe else 0

    # Décote vs médiane sectorielle
    if pe_discount >= 0.30:
        score += 3.5
        details.append(f"P/E={pe}× vs médiane {median_pe}× — Décote {pe_discount*100:.0f}% ✓✓")
    elif pe_discount >= 0.10:
        score += 2.0
        details.append(f"Décote {pe_discount*100:.0f}% ✓")
    elif pe_discount >= 0:
        score += 1.0
        details.append(f"Décote {pe_discount*100:.0f}% — En ligne")
    else:
        details.append(f"Prime {-pe_discount*100:.0f}% vs secteur ✗")

    # P/B relatif à ROE (Warranted P/B)
    warranted_pb = roe / (REQUIRED_RETURN * 100)
    pb_gap = warranted_pb - pb
    if pb_gap > 1.0:
        score += 3.0
        details.append(f"P/B warranté={warranted_pb:.1f}× vs actuel={pb}× — Sous-évalué ✓✓")
    elif pb_gap > 0.3:
        score += 2.0
        details.append(f"P/B warranté={warranted_pb:.1f}× — Légèrement sous-évalué ✓")
    elif pb_gap > -0.3:
        score += 1.0
        details.append(f"P/B warranté={warranted_pb:.1f}× — Juste prix")
    else:
        details.append(f"P/B warranté={warranted_pb:.1f}× — Surévalué ✗")

    # Rendement dividende vs secteur (signal attractivité)
    if div_yield >= 7:
        score += 2.0
        details.append(f"Rendement={div_yield:.1f}% — Très attractif ✓✓")
    elif div_yield >= 4:
        score += 1.0
        details.append(f"Rendement={div_yield:.1f}% ✓")

    # EV/EBITDA proxy (via PE/ROE)
    ev_ebitda_proxy = pe * (REQUIRED_RETURN * 100 / roe) if roe else pe
    sector_ev = SECTOR_MEDIAN_EV_EBITDA.get(sector, 6.0)
    if ev_ebitda_proxy < sector_ev * 0.6:
        score += 1.5
        details.append(f"EV/EBITDA~{ev_ebitda_proxy:.1f}× vs médiane {sector_ev}× ✓✓")
    elif ev_ebitda_proxy < sector_ev:
        score += 0.5
        details.append(f"EV/EBITDA~{ev_ebitda_proxy:.1f}× ✓")

    score = min(10.0, max(0.0, score))
    return {"score": round(score, 1), "label": "Relatif", "details": " | ".join(details)}


# ──────────────────────────────────────────────────────────────────────────────
# SCORE COMPOSITE
# ──────────────────────────────────────────────────────────────────────────────
def compute_all_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Calcule les 7 scores et le score composite pour chaque action"""
    results = []

    for _, row in df.iterrows():
        r = row.to_dict()
        ticker = r["ticker"]

        g   = score_graham(r)
        dcf = score_dcf(r)
        ddm = score_ddm(r)
        epv = score_epv(r)
        buf = score_buffett(r)
        rev = score_reverse_dcf(r)
        rel = score_relative(r)

        # Pénalité géopolitique
        geo_penalty = GEO_RISK_PENALTY.get(r.get("country", ""), 0)

        composite = (
            g["score"] + dcf["score"] + ddm["score"] + epv["score"]
            + buf["score"] + rev["score"] + rel["score"]
        )
        composite_adj = max(0, composite + geo_penalty * 7 / 10)  # ramené /70

        results.append({
            "ticker": ticker,
            "name": r.get("name", ""),
            "sector": r.get("sector", ""),
            "country": r.get("country", ""),
            "price": r.get("price"),
            "change_pct": r.get("change_pct", 0),
            "div_yield": r.get("div_yield"),
            "pe_ref": r.get("pe_ref"),
            "pb_ref": r.get("pb_ref"),
            "roe": r.get("roe"),
            "market_cap_xof": r.get("market_cap_xof"),
            "div_per_share": r.get("div_per_share"),
            "eps_est": r.get("eps_est"),
            "book_value_per_share": r.get("book_value_per_share"),
            "ex_div_date": r.get("ex_div_date", "N/D"),
            "pay_div_date": r.get("pay_div_date", "N/D"),
            # Scores individuels
            "score_graham": g["score"],
            "score_dcf": dcf["score"],
            "score_ddm": ddm["score"],
            "score_epv": epv["score"],
            "score_buffett": buf["score"],
            "score_rev_dcf": rev["score"],
            "score_relatif": rel["score"],
            # Composite
            "geo_penalty": geo_penalty,
            "composite_raw": round(composite, 1),
            "composite_adj": round(composite_adj, 1),
            # Détails pour le PDF
            "detail_graham": g["details"],
            "detail_dcf": dcf["details"],
            "detail_ddm": ddm["details"],
            "detail_epv": epv["details"],
            "detail_buffett": buf["details"],
            "detail_rev_dcf": rev["details"],
            "detail_relatif": rel["details"],
        })

    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values("composite_adj", ascending=False).reset_index(drop=True)
    result_df["rank"] = result_df.index + 1
    return result_df


def tier_label(score: float) -> str:
    """Classe une action selon son score composite /70"""
    if score >= 50:
        return "★★★ FORT"
    elif score >= 35:
        return "★★ MODÉRÉ"
    elif score >= 20:
        return "★ FAIBLE"
    else:
        return "✗ ÉVITER"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Test rapide avec données fictives
    test_data = {
        "ticker": "TEST", "name": "Test Bank", "sector": "Banque",
        "country": "Côte d'Ivoire", "price": 10000, "change_pct": 1.5,
        "pe_ref": 8.0, "pb_ref": 1.5, "roe": 20, "div_per_share": 800,
        "div_yield": 8.0, "debt_level": "Faible", "earnings_stable": True,
        "market_cap_xof": 500_000_000_000,
    }
    for fn in [score_graham, score_dcf, score_ddm, score_epv, score_buffett, score_reverse_dcf, score_relative]:
        r = fn(test_data)
        print(f"{r['label']:10} {r['score']:5.1f}/10  {r['details'][:80]}")
