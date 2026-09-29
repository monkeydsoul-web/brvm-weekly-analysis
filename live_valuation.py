"""
live_valuation.py — Recalcul du score /80 avec prix live brvm.org
Enveloppe valuation.py sans le modifier.
Injecte le prix live dans le row avant appel des 7 modèles + score technique.
"""

import logging
from datetime import datetime, timezone

from price_sanity import resolve_price, get_reference_prices
from verdict import (
    note10,
    conseil as conseil_verdict,
    libelle_conseil,
    couleur_conseil,
    normaliser_statut,
    STATUT_COTE,
    STATUT_NON_NOTE,
)
from valuation import (
    score_graham, score_dcf, score_ddm, score_epv,
    score_buffett, score_reverse_dcf, score_relative,
    GEO_RISK_PENALTY,
)

logger = logging.getLogger(__name__)

_score_cache = {}
_CACHE_TTL = 300

def _get_cached(ticker):
    import time
    entry = _score_cache.get(ticker)
    if entry and (time.time() - entry['ts']) < _CACHE_TTL:
        return entry['data']
    return None

def _set_cached(ticker, data):
    import time
    _score_cache[ticker] = {'ts': time.time(), 'data': data}


# ──────────────────────────────────────────────────────────────────────────────
# Score technique /10 — clôtures passées seulement (D-3 = B)
#
# Ne lit pas la séance : ni variation du jour, ni ouverture, ni volume du jour,
# ni top/flop. Deux composantes :
#   - tendance sur 20 à 30 clôtures (7 points)
#   - liquidité moyenne sur 20 séances (3 points)
# Repli si l'historique est trop court : milieu de la composante, signalé
# dans le détail (« historique insuffisant », « historique court »,
# « volumes insuffisants »). La variation annuelle BOC n'entre plus ici.
# ──────────────────────────────────────────────────────────────────────────────

TENDANCE_SEANCES_MAX = 30
TENDANCE_SEANCES_MIN = 20
TENDANCE_SEANCES_REPLI = 5
LIQUIDITE_SEANCES = 20
LIQUIDITE_SEANCES_REPLI = 5
# Milieu de chaque composante : ni récompense ni punition sans données.
TENDANCE_NEUTRE = 3.5
LIQUIDITE_NEUTRE = 1.5


def _nombre(valeur):
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    if valeur != valeur or valeur in (float("inf"), float("-inf")):
        return None
    return float(valeur)


def _cours_point(point):
    if not isinstance(point, dict):
        return None
    for cle in ("price", "close"):
        cours = _nombre(point.get(cle))
        if cours is not None and cours > 0:
            return cours
    return None


def _volume_point(point):
    """None si le volume n'est pas renseigné (distinct d'un volume à 0)."""
    if not isinstance(point, dict) or "volume" not in point:
        return None
    volume = _nombre(point.get("volume"))
    if volume is None or volume < 0:
        return None
    return volume


def _jour_iso(moment):
    if moment is None:
        moment = datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    else:
        moment = moment.astimezone(timezone.utc)
    return moment, moment.date().isoformat()


def serie_clotures(points, jour_exclu):
    """Clôtures complètes, une par date, hors séance `jour_exclu` et hors
    points annuels (source historical). `volume` vaut None s'il manque.
    """
    par_date = {}
    for point in points or []:
        if not isinstance(point, dict):
            continue
        if point.get("source") == "historical":
            continue
        date = point.get("date") or ""
        if not isinstance(date, str):
            continue
        date = date[:10]
        if len(date) != 10:
            continue
        if jour_exclu and date >= jour_exclu:
            continue
        cours = _cours_point(point)
        if cours is None:
            continue
        par_date[date] = {"date": date, "cours": cours, "volume": _volume_point(point)}
    return [par_date[date] for date in sorted(par_date)]


def _points_rendement(rendement):
    if rendement >= 15:
        return 7.0
    if rendement >= 8:
        return 5.5
    if rendement >= 3:
        return 4.5
    if rendement >= -3:
        return 3.5
    if rendement >= -8:
        return 2.0
    if rendement >= -15:
        return 1.0
    return 0.0


def _points_tendance(serie):
    n = len(serie)
    if n < TENDANCE_SEANCES_REPLI:
        return TENDANCE_NEUTRE, (
            "Tendance : historique insuffisant (%d clôtures, seuil %d) — neutre"
            % (n, TENDANCE_SEANCES_REPLI)
        )
    fenetre = min(TENDANCE_SEANCES_MAX, n)
    debut = serie[-fenetre]["cours"]
    fin = serie[-1]["cours"]
    if not debut:
        return TENDANCE_NEUTRE, "Tendance: cours de depart nul — neutre"
    rendement = (fin / debut - 1.0) * 100.0
    points = _points_rendement(rendement)
    texte = "Tendance %d séances %+.1f %%" % (fenetre, rendement)
    if n < TENDANCE_SEANCES_MIN:
        texte += " — historique court (seuil %d)" % TENDANCE_SEANCES_MIN
    return points, texte


def _points_liquidite(serie):
    fenetre = serie[-LIQUIDITE_SEANCES:]
    volumes = [point["volume"] for point in fenetre if point.get("volume") is not None]
    if len(volumes) < LIQUIDITE_SEANCES_REPLI:
        return LIQUIDITE_NEUTRE, (
            "Liquidité : volumes insuffisants (%d séances, seuil %d) — neutre"
            % (len(volumes), LIQUIDITE_SEANCES_REPLI)
        )
    moyenne = sum(volumes) / float(len(volumes))
    if moyenne > 10000:
        points, mot = 3.0, "liquide"
    elif moyenne > 1000:
        points, mot = 2.0, "correcte"
    elif moyenne > 0:
        points, mot = 1.0, "faible"
    else:
        points, mot = 0.0, "sans echange"
    return points, "Liquidité moyenne %d séances = %d — %s" % (
        len(volumes), int(round(moyenne)), mot,
    )


def _historique_ticker(row):
    """Liste de points. La clé présente (même vide) empêche la lecture disque."""
    if "historique_clotures" in row:
        return row.get("historique_clotures") or []
    ticker = row.get("ticker") or ""
    if not ticker:
        return []
    try:
        from price_history_builder import load_history
        historique = load_history()
    except Exception:
        return []
    if not isinstance(historique, dict):
        return []
    points = historique.get(ticker) or []
    return points if isinstance(points, list) else []


def score_technique_live(row: dict) -> dict:
    """Technique /10 sur les clôtures, pas sur la séance en cours.

    `_inclure_cloture_du_jour` (posé par le classement après 15h30 UTC) ajoute
    le cours du row comme dernière clôture. Le volume de ce cours n'est pas
    utilisé : la liquidité reste celle des séances déjà enregistrées.
    """
    jour = _jour_iso(row.get("_moment"))[1]
    serie = serie_clotures(_historique_ticker(row), jour)
    points_liq, texte_liq = _points_liquidite(serie)
    if row.get("_inclure_cloture_du_jour"):
        cours = _nombre(row.get("price"))
        if cours is not None and cours > 0:
            serie = list(serie)
            serie.append({"date": jour, "cours": cours, "volume": None})
    points_tendance, texte_tendance = _points_tendance(serie)
    score = min(10.0, max(0.0, points_tendance + points_liq))
    return {
        "score": round(score, 1),
        "label": "Technique",
        "details": texte_tendance + " | " + texte_liq,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Recalcul P/E et P/B live
# ──────────────────────────────────────────────────────────────────────────────
def _inject_live_price(base_row: dict, live_price: float, live_data: dict) -> dict:
    """
    Crée une copie du row fondamental avec le prix live injecté.
    Recalcule pe_ref et pb_ref si le prix change significativement.
    """
    row = dict(base_row)
    old_price = row.get("price") or live_price

    _t = row.get("ticker") or base_row.get("ticker")
    _refs = get_reference_prices().get(_t, {})
    _pr = resolve_price(live_price, _refs.get("hist"), boc_last=_refs.get("boc"))
    row["price"] = _pr["price"]
    row["price_source"] = _pr["source"]
    row["price_verified"] = _pr["verified"]
    row["change_pct"] = live_data.get("change_pct", 0)
    row["open"] = live_data.get("open")
    row["volume"]     = live_data.get("volume", 0)
    row["trend"]      = live_data.get("trend")

    # Recalcul P/E et P/B proportionnels au nouveau prix
    if old_price and old_price != live_price:
        ratio = live_price / old_price
        old_pe = row.get("pe_ref") or row.get("pe_hist")
        old_pb = row.get("pb_ref") or row.get("pb_hist")
        if old_pe and old_pe < 990:
            row["pe_ref"] = round(old_pe * ratio, 2)
        if old_pb and old_pb < 990:
            row["pb_ref"] = round(old_pb * ratio, 2)

        # Recalcul div_yield
        old_div_yield = row.get("div_yield") or 0
        if old_div_yield and old_price:
            div_per_share = old_div_yield / 100 * old_price
            row["div_yield"] = round(div_per_share / live_price * 100, 2)
            row["div_per_share"] = div_per_share

    return row


# ──────────────────────────────────────────────────────────────────────────────
# Point d'entrée principal
# ──────────────────────────────────────────────────────────────────────────────
def compute_live_score(ticker: str, base_fundamentals: dict, live_cache: dict) -> dict:
    """
    Calcule le score /80 live pour un ticker.

    Args:
        ticker: ex. "SGBCI"
        base_fundamentals: row fondamental depuis scraper.py (STOCK_FUNDAMENTALS[ticker])
        live_cache: résultat de live_data.get_live_data() — contient ["prices"][ticker]

    Returns:
        dict avec tous les scores + métadonnées live
    """
    # Cache désactivé — score vient de live_ranker.py
    pass
    prices = live_cache.get("prices", {})
    live_data_ticker = prices.get(ticker, {})
    live_price = live_data_ticker.get("price")

    # Si pas de prix live, on utilise le prix fondamental
    if not live_price:
        live_price = base_fundamentals.get("price")
        live_data_ticker = {}
        live_source = "static"
    else:
        live_source = live_data_ticker.get("source", "live")

    if not live_price:
        return {
            "ticker": ticker,
            "error": "Prix indisponible",
            "composite_adj": 0,
            "live_price": None,
            "live_source": "unavailable",
        }

    # Injection du prix live dans le row
    row = _inject_live_price(base_fundamentals, live_price, live_data_ticker)

    # Calcul des 7 modèles fondamentaux
    g   = score_graham(row)
    dcf = score_dcf(row)
    ddm = score_ddm(row)
    epv = score_epv(row)
    buf = score_buffett(row)
    rev = score_reverse_dcf(row)
    rel = score_relative(row)
    tec = score_technique_live(row)

    # Pénalité géopolitique
    geo_penalty = GEO_RISK_PENALTY.get(base_fundamentals.get("country", ""), 0)

    # Score composite /70 fondamental
    composite_raw = (
        g["score"] + dcf["score"] + ddm["score"] + epv["score"]
        + buf["score"] + rev["score"] + rel["score"]
    )
    composite_adj_70 = max(0, composite_raw + geo_penalty * 7 / 10)

    # Score total /80 avec technique
    composite_adj_80 = round(min(80, composite_adj_70 + tec["score"]), 1)

    # Meme regle que live_ranker, sans amortisseur (ce chemin n'a pas de precedent).
    _statut = normaliser_statut(base_fundamentals.get("statut"))
    if not _statut:
        _statut = STATUT_COTE if live_price else STATUT_NON_NOTE
    _note = note10(composite_adj_80)
    if live_price and _statut == STATUT_COTE:
        _avis = conseil_verdict(composite_adj_80, None, _statut)
    else:
        _avis = None

    result = {
        "ticker":           ticker,
        "live_price":       live_price,
        "live_change_pct":  live_data_ticker.get("change_pct", 0),
        "live_source":      live_source,
        "live_updated_at":  live_data_ticker.get("fetched_at"),
        "market_open":      live_cache.get("market_open", False),
        # Scores individuels
        "score_graham":     g["score"],
        "score_dcf":        dcf["score"],
        "score_ddm":        ddm["score"],
        "score_epv":        epv["score"],
        "score_buffett":    buf["score"],
        "score_rev_dcf":    rev["score"],
        "score_relatif":    rel["score"],
        "score_technique":  tec["score"],
        # Détails
        "detail_graham":    g["details"],
        "detail_dcf":       dcf["details"],
        "detail_ddm":       ddm["details"],
        "detail_epv":       epv["details"],
        "detail_buffett":   buf["details"],
        "detail_rev_dcf":   rev["details"],
        "detail_relatif":   rel["details"],
        "detail_technique": tec["details"],
        # Composite
        "geo_penalty":      geo_penalty,
        "composite_raw":    round(composite_raw, 1),
        "composite_adj":    composite_adj_80,
        "note10":           _note,
        "conseil":          _avis,
        "conseil_libelle":  libelle_conseil(_avis) if _avis else None,
        "conseil_couleur":  couleur_conseil(_avis),
        "statut":           _statut,
        "note_calculee_le": datetime.now(timezone.utc).isoformat(),
        "pe_ref_live":      row.get("pe_ref") or row.get("pe_hist") or row.get("pe_hist"),
        "pb_ref_live":      row.get("pb_ref") or row.get("pb_hist") or row.get("pb_hist"),
        "div_yield_live":   row.get("div_yield"),
    }
    return result


def compute_all_live_scores(base_fundamentals_dict: dict, live_cache: dict) -> list:
    """
    Recalcule les scores live pour tous les tickers.

    Args:
        base_fundamentals_dict: {ticker: row_dict} depuis STOCK_FUNDAMENTALS
        live_cache: résultat de get_live_data()

    Returns:
        liste de dicts triée par composite_adj décroissant
    """
    results = []
    for ticker, row in base_fundamentals_dict.items():
        try:
            result = compute_live_score(ticker, row, live_cache)
            results.append(result)
        except Exception as e:
            logger.warning(f"Erreur score live {ticker}: {e}")
            results.append({"ticker": ticker, "composite_adj": 0, "error": str(e), "conseil": None})

    results.sort(key=lambda x: x.get("composite_adj", 0), reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    return results
