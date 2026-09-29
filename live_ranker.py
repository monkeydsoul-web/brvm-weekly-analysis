"""
live_ranker.py — Reclassement automatique des 47 sociétés BRVM
Recalcule les 8 modèles dès qu'un prix change ou qu'un rapport est analysé.
Cache : data/live_ranking.json (mis à jour à chaque déclenchement)
"""

import os
import json
import hashlib
import logging
import time
import threading
import tempfile
import unicodedata
from datetime import datetime, timezone
from copy import deepcopy
from price_sanity import resolve_price, get_reference_prices

logger = logging.getLogger(__name__)

from paths import DATA_DIR
from verdict import (
    note10,
    conseil as conseil_verdict,
    libelle_conseil,
    couleur_conseil,
    normaliser_statut,
    STATUT_COTE,
    STATUT_NON_NOTE,
)
RANKING_PATH  = os.path.join(DATA_DIR, "live_ranking.json")
HISTORY_PATH  = os.path.join(DATA_DIR, "ranking_history.json")

# Verrou pour éviter les recalculs simultanés
_lock = threading.Lock()
_cache_lock = threading.Lock()
_last_ranking = None          # Cache en mémoire
_last_stamp = None            # (inode, mtime_ns, taille) du fichier mis en cache
_last_updated_at = None       # updated_at du fichier mis en cache
_last_prices  = {}            # Derniers prix connus (pour détecter les changements)

def _save_json_atomic(path, data):
    """Ecriture atomique d un JSON : temporaire dans le meme repertoire, fsync, os.replace."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=os.path.dirname(path), delete=False)
    tmp_path = tmp.name
    try:
        with tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


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


USD_XOF = 575.0  # Taux USD→XOF approx. au 2026-07-13 (FCFA arrimé EUR ; à rafraîchir au rituel macro trimestriel)

def _convert_pdf_div(ticker, value, unite):
    """Convertit un dividende PDF selon son unité déclarée (analyses_summary.json).
    None si unité inconnue — traité comme donnée absente en aval."""
    if value is None:
        return None
    u = (unite or "").strip().upper()
    if u in ("", "FCFA", "XOF"):
        return value
    if u == "USD":
        return value * USD_XOF
    logger.warning("dividende %s: unité inconnue '%s' — valeur ignorée", ticker, unite)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Construction du row fondamental enrichi
# ─────────────────────────────────────────────────────────────────────────────

# Bande rapport/BOC, fermée. En dehors, le chiffre du rapport est écarté et
# le BOC est retenu. 0,80–1,25 (et non plus 0,70–1,43) : les ratios ~1,3–1,4
# de PALC, SLBC, SOGC et NSBC viennent d'un nombre d'actions faux dans
# STOCK_FUNDAMENTALS. On garde le BOC jusqu'au PR qui corrige ces nombres.
_BANDE_BAS = 0.8
_BANDE_HAUT = 1.25
# Seuls ces documents publiés, en millions de FCFA, donnent un BNA ou un BVPA.
_DOCS_COMPTABLES = frozenset(("etats financiers", "rapport annuel"))


def _flottant_positif(valeur):
    """Nombre > 0, ou None. Les booléens et les textes non numériques sont ignorés."""
    if isinstance(valeur, bool):
        return None
    if isinstance(valeur, (int, float)):
        nombre = float(valeur)
    elif isinstance(valeur, str):
        texte = valeur.strip().replace(" ", "").replace(",", ".")
        if not texte:
            return None
        try:
            nombre = float(texte)
        except ValueError:
            return None
    else:
        return None
    if nombre != nombre or nombre <= 0 or nombre == float("inf"):
        return None
    return nombre


def _pli(texte):
    """Minuscules, sans accent, espaces simples. Pour comparer un type de document."""
    if not isinstance(texte, str):
        return ""
    decompose = unicodedata.normalize("NFD", texte)
    sans = "".join(c for c in decompose if not unicodedata.combining(c))
    return " ".join(sans.lower().split())


def _doc_comptable(pdf_analysis):
    """Vrai pour un état financier ou un rapport annuel, pas un trimestriel ni une note enrichie."""
    if not isinstance(pdf_analysis, dict) or pdf_analysis.get("status") != "ok":
        return False
    brut = pdf_analysis.get("doc_type") or pdf_analysis.get("type")
    return _pli(brut) in _DOCS_COMPTABLES


def _bloc_kpi(pdf_analysis, key):
    if not isinstance(pdf_analysis, dict):
        return {}
    kpis = pdf_analysis.get("kpis") or {}
    if not isinstance(kpis, dict):
        return {}
    bloc = kpis.get(key) or {}
    if not isinstance(bloc, dict):
        return {}
    return bloc


def _kpi_pdf(pdf_analysis, key):
    """Valeur d'un KPI, ou None si le rapport n'est pas un document comptable en MFCFA."""
    if not _doc_comptable(pdf_analysis):
        return None
    bloc = _bloc_kpi(pdf_analysis, key)
    unite = bloc.get("unite")
    if not isinstance(unite, str) or unite.strip() != "MFCFA":
        return None
    return _flottant_positif(bloc.get("valeur"))


def _exercice_rapport(pdf_analysis):
    """Année de l'exercice (`annee`), pas l'année de publication (`year`)."""
    if not isinstance(pdf_analysis, dict):
        return None
    return pdf_analysis.get("annee") or pdf_analysis.get("year")


def _ratio(valeur_rapport, valeur_boc):
    if not valeur_rapport or not valeur_boc:
        return None
    return float(valeur_rapport) / float(valeur_boc)


def _hors_bande(ratio):
    """Vrai si le rapport et le BOC sont trop éloignés (bande fermée [0,8 ; 1,25])."""
    if ratio is None:
        return False
    return ratio < _BANDE_BAS or ratio > _BANDE_HAUT


def _annee_entiere(valeur):
    """Année civile plausible, ou None. Le cours et les pourcentages ne comptent pas."""
    if isinstance(valeur, bool):
        return None
    if isinstance(valeur, int):
        annee = valeur
    elif isinstance(valeur, float) and valeur == int(valeur):
        annee = int(valeur)
    elif isinstance(valeur, str) and valeur.strip().isdigit():
        annee = int(valeur.strip())
    else:
        return None
    if 1990 <= annee <= 2100:
        return annee
    return None


def _annee_du_rapport(pdf_analysis):
    """Exercice du document analysé : `annee`, sinon `year` s'il n'y a pas d'annee."""
    if not isinstance(pdf_analysis, dict):
        return None
    annee = _annee_entiere(pdf_analysis.get("annee"))
    if annee is None:
        annee = _annee_entiere(pdf_analysis.get("year"))
    return annee


def _plancher_exercice(moment):
    """Plus petit exercice encore accepté.

    Les catalogues de rapports portent l'année de publication (souvent 2026
    pour un exercice 2025) : on ne les compare pas à `annee`.

    À partir du 1er juillet, l'exercice doit être au moins l'année précédente.
    Avant cette date, les états de N-1 ne sont pas tous sortis : on accepte
    encore N-2. Le 29 septembre 2026, 2024 et avant sont écartés
    (BOAC 2024, CFAC 2023, UNLC 2023, SEMC 2023). 2025 reste.
    """
    if moment is None:
        moment = datetime.now(timezone.utc)
    else:
        moment = _moment_utc(moment)
    if moment.month < 7:
        return moment.year - 2
    return moment.year - 1


def _rapport_perime(pdf_analysis, ticker="", moment=None):
    """Vrai si l'exercice comptable est trop ancien pour servir de BNA.

    Seul un état financier ou un rapport annuel est concerné. Une note
    enrichie n'a souvent pas d'`annee` : son `year` est une année de
    publication, et s'en servir ici écartait le BVPA de la plupart des
    sociétés. Le BVPA, lui, reste lu plus bas.
    """
    if not _doc_comptable(pdf_analysis):
        return False
    annee = _annee_du_rapport(pdf_analysis)
    if annee is None:
        return False
    plancher = _plancher_exercice(moment)
    if annee >= plancher:
        return False
    logger.warning(
        "BNA %s : exercice %s antérieur à %s — BNA du rapport ignoré",
        ticker, annee, plancher,
    )
    return True


def _nb_actions(row):
    if not isinstance(row, dict):
        return None
    for cle in ("shares", "shares_outstanding", "nb_actions"):
        nombre = _flottant_positif(row.get(cle))
        if nombre is not None:
            return nombre
    return None


def _bna_depuis_rapport(pdf_analysis, nb_actions):
    """BNA du rapport : résultat net (MFCFA) / nombre d'actions. Avec l'exercice.

    Un autre type de document, ou une unité qui n'est pas MFCFA, est traité
    comme un rapport absent.
    """
    rn = _kpi_pdf(pdf_analysis, "resultat_net")
    if rn is None or not nb_actions:
        return None, None
    eps = rn * 1000000.0 / nb_actions
    if eps <= 0:
        return None, None
    return round(eps, 0), _exercice_rapport(pdf_analysis)


def _bna_depuis_boc(cours_clot, per_boc):
    """BNA du BOC : cours de clôture du jour du BOC / PER du même BOC.

    Jamais le cours de la séance. Le PER hors ]0, 500[ est ignoré, comme avant.
    """
    cours = _flottant_positif(cours_clot)
    per = _flottant_positif(per_boc)
    if cours is None or per is None or per >= 500:
        return None
    bna = round(cours / per, 1)
    if bna <= 0:
        return None
    return bna


def _bna_statique(base_row):
    """BNA déjà porté par les fondamentaux. `eps_est` est ignoré : il vaut cours / PE."""
    if not isinstance(base_row, dict):
        return None
    for cle in ("bna", "eps"):
        valeur = _flottant_positif(base_row.get(cle))
        if valeur is not None:
            return valeur
    return None


def _choisir_bna(bna_rapport, annee, bna_boc, date_boc, bna_statique):
    """Priorité rapport > BOC > statique.

    Retourne (bna, source, exercice, date, ecart, alerter).
    `ecart` est le ratio rapport/BOC arrondi, quand les deux existent.
    Si ce ratio sort de [0,8 ; 1,25], le BOC est retenu et `alerter` est vrai.
    Sans aucune source, le BNA est absent (None), pas inventé depuis le cours.
    """
    ecart_brut = _ratio(bna_rapport, bna_boc)
    ecart = None if ecart_brut is None else round(ecart_brut, 2)
    if bna_rapport is not None and bna_rapport > 0 and not _hors_bande(ecart_brut):
        return bna_rapport, "rapport", annee, None, ecart, False
    if bna_boc is not None and bna_boc > 0:
        alerter = _hors_bande(ecart_brut)
        return bna_boc, "boc", None, date_boc or None, ecart, alerter
    if bna_statique is not None and bna_statique > 0:
        return bna_statique, "statique", None, None, None, False
    return None, None, None, None, None, False


def _bvpa_depuis_rapport(pdf_analysis, nb_actions):
    """BVPA du rapport : capitaux propres (MFCFA) / nombre d'actions.

    Même filtre que le BNA : états financiers ou rapport annuel, unité MFCFA.
    """
    cap = _kpi_pdf(pdf_analysis, "capitaux_propres")
    if cap is None or not nb_actions:
        return None
    vcp = cap * 1000000.0 / nb_actions
    if vcp <= 0:
        return None
    return round(vcp, 1)


def _bvpa_depuis_boc(cours_clot, pb_boc, bvpa_explicite):
    """BVPA du BOC seulement s'il est déjà dans le bulletin.

    Soit un BVPA explicite, soit cours de clôture du jour BOC / P/B du même
    BOC. Jamais le cours de la séance. Sans ces champs, il n'y a pas de BVPA BOC.
    """
    explicite = _flottant_positif(bvpa_explicite)
    if explicite is not None:
        return explicite
    cours = _flottant_positif(cours_clot)
    pb = _flottant_positif(pb_boc)
    if cours is None or pb is None or pb >= 500:
        return None
    valeur = round(cours / pb, 1)
    if valeur <= 0:
        return None
    return valeur


def _bvpa_statique(base_row):
    """BVPA déjà porté par les fondamentaux. Jamais cours / P/B."""
    if not isinstance(base_row, dict):
        return None
    return _flottant_positif(base_row.get("bvpa"))


def _bvpa_depuis_capitaux(pdf_analysis, nb_actions):
    """Capitaux propres en MFCFA / actions, sans regarder le type de document."""
    if not isinstance(pdf_analysis, dict) or pdf_analysis.get("status") != "ok":
        return None
    bloc = _bloc_kpi(pdf_analysis, "capitaux_propres")
    unite = bloc.get("unite")
    if not isinstance(unite, str) or unite.strip() != "MFCFA":
        return None
    cap = _flottant_positif(bloc.get("valeur"))
    if cap is None or not nb_actions:
        return None
    valeur = round(cap * 1000000.0 / nb_actions, 1)
    if valeur <= 0:
        return None
    return valeur


def _bvpa_estime(pdf_analysis, nb_actions):
    """BVPA d'un document qui n'est pas un état financier à jour.

    Unité MFCFA. On ne s'en sert que s'il n'y a pas de BVPA comptable
    encore valable : note enrichie, ou état financier trop ancien.
    Source affichée : « estime ».
    """
    if _doc_comptable(pdf_analysis):
        return None
    return _bvpa_depuis_capitaux(pdf_analysis, nb_actions)


def _choisir_bvpa(bvpa_rapport, bvpa_boc, bvpa_estime, bvpa_statique):
    """Rapport comptable à jour, puis BOC s'il existe, puis estimation, puis statique.

    La bande rapport/BOC ne s'applique que lorsqu'un BVPA BOC existe.
    Un document non comptable, ou un état financier trop ancien, donne un
    BVPA « estime » à partir des capitaux propres en MFCFA, avant le statique.
    Retourne (bvpa, source, alerter).
    """
    ecart_brut = _ratio(bvpa_rapport, bvpa_boc)
    if bvpa_rapport is not None and bvpa_rapport > 0 and not _hors_bande(ecart_brut):
        return bvpa_rapport, "rapport", False
    if bvpa_boc is not None and bvpa_boc > 0:
        return bvpa_boc, "boc", _hors_bande(ecart_brut)
    if bvpa_estime is not None and bvpa_estime > 0:
        return bvpa_estime, "estime", False
    if bvpa_statique is not None and bvpa_statique > 0:
        return bvpa_statique, "statique", False
    return None, None, False


def _appliquer_bna_bvpa(row, base_row, pdf_analysis, ticker="", moment=None):
    """Fige BNA et BVPA, puis P/E et P/B = cours actuel / ces chiffres."""
    nb = _nb_actions(row)
    # L'exercice trop ancien retire le BNA du rapport, pas les capitaux propres.
    perime = _rapport_perime(pdf_analysis, ticker, moment)
    pdf_bna = None if perime else pdf_analysis
    bna_rapport, annee = _bna_depuis_rapport(pdf_bna, nb)
    bna_boc = _bna_depuis_boc(row.get("_boc_cours"), row.get("_boc_per"))
    bna, source, exercice, date_boc, ecart, alerter_bna = _choisir_bna(
        bna_rapport,
        annee,
        bna_boc,
        row.get("_boc_date"),
        _bna_statique(base_row),
    )
    if alerter_bna:
        logger.warning(
            "BNA %s : rapport/BOC = %s hors [%.2f, %.2f] — le BOC est retenu",
            ticker, ecart, _BANDE_BAS, _BANDE_HAUT,
        )
    row["bna"] = bna
    row["eps"] = bna
    row["bna_source"] = source
    row["bna_exercice"] = exercice
    row["bna_date"] = date_boc
    row["bna_ecart_boc"] = ecart

    bvpa_boc = _bvpa_depuis_boc(
        row.get("_boc_cours"), row.get("_boc_pb"), row.get("_boc_bvpa"),
    )
    if perime:
        bvpa_rapport = None
        bvpa_estime = _bvpa_depuis_capitaux(pdf_analysis, nb)
    else:
        bvpa_rapport = _bvpa_depuis_rapport(pdf_analysis, nb)
        bvpa_estime = _bvpa_estime(pdf_analysis, nb)
    bvpa, bvpa_source, alerter_bvpa = _choisir_bvpa(
        bvpa_rapport,
        bvpa_boc,
        bvpa_estime,
        _bvpa_statique(base_row),
    )
    if alerter_bvpa:
        logger.warning(
            "BVPA %s : rapport/BOC hors [%.2f, %.2f] — le BOC est retenu",
            ticker, _BANDE_BAS, _BANDE_HAUT,
        )
    row["bvpa"] = bvpa
    row["bvpa_source"] = bvpa_source

    prix = _flottant_positif(row.get("price"))
    if bna and prix:
        row["pe_ref"] = round(prix / bna, 2)
    else:
        row.pop("pe_ref", None)
    if bvpa and prix:
        row["pb_ref"] = round(prix / bvpa, 2)
    else:
        row.pop("pb_ref", None)
    return row


def _build_enriched_row(ticker, base_row, live_price_data, pdf_analysis, boc_snapshot=None, moment=None):
    """
    Fusionne les 3 sources de données pour un ticker :
    1. Fondamentaux statiques (scraper.py)
    2. Prix live (live_data.py)
    3. KPIs extraits des PDF (bulk_analyzer.py)
    """
    row = dict(base_row)

    # ── Prix live ──────────────────────────────────────────────────────────
    live_price = live_price_data.get("price")
    _refs = get_reference_prices().get(ticker, {})
    _pr = resolve_price(live_price, _refs.get("hist"), boc_last=_refs.get("boc"))
    row["price"] = _pr["price"]
    row["price_source"] = _pr["source"]
    row["price_verified"] = _pr["verified"]
    if live_price and live_price > 0:
        old_price = row.get("price") or live_price
        row["change_pct"] = live_price_data.get("change_pct", 0)
        row["open"] = live_price_data.get("open")
        row["volume"]     = live_price_data.get("volume", 0)
        row["trend"]      = live_price_data.get("trend")

        # Le P/E et le P/B sont posés à la fin : cours actuel / BNA figé,
        # cours actuel / BVPA figé. Le cours ne recalcule pas le bénéfice.

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
        # Le classement passe le fichier déjà lu après l'empreinte.
        # Sans ce cliché, on relirait boc_data.json au milieu du calcul.
        if boc_snapshot is None:
            from boc_scraper import get_boc_price_history
            _boc = get_boc_price_history()
        else:
            _boc = boc_snapshot
        boc_entry = _boc.get(ticker, {}) if isinstance(_boc, dict) else {}
        if boc_entry:
            per_boc = boc_entry.get('per_boc')
            if per_boc and 0 < float(per_boc) < 500:
                row['pe_hist'] = float(per_boc)
            if boc_entry.get('var_annee') is not None:
                row['var_annee'] = boc_entry['var_annee']
            if boc_entry.get('div_date'):
                row['ex_div_date'] = boc_entry['div_date']
            row['_boc_per']      = per_boc
            row['_boc_div']      = boc_entry.get('div_net') or 0
            row['_boc_div_date'] = boc_entry.get('div_date', '')
            row['_boc_cours']    = boc_entry.get('cours_clot')
            row['_boc_date']     = boc_entry.get('date')
            row['_boc_pb']       = boc_entry.get('pb_boc')
            row['_boc_bvpa']     = boc_entry.get('bvpa')
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
    div_pdf = None  # initialisé avant le bloc pour la référence BOC plus bas
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
        # div_pdf=0 signifie "pas de dividende récurrent" (ex: HAO exceptionnel) → efface la valeur
        div_pdf = kv("dividende_par_action")
        div_unite = (kpis.get("dividende_par_action") or {}).get("unite")
        div_pdf = _convert_pdf_div(ticker, div_pdf, div_unite)
        if div_pdf is not None:
            if div_pdf > 0:
                row["div_per_share"] = div_pdf
                if price > 0:
                    row["div_yield"] = round(div_pdf / price * 100, 2)
            else:
                # Valeur explicitement nulle = dividende non récurrent ou non vérifié
                row["div_per_share"] = 0
                row["div_yield"]     = 0.0

        # Le BNA (résultat net / actions) et le BVPA (capitaux propres / actions)
        # sont figés plus bas. Ils ne dépendent pas du cours.
        ca_pdf = kv("chiffre_affaires")  # en MFCFA
        nb_actions = row.get("shares") or row.get("shares_outstanding") or row.get("nb_actions")

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
    boc_div      = row.get('_boc_div') or 0
    boc_div_date = row.get('_boc_div_date', '')
    boc_cours    = row.get('_boc_cours')
    price_final  = row.get('price') or boc_cours or 0

    # BNA et BVPA figés avant le dividende : le cours du jour ne les change pas.
    _appliquer_bna_bvpa(row, base_row, pdf_analysis, ticker, moment)

    # Dividende BOC : appliqué si date récente ET cohérent avec existant (≥ 50%)
    # Exception : si PDF a explicitement fixé 0 (dividende non récurrent), le BOC ne peut pas l'écraser
    _pdf_zeroed = (div_pdf is not None and div_pdf == 0)
    if boc_div > 0 and _is_div_date_recent(boc_div_date, max_years=3) and not _pdf_zeroed:
        existing_div = row.get('div_per_share') or 0
        if not existing_div or boc_div >= existing_div * 0.5:
            row['div_per_share'] = boc_div
            if price_final > 0:
                row['div_yield'] = round(boc_div / price_final * 100, 2)

    # Nettoyage des clés internes
    for k in ('_boc_per', '_boc_div', '_boc_div_date', '_boc_cours', '_boc_date',
              '_boc_pb', '_boc_bvpa'):
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

    resultat = {
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
    return _poser_verdict(resultat, composite_adj_80, None, row)


def _statut_ligne(row):
    """La liste manuelle prime. Sinon un statut explicite, sinon le prix.

    Une suspension datee et encore active gagne sur le prix et sur un
    statut deja pose sur la ligne. Liste illisible : on n'en tient pas
    compte, le classement continue.
    """
    if not isinstance(row, dict):
        return STATUT_NON_NOTE
    manuel = None
    try:
        from statuts_cotation import statut_de
        manuel = statut_de(row.get("ticker"), row.get("_moment"))
    except Exception:
        logger.warning("Liste des statuts de cotation indisponible, ignoree")
        manuel = None
    if manuel:
        return manuel
    if row.get("statut") not in (None, ""):
        explicite = normaliser_statut(row.get("statut"))
        if explicite:
            return explicite
        return STATUT_NON_NOTE
    if row.get("price"):
        return STATUT_COTE
    return STATUT_NON_NOTE


def _annoter_suspensions(results, historique, moment):
    """Pose statut_depuis, statut_source, alerte_cotation. Liste active :
    statut suspendu, conseil vide. Ne touche pas a la note."""
    from statuts_cotation import appliquer
    hist = historique if isinstance(historique, dict) else {}
    for ligne in results:
        if not isinstance(ligne, dict):
            continue
        ticker = ligne.get("ticker")
        try:
            alerte = appliquer(ligne, hist.get(ticker), moment)
        except Exception:
            logger.warning("statuts cotation: annotation ignoree pour %s", ticker)
            ligne.setdefault("statut_depuis", None)
            ligne.setdefault("statut_source", None)
            ligne.setdefault("alerte_cotation", None)
            continue
        if not alerte:
            continue
        logger.warning(
            "alerte cotation %s type=%s depuis=%s seances=%s",
            ticker,
            alerte.get("type"),
            alerte.get("depuis"),
            alerte.get("seances"),
        )


def _poser_verdict(scores, composite, precedent, row):
    """Remplit note10, conseil, libelle, couleur, statut. N'ecrit rien sur disque."""
    statut = _statut_ligne(row)
    prix = row.get("price")
    if statut == STATUT_COTE and not prix:
        statut = STATUT_NON_NOTE
    avis = _hysteresis_conseil(composite, precedent, prix, statut)
    scores["statut"] = statut
    scores["note10"] = note10(composite)
    scores["conseil"] = avis
    scores["conseil_libelle"] = libelle_conseil(avis) if avis else None
    # Couleur du mot (vert / orange / rouge), pas celle de la note /10.
    scores["conseil_couleur"] = couleur_conseil(avis)
    if "note_calculee_le" not in scores:
        scores["note_calculee_le"] = datetime.now(timezone.utc).isoformat()
    return scores


def _hysteresis_conseil(adj, prev, price, statut=None):
    """Conseil avec amortisseur. None sans prix.

    Le composite reçu est déjà celui de la note figée ou celui du recalcul
    de clôture : l'amortisseur ne voit pas le cours de la séance.
    """
    if not price:
        return None
    if statut is None:
        statut = STATUT_COTE
    return conseil_verdict(adj, prev, statut)


# ─────────────────────────────────────────────────────────────────────────────
# Gel de la note en séance (D-2 = C)
# ─────────────────────────────────────────────────────────────────────────────

# Présent dans live_ranking.json une fois la note calculée par cette formule.
# cloture-v2 : le BNA ne suit plus le cours de la séance (PR-06). Un fichier
# encore en cloture-v1, ou sans cette marque, garde sa note tant que le
# marché est ouvert et la recalcule une fois le marché fermé.
NOTE_FORMULE = "cloture-v2"

_CHAMPS_NOTE = (
    "score_graham", "score_dcf", "score_ddm", "score_epv",
    "score_buffett", "score_rev_dcf", "score_relatif", "score_technique",
    "detail_graham", "detail_dcf", "detail_ddm", "detail_epv",
    "detail_buffett", "detail_rev_dcf", "detail_relatif", "detail_technique",
    "geo_penalty", "composite_raw", "composite_adj",
    "note10", "conseil", "conseil_libelle", "conseil_couleur", "statut",
    "note_calculee_le",
)


def _moment_utc(moment=None):
    from live_data import _en_utc
    return _en_utc(moment)


def _seance_ouverte(moment):
    from live_data import is_market_open_at
    return is_market_open_at(moment)


def _cloture_du_jour_incluse(moment):
    """Vrai après 15h30 UTC un jour de semaine : le cours live est la clôture."""
    from live_data import CLOTURE_HEURE, CLOTURE_MINUTE
    moment = _moment_utc(moment)
    if moment.weekday() >= 5:
        return False
    return (moment.hour, moment.minute) >= (CLOTURE_HEURE, CLOTURE_MINUTE)


def derniere_cloture(moment):
    """Dernier instant de clôture (15h30 UTC, lun-ven) déjà passé."""
    from datetime import timedelta, time as heure
    from live_data import CLOTURE_HEURE, CLOTURE_MINUTE
    moment = _moment_utc(moment)
    jour = moment.date()
    for _ in range(8):
        if jour.weekday() < 5:
            cloture = datetime.combine(
                jour, heure(CLOTURE_HEURE, CLOTURE_MINUTE), tzinfo=timezone.utc,
            )
            if cloture <= moment:
                return cloture
        jour = jour - timedelta(days=1)
    return None


def _lire_moment(valeur):
    if not isinstance(valeur, str) or not valeur:
        return None
    try:
        moment = datetime.fromisoformat(valeur.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _moment_utc(moment)


class EmpreinteIllisible(Exception):
    """Un fichier de faits existe mais son JSON n'est pas lisible.

    Le classement ne doit pas enregistrer d'empreinte dans ce cas :
    le passage suivant retentera. Après une nouvelle clôture, la note
    est quand même recalculée sans cette source.
    """

    def __init__(self, path):
        super().__init__(path)
        self.path = path


# Clés réécrites à chaque job sans changer le fait (date de scrape, etc.).
_CLES_VOLATILES = {
    "boc_data.json": frozenset({"last_update"}),
    "analyses_summary.json": frozenset({"analyzed_at"}),
    "external_dividends.json": frozenset({"scraped_at"}),
}


def _oter_cles(valeur, cles):
    if isinstance(valeur, dict):
        return dict(
            (cle, _oter_cles(fils, cles))
            for cle, fils in valeur.items()
            if cle not in cles
        )
    if isinstance(valeur, list):
        return [_oter_cles(fils, cles) for fils in valeur]
    return valeur


def _empreinte_contenu(path):
    """sha1 du JSON canonique. Fichier absent : « absent ».

    last_update, analyzed_at et scraped_at ne comptent pas : le job de 19h
    les réécrit tous les jours, y compris le week-end, sans fait nouveau.
    """
    nom = os.path.basename(path)
    try:
        with open(path, encoding="utf-8") as f:
            brut = f.read()
    except FileNotFoundError:
        return "absent"
    except OSError as exc:
        raise EmpreinteIllisible(path) from exc
    if not brut.strip():
        raise EmpreinteIllisible(path)
    try:
        data = json.loads(brut)
    except ValueError as exc:
        raise EmpreinteIllisible(path) from exc
    if not isinstance(data, dict):
        raise EmpreinteIllisible(path)
    nettoye = _oter_cles(data, _CLES_VOLATILES.get(nom, frozenset()))
    canon = json.dumps(nettoye, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(canon.encode("utf-8")).hexdigest()


def chemins_faits():
    """Fichiers dont un changement de contenu est un fait nouveau pour la note.

    boc_data.json et external_dividends.json : job 19h00.
    analyses_summary.json : nouveau rapport annuel analysé.
    statuts_cotation.json : suspension ajoutée ou levée, appliquée en séance.
    """
    from statuts_cotation import CHEMIN_LISTE
    return (
        os.path.join(DATA_DIR, "boc_data.json"),
        os.path.join(DATA_DIR, "analyses_summary.json"),
        os.path.join(DATA_DIR, "external_dividends.json"),
        CHEMIN_LISTE,
    )


def empreinte_faits(chemins=None, moment=None):
    """Empreinte de contenu. Lève EmpreinteIllisible si un fichier est illisible.

    Le suffixe ``suspensions:`` dépend des entrées actives à ``moment``
    (défaut : aujourd'hui UTC), pas seulement des octets du fichier.
    Le lendemain d'une fin, la note est donc recalculée en séance.
    """
    if chemins is None:
        chemins = chemins_faits()
    base = "|".join(_empreinte_contenu(chemin) for chemin in chemins)
    try:
        from statuts_cotation import empreinte_actives
        actif = empreinte_actives(moment)
    except Exception:
        logger.warning("Empreinte des suspensions indisponible")
        actif = "illisible"
    return base + "|suspensions:" + actif


def _lire_fichier_faits(path):
    """(dict, lisible). Un fichier absent n'est pas une erreur de lecture."""
    if not os.path.exists(path):
        return {}, True
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError, UnicodeError):
        return {}, False
    if not isinstance(data, dict):
        return {}, False
    return data, True


def _note_calculee_payload(payload):
    if not isinstance(payload, dict):
        return None
    moment = _lire_moment(payload.get("note_calculee_le"))
    if moment is not None:
        return moment
    for ligne in payload.get("ranking") or []:
        if isinstance(ligne, dict):
            moment = _lire_moment(ligne.get("note_calculee_le"))
            if moment is not None:
                return moment
    return None


def doit_recalculer_note(payload, moment, empreinte):
    """True si composite / note10 / conseil doivent être recalculés.

    En séance : seulement sur un fait nouveau, ou s'il n'existe aucune note.
    Une formule inconnue (fichier d'avant ce PR) est conservée en séance.
    Marché fermé : recalcul si la formule a changé, si un fait est nouveau,
    ou si la dernière clôture est postérieure à note_calculee_le.
    """
    moment = _moment_utc(moment)
    if not isinstance(payload, dict) or not payload.get("ranking"):
        return True
    if payload.get("note_formule") != NOTE_FORMULE:
        return not _seance_ouverte(moment)
    if payload.get("faits_empreinte") != empreinte:
        return True
    if _seance_ouverte(moment):
        return False
    calcule = _note_calculee_payload(payload)
    cloture = derniere_cloture(moment)
    if calcule is None or cloture is None:
        return True
    return calcule < cloture


def nombre_note(valeur, defaut=0):
    """None (société non notée) ne casse pas un calcul ni un format."""
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return defaut
    return valeur


def cle_tri_note(ligne):
    """Notes chiffrées d'abord, sociétés sans note en dernier."""
    if not isinstance(ligne, dict):
        return (0, 0.0)
    valeur = ligne.get("composite_adj")
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return (0, 0.0)
    return (1, float(valeur))


def _a_une_note(ligne):
    """Une ligne en erreur (composite souvent à 0) n'est pas une note figée."""
    if not isinstance(ligne, dict):
        return False
    if ligne.get("error"):
        return False
    valeur = ligne.get("composite_adj")
    return isinstance(valeur, (int, float)) and not isinstance(valeur, bool)


def _note_sans_prix(moment):
    """Pas de clôture à noter : scores vides, pas un composite calculé sans cours."""
    scores = dict((cle, None) for cle in (
        "score_graham", "score_dcf", "score_ddm", "score_epv",
        "score_buffett", "score_rev_dcf", "score_relatif", "score_technique",
        "detail_graham", "detail_dcf", "detail_ddm", "detail_epv",
        "detail_buffett", "detail_rev_dcf", "detail_relatif", "detail_technique",
        "geo_penalty", "composite_raw", "composite_adj",
        "note10", "conseil", "conseil_libelle", "conseil_couleur",
    ))
    scores["statut"] = STATUT_NON_NOTE
    scores["note_calculee_le"] = _moment_utc(moment).isoformat()
    return scores


def _extraire_note(ligne):
    return dict((cle, ligne[cle]) for cle in _CHAMPS_NOTE if cle in ligne)


def _completer_ligne(ticker, base_row, live_price_data, pdf_analysis,
                     boc_data, am_cache, ph, moment):
    """Row enrichi + dividende validé + variation plafonnée. Même règles qu'avant."""
    from data_validator import validate_dividend

    row = _build_enriched_row(
        ticker, base_row, live_price_data or {}, pdf_analysis,
        boc_snapshot=boc_data, moment=moment,
    )
    _boc_e = boc_data.get(ticker, {}) if isinstance(boc_data, dict) else {}
    if not isinstance(_boc_e, dict):
        _boc_e = {}
    _boc_div = _boc_e.get("div_net") if _boc_e else None
    _pdf_kpis = ((pdf_analysis or {}).get("kpis") or {}) if pdf_analysis else {}
    _pdf_raw = (_pdf_kpis.get("dividende_par_action") or {}).get("valeur")
    _pdf_unite = (_pdf_kpis.get("dividende_par_action") or {}).get("unite")
    _pdf_raw = _convert_pdf_div(ticker, _pdf_raw, _pdf_unite)
    _pdf_div = float(_pdf_raw) if (_pdf_raw is not None and _pdf_raw > 0) else None
    _hist_div = base_row.get("div_hist")
    _price = row.get("price") or 0
    _boc_date = _boc_e.get("div_date") if _boc_e else None
    _am_entry = am_cache.get(ticker, {}) if isinstance(am_cache, dict) else {}
    if not isinstance(_am_entry, dict):
        _am_entry = {}
    _dv = validate_dividend(
        ticker, _hist_div, _pdf_div, _boc_div, _price,
        am_div=_am_entry.get("amount"), am_date=_am_entry.get("paid_date"),
        boc_date=_boc_date,
    )
    row["div_per_share"] = _dv["value"]
    row["div_yield"] = _dv["yield_for_calc"]
    row["div_confidence"] = _dv["confidence"]
    row["div_flag"] = _dv["flag"]
    row["div_is_exceptional"] = _dv["is_exceptional"]
    row["div_exceptional_value"] = _dv["raw_value"]
    row["div_source_used"] = _dv["source_used"]
    row["div_source_detail"] = _dv["source_detail"]
    row["div_ecart_boc_pdf"] = _dv["ecart_boc_pdf"]
    row["div_am_value"] = _dv["am_div_raw"]
    row["div_am_date"] = _dv["am_paid_date"]
    row["div_am_split"] = _dv["am_split_flag"]
    row["div_am_net_brut"] = _dv["am_net_brut_flag"]

    _raw_chg = row.get("change_pct")
    if _raw_chg is not None and abs(_raw_chg) > 7.5:
        _today = _moment_utc(moment).date().isoformat()
        _hist = ph.get(ticker, []) if isinstance(ph, dict) else []
        _ref = None
        if _hist:
            if len(_hist) >= 2 and _hist[-1].get("date") == _today:
                _ref = _hist[-2].get("price")
            else:
                _ref = _hist[-1].get("price")
        if _ref is None:
            _ref = _boc_e.get("cours_prev")
        _cur = row.get("price")
        if _ref and _ref > 0 and _cur:
            _chg2 = (_cur / _ref - 1) * 100
            row["change_pct"] = _chg2 if abs(_chg2) <= 7.5 else None
        else:
            row["change_pct"] = None
    return row


def _prix_pour_la_note(prix_live, points, moment):
    """Cours qui entre dans les 8 modèles.

    Après la clôture du jour : le cours live (c'est la clôture).
    Sinon : la dernière clôture de l'historique, pas le tick de séance.
    En séance, sans aucune clôture : None. La société reste non notée.
    On ne met pas le cours de la minute à la place.
    """
    from live_valuation import _nombre, serie_clotures
    moment = _moment_utc(moment)
    cours_live = _nombre(prix_live)
    if _cloture_du_jour_incluse(moment) and cours_live is not None and cours_live > 0:
        return cours_live
    serie = serie_clotures(points, moment.date().isoformat())
    if serie:
        return serie[-1]["cours"]
    if _seance_ouverte(moment):
        return None
    if cours_live is not None and cours_live > 0:
        return cours_live
    return None


def _donnees_prix_note(live_price_data, prix_note):
    data = dict(live_price_data or {})
    data["price"] = prix_note
    data["change_pct"] = 0
    data["volume"] = 0
    data["open"] = prix_note
    data["trend"] = None
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Reclassement complet
# ─────────────────────────────────────────────────────────────────────────────

def compute_live_ranking(trigger="manual", force=False, moment=None):
    """
    Met à jour le classement des 47 sociétés.

    En séance, le prix et la variation du jour bougent ; la note
    (composite, note10, conseil) reste celle de la dernière clôture
    ou du dernier fait nouveau. `moment` sert aux tests.
    `force` ne débloque pas une note intraday.
    trigger: "price_update" | "pdf_analysis" | "manual" | "scheduler" | "startup"
    """
    global _last_ranking, _last_prices
    moment = _moment_utc(moment)

    with _lock:
        try:
            from scraper import STOCK_FUNDAMENTALS
            from live_data import get_live_data

            # Note précédente d'abord : si un fait est illisible, on garde
            # son empreinte et on ne fige pas une note calculée à vide.
            _payload_precedent = None
            _precedent = {}
            _prev_conseil = {}
            try:
                with open(RANKING_PATH, encoding="utf-8") as _f:
                    _payload_precedent = json.load(_f)
                for _r in (_payload_precedent or {}).get("ranking", []):
                    if isinstance(_r, dict) and _r.get("ticker"):
                        _precedent[_r["ticker"]] = _r
                        if _r.get("conseil"):
                            _prev_conseil[_r["ticker"]] = _r["conseil"]
            except Exception:
                _payload_precedent = None

            _empreinte_precedente = None
            if isinstance(_payload_precedent, dict):
                _empreinte_precedente = _payload_precedent.get("faits_empreinte")

            # Empreinte AVANT de lire les faits pour scorer. boc_scraper écrit
            # boc_data.json sans os.replace : une lecture pendant l'écriture
            # peut voir un fichier vide, puis une empreinte du fichier fini.
            _faits_lisibles = True
            _illisibles = []

            def _marquer_illisible(chemin):
                nom = os.path.basename(chemin) if chemin else ""
                if nom and nom not in _illisibles:
                    _illisibles.append(nom)

            try:
                _empreinte = empreinte_faits(moment=moment)
            except EmpreinteIllisible as exc:
                logger.warning("Empreinte des faits illisible: %s", exc)
                _faits_lisibles = False
                _empreinte = None
                _marquer_illisible(getattr(exc, "path", None) or str(exc))

            pdf_summary = {}
            boc_data = {}
            am_cache = {}
            for _chemin in chemins_faits():
                _data, _ok = _lire_fichier_faits(_chemin)
                if not _ok:
                    logger.warning("Fichier de faits illisible, traité comme vide: %s", _chemin)
                    _faits_lisibles = False
                    _data = {}
                    _marquer_illisible(_chemin)
                _nom = os.path.basename(_chemin)
                if _nom == "analyses_summary.json":
                    pdf_summary = _data
                elif _nom == "boc_data.json":
                    boc_data = _data
                elif _nom == "external_dividends.json":
                    am_cache = _data

            # En séance, un fichier illisible ne change pas la note (écriture
            # en cours). À la première clôture où il est encore illisible, on
            # recalcule sans cette source, comme avant, et on le signale.
            _empreinte_decision = _empreinte if _faits_lisibles else _empreinte_precedente
            _recalcul = doit_recalculer_note(_payload_precedent, moment, _empreinte_decision)

            # Historique prix pour le sas variation
            _ph = {}
            try:
                from price_history_builder import load_history as _load_ph
                _ph = _load_ph()
            except Exception:
                pass

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

                    # Cours et variation du jour (affichage). La note est plus bas.
                    row = _completer_ligne(
                        ticker, base_row, live_price_data, pdf_analysis,
                        boc_data, am_cache, _ph, moment,
                    )

                    ancienne = _precedent.get(ticker)
                    if not _recalcul and _a_une_note(ancienne):
                        scores = _extraire_note(ancienne)
                    else:
                        points = _ph.get(ticker, []) if isinstance(_ph, dict) else []
                        prix_note = _prix_pour_la_note(row.get("price"), points, moment)
                        if prix_note is None:
                            scores = _note_sans_prix(moment)
                        else:
                            if prix_note != row.get("price"):
                                row_note = _completer_ligne(
                                    ticker, base_row,
                                    _donnees_prix_note(live_price_data, prix_note),
                                    pdf_analysis, boc_data, am_cache, _ph, moment,
                                )
                            else:
                                row_note = dict(row)
                            row_note["ticker"] = ticker
                            row_note["_moment"] = moment
                            row_note["_inclure_cloture_du_jour"] = _cloture_du_jour_incluse(moment)
                            row_note["historique_clotures"] = points
                            scores = _compute_scores(row_note)
                            _poser_verdict(
                                scores,
                                nombre_note(scores.get("composite_adj")),
                                _prev_conseil.get(ticker),
                                row_note,
                            )
                            scores["note_calculee_le"] = moment.isoformat()

                    result = {
                        "ticker":        ticker,
                        "name":          base_row.get("name", ""),
                        "sector":        base_row.get("sector", ""),
                        "country":       base_row.get("country", ""),
                        "price":         row.get("price"),
                        "price_source":  row.get("price_source", "live"),
                        "price_verified": row.get("price_verified", True),
                        "change_pct":    row.get("change_pct", 0),
                        "volume":        row.get("volume", 0),
                        "trend":         row.get("trend"),
                        "pe_ref":        row.get("pe_ref") if row.get("bna") else None,
                        "pe_hist":       row.get("pe_hist"),
                        "pb_ref":        row.get("pb_ref") if row.get("bvpa") else None,
                        "pb_hist":       row.get("pb_hist"),
                        "roe":           row.get("roe"),
                        "div_yield":              row.get("div_yield"),
                        "div_per_share":           row.get("div_per_share"),
                        "div_confidence":          row.get("div_confidence", "inconnue"),
                        "div_flag":                row.get("div_flag", ""),
                        "div_is_exceptional":      row.get("div_is_exceptional", False),
                        "div_exceptional_value":   row.get("div_exceptional_value", 0),
                        "div_source_used":         row.get("div_source_used", "none"),
                        "div_source_detail":       row.get("div_source_detail", ""),
                        "div_ecart_boc_pdf":       row.get("div_ecart_boc_pdf"),
                        "div_am_value":            row.get("div_am_value"),
                        "div_am_date":             row.get("div_am_date"),
                        "div_am_split":            row.get("div_am_split", False),
                        "div_am_net_brut":         row.get("div_am_net_brut", False),
                        "pdf_verdict":   row.get("pdf_verdict"),
                        "pdf_ca":        row.get("pdf_ca"),
                        "pdf_rn":        row.get("pdf_rn"),
                        "pdf_year":      row.get("pdf_year"),
                        "pdf_resume":    row.get("pdf_resume"),
                        "pdf_points_cles": row.get("pdf_points_cles", []),
                        "shares":        row.get("shares"),
                        "eps":           row.get("eps"),
                        "bna":           row.get("bna"),
                        "bna_source":    row.get("bna_source"),
                        "bna_exercice":  row.get("bna_exercice"),
                        "bna_date":      row.get("bna_date"),
                        "bna_ecart_boc": row.get("bna_ecart_boc"),
                        "bvpa":          row.get("bvpa"),
                        "bvpa_source":   row.get("bvpa_source"),
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
                        "statut_depuis": None,
                        "statut_source": None,
                        "alerte_cotation": None,
                    }
                    results.append(result)

                except Exception as e:
                    logger.warning(f"Erreur scoring {ticker}: {e}")
                    ancienne = _precedent.get(ticker)
                    if not _recalcul and _a_une_note(ancienne):
                        conservee = dict(ancienne)
                        conservee["error"] = str(e)
                        results.append(conservee)
                    else:
                        results.append({
                            "ticker": ticker,
                            "name":   base_row.get("name", ""),
                            "composite_adj": 0,
                            "error": str(e),
                        })

            # La liste manuelle et les alertes, avant le tri : un suspendu
            # ne peut pas rester devant les titres cotes a cause de sa note.
            _annoter_suspensions(results, _ph, moment)

            def _cle_avec_suspension(ligne):
                cote = 1 if isinstance(ligne, dict) and ligne.get("statut") == STATUT_COTE else 0
                return (cote,) + cle_tri_note(ligne)

            # Notes chiffrées d'abord, parmi les titres cotes. Les suspendus
            # (note conservee, classe fausse) passent apres tous les cotes.
            results.sort(key=_cle_avec_suspension, reverse=True)

            # Calculer les mouvements de rang
            old_ranks = {}
            if _last_ranking:
                for r in _last_ranking.get("ranking", []):
                    old_ranks[r["ticker"]] = r.get("rank", 0)

            for i, r in enumerate(results):
                r["rank"]      = i + 1
                old_rank       = old_ranks.get(r["ticker"], i + 1)
                r["rank_delta"] = old_rank - (i + 1)  # positif = monté
                r["classe"] = r.get("statut") == STATUT_COTE

            # ── Garde-fou dividendes aberrants ────────────────────────────
            _YIELD_HARD_CAP = 15.0   # % — au-dessus = forcé à 0
            _YIELD_WARN     = 8.0    # % — entre 8 et 15 = log warning
            for r in results:
                dy = r.get("div_yield") or 0
                t  = r.get("ticker", "?")
                if dy > _YIELD_HARD_CAP:
                    logger.warning(
                        f"[garde-fou div] {t}: div_yield={dy:.2f}% > {_YIELD_HARD_CAP}% "
                        f"— forcé à 0 (div_per_share={r.get('div_per_share')})"
                    )
                    r["div_yield"]     = 0.0
                    r["div_per_share"] = 0
                elif dy > _YIELD_WARN:
                    logger.warning(
                        f"[à vérifier div] {t}: div_yield={dy:.2f}% "
                        f"(div_per_share={r.get('div_per_share')}, price={r.get('price')})"
                    )

            # updated_at suit le prix. note_calculee_le ne bouge que si la note
            # a vraiment été recalculée (les lignes déjà copiées gardent la leur).
            _horodatage = moment.isoformat()
            if _recalcul:
                _note_le = _horodatage
            else:
                _note_le = None
                if isinstance(_payload_precedent, dict):
                    _note_le = _payload_precedent.get("note_calculee_le")
                if not _note_le:
                    for _ligne in results:
                        if _ligne.get("note_calculee_le"):
                            _note_le = _ligne["note_calculee_le"]
                            break

            # Fichier illisible : on ne stocke pas la nouvelle empreinte,
            # même si le hash avait réussi avant une lecture ratée.
            if not _faits_lisibles:
                _empreinte_stockee = _empreinte_precedente
            elif _recalcul or _empreinte_precedente is None:
                _empreinte_stockee = _empreinte
            else:
                _empreinte_stockee = _empreinte_precedente

            # Payload final
            payload = {
                "updated_at":       _horodatage,
                "note_calculee_le": _note_le,
                "note_formule":     NOTE_FORMULE if (_recalcul or (isinstance(_payload_precedent, dict) and _payload_precedent.get("note_formule") == NOTE_FORMULE)) else (_payload_precedent or {}).get("note_formule"),
                "note_recalculee":  _recalcul,
                "faits_empreinte":  _empreinte_stockee,
                "faits_illisibles": _illisibles,
                "trigger":          trigger,
                "market_open":      _seance_ouverte(moment),
                "changed_tickers":  changed_tickers,
                "total":            len(results),
                "ranking":          results,
            }

            # Sauvegarder
            _save_json_atomic(RANKING_PATH, payload)

            # Sauvegarder dans l'historique (top 10 seulement, max 30 entrées)
            _save_history(payload)

            payload = _copier_updated_at(payload)
            with _cache_lock:
                _memo_cache(payload, _stamp_fichier(RANKING_PATH))
            logger.info(
                "Ranking mis a jour — trigger=%s note_recalculee=%s changements=%s top1=%s",
                trigger, _recalcul, len(changed_tickers),
                results[0]["ticker"] if results else "?",
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

        _save_json_atomic(HISTORY_PATH, history)
    except Exception as e:
        logger.warning(f"_save_history: {e}")


def _stamp_fichier(path):
    """(inode, mtime_ns, taille) ou None si le fichier manque.

    _save_json_atomic ecrit un temporaire puis os.replace : chaque
    reecriture change l'inode, meme si le mtime et la taille restent
    identiques. Pas de lecture du JSON pour decider du cache.
    """
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_ino, st.st_mtime_ns, st.st_size)


def _lire_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _updated_at_de(data):
    if isinstance(data, dict):
        return data.get("updated_at")
    return None


def _copier_updated_at(data):
    """Recopie le updated_at du payload sur chaque ligne qui n'en a pas.

    N'ecrit pas le fichier : les routes ajoutent le champ, elles n'en retirent aucun.
    """
    if not isinstance(data, dict):
        return data
    horodatage = data.get("updated_at")
    lignes = data.get("ranking")
    if not horodatage or not isinstance(lignes, list):
        return data
    for ligne in lignes:
        if isinstance(ligne, dict) and not ligne.get("updated_at"):
            ligne["updated_at"] = horodatage
    return data


def _memo_cache(data, stamp):
    """A appeler en tenant _cache_lock."""
    global _last_ranking, _last_stamp, _last_updated_at
    _last_ranking = data
    _last_stamp = stamp
    _last_updated_at = _updated_at_de(data)


def _oublier_cache():
    """A appeler en tenant _cache_lock."""
    global _last_ranking, _last_stamp, _last_updated_at
    _last_ranking = None
    _last_stamp = None
    _last_updated_at = None


def load_ranking():
    """Dernier classement ecrit par compute_live_ranking.

    Recharge le fichier si l'inode, le mtime ou la taille change.
    Fichier absent ou illisible : None, jamais l'ancien cache.
    """
    stamp = _stamp_fichier(RANKING_PATH)
    if stamp is None:
        with _cache_lock:
            _oublier_cache()
        return None

    with _cache_lock:
        cached = _last_ranking
        cached_stamp = _last_stamp

    if cached is not None and cached_stamp == stamp:
        return cached

    try:
        data = _lire_json(RANKING_PATH)
    except Exception as e:
        logger.warning("load_ranking illisible: %s", e)
        return None
    data = _copier_updated_at(data)
    stamp_apres = _stamp_fichier(RANKING_PATH)
    with _cache_lock:
        if stamp_apres == stamp:
            _memo_cache(data, stamp)
    return data


def lire_lignes(path=None):
    """Lignes du classement. Pas de repli sur d'anciens scores_*.json.

    Le chemin canonique passe par load_ranking. Un autre chemin est lu
    directement (tests qui pointent un repertoire temporaire).
    """
    if path is None or os.path.abspath(path) == os.path.abspath(RANKING_PATH):
        data = load_ranking()
    else:
        try:
            data = _lire_json(path)
        except Exception:
            return []
        data = _copier_updated_at(data)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        lignes = data.get("ranking")
        if isinstance(lignes, list):
            return lignes
    return []


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
                f"{nombre_note(r.get('composite_adj')):5.1f}  "
                f"{pe:6s} {roe:6s} {pdf:8s} {delta_str:4s}"
            )

        changes = get_ranking_changes()
        if changes:
            print(f"\nMouvements ({len(changes)}):")
            for c in changes[:5]:
                arrow = "▲" if c["rank_delta"] > 0 else "▼"
                print(f"  {arrow} {c['ticker']:8s} rang {c['rank']} ({c['rank_delta']:+d})")
