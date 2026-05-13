"""
live_ranker.py — Reclassement automatique des 47 sociétés BRVM
Recalcule les 8 modèles dès qu'un prix change ou qu'un rapport est analysé.
Cache : data/live_ranking.json (mis à jour à chaque déclenchement)
"""

import os
import json
import logging
import time
import threading
from datetime import datetime, timezone
from copy import deepcopy

logger = logging.getLogger(__name__)

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
RANKING_PATH  = os.path.join(BASE_DIR, "data", "live_ranking.json")
HISTORY_PATH  = os.path.join(BASE_DIR, "data", "ranking_history.json")

# Verrou pour éviter les recalculs simultanés
_lock = threading.Lock()
_last_ranking = None          # Cache en mémoire
_last_prices  = {}            # Derniers prix connus (pour détecter les changements)


def _is_div_date_recent(date_str: str, max_years: int = 3) -> bool:
    """Retourne True si la date BOC est dans les max_years dernières années.
    Format attendu: '3-juin-25', '21-juil.-25', '23-avr.-26', '20-août-21'
    """
    if not date_str:
        return False
    try:
        # Supprimer les points (mois abrégés comme 'juil.'), split sur '-'
        cleaned = date_str.replace('.', '').replace('  ', ' ').strip()
        parts = cleaned.split('-')
        if len(parts) >= 3:
            year_str = parts[-1].strip()
            year = int(year_str)
            if year < 100:
                year += 2000
            return (datetime.now().year - year) <= max_years
    except (ValueError, IndexError):
        pass
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Construction du row fondamental enrichi
# ─────────────────────────────────────────────────────────────────────────────

def _build_enriched_row(ticker, base_row, live_price_data, pdf_analysis):
    """
    Fusionne les 3 sources de données pour un ticker :
    1. Fondamentaux statiques (scraper.py)
    2. Prix live (live_data.py)
    3. KPIs extraits des PDF (bulk_analyzer.py)
    """
    row = dict(base_row)

    # ── Prix live ──────────────────────────────────────────────────────────
    live_price = live_price_data.get("price")
    if live_price and live_price > 0:
        old_price = row.get("price") or live_price
        row["price"]      = live_price
        row["change_pct"] = live_price_data.get("change_pct", 0)
        row["prev_close"] = live_price_data.get("prev_close")
        row["volume"]     = live_price_data.get("volume", 0)
        row["trend"]      = live_price_data.get("trend")

        # Recalcul P/E live depuis EPS si disponible
        eps = row.get("eps") or row.get("eps_est")
        if eps and eps > 0:
            row["pe_ref"] = round(live_price / eps, 2)
        elif old_price and old_price > 0 and old_price != live_price:
            ratio = live_price / old_price
            for key in ("pe_ref", "pe_hist"):
                old_val = row.get(key)
                if old_val and 0 < old_val < 990:
                    row[key] = round(old_val * ratio, 2)
            for key in ("pb_ref", "pb_hist"):
                old_val = row.get(key)
                if old_val and 0 < old_val < 990:
                    row[key] = round(old_val * ratio, 2)

        # Recalcul div_yield depuis dividende par action (source la plus fiable)
        dps = (row.get("div_per_share") or row.get("div_hist") or
               row.get("div_2024") or row.get("div_2023") or 0)
        if dps and dps > 0 and live_price > 0:
            row["div_yield"]     = round(float(dps) / live_price * 100, 2)
            row["div_per_share"] = float(dps)
        elif row.get("div_yield") and old_price and old_price > 0 and old_price != live_price:
            # Fallback: recalcul proportionnel seulement si div_yield existait
            dps_calc = row["div_yield"] / 100 * old_price
            row["div_yield"] = round(dps_calc / live_price * 100, 2)

    # ── BOC — PER réel, BNA dérivé, var_annee, ex_div_date ─────────────────
    try:
        from boc_scraper import get_boc_price_history
        _boc = get_boc_price_history()
        boc_entry = _boc.get(ticker, {})
        if boc_entry:
            per_boc = boc_entry.get('per_boc')
            if per_boc and 0 < float(per_boc) < 500:
                row['pe_hist'] = float(per_boc)
                price_ref = row.get('price') or boc_entry.get('cours_clot')
                existing_eps = row.get('eps') or row.get('bna') or 0
                if price_ref and price_ref > 0:
                    bna_boc = round(price_ref / float(per_boc), 1)
                    if bna_boc > 0 and (not existing_eps or bna_boc >= existing_eps * 0.7):
                        # BOC cohérent → appliquer eps et pe_ref BOC
                        row['bna']    = bna_boc
                        row['eps']    = bna_boc
                        row['pe_ref'] = float(per_boc)
                    elif existing_eps > 0:
                        # Garder EPS scraper, pe_ref = prix / eps (cohérent)
                        row['pe_ref'] = round(price_ref / existing_eps, 2)
                    else:
                        row['pe_ref'] = float(per_boc)
            if boc_entry.get('var_annee') is not None:
                row['var_annee'] = boc_entry['var_annee']
            if boc_entry.get('div_date'):
                row['ex_div_date'] = boc_entry['div_date']
            row['_boc_per']      = per_boc
            row['_boc_div']      = boc_entry.get('div_net') or 0
            row['_boc_div_date'] = boc_entry.get('div_date', '')
            row['_boc_cours']    = boc_entry.get('cours_clot')
    except Exception as _e:
        pass

    # ── earnings_stable automatique si absent ─────────────────────────────
    if not row.get('earnings_stable'):
        roe = row.get('roe') or 0
        debt = row.get('debt_level') or 'medium'
        verdict = row.get('pdf_verdict') or ''
        var_annee = row.get('var_annee') or 0
        div = row.get('div_per_share') or 0
        if roe >= 12 and debt in ('low','medium') and div > 0:
            row['earnings_stable'] = True
        elif roe >= 15 and verdict in ('POSITIF','NEUTRE'):
            row['earnings_stable'] = True
        elif roe >= 10 and var_annee >= 5 and div > 0:
            row['earnings_stable'] = True
        else:
            row['earnings_stable'] = roe >= 18

    # ── KPIs PDF — enrichissement prioritaire des modeles ────────────────
    if pdf_analysis and pdf_analysis.get("status") == "ok":
        kpis = pdf_analysis.get("kpis") or {}

        def kv(key):
            v = (kpis.get(key) or {}).get("valeur")
            return float(v) if v is not None else None

        price = row.get("price") or 0

        # ROE depuis PDF (plus fiable que statique)
        roe_pdf = kv("roe")
        if roe_pdf is not None and 0 < roe_pdf < 200:
            row["roe"] = round(roe_pdf, 1)
            # ROE > 15% = earnings_stable pour Buffett/Relatif
            row["earnings_stable"] = roe_pdf >= 12

        # Dividende par action depuis PDF → div_yield recalculé
        div_pdf = kv("dividende_par_action")
        if div_pdf and div_pdf > 0:
            row["div_per_share"] = div_pdf
            if price > 0:
                row["div_yield"] = round(div_pdf / price * 100, 2)

        # EPS depuis résultat net / nb actions (si disponible)
        rn_pdf  = kv("resultat_net")    # en MFCFA
        ca_pdf  = kv("chiffre_affaires") # en MFCFA
        nb_actions = row.get("shares") or row.get("shares_outstanding") or row.get("nb_actions")

        if rn_pdf and nb_actions and nb_actions > 0:
            # rn_pdf en MFCFA → FCFA : * 1_000_000
            eps_calc = rn_pdf * 1_000_000 / nb_actions
            if eps_calc > 0:
                row["eps"] = round(eps_calc, 0)
                if price > 0:
                    row["pe_ref"] = round(price / eps_calc, 2)

        # P/B depuis capitaux propres / nb actions
        cap_propres = kv("capitaux_propres")  # MFCFA
        if cap_propres and nb_actions and nb_actions > 0 and price > 0:
            vcp = cap_propres * 1_000_000 / nb_actions
            if vcp > 0:
                row["pb_ref"] = round(price / vcp, 2)
                row["bvpa"]   = round(vcp, 1)

        # EBITDA → dette implicite et niveau d'endettement
        ebitda_pdf  = kv("ebitda")
        dette_nette = kv("dette_nette")
        if ebitda_pdf and ebitda_pdf > 0 and dette_nette is not None:
            ratio_dette = dette_nette / ebitda_pdf if ebitda_pdf else 0
            if ratio_dette < 1:
                row["debt_level"] = "low"
            elif ratio_dette < 2.5:
                row["debt_level"] = "medium"
            else:
                row["debt_level"] = "high"

        # Marge nette → proxy qualité (FCF)
        marge = kv("marge_nette")
        if marge is not None and ca_pdf and ca_pdf > 0:
            fcf_proxy = ca_pdf * (marge / 100) * 0.7  # MFCFA
            row["fcf_margin"] = round(marge, 1)
            if nb_actions and nb_actions > 0:
                row["fcf_per_share"] = round(fcf_proxy * 1_000_000 / nb_actions, 0)

        # Métadonnées PDF pour affichage
        row["pdf_verdict"]      = pdf_analysis.get("verdict_investisseur")
        row["pdf_ca"]           = kv("chiffre_affaires")
        row["pdf_rn"]           = kv("resultat_net")
        row["pdf_ebitda"]       = kv("ebitda")
        row["pdf_marge"]        = kv("marge_nette")
        row["pdf_year"]         = pdf_analysis.get("year")
        row["pdf_points_cles"]  = pdf_analysis.get("points_cles", [])[:3]
        row["pdf_perspectives"] = pdf_analysis.get("perspectives", "")[:200]
        row["pdf_resume"]       = pdf_analysis.get("resume", "")[:300]

    # ── BOC — override final après PDF ───────────────────────────────────────
    boc_per      = row.get('_boc_per')
    boc_div      = row.get('_boc_div') or 0
    boc_div_date = row.get('_boc_div_date', '')
    boc_cours    = row.get('_boc_cours')
    price_final  = row.get('price') or boc_cours or 0

    # pe_ref + EPS BOC après PDF : cohérence obligatoire pe_ref = prix / eps
    if boc_per and 0 < float(boc_per) < 500:
        existing_eps = row.get('eps') or row.get('bna') or 0
        if price_final > 0:
            bna_boc = round(price_final / float(boc_per), 1)
            if bna_boc > 0 and (not existing_eps or bna_boc >= existing_eps * 0.7):
                # BOC cohérent avec données existantes → on applique
                row['bna']    = bna_boc
                row['eps']    = bna_boc
                row['pe_ref'] = float(boc_per)
            elif existing_eps > 0:
                # Garder l'EPS PDF (fiable), recalculer pe_ref cohérent
                row['pe_ref'] = round(price_final / existing_eps, 2)
            else:
                row['pe_ref'] = float(boc_per)

    # Dividende BOC : appliqué si date récente ET cohérent avec existant (≥ 50%)
    if boc_div > 0 and _is_div_date_recent(boc_div_date, max_years=3):
        existing_div = row.get('div_per_share') or 0
        if not existing_div or boc_div >= existing_div * 0.5:
            row['div_per_share'] = boc_div
            if price_final > 0:
                row['div_yield'] = round(boc_div / price_final * 100, 2)

    # Nettoyage des clés internes
    for k in ('_boc_per', '_boc_div', '_boc_div_date', '_boc_cours'):
        row.pop(k, None)

    return row


# ─────────────────────────────────────────────────────────────────────────────
# Calcul des 8 modèles
# ─────────────────────────────────────────────────────────────────────────────

def _compute_scores(row):
    """Calcule les 8 scores et le composite /80."""
    from valuation import (
        score_graham, score_dcf, score_ddm, score_epv,
        score_buffett, score_reverse_dcf, score_relative,
        GEO_RISK_PENALTY,
    )
    from live_valuation import score_technique_live

    g   = score_graham(row)
    dcf = score_dcf(row)
    ddm = score_ddm(row)
    epv = score_epv(row)
    buf = score_buffett(row)
    rev = score_reverse_dcf(row)
    rel = score_relative(row)
    tec = score_technique_live(row)

    geo_penalty  = GEO_RISK_PENALTY.get(row.get("country", ""), 0)
    composite_raw = (
        g["score"] + dcf["score"] + ddm["score"] + epv["score"]
        + buf["score"] + rev["score"] + rel["score"]
    )
    composite_adj_70 = max(0, composite_raw + geo_penalty * 7 / 10)
    composite_adj_80 = round(min(80, composite_adj_70 + tec["score"]), 1)

    return {
        "score_graham":    g["score"],
        "score_dcf":       dcf["score"],
        "score_ddm":       ddm["score"],
        "score_epv":       epv["score"],
        "score_buffett":   buf["score"],
        "score_rev_dcf":   rev["score"],
        "score_relatif":   rel["score"],
        "score_technique": tec["score"],
        "detail_graham":   g["details"],
        "detail_dcf":      dcf["details"],
        "detail_ddm":      ddm["details"],
        "detail_epv":      epv["details"],
        "detail_buffett":  buf["details"],
        "detail_rev_dcf":  rev["details"],
        "detail_relatif":  rel["details"],
        "detail_technique":tec["details"],
        "geo_penalty":     geo_penalty,
        "composite_raw":   round(composite_raw, 1),
        "composite_adj":   composite_adj_80,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Reclassement complet
# ─────────────────────────────────────────────────────────────────────────────

def compute_live_ranking(trigger="manual", force=False):
    """
    Recalcule le classement complet des 47 sociétés.
    trigger: "price_update" | "pdf_analysis" | "manual" | "scheduler"
    """
    global _last_ranking, _last_prices

    with _lock:
        try:
            from scraper import STOCK_FUNDAMENTALS
            from live_data import get_live_data

            # Charger les analyses PDF
            summary_path = os.path.join(BASE_DIR, "data", "analyses_summary.json")
            pdf_summary  = {}
            if os.path.exists(summary_path):
                with open(summary_path, encoding="utf-8") as f:
                    pdf_summary = json.load(f)

            # Charger les prix live (depuis cache, pas de re-fetch)
            live_cache  = get_live_data(force_refresh=False)
            live_prices = live_cache.get("prices", {})

            results = []
            changed_tickers = []

            for ticker, base_row in STOCK_FUNDAMENTALS.items():
                try:
                    live_price_data = live_prices.get(ticker, {})
                    pdf_analysis    = pdf_summary.get(ticker)

                    # Détecter si le prix a changé
                    new_price = live_price_data.get("price")
                    old_price = _last_prices.get(ticker)
                    if new_price and new_price != old_price:
                        changed_tickers.append(ticker)
                        _last_prices[ticker] = new_price

                    # Construire le row enrichi
                    row = _build_enriched_row(ticker, base_row, live_price_data, pdf_analysis)

                    # Calculer les 8 scores
                    scores = _compute_scores(row)

                    result = {
                        "ticker":        ticker,
                        "name":          base_row.get("name", ""),
                        "sector":        base_row.get("sector", ""),
                        "country":       base_row.get("country", ""),
                        "price":         row.get("price"),
                        "change_pct":    row.get("change_pct", 0),
                        "volume":        row.get("volume", 0),
                        "trend":         row.get("trend"),
                        "pe_ref":        row.get("pe_ref") or row.get("pe_hist"),
                        "pb_ref":        row.get("pb_ref") or row.get("pb_hist"),
                        "roe":           row.get("roe"),
                        "div_yield":     row.get("div_yield"),
                        "div_per_share": row.get("div_per_share"),
                        "pdf_verdict":   row.get("pdf_verdict"),
                        "pdf_ca":        row.get("pdf_ca"),
                        "pdf_rn":        row.get("pdf_rn"),
                        "pdf_year":      row.get("pdf_year"),
                        "pdf_resume":    row.get("pdf_resume"),
                        "pdf_points_cles": row.get("pdf_points_cles", []),
                        "shares":        row.get("shares"),
                        "eps":           row.get("eps"),
                        "bna":           row.get("eps"),
                        "bvpa":          row.get("bvpa"),
                        "var_annee":       row.get("var_annee"),
                        "ex_div_date":     row.get("ex_div_date"),
                        "earnings_stable": row.get("earnings_stable"),
                        "debt_level":      row.get("debt_level"),
                        "pdf_rn_mfcfa":  row.get("pdf_rn") or row.get("pdf_rn_mfcfa"),
                        "pdf_cap_propres": row.get("pdf_cap_propres"),
                        "pdf_ca_mfcfa":  row.get("pdf_ca") or row.get("pdf_ca_mfcfa"),
                        "ebitda":        row.get("pdf_ebitda") or row.get("pdf_ebitda_mfcfa"),
                        "bvpa":          row.get("bvpa"),
                        "var_annee":       row.get("var_annee"),
                        "ex_div_date":     row.get("ex_div_date"),
                        "earnings_stable": row.get("earnings_stable"),
                        "debt_level":      row.get("debt_level"),
                        "debt_level":    row.get("debt_level"),
                        **scores,
                    }
                    results.append(result)

                except Exception as e:
                    logger.warning(f"Erreur scoring {ticker}: {e}")
                    results.append({
                        "ticker": ticker,
                        "name":   base_row.get("name", ""),
                        "composite_adj": 0,
                        "error": str(e),
                    })

            # Trier par score décroissant
            results.sort(key=lambda x: x.get("composite_adj", 0), reverse=True)

            # Calculer les mouvements de rang
            old_ranks = {}
            if _last_ranking:
                for r in _last_ranking.get("ranking", []):
                    old_ranks[r["ticker"]] = r.get("rank", 0)

            for i, r in enumerate(results):
                r["rank"]      = i + 1
                old_rank       = old_ranks.get(r["ticker"], i + 1)
                r["rank_delta"] = old_rank - (i + 1)  # positif = monté

            # Payload final
            payload = {
                "updated_at":       datetime.now(timezone.utc).isoformat(),
                "trigger":          trigger,
                "market_open":      live_cache.get("market_open", False),
                "changed_tickers":  changed_tickers,
                "total":            len(results),
                "ranking":          results,
            }

            # Sauvegarder
            os.makedirs(os.path.dirname(RANKING_PATH), exist_ok=True)
            with open(RANKING_PATH, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            # Sauvegarder dans l'historique (top 10 seulement, max 30 entrées)
            _save_history(payload)

            _last_ranking = payload
            logger.info(
                f"Ranking recalculé — trigger={trigger} "
                f"changements={len(changed_tickers)} "
                f"top1={results[0]['ticker'] if results else '?'}"
            )
            return payload

        except Exception as e:
            logger.error(f"compute_live_ranking erreur: {e}")
            return _last_ranking or {}


def _save_history(payload):
    """Sauvegarde un snapshot du top 10 dans l'historique."""
    try:
        history = []
        if os.path.exists(HISTORY_PATH):
            with open(HISTORY_PATH, encoding="utf-8") as f:
                history = json.load(f)

        snapshot = {
            "ts":      payload["updated_at"],
            "trigger": payload["trigger"],
            "top10":   [
                {"ticker": r["ticker"], "score": r["composite_adj"], "rank": r["rank"]}
                for r in payload["ranking"][:10]
            ],
        }
        history.append(snapshot)
        history = history[-30:]  # Garder 30 derniers

        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"_save_history: {e}")


def load_ranking():
    """Charge le dernier classement depuis le cache fichier."""
    global _last_ranking
    if _last_ranking:
        return _last_ranking
    if os.path.exists(RANKING_PATH):
        try:
            with open(RANKING_PATH, encoding="utf-8") as f:
                _last_ranking = json.load(f)
                return _last_ranking
        except Exception:
            pass
    return None


def get_ranking_changes():
    """Retourne les sociétés dont le rang a changé depuis le dernier calcul."""
    ranking = load_ranking()
    if not ranking:
        return []
    changes = [
        {
            "ticker":      r["ticker"],
            "name":        r.get("name", ""),
            "rank":        r["rank"],
            "rank_delta":  r.get("rank_delta", 0),
            "score":       r.get("composite_adj", 0),
            "change_pct":  r.get("change_pct", 0),
        }
        for r in ranking.get("ranking", [])
        if r.get("rank_delta", 0) != 0
    ]
    return sorted(changes, key=lambda x: abs(x["rank_delta"]), reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler intégration
# ─────────────────────────────────────────────────────────────────────────────

def schedule_ranking_jobs(scheduler):
    """
    Ajoute les jobs de reclassement à l'APScheduler existant.
    Appeler depuis app.py après start_scheduler().
    """
    # Recalcul après chaque mise à jour des prix live (toutes les 5 min)
    def job_ranking_on_price():
        compute_live_ranking(trigger="price_update")

    scheduler.add_job(
        job_ranking_on_price,
        "interval", minutes=5,
        id="live_ranking_price",
        replace_existing=True,
    )

    # Recalcul après analyse PDF (quotidien 23h30)
    def job_ranking_on_pdf():
        compute_live_ranking(trigger="pdf_analysis")

    scheduler.add_job(
        job_ranking_on_pdf,
        "cron", hour=23, minute=30,
        id="live_ranking_pdf",
        replace_existing=True,
    )

    logger.info("Jobs ranking schedulés")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    print("Calcul du classement live...")
    result = compute_live_ranking(trigger="manual")

    if result.get("ranking"):
        print(f"\nClassement live — {result['updated_at'][:19]}")
        print(f"{'Rg':3} {'Ticker':8} {'Score':6} {'P/E':6} {'ROE':6} {'PDF':8} {'Δ':4}")
        print("-" * 55)
        for r in result["ranking"][:20]:
            delta = r.get("rank_delta", 0)
            delta_str = f"+{delta}" if delta > 0 else str(delta) if delta < 0 else "—"
            pdf = r.get("pdf_verdict", "")[:7] if r.get("pdf_verdict") else "—"
            pe  = f"{r.get('pe_ref',0):.1f}x" if r.get("pe_ref") else "—"
            roe = f"{r.get('roe',0):.0f}%" if r.get("roe") else "—"
            print(
                f"{r['rank']:3d} {r['ticker']:8s} "
                f"{r.get('composite_adj',0):5.1f}  "
                f"{pe:6s} {roe:6s} {pdf:8s} {delta_str:4s}"
            )

        changes = get_ranking_changes()
        if changes:
            print(f"\nMouvements ({len(changes)}):")
            for c in changes[:5]:
                arrow = "▲" if c["rank_delta"] > 0 else "▼"
                print(f"  {arrow} {c['ticker']:8s} rang {c['rank']} ({c['rank_delta']:+d})")
