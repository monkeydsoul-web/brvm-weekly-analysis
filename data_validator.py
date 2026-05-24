"""
data_validator.py — Validation multi-source des données financières BRVM.

Principe de priorité (dividende par action) :
  1. BOC (brvm.org/BOC)  ← référence officielle
  2. PDF IA (analyses_summary.json) ← cross-check
  3. scraper.py div_hist ← fallback historique, exclu du scoring de confiance

Règles de confiance BOC↔PDF :
  écart ≤ 10%  → HAUTE   (concordance multi-source)
  écart 10-30% → MOYENNE (divergence modérée)
  écart > 30%  → FAIBLE  (BOC retenu, PDF suspect — souvent STATIC_DATA faux)
  source unique→ MOYENNE (non recoupé)
  sans BOC ni PDF → FAIBLE

Sanity checks :
  div_yield > 15%          → exceptionnel/non récurrent
  div_per_share > 50% prix → exceptionnel/non récurrent
"""
import logging
logger = logging.getLogger(__name__)

DIV_YIELD_HARD_CAP    = 15.0  # % — au-delà : suspect/exceptionnel
DIV_PRICE_RATIO_MAX   = 0.50  # div > 50% cours → exceptionnel
DIV_DIVERGENCE_HIGH   = 30.0  # % BOC↔PDF → confiance faible, BOC gagne
DIV_DIVERGENCE_MED    = 10.0  # % BOC↔PDF → confiance moyenne


def _ecart(a, b):
    if a is None or b is None:
        return None
    m = max(abs(a), abs(b))
    return 0.0 if m == 0 else abs(a - b) / m * 100


def validate_dividend(ticker, scraper_div, pdf_div, boc_div, price):
    """
    Valide et arbitre div_per_share à partir des trois sources.

    Retourne un dict :
      value              float  – valeur pour CALCULS (0 si exceptionnel)
      raw_value          float  – valeur brute originale (affichage fiche)
      confidence         str    – "haute"|"moyenne"|"faible"|"exceptionnelle"|"inconnue"
      is_exceptional     bool   – dividende non récurrent détecté
      flag               str    – ""|"exceptionnel_non_recurrent"|"a_verifier"
      source_used        str    – "boc"|"pdf"|"scraper"|"none"
      source_detail      str    – description lisible pour tooltip
      ecart_boc_pdf      float  – écart % BOC↔PDF (None si l'une manque)
      yield_for_calc     float  – rendement utilisé dans calculs
    """
    boc = float(boc_div) if (boc_div and boc_div > 0) else None
    pdf = float(pdf_div) if (pdf_div and pdf_div > 0) else None
    scr = float(scraper_div) if (scraper_div and scraper_div > 0) else None

    ecart_bp = _ecart(boc, pdf)

    # ── Sélection valeur + confiance ──────────────────────────────────────
    if boc is not None and pdf is not None:
        if ecart_bp > DIV_DIVERGENCE_HIGH:
            value, source_used, confidence = boc, "boc", "faible"
            detail = f"BOC={boc:.0f} XOF · PDF={pdf:.0f} XOF · écart {ecart_bp:.0f}% — BOC retenu"
            logger.warning(
                "[validation div] %s: BOC=%.1f vs PDF=%.1f — écart %.1f%% > %.0f%% "
                "→ BOC retenu, confiance faible",
                ticker, boc, pdf, ecart_bp, DIV_DIVERGENCE_HIGH,
            )
        elif ecart_bp > DIV_DIVERGENCE_MED:
            value, source_used, confidence = boc, "boc", "moyenne"
            detail = f"BOC={boc:.0f} XOF · PDF={pdf:.0f} XOF · écart {ecart_bp:.0f}%"
            logger.info("[validation div] %s: BOC/PDF écart %.1f%% → confiance moyenne", ticker, ecart_bp)
        else:
            value, source_used, confidence = boc, "boc", "haute"
            detail = f"BOC={boc:.0f} XOF · PDF={pdf:.0f} XOF · concordants"
    elif boc is not None:
        value, source_used, confidence = boc, "boc", "moyenne"
        detail = f"BOC={boc:.0f} XOF (PDF absent)"
    elif pdf is not None:
        value, source_used, confidence = pdf, "pdf", "faible"
        detail = f"PDF={pdf:.0f} XOF (BOC absent — à vérifier)"
        logger.info("[validation div] %s: PDF seul=%.1f, pas de BOC → confiance faible", ticker, pdf)
    elif scr is not None:
        value, source_used, confidence = scr, "scraper", "faible"
        detail = f"Historique={scr:.0f} XOF (source unique 2022-23, non recoupé)"
        logger.info("[validation div] %s: scraper fallback=%.1f, pas de BOC/PDF", ticker, scr)
    else:
        return dict(
            value=0, raw_value=0, confidence="inconnue",
            is_exceptional=False, flag="", source_used="none",
            source_detail="Aucune source disponible",
            ecart_boc_pdf=None, yield_for_calc=0,
        )

    raw_value = value
    price_f   = float(price) if price else 0.0
    yield_est = round(value / price_f * 100, 2) if price_f > 0 else 0.0
    is_exceptional = False
    flag = ""

    # ── Sanity checks ─────────────────────────────────────────────────────
    if yield_est > DIV_YIELD_HARD_CAP or (price_f > 0 and value > price_f * DIV_PRICE_RATIO_MAX):
        is_exceptional = True
        flag           = "exceptionnel_non_recurrent"
        confidence     = "exceptionnelle"
        detail        += f" · ⚠ rendement {yield_est:.1f}% — EXCEPTIONNEL non récurrent (exclu des calculs)"
        value          = 0.0
        yield_est      = 0.0
        logger.warning(
            "[validation div] %s: div=%.1f yield=%.2f%% → EXCEPTIONNEL — exclu calculs récurrents",
            ticker, raw_value, raw_value / price_f * 100 if price_f > 0 else 0,
        )
    elif confidence == "faible":
        flag = "a_verifier"

    return dict(
        value=value,
        raw_value=raw_value,
        confidence=confidence,
        is_exceptional=is_exceptional,
        flag=flag,
        source_used=source_used,
        source_detail=detail,
        ecart_boc_pdf=ecart_bp,
        yield_for_calc=yield_est,
    )


def run_full_audit(ranking_list, summary_dict, boc_dict, fundamentals_dict):
    """
    Passe les N tickers en revue et retourne un dict ticker → résultat de validation.
    Utilisé pour les rapports de diagnostic et pour enrichir live_ranking.json.
    """
    results = {}
    for r in ranking_list:
        t      = r.get("ticker", "")
        price  = r.get("price") or 0
        boc_e  = boc_dict.get(t, {})
        boc_d  = boc_e.get("div_net") if boc_e else None
        pdf_kpis = ((summary_dict.get(t) or {}).get("kpis") or {})
        pdf_raw  = (pdf_kpis.get("dividende_par_action") or {}).get("valeur")
        pdf_d    = float(pdf_raw) if (pdf_raw is not None and pdf_raw > 0) else None
        hist_d   = (fundamentals_dict.get(t) or {}).get("div_hist")
        results[t] = validate_dividend(t, hist_d, pdf_d, boc_d, price)
    return results
