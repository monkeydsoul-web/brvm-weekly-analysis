"""
score_enricher.py — Enrichit STOCK_FUNDAMENTALS avec les KPIs extraits des PDF
Met à jour le fichier data/scores_enriched.json utilisé par le dashboard.
"""

import os
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
SUMMARY_PATH     = os.path.join(BASE_DIR, "data", "analyses_summary.json")
ENRICHED_PATH    = os.path.join(BASE_DIR, "data", "scores_enriched.json")


def load_summary():
    if not os.path.exists(SUMMARY_PATH):
        return {}
    with open(SUMMARY_PATH, encoding="utf-8") as f:
        return json.load(f)


def kpi_val(analysis, key):
    """Extrait une valeur KPI de l'analyse IA."""
    kpis = analysis.get("kpis") or {}
    item = kpis.get(key) or {}
    return item.get("valeur")


def enrich_fundamentals(base_fundamentals, analysis):
    """
    Fusionne les KPIs extraits par Claude dans le row fondamental.
    Les données PDF ont priorité sur les données statiques scraper.py
    seulement si elles sont non nulles.
    """
    row = dict(base_fundamentals)

    if not analysis or analysis.get("status") != "ok":
        return row

    kpis = analysis.get("kpis") or {}

    # Chiffre d'affaires → proxy pour market_cap et EPS
    ca = kpi_val(analysis, "chiffre_affaires")
    rn = kpi_val(analysis, "resultat_net")
    roe_pdf = kpi_val(analysis, "roe")
    marge = kpi_val(analysis, "marge_nette")
    div_pdf = kpi_val(analysis, "dividende_par_action")
    ebitda = kpi_val(analysis, "ebitda")
    cap_propres = kpi_val(analysis, "capitaux_propres")
    total_bilan = kpi_val(analysis, "total_bilan")

    # Mettre à jour ROE si dispo dans le PDF (plus fiable)
    if roe_pdf is not None:
        row["roe"] = round(float(roe_pdf), 1)

    # Mettre à jour dividende si dispo
    if div_pdf is not None and div_pdf > 0:
        row["div_per_share"] = float(div_pdf)
        # Recalculer div_yield avec le prix courant
        price = row.get("price") or row.get("price_ref") or 0
        if price and price > 0:
            row["div_yield"] = round(float(div_pdf) / price * 100, 2)

    # Ajouter métadonnées PDF
    row["pdf_ca_mfcfa"]      = ca
    row["pdf_rn_mfcfa"]      = rn
    row["pdf_ebitda_mfcfa"]  = ebitda
    row["pdf_marge_nette"]   = marge
    row["pdf_cap_propres"]   = cap_propres
    row["pdf_total_bilan"]   = total_bilan
    row["pdf_verdict"]       = analysis.get("verdict_investisseur")
    row["pdf_resume"]        = analysis.get("resume")
    row["pdf_points_cles"]   = analysis.get("points_cles", [])
    row["pdf_risques"]       = analysis.get("risques", [])
    row["pdf_perspectives"]  = analysis.get("perspectives")
    row["pdf_year"]          = analysis.get("year")
    row["pdf_analyzed_at"]   = analysis.get("analyzed_at")

    return row


def build_enriched_scores():
    """
    Charge les scores existants, les enrichit avec les analyses PDF,
    recalcule les scores /80, sauvegarde dans scores_enriched.json.
    """
    import glob

    # Charger les scores existants
    score_files = sorted(glob.glob(os.path.join(BASE_DIR, "data", "scores_*.json")))
    if not score_files:
        logger.warning("Aucun fichier scores_*.json trouvé")
        return []

    with open(score_files[-1], encoding="utf-8") as f:
        scores = json.load(f)

    # Charger les analyses PDF
    summary = load_summary()

    # Enrichir chaque score
    enriched = []
    for stock in scores:
        ticker = stock.get("ticker", "")
        analysis = summary.get(ticker)

        if analysis and analysis.get("status") == "ok":
            # Fusionner KPIs PDF dans le stock
            stock = {**stock, **enrich_from_analysis(stock, analysis)}

        enriched.append(stock)

    # Trier par score décroissant
    enriched.sort(key=lambda x: x.get("composite_adj", 0), reverse=True)

    # Sauvegarder
    os.makedirs(os.path.dirname(ENRICHED_PATH), exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total":      len(enriched),
        "scores":     enriched,
    }
    with open(ENRICHED_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    logger.info(f"scores_enriched.json — {len(enriched)} sociétés")
    return enriched


def enrich_from_analysis(stock, analysis):
    """Retourne les champs à ajouter/mettre à jour dans un stock."""
    kpis = analysis.get("kpis") or {}
    updates = {}

    def v(key):
        return (kpis.get(key) or {}).get("valeur")

    roe_pdf = v("roe")
    div_pdf = v("dividende_par_action")

    if roe_pdf is not None:
        updates["roe"] = round(float(roe_pdf), 1)

    if div_pdf is not None and div_pdf > 0:
        updates["div_per_share"] = float(div_pdf)
        price = stock.get("price") or 0
        if price > 0:
            updates["div_yield"] = round(float(div_pdf) / price * 100, 2)

    updates.update({
        "pdf_ca":          v("chiffre_affaires"),
        "pdf_rn":          v("resultat_net"),
        "pdf_ebitda":      v("ebitda"),
        "pdf_marge":       v("marge_nette"),
        "pdf_verdict":     analysis.get("verdict_investisseur"),
        "pdf_resume":      analysis.get("resume"),
        "pdf_points_cles": analysis.get("points_cles", []),
        "pdf_perspectives":analysis.get("perspectives"),
        "pdf_year":        analysis.get("year"),
        "pdf_analyzed_at": analysis.get("analyzed_at"),
    })
    return updates


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    enriched = build_enriched_scores()
    print(f"\nScores enrichis: {len(enriched)} sociétés")
    print(f"Fichier: {ENRICHED_PATH}")

    # Afficher top 10
    print("\nTop 10 après enrichissement:")
    for s in enriched[:10]:
        verdict = s.get("pdf_verdict", "")
        ca      = s.get("pdf_ca")
        ca_str  = f"CA:{ca:,.0f}M" if ca else ""
        print(f"  {s.get('rank',0):2d}. {s['ticker']:8s} {s.get('composite_adj',0):5.1f}/80  "
              f"{verdict:8s} {ca_str}")
