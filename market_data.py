"""
market_data.py — Données marché BRVM depuis brvm.org/fr/resume
Indices, capitalisations, top/flop, secteurs
Refresh automatique intégré au scheduler live_data
"""
import json, logging, os, tempfile, threading, time
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
from paths import DATA_DIR
CACHE_PATH = os.path.join(DATA_DIR, "market_cache.json")
HEADERS    = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Le scrape de brvm.org/fr/resume prend plusieurs secondes. On ne le fait
# plus dans la requete HTTP : memoire + fichier, revalidation en fond.
# 60 s pendant la seance (les indices bougent), 15 min marche ferme.
TTL_SEANCE_S = 60
TTL_FERME_S = 15 * 60
ATTENTE_SCRAPE_S = 20

_verrou = threading.Lock()
_cond = threading.Condition(_verrou)
_memoire = None
_en_cours = False
_dernier_essai = 0.0
_dernier_fil = None

def clean(s):
    return s.replace("\u202f","").replace("\xa0","").replace(" ","").replace(",",".").strip()

def fetch_market_data():
    """Scrape brvm.org/fr/resume — 6 tables de données marché"""
    result = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "market_activity": {},
        "top5": [],
        "flop5": [],
        "indices": [],
        "sector_indices": [],
        "total_return": {},
    }
    try:
        r = requests.get("https://www.brvm.org/fr/resume", headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        tables = soup.find_all("table")

        # Table 0 : Activités du marché
        if len(tables) > 0:
            for row in tables[0].find_all("tr")[1:]:
                cols = row.find_all(["td","th"])
                if len(cols) >= 2:
                    label = cols[0].get_text(strip=True)
                    value = cols[1].get_text(strip=True)
                    result["market_activity"][label] = value

        # Détecter dynamiquement les tables Top5/Flop5/market_activity
        for i, table in enumerate(tables):
            headers = [th.get_text(strip=True) for th in table.find_all("th")]
            first_header = headers[0] if headers else ""

            if "Top 5" in first_header or "Top5" in first_header:
                for row in table.find_all("tr")[1:]:
                    cols = row.find_all(["td","th"])
                    if len(cols) >= 3:
                        try:
                            result["top5"].append({
                                "ticker": cols[0].get_text(strip=True).upper(),
                                "price":  float(clean(cols[1].get_text(strip=True))),
                                "change": float(clean(cols[2].get_text(strip=True)).replace("%","")),
                            })
                        except: pass

            elif "Flop 5" in first_header or "Flop5" in first_header:
                for row in table.find_all("tr")[1:]:
                    cols = row.find_all(["td","th"])
                    if len(cols) >= 3:
                        try:
                            result["flop5"].append({
                                "ticker": cols[0].get_text(strip=True).upper(),
                                "price":  float(clean(cols[1].get_text(strip=True))),
                                "change": float(clean(cols[2].get_text(strip=True)).replace("%","")),
                            })
                        except: pass

            elif "Activit" in first_header or len(cols if (cols:=table.find_all("td")) else []) and "Capitalisation" in table.get_text():
                for row in table.find_all("tr"):
                    cols = row.find_all(["td","th"])
                    if len(cols) >= 2:
                        label = cols[0].get_text(strip=True)
                        value = cols[1].get_text(strip=True)
                        if label:
                            result["market_activity"][label] = value

        # Table 3 : Indices BRVM
        if len(tables) > 3:
            for row in tables[3].find_all("tr")[1:]:
                cols = row.find_all(["td","th"])
                if len(cols) >= 4:
                    try:
                        result["indices"].append({
                            "name":    cols[0].get_text(strip=True),
                            "prev":    float(clean(cols[1].get_text(strip=True))),
                            "current": float(clean(cols[2].get_text(strip=True))),
                            "change":  float(clean(cols[3].get_text(strip=True)).replace("%","")),
                            "ytd":     float(clean(cols[4].get_text(strip=True)).replace("%","")) if len(cols)>4 else 0,
                        })
                    except: pass

        # Table 4 : Indices sectoriels
        if len(tables) > 4:
            for row in tables[4].find_all("tr")[1:]:
                cols = row.find_all(["td","th"])
                if len(cols) >= 4:
                    try:
                        result["sector_indices"].append({
                            "name":    cols[0].get_text(strip=True).replace("BRVM – ",""),
                            "prev":    float(clean(cols[1].get_text(strip=True))),
                            "current": float(clean(cols[2].get_text(strip=True))),
                            "change":  float(clean(cols[3].get_text(strip=True)).replace("%","")),
                            "ytd":     float(clean(cols[4].get_text(strip=True)).replace("%","")) if len(cols)>4 else 0,
                        })
                    except: pass

        # Table 5 : Total return
        if len(tables) > 5:
            for row in tables[5].find_all("tr")[1:]:
                cols = row.find_all(["td","th"])
                if len(cols) >= 3:
                    try:
                        result["total_return"] = {
                            "name":    cols[0].get_text(strip=True),
                            "prev":    float(clean(cols[1].get_text(strip=True))),
                            "current": float(clean(cols[2].get_text(strip=True))),
                            "change":  float(clean(cols[3].get_text(strip=True)).replace("%","")) if len(cols)>3 else 0,
                        }
                    except: pass

        logger.info(f"market_data: top5={len(result['top5'])} flop5={len(result['flop5'])} indices={len(result['indices'])}")
    except Exception as e:
        logger.warning(f"market_data erreur: {e}")
    return result

def save_market_cache(data):
    dossier = os.path.dirname(CACHE_PATH)
    os.makedirs(dossier, exist_ok=True)
    tmp_path = None
    try:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=dossier, delete=False
        )
        tmp_path = tmp.name
        with tmp:
            json.dump(data, tmp, indent=2, ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, CACHE_PATH)
    except Exception:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    return data

def load_market_cache():
    if not os.path.exists(CACHE_PATH): return None
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _maintenant():
    return datetime.now(timezone.utc)

def _ttl_secondes(moment=None):
    from live_data import is_market_open_at
    moment = moment or _maintenant()
    if is_market_open_at(moment):
        return TTL_SEANCE_S
    return TTL_FERME_S

def _age_secondes(data, moment=None):
    if not isinstance(data, dict):
        return None
    brut = data.get("updated_at")
    if not brut:
        return None
    try:
        horodatage = datetime.fromisoformat(brut)
    except (TypeError, ValueError):
        return None
    if horodatage.tzinfo is None:
        horodatage = horodatage.replace(tzinfo=timezone.utc)
    moment = moment or _maintenant()
    return (moment - horodatage).total_seconds()

def _est_frais(data, moment=None):
    moment = moment or _maintenant()
    age = _age_secondes(data, moment)
    if age is None:
        return False
    return age < _ttl_secondes(moment)

def _donnees_utiles(data):
    if not isinstance(data, dict):
        return False
    if data.get("indices") or data.get("top5") or data.get("flop5"):
        return True
    return bool(data.get("market_activity"))

def _lire():
    """Memoire si elle est fraiche, sinon le fichier (partage entre workers)."""
    global _memoire
    with _verrou:
        mem = _memoire
    if mem is not None and _est_frais(mem):
        return mem
    disque = load_market_cache()
    if not isinstance(disque, dict):
        return mem
    age_disque = _age_secondes(disque)
    age_mem = _age_secondes(mem) if mem is not None else None
    if age_mem is None or (age_disque is not None and age_disque < age_mem):
        with _verrou:
            actuel = _memoire
            age_actuel = _age_secondes(actuel) if actuel is not None else None
            if age_actuel is None or (age_disque is not None and age_disque < age_actuel):
                _memoire = disque
            return _memoire
    return mem

def _ecrire(data):
    global _memoire
    sauve = save_market_cache(data)
    with _verrou:
        _memoire = sauve
    return sauve

def _faire():
    try:
        nouveau = fetch_market_data()
    except Exception as e:
        logger.warning("market_data: scrape interrompu: %s", e)
        nouveau = None
    actuel = _lire()
    if not _donnees_utiles(nouveau):
        if _donnees_utiles(actuel):
            logger.warning("market_data: scrape sans donnees, cache precedent conserve")
            return actuel
        if isinstance(nouveau, dict):
            return _ecrire(nouveau)
        return actuel
    return _ecrire(nouveau)

def _fil_rafraichissement():
    global _en_cours
    try:
        _faire()
    except Exception:
        logger.exception("market_data: rafraichissement en arriere-plan")
    finally:
        with _cond:
            _en_cours = False
            _cond.notify_all()

def _lancer(bloquant, ignorer_cooldown=False):
    """Un seul scrape a la fois. Retourne False si un scrape est deja en cours
    ou si le delai minimum depuis le dernier essai n'est pas ecoule."""
    global _en_cours, _dernier_essai, _dernier_fil
    with _cond:
        if _en_cours:
            if bloquant:
                _cond.wait(timeout=ATTENTE_SCRAPE_S)
            return False
        if (
            not ignorer_cooldown
            and _dernier_essai
            and (time.monotonic() - _dernier_essai) < _ttl_secondes()
        ):
            return False
        _en_cours = True
        _dernier_essai = time.monotonic()
        if not bloquant:
            fil = threading.Thread(
                target=_fil_rafraichissement, name="market-refresh", daemon=True
            )
            _dernier_fil = fil
            fil.start()
            return True
    try:
        _faire()
    finally:
        with _cond:
            _en_cours = False
            _cond.notify_all()
    return True

def get_market_data(force_refresh=False, synchroniser=False):
    """Donnees marche. Le JSON renvoye est celui du scrape (ou du cache), sans champ ajoute.

    Cache frais : retour immediat.
    Cache perime : retour immediat (stale-while-revalidate) et scrape en fond.
    Pas de cache : un seul scrape, la requete attend.
    synchroniser=True (planificateur, script) attend la fin du scrape.
    """
    data = _lire()
    if data and _est_frais(data) and not force_refresh:
        return data
    if data and not synchroniser:
        _lancer(bloquant=False, ignorer_cooldown=False)
        return data
    _lancer(bloquant=True, ignorer_cooldown=True)
    frais = _lire()
    if frais is not None:
        return frais
    return data or {
        "updated_at": _maintenant().isoformat(),
        "market_activity": {},
        "top5": [],
        "flop5": [],
        "indices": [],
        "sector_indices": [],
        "total_return": {},
    }

def preparer_cache_marche():
    """Au demarrage du serveur : remplit le cache hors de la premiere requete."""
    def _run():
        try:
            get_market_data()
        except Exception as e:
            logger.warning("market_data: prechauffage ignore: %s", e)
    threading.Thread(target=_run, name="market-warmup", daemon=True).start()

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    d = get_market_data(force_refresh=True, synchroniser=True)
    print(f"\nActivités: {d['market_activity']}")
    print(f"Top 5: {d['top5']}")
    print(f"Flop 5: {d['flop5']}")
    print(f"Indices: {d['indices']}")
    print(f"Secteurs: {d['sector_indices']}")
