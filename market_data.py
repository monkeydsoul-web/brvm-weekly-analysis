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
# Apres un scrape vide ou une exception : nouvel essai, sans ecrire le squelette.
DELAI_NOUVEL_ESSAI_S = 30
ATTENTE_SCRAPE_S = 20
# Meme fourchette que le contexte macro : un indice BRVM hors de la plage
# n'est pas une cotation utilisable.
_INDICE_MIN = 50
_INDICE_MAX = 5000

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

def _indice_plausible(item):
    if not isinstance(item, dict):
        return False
    nom = item.get("name")
    if not isinstance(nom, str) or not nom.strip():
        return False
    courant = item.get("current")
    if isinstance(courant, bool) or not isinstance(courant, (int, float)):
        return False
    return _INDICE_MIN <= float(courant) <= _INDICE_MAX


def _scrape_utile(data):
    """Un scrape n'est gardable que s'il contient au moins un indice plausible."""
    if not isinstance(data, dict):
        return False
    indices = data.get("indices")
    if not isinstance(indices, list) or not indices:
        return False
    return any(_indice_plausible(item) for item in indices)


def _squelette():
    return {
        "updated_at": _maintenant().isoformat(),
        "market_activity": {},
        "top5": [],
        "flop5": [],
        "indices": [],
        "sector_indices": [],
        "total_return": {},
    }


def save_market_cache(data):
    if not _scrape_utile(data):
        logger.warning("market_data: ecriture refusee, indices absents ou non plausibles")
        return data
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
    if not _scrape_utile(data):
        return False
    moment = moment or _maintenant()
    age = _age_secondes(data, moment)
    if age is None:
        return False
    return age < _ttl_secondes(moment)

def _plus_jeune(a, b):
    """Vrai si a est au moins aussi recent que b."""
    age_a = _age_secondes(a)
    age_b = _age_secondes(b)
    if age_a is None:
        return False
    if age_b is None:
        return True
    return age_a <= age_b

def _liste_garde(ancienne, nouvelle, cle):
    """Ne remplace jamais une liste non vide par une liste vide."""
    if cle == "indices":
        if isinstance(nouvelle, list) and any(_indice_plausible(item) for item in nouvelle):
            return nouvelle
        if isinstance(ancienne, list) and ancienne:
            return ancienne
        return nouvelle if isinstance(nouvelle, list) else []
    if isinstance(nouvelle, list) and nouvelle:
        return nouvelle
    if isinstance(ancienne, list) and ancienne:
        return ancienne
    return nouvelle if isinstance(nouvelle, list) else (ancienne if isinstance(ancienne, list) else [])

def _fusionner(actuel, nouveau):
    """Reprend le cache utile et n'y pose que les champs non vides du scrape."""
    fusion = dict(actuel)
    for cle in ("top5", "flop5", "indices", "sector_indices"):
        fusion[cle] = _liste_garde(actuel.get(cle), nouveau.get(cle), cle)
    activite = nouveau.get("market_activity")
    if isinstance(activite, dict) and activite:
        base = dict(actuel.get("market_activity") or {})
        for cle, valeur in activite.items():
            if valeur not in (None, ""):
                base[cle] = valeur
        fusion["market_activity"] = base
    retour = nouveau.get("total_return")
    if isinstance(retour, dict) and retour:
        fusion["total_return"] = retour
    if _scrape_utile(nouveau) and nouveau.get("updated_at"):
        fusion["updated_at"] = nouveau["updated_at"]
    return fusion

def _retirer_cache_inutile():
    if not os.path.exists(CACHE_PATH):
        return
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    if _scrape_utile(data):
        return
    try:
        os.remove(CACHE_PATH)
        logger.warning("market_data: cache disque sans indices retiré")
    except OSError:
        pass

def _lire():
    """Memoire fraiche et utile, sinon le fichier s'il a des indices."""
    global _memoire
    with _verrou:
        mem = _memoire
    if _scrape_utile(mem) and _est_frais(mem):
        return mem
    _retirer_cache_inutile()
    disque = load_market_cache()
    if not _scrape_utile(disque):
        disque = None
    if _scrape_utile(mem) and (disque is None or _plus_jeune(mem, disque)):
        return mem
    if disque is not None:
        with _verrou:
            actuel = _memoire
            if not _scrape_utile(actuel) or _plus_jeune(disque, actuel):
                _memoire = disque
            return _memoire if _scrape_utile(_memoire) else disque
    return mem if isinstance(mem, dict) else None

def _memoriser(data):
    """Squelette ou echec : memoire seule, jamais le disque."""
    global _memoire
    with _verrou:
        _memoire = data
    return data

def _ecrire(data):
    global _memoire
    if not _scrape_utile(data):
        return _memoriser(data)
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
    if not isinstance(nouveau, dict) or not _scrape_utile(nouveau):
        if _scrape_utile(actuel) and isinstance(nouveau, dict):
            fusion = _fusionner(actuel, nouveau)
            if fusion != actuel and _scrape_utile(fusion):
                return _ecrire(fusion)
            logger.warning("market_data: scrape sans indices, cache precedent conserve")
            return actuel
        if _scrape_utile(actuel):
            logger.warning("market_data: scrape interrompu, cache precedent conserve")
            return actuel
        return _memoriser(nouveau if isinstance(nouveau, dict) else _squelette())
    if _scrape_utile(actuel):
        return _ecrire(_fusionner(actuel, nouveau))
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
            and (time.monotonic() - _dernier_essai) < DELAI_NOUVEL_ESSAI_S
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
