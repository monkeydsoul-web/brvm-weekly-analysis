"""
Clôtures des indices BRVM et instantané rang/note, une fois par séance.

Source des niveaux : le cache qui alimente /api/market (market_cache.json),
champ indices[].current. Aucune série passée fiable n'existe dans le dépôt :
le fichier part vide, rien n'est inventé.

Écrit data/index_history.json (BRVM_DATA_DIR, disque persistant sur Render).
Une date = une séance. Réécriture atomique. Le second passage le même jour
ne change pas les niveaux déjà enregistrés.

Jour sans séance : même heuristique que price_history_builder (cours et
volumes identiques à la séance précédente). Pas de calendrier de fériés.
Week-end et appel avant 15h30 UTC : rien n'est écrit.
"""
import calendar
import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone

from live_data import CLOTURE_HEURE, CLOTURE_MINUTE, _en_utc
from paths import DATA_DIR
from price_history_builder import _reproduit_seance_precedente

logger = logging.getLogger(__name__)

HISTORY_PATH = os.path.join(DATA_DIR, "index_history.json")

INDICES = ("BRVM-C", "BRVM-30", "Prestige", "Principal")
PLAGES = ("1S", "1M", "YTD", "1A")

# Même garde que news_scraper.fetch_macro_context sur cette source :
# écarte une capitalisation lue par erreur à la place d'un indice.
_MIN_INDICE = 50
_MAX_INDICE = 5000

_ALIAS = {
    "BRVM-C": "BRVM-C",
    "BRVMC": "BRVM-C",
    "COMPOSITE": "BRVM-C",
    "BRVM-COMPOSITE": "BRVM-C",
    "BRVM-30": "BRVM-30",
    "BRVM30": "BRVM-30",
    "PRESTIGE": "Prestige",
    "BRVM-PRESTIGE": "Prestige",
    "BRVM-PRES": "Prestige",
    "PRINCIPAL": "Principal",
    "BRVM-PRINCIPAL": "Principal",
}

_CACHE = {"stamp": None, "data": None}
_CACHE_LOCK = threading.Lock()


def pret_pour_cloture(moment=None):
    """Vrai après 15h30 UTC un jour de semaine."""
    moment = _en_utc(moment)
    if moment.weekday() >= 5:
        return False
    return (moment.hour, moment.minute) >= (CLOTURE_HEURE, CLOTURE_MINUTE)


def normaliser_index(brut):
    if not isinstance(brut, str):
        return None
    cle = brut.strip().upper().replace(" ", "").replace("_", "-")
    return _ALIAS.get(cle)


def code_indice(nom):
    """Nom publié dans market_cache indices[].name → code canonique."""
    if not isinstance(nom, str):
        return None
    n = nom.upper().replace("–", " ").replace("—", " ").replace("-", " ")
    n = " ".join(n.split())
    if "PRESTIGE" in n:
        return "Prestige"
    if "PRINCIPAL" in n:
        return "Principal"
    if "COMPOSITE" in n or n == "BRVM C":
        return "BRVM-C"
    if _contient_30(n):
        return "BRVM-30"
    return None


def _contient_30(nom):
    taille = len(nom)
    debut = 0
    while True:
        i = nom.find("30", debut)
        if i < 0:
            return False
        avant_ok = i == 0 or not nom[i - 1].isdigit()
        apres = i + 2
        apres_ok = apres >= taille or not nom[apres].isdigit()
        if avant_ok and apres_ok:
            return True
        debut = i + 1


def valeur_indice(valeur):
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    if valeur != valeur or valeur in (float("inf"), float("-inf")):
        return None
    if valeur < _MIN_INDICE or valeur > _MAX_INDICE:
        return None
    return round(float(valeur), 2)


def extraire_indices(marche):
    if not isinstance(marche, dict):
        return {}
    brut = marche.get("indices")
    if not isinstance(brut, list):
        return {}
    trouves = {}
    for entree in brut:
        if not isinstance(entree, dict):
            continue
        code = code_indice(entree.get("name"))
        if code is None or code in trouves:
            continue
        valeur = valeur_indice(entree.get("current"))
        if valeur is None:
            continue
        trouves[code] = valeur
    return trouves


def extraire_societes(classement):
    """Copie rang et note10 déjà calculés. Ne recalcule rien."""
    if not isinstance(classement, dict):
        return []
    lignes = classement.get("ranking")
    if not isinstance(lignes, list):
        return []
    vus = set()
    sortie = []
    for row in lignes:
        if not isinstance(row, dict):
            continue
        ticker = row.get("ticker")
        if not isinstance(ticker, str):
            continue
        ticker = ticker.strip().upper()
        if not ticker or ticker in vus:
            continue
        rang = row.get("rank")
        if isinstance(rang, bool) or not isinstance(rang, int) or rang < 1:
            continue
        note = None
        if "note10" in row:
            brut = row.get("note10")
            if not isinstance(brut, bool) and isinstance(brut, (int, float)):
                note = brut
        vus.add(ticker)
        sortie.append({"ticker": ticker, "rang": rang, "note": note})
    sortie.sort(key=lambda s: (s["rang"], s["ticker"]))
    return sortie


def _statut(statut, jour):
    return {"statut": statut, "date": jour}


def _horodatage(valeur):
    if not isinstance(valeur, str) or not valeur:
        return None
    try:
        moment = datetime.fromisoformat(valeur.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _en_utc(moment)


def _cache_du_jour(payload, jour):
    if not isinstance(payload, dict):
        return False
    moment = _horodatage(payload.get("updated_at"))
    return moment is not None and moment.date() == jour


def _marche_est_la_cloture(payload, jour):
    moment = _horodatage(payload.get("updated_at") if isinstance(payload, dict) else None)
    if moment is None or moment.date() != jour:
        return False
    return (moment.hour, moment.minute) >= (CLOTURE_HEURE, CLOTURE_MINUTE)


def _seance_confirmee(cours, historique, jour_iso):
    if not _cache_du_jour(cours, datetime.strptime(jour_iso, "%Y-%m-%d").date()):
        return False
    prices = cours.get("prices")
    if not isinstance(prices, dict):
        return False
    if not any(isinstance(v, dict) and v.get("price") for v in prices.values()):
        return False
    if not isinstance(historique, dict):
        historique = {}
    if _reproduit_seance_precedente(historique, prices, jour_iso):
        return False
    return True


def _stamp(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_ino, st.st_mtime_ns, st.st_size)


def invalider_cache():
    with _CACHE_LOCK:
        _CACHE["stamp"] = None
        _CACHE["data"] = None


def charger():
    """Lecture pour l'API. Fichier absent ou illisible → série vide."""
    stamp = _stamp(HISTORY_PATH)
    if stamp is None:
        return {"seances": []}
    with _CACHE_LOCK:
        if _CACHE["stamp"] == stamp and isinstance(_CACHE["data"], dict):
            return _CACHE["data"]
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.warning("index history illisible, serie vide: %s", exc)
        return {"seances": []}
    if not isinstance(data, dict) or not isinstance(data.get("seances"), list):
        logger.warning("index history: format inattendu, serie vide")
        return {"seances": []}
    with _CACHE_LOCK:
        _CACHE["stamp"] = stamp
        _CACHE["data"] = data
    return data


def _charger_strict():
    if not os.path.exists(HISTORY_PATH):
        return {"seances": []}
    with open(HISTORY_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("seances"), list):
        raise ValueError("format index_history inattendu")
    return data


def _ecrire(data):
    dossier = os.path.dirname(HISTORY_PATH) or "."
    os.makedirs(dossier, exist_ok=True)
    tmp_path = None
    try:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=dossier, delete=False,
        )
        tmp_path = tmp.name
        with tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, HISTORY_PATH)
        tmp_path = None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    invalider_cache()


def _lire_marche(marche):
    if marche is not None:
        return marche
    from market_data import load_market_cache
    return load_market_cache()


def _lire_cours(cours):
    if cours is not None:
        return cours
    from live_data import load_cache
    return load_cache()


def _lire_historique_prix(historique):
    if historique is not None:
        return historique
    from price_history_builder import load_history
    return load_history()


def _lire_classement(classement):
    if classement is not None:
        return classement
    path = os.path.join(DATA_DIR, "live_ranking.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("index history: live_ranking.json illisible (%s)", exc)
        return None


def _seance_existante(seances, jour):
    for seance in seances:
        if isinstance(seance, dict) and seance.get("date") == jour:
            return seance
    return None


def enregistrer_cloture(moment=None, marche=None, cours=None,
                        historique_prix=None, classement=None):
    """Enregistre la séance du jour, ou ne touche pas au fichier.

    Les arguments optionnels servent aux tests. En production ils sont lus
    sur le disque : cache marché, cache de cours, historique de prix,
    classement déjà calculé.
    """
    moment = _en_utc(moment)
    jour = moment.date()
    iso = jour.isoformat()
    if moment.weekday() >= 5:
        logger.info("index history: week-end, rien ecrit")
        return _statut("week-end", iso)
    if not pret_pour_cloture(moment):
        logger.info("index history: avant la cloture, rien ecrit")
        return _statut("avant_cloture", iso)

    cours = _lire_cours(cours)
    historique_prix = _lire_historique_prix(historique_prix)
    if not _seance_confirmee(cours, historique_prix, iso):
        logger.info("index history: pas de seance le %s", iso)
        return _statut("sans_seance", iso)

    marche = _lire_marche(marche)
    if not _marche_est_la_cloture(marche, jour):
        logger.info("index history: cache marche anterieur a la cloture")
        return _statut("marche_perime", iso)
    indices = extraire_indices(marche)
    if not indices:
        logger.info("index history: aucun indice reconnu")
        return _statut("indices_absents", iso)

    societes = extraire_societes(_lire_classement(classement))

    try:
        data = _charger_strict()
    except Exception as exc:
        logger.error("index history illisible, ecriture annulee: %s", exc)
        return _statut("fichier_illisible", iso)

    seances = data["seances"]
    existante = _seance_existante(seances, iso)
    if existante is not None:
        if not existante.get("societes") and societes:
            existante["societes"] = societes
            _ecrire(data)
            logger.info("index history: societes completees pour %s", iso)
            return _statut("societes_completees", iso)
        logger.info("index history: %s deja enregistre", iso)
        return _statut("deja_enregistre", iso)

    seances.append({
        "date": iso,
        "indices": indices,
        "societes": societes,
    })
    seances.sort(key=lambda s: s.get("date") or "")
    _ecrire(data)
    logger.info("index history: %s enregistre (%s)", iso, ",".join(sorted(indices)))
    return _statut("enregistre", iso)


def _decaler_mois(jour, delta):
    index = jour.year * 12 + (jour.month - 1) + delta
    annee, mois0 = divmod(index, 12)
    mois = mois0 + 1
    dernier = calendar.monthrange(annee, mois)[1]
    return jour.replace(year=annee, month=mois, day=min(jour.day, dernier))


def _decaler_annees(jour, delta):
    try:
        return jour.replace(year=jour.year + delta)
    except ValueError:
        return jour.replace(year=jour.year + delta, day=28)


def _aujourdhui():
    return datetime.now(timezone.utc).date()


def debut_plage(jour, plage):
    if plage == "1S":
        return jour - timedelta(days=6)
    if plage == "1M":
        return _decaler_mois(jour, -1)
    if plage == "YTD":
        return jour.replace(month=1, day=1)
    if plage == "1A":
        return _decaler_annees(jour, -1)
    return None


def reponse_index_history(index, plage, jour=None):
    """(status, body, cacheable). Points = [date, valeur], croissants."""
    code = normaliser_index(index)
    if code is None:
        return 400, {"error": "index inconnu", "index": list(INDICES)}, False
    if plage not in PLAGES:
        return 400, {"error": "range inconnu", "range": list(PLAGES)}, False
    if jour is None:
        jour = _aujourdhui()
    debut = debut_plage(jour, plage).isoformat()
    fin = jour.isoformat()
    data = charger()
    points = []
    vus = set()
    for seance in data.get("seances") or []:
        if not isinstance(seance, dict):
            continue
        date = seance.get("date")
        if not isinstance(date, str) or date in vus:
            continue
        if date < debut or date > fin:
            continue
        indices = seance.get("indices")
        if not isinstance(indices, dict) or code not in indices:
            continue
        valeur = indices.get(code)
        if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
            continue
        vus.add(date)
        points.append([date, valeur])
    points.sort(key=lambda p: p[0])
    return 200, {"index": code, "range": plage, "points": points}, True
