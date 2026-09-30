"""
Clôtures des indices BRVM et instantané rang/note, une fois par séance.

Source des niveaux : le cache qui alimente /api/market (market_cache.json),
champ indices[].current. Aucune série passée fiable n'existe dans le dépôt :
le fichier part vide, rien n'est inventé.

Écrit data/index_history.json (BRVM_DATA_DIR, disque persistant sur Render).
Une date = une séance. Réécriture atomique, sous verrou fcntl. Le second
passage le même jour peut compléter un indice ou une société manquants.
Il ne remplace jamais une valeur déjà écrite.

Jour sans séance : cours et volumes identiques à la séance précédente,
ou les quatre indices identiques à la dernière clôture enregistrée,
ou current == prev pour les quatre. La date écrite est session_date
du cache (horloge publiée par brvm.org) quand elle est lisible.
Jamais la valeur de la veille sous la date du jour.
Week-end et appel avant 15h30 UTC : rien n'est écrit.
"""
import calendar
import fcntl
import json
import logging
import os
import tempfile
import threading
import time
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
# Au-delà, le niveau n'est pas une clôture plausible face à la séance d'avant.
_ECART_MAX = 0.15

DELAI_VERROU_S = 10.0
_PAUSE_VERROU_S = 0.05

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


def _lignes_indices(marche):
    if not isinstance(marche, dict):
        return []
    brut = marche.get("indices")
    if not isinstance(brut, list):
        return []
    return [entree for entree in brut if isinstance(entree, dict)]


def extraire_indices(marche):
    trouves = {}
    for entree in _lignes_indices(marche):
        code = code_indice(entree.get("name"))
        if code is None or code in trouves:
            continue
        valeur = valeur_indice(entree.get("current"))
        if valeur is None:
            continue
        trouves[code] = valeur
    return trouves


def tous_current_egal_prev(marche):
    """Vrai si les quatre indices publiés ont current == prev.

    Un seul tableau plat : la page republie la clôture précédente.
    """
    vus = {}
    for entree in _lignes_indices(marche):
        code = code_indice(entree.get("name"))
        if code is None or code in vus:
            continue
        courant = valeur_indice(entree.get("current"))
        precedent = valeur_indice(entree.get("prev"))
        if courant is None or precedent is None:
            return False
        vus[code] = courant == precedent
    if not all(code in vus for code in INDICES):
        return False
    return all(vus.values())


def filtrer_ecart(indices, seance_ref):
    """Retire un indice trop loin de sa dernière clôture enregistrée.

    Sans référence (première séance de cet indice), la borne absolue
    de ``valeur_indice`` suffit. Une valeur déjà absente n'est pas inventée.
    """
    anciens = {}
    if isinstance(seance_ref, dict) and isinstance(seance_ref.get("indices"), dict):
        anciens = seance_ref["indices"]
    gardes = {}
    ecartes = []
    for code, valeur in indices.items():
        ref = anciens.get(code)
        if isinstance(ref, bool) or not isinstance(ref, (int, float)) or ref == 0:
            gardes[code] = valeur
            continue
        if abs(float(valeur) - float(ref)) / abs(float(ref)) > _ECART_MAX:
            ecartes.append(code)
            continue
        gardes[code] = valeur
    return gardes, ecartes


def reprise_de_la_veille(indices, seance_ref):
    """Vrai si chaque niveau qu'on écrirait recopie la dernière séance.

    Ouvrir une date neuve dans ce cas collerait la veille sur le jour.
    """
    if not indices or not isinstance(seance_ref, dict):
        return False
    anciens = seance_ref.get("indices")
    if not isinstance(anciens, dict) or not anciens:
        return False
    for code, valeur in indices.items():
        if code not in anciens or anciens[code] != valeur:
            return False
    return True


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
    """Cache du jour, rafraîchi à ou après 15h30 UTC."""
    moment = _horodatage(payload.get("updated_at") if isinstance(payload, dict) else None)
    if moment is None or moment.date() != jour:
        return False
    return (moment.hour, moment.minute) >= (CLOTURE_HEURE, CLOTURE_MINUTE)


def cache_marche_utilisable(moment=None, marche=None):
    """Le rattrapage au démarrage ne scrape pas : ce cache, ou rien."""
    moment = _en_utc(moment)
    if not pret_pour_cloture(moment):
        return False
    if marche is None:
        from market_data import load_market_cache
        marche = load_market_cache()
    return _marche_est_la_cloture(marche, moment.date())


def _instant_cloture(jour):
    return datetime(
        jour.year, jour.month, jour.day,
        CLOTURE_HEURE, CLOTURE_MINUTE, tzinfo=timezone.utc,
    )


def _cache_couvre_la_seance(marche, jour):
    moment = _horodatage(marche.get("updated_at") if isinstance(marche, dict) else None)
    if moment is None:
        return False
    return moment >= _instant_cloture(jour)


def _date_cible(marche, moment):
    """Date de séance publiée, sinon le jour de l'appel.

    ``session_date`` vient de l'en-tête brvm.org (« 30 septembre 2026 »).
    La page ne publie pas d'autre date de séance. Une valeur illisible
    n'est pas remplacée par aujourd'hui : on refuse d'écrire.
    """
    if not isinstance(marche, dict) or marche.get("session_date") in (None, ""):
        return moment.date()
    brut = marche.get("session_date")
    if not isinstance(brut, str):
        return None
    try:
        return datetime.strptime(brut[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


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


def _seance_avant(seances, jour):
    avant = [
        seance for seance in seances
        if isinstance(seance, dict) and isinstance(seance.get("date"), str) and seance["date"] < jour
    ]
    if not avant:
        return None
    return max(avant, key=lambda seance: seance["date"])


def _acquerir_verrou(verrou, delai_s):
    """LOCK_EX non bloquant, réessayé jusqu'à ``delai_s`` secondes."""
    echeance = time.monotonic() + delai_s
    while True:
        try:
            fcntl.flock(verrou.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            reste = echeance - time.monotonic()
            if reste <= 0:
                return False
            time.sleep(min(_PAUSE_VERROU_S, reste))


def _fusionner_indices(existante, indices):
    dest = existante.get("indices")
    if not isinstance(dest, dict):
        dest = {}
        existante["indices"] = dest
    ajoute = False
    for code, valeur in indices.items():
        if code in dest:
            continue
        dest[code] = valeur
        ajoute = True
    return ajoute


def _fusionner_societes(existante, nouvelles):
    """Ajoute les tickers absents. Ne remplace pas une ligne déjà écrite."""
    deja = existante.get("societes")
    if not isinstance(deja, list):
        deja = []
    par = {}
    ordre = []
    for row in deja:
        if not isinstance(row, dict) or not isinstance(row.get("ticker"), str):
            continue
        ticker = row["ticker"]
        if ticker in par:
            continue
        par[ticker] = row
        ordre.append(ticker)
    ajoute = False
    for row in nouvelles:
        ticker = row["ticker"]
        if ticker in par:
            continue
        par[ticker] = row
        ordre.append(ticker)
        ajoute = True
    if ajoute:
        fusion = [par[ticker] for ticker in ordre]
        fusion.sort(key=lambda row: (row.get("rang") if isinstance(row.get("rang"), int) else 9999, row["ticker"]))
        existante["societes"] = fusion
    return ajoute


def _appliquer(iso, indices, societes):
    try:
        data = _charger_strict()
    except Exception as exc:
        logger.error("index history illisible, ecriture annulee: %s", exc)
        return _statut("fichier_illisible", iso)
    seances = data["seances"]
    precedente = _seance_avant(seances, iso)
    gardes, ecartes = filtrer_ecart(indices, precedente)
    if ecartes:
        logger.info("index history: indice hors ecart ignore (%s)", ",".join(ecartes))
    existante = _seance_existante(seances, iso)
    if existante is None and reprise_de_la_veille(gardes, precedente):
        logger.info("index history: reprise de la veille, %s non ouvert", iso)
        return _statut("reprise_veille", iso)
    if not gardes and existante is None:
        logger.info("index history: aucun indice plausible")
        return _statut("indices_aberrants", iso)

    if existante is None:
        seances.append({
            "date": iso,
            "indices": gardes,
            "societes": list(societes),
        })
        seances.sort(key=lambda seance: seance.get("date") or "")
        _ecrire(data)
        logger.info("index history: %s enregistre (%s)", iso, ",".join(sorted(gardes)))
        return _statut("enregistre", iso)

    indices_ajoutes = _fusionner_indices(existante, gardes)
    societes_ajoutees = _fusionner_societes(existante, societes)
    if indices_ajoutes or societes_ajoutees:
        _ecrire(data)
        if indices_ajoutes:
            logger.info("index history: indices completes pour %s", iso)
            return _statut("indices_completes", iso)
        logger.info("index history: societes completees pour %s", iso)
        return _statut("societes_completees", iso)
    logger.info("index history: %s deja enregistre", iso)
    return _statut("deja_enregistre", iso)


def _sous_verrou(action, delai_s):
    dossier = os.path.dirname(HISTORY_PATH) or "."
    os.makedirs(dossier, exist_ok=True)
    verrou_path = HISTORY_PATH + ".lock"
    verrou = open(verrou_path, "a")
    acquis = False
    try:
        acquis = _acquerir_verrou(verrou, delai_s)
        if not acquis:
            logger.warning(
                "index history abandonne : verrou occupe apres %.0f s (%s)",
                delai_s, verrou_path,
            )
            return None
        return action()
    finally:
        if acquis:
            fcntl.flock(verrou.fileno(), fcntl.LOCK_UN)
        verrou.close()


def enregistrer_cloture(moment=None, marche=None, cours=None,
                        historique_prix=None, classement=None,
                        delai_verrou_s=DELAI_VERROU_S):
    """Enregistre la séance, ou ne touche pas au fichier.

    Les arguments optionnels servent aux tests. En production ils sont lus
    sur le disque : cache marché, cache de cours, historique de prix,
    classement déjà calculé. Un seul process écrit à la fois.
    """
    moment = _en_utc(moment)
    jour_appel = moment.date()
    iso_appel = jour_appel.isoformat()
    if moment.weekday() >= 5:
        logger.info("index history: week-end, rien ecrit")
        return _statut("week-end", iso_appel)
    if not pret_pour_cloture(moment):
        logger.info("index history: avant la cloture, rien ecrit")
        return _statut("avant_cloture", iso_appel)

    cours = _lire_cours(cours)
    historique_prix = _lire_historique_prix(historique_prix)
    if not _seance_confirmee(cours, historique_prix, iso_appel):
        logger.info("index history: pas de seance le %s", iso_appel)
        return _statut("sans_seance", iso_appel)

    marche = _lire_marche(marche)
    if tous_current_egal_prev(marche):
        logger.info("index history: current == prev pour les quatre indices")
        return _statut("reprise_veille", iso_appel)

    jour = _date_cible(marche, moment)
    if jour is None:
        logger.info("index history: session_date illisible")
        return _statut("date_incoherente", iso_appel)
    iso = jour.isoformat()
    if jour.weekday() >= 5:
        logger.info("index history: session_date tombe un week-end")
        return _statut("week-end", iso)
    if jour > jour_appel:
        logger.info("index history: session_date dans le futur")
        return _statut("date_incoherente", iso)
    if not _cache_couvre_la_seance(marche, jour):
        logger.info("index history: cache marche anterieur a la cloture")
        return _statut("marche_perime", iso)

    indices = extraire_indices(marche)
    if not indices:
        logger.info("index history: aucun indice reconnu")
        return _statut("indices_absents", iso)

    societes = extraire_societes(_lire_classement(classement))

    resultat = _sous_verrou(
        lambda: _appliquer(iso, indices, societes),
        delai_verrou_s,
    )
    if resultat is None:
        return _statut("verrou_occupe", iso)
    return resultat


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
