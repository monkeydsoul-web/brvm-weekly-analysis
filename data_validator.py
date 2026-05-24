"""
data_validator.py — Validation multi-source des données financières BRVM.

Priorité sources (dividende par action) :
  1. BOC (brvm.org/BOC)            ← référence officielle
  2. PDF IA (analyses_summary.json) ← cross-check
  3. scraper.py div_hist            ← fallback historique, exclu scoring confiance
  4. african-markets.com            ← 3e source externe, confirmateur de tendance

Règles BOC↔PDF :
  écart ≤ 10%  → HAUTE   (concordance multi-source)
  écart 10-30% → MOYENNE (divergence modérée)
  écart > 30%  → FAIBLE  (BOC retenu, PDF suspect)
  source unique→ MOYENNE (non recoupé)
  sans BOC ni PDF → FAIBLE

Règles AM (african-markets) — APRÈS sélection BOC/PDF :
  1. Détection split  : ratio AM/valeur ≈ 2, 3, 4, 0.5, 1/3, 0.25 (±15%)
     → PAS de pénalité, note "split probable" en tooltip
  2. AM confirme (écart <20%, pas split)    : moyenne→haute, faible→moyenne
  3. AM diverge  (écart >30%, pas split, délai ≤12 mois) : haute→moyenne, moyenne→faible
  4. AM diverge  (délai >12 mois ou split) : NE PAS pénaliser (décalage exercice)
  5. AM > BOC * 1.30 sans split            : flag "BOC à vérifier (net vs brut ?)"

Sanity checks :
  div_yield > 15%          → exceptionnel / non récurrent
  div_per_share > 50% prix → exceptionnel / non récurrent
"""
import re
import logging

logger = logging.getLogger(__name__)

DIV_YIELD_HARD_CAP   = 15.0
DIV_PRICE_RATIO_MAX  = 0.50
DIV_DIVERGENCE_HIGH  = 30.0
DIV_DIVERGENCE_MED   = 10.0

_SPLIT_RATIOS    = [2.0, 3.0, 4.0, 5.0, 0.5, 1/3, 0.25, 0.2]
_SPLIT_TOLERANCE = 0.15   # ±15 %
_MOIS_FR = {
    "jan": 1, "fev": 2, "fév": 2, "mar": 3, "avr": 4, "mai": 5,
    "juin": 6, "jul": 7, "juil": 7, "aou": 8, "aoû": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12, "déc": 12,
}


# ── Helpers internes ────────────────────────────────────────────────────────

def _ecart(a, b):
    if a is None or b is None:
        return None
    m = max(abs(a), abs(b))
    return 0.0 if m == 0 else abs(a - b) / m * 100


def _parse_month_year(date_str):
    """(month_int|None, year_int|None) depuis une chaîne de date française."""
    if not date_str:
        return None, None
    s = date_str.lower()
    # Année 4 chiffres
    m4 = re.search(r"\b(20\d{2})\b", s)
    if m4:
        year = int(m4.group(1))
    else:
        # Année 2 chiffres en fin de chaîne : "11-juil.-25", "23-avr.-26"
        m2 = re.search(r"[-\s](\d{2})\s*$", s.strip())
        year = (2000 + int(m2.group(1))) if m2 else None

    month = None
    # Longest-match first pour éviter "mai" dans "mais"
    for abbr in sorted(_MOIS_FR, key=len, reverse=True):
        if abbr in s:
            month = _MOIS_FR[abbr]
            break
    return month, year


def _months_between(am_date_str, boc_date_str):
    """
    Écart en mois entre la date de paiement AM et la date BOC.
    Positif = BOC est plus récent. None si l'une des dates est non parsable.
    """
    am_m,  am_y  = _parse_month_year(am_date_str)
    boc_m, boc_y = _parse_month_year(boc_date_str)
    if am_y is None or boc_y is None:
        return None
    return (boc_y * 12 + (boc_m or 6)) - (am_y * 12 + (am_m or 6))


def _detect_split(am_val, ref_val):
    """
    Retourne (is_split: bool, description: str|None).
    Split détecté si am/ref ≈ ratio entier connu (±15 %).
    """
    if not am_val or not ref_val or ref_val == 0:
        return False, None
    ratio = am_val / ref_val
    for r in _SPLIT_RATIOS:
        if r > 0 and abs(ratio - r) / r <= _SPLIT_TOLERANCE:
            if ratio > 1.05:
                label = f"split ~{r:.0f}:1" if r >= 1.5 else f"split ~{ratio:.1f}:1"
                return True, f"{label} probable (AM pré-split)"
            else:
                inv = round(1 / ratio)
                return True, f"regroupement ~{inv}:1 probable (AM post-split)"
    return False, None


# ── Validation principale ───────────────────────────────────────────────────

def validate_dividend(
    ticker, scraper_div, pdf_div, boc_div, price,
    am_div=None, am_date=None, boc_date=None,
):
    """
    Valide et arbitre div_per_share depuis BOC / PDF / scraper / african-markets.

    Retourne un dict :
      value              float  – valeur pour CALCULS (0 si exceptionnel)
      raw_value          float  – valeur brute originale (affichage fiche)
      confidence         str    – "haute"|"moyenne"|"faible"|"exceptionnelle"|"inconnue"
      is_exceptional     bool
      flag               str    – ""|"exceptionnel_non_recurrent"|"a_verifier"
      source_used        str    – "boc"|"pdf"|"scraper"|"none"
      source_detail      str    – description lisible pour tooltip
      ecart_boc_pdf      float|None
      yield_for_calc     float
      am_div_raw         float|None  – valeur brute african-markets
      am_paid_date       str|None    – date de paiement AM
      am_split_flag      bool        – split d'actions probable
      am_net_brut_flag   bool        – BOC probablement net vs brut AM
    """
    boc = float(boc_div) if (boc_div and boc_div > 0) else None
    pdf = float(pdf_div) if (pdf_div and pdf_div > 0) else None
    scr = float(scraper_div) if (scraper_div and scraper_div > 0) else None
    am  = float(am_div)  if (am_div  and am_div  > 0) else None

    ecart_bp = _ecart(boc, pdf)

    # ── 1. Sélection valeur + confiance (BOC / PDF / scraper) ──────────────
    if boc is not None and pdf is not None:
        if ecart_bp > DIV_DIVERGENCE_HIGH:
            value, source_used, confidence = boc, "boc", "faible"
            detail = f"BOC={boc:.0f} XOF · PDF={pdf:.0f} XOF · écart {ecart_bp:.0f}% — BOC retenu"
            logger.warning(
                "[validation div] %s: BOC=%.1f vs PDF=%.1f — écart %.1f%% > %.0f%%"
                " → BOC retenu, confiance faible",
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
            am_div_raw=None, am_paid_date=None,
            am_split_flag=False, am_net_brut_flag=False,
        )

    # ── 2. Intégration african-markets (3e source) ─────────────────────────
    am_split_flag    = False
    am_net_brut_flag = False

    if am is not None and value > 0:
        is_split, split_desc = _detect_split(am, value)
        gap_months = _months_between(am_date, boc_date)  # None si non parsable
        large_gap  = gap_months is not None and gap_months > 12
        ecart_am   = abs(am - value) / max(am, value) * 100

        am_date_label = am_date or "?"
        am_tag = f"AM={am:.0f} XOF ({am_date_label})"

        if is_split:
            am_split_flag = True
            detail += f" · {am_tag} · {split_desc}"
            # Pas de modification de confiance sur un split
        elif large_gap:
            # Décalage d'exercice légitime — ne pas pénaliser
            detail += f" · {am_tag} écart {ecart_am:.0f}% ({gap_months}m)"
            if ecart_am < 20:
                # Tendance confirmée malgré l'écart de date
                if confidence == "moyenne":
                    confidence = "haute"
                    detail += " · tendance confirmée (source externe)"
                elif confidence == "faible":
                    confidence = "moyenne"
                    detail += " · tendance confirmée (source externe)"
        else:
            # Même exercice ou écart < 12 mois → comparaison directe
            detail += f" · {am_tag} écart {ecart_am:.0f}%"
            if ecart_am < 20:
                if confidence == "moyenne":
                    confidence = "haute"
                    detail += " · confirmé 3 sources"
                elif confidence == "faible":
                    confidence = "moyenne"
                    detail += " · confirmé 3 sources"
            elif ecart_am > 30:
                # AM diverge : protections levées (pas split, pas large_gap)
                if confidence == "haute":
                    confidence = "moyenne"
                    detail += " · divergence source externe"
                elif confidence == "moyenne" and source_used == "pdf":
                    # Ne baisser que si source de base est déjà fragile
                    confidence = "faible"
                    detail += " · divergence source externe"

        # Signal net vs brut (AM sensiblement plus haut que BOC)
        if not is_split and am > value * 1.30:
            am_net_brut_flag = True
            ratio_pct = round((am / value - 1) * 100)
            detail += f" · ⚠ AM dépasse BOC de {ratio_pct}% — BOC pourrait afficher le net (IRVM)"
            logger.info(
                "[validation div] %s: AM=%.0f > BOC=%.0f de %d%% → flag net/brut",
                ticker, am, value, ratio_pct,
            )

    # ── 3. Sanity checks (exceptionnel) ────────────────────────────────────
    raw_value = value
    price_f   = float(price) if price else 0.0
    yield_est = round(value / price_f * 100, 2) if price_f > 0 else 0.0
    is_exceptional = False
    flag = ""

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
        am_div_raw=am,
        am_paid_date=am_date,
        am_split_flag=am_split_flag,
        am_net_brut_flag=am_net_brut_flag,
    )


def run_full_audit(ranking_list, summary_dict, boc_dict, fundamentals_dict,
                   am_cache=None):
    """
    Passe les N tickers en revue et retourne un dict ticker → résultat de validation.
    am_cache : dict issu de external_source.get_cached_dividends() (optionnel).
    """
    am_cache = am_cache or {}
    results  = {}
    for r in ranking_list:
        t       = r.get("ticker", "")
        price   = r.get("price") or 0
        boc_e   = boc_dict.get(t, {})
        boc_d   = boc_e.get("div_net") if boc_e else None
        boc_dt  = boc_e.get("div_date") if boc_e else None
        pdf_kpis = ((summary_dict.get(t) or {}).get("kpis") or {})
        pdf_raw  = (pdf_kpis.get("dividende_par_action") or {}).get("valeur")
        pdf_d    = float(pdf_raw) if (pdf_raw is not None and pdf_raw > 0) else None
        hist_d   = (fundamentals_dict.get(t) or {}).get("div_hist")
        am_e     = am_cache.get(t, {})
        am_d     = am_e.get("amount")
        am_dt    = am_e.get("paid_date")
        results[t] = validate_dividend(
            t, hist_d, pdf_d, boc_d, price,
            am_div=am_d, am_date=am_dt, boc_date=boc_dt,
        )
    return results
