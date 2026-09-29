# -*- coding: utf-8 -*-
"""Liste manuelle des cotations suspendues (décision D-5 = D).

La liste versionnée ``statuts_cotation.json`` (racine du dépôt, pas
``data/``) est la source de vérité. La détection automatique ne change
jamais un statut ni un conseil : elle remplit seulement ``alerte_cotation``.

Ajouter ou retirer une suspension (le propriétaire demande, l'agent ouvre
une PR ; personne ne commit ``data/*.json``) :

1. Ouvrir ``statuts_cotation.json`` à la racine du dépôt.
2. Pour suspendre : ajouter une clé ticker (ex. ``"SICC"``) avec
   ``statut`` = ``"suspendu"``, ``depuis`` = ``"AAAA-MM-JJ"`` (premier jour),
   ``fin`` = ``null``, ``source`` = titre et URL de l'avis ou de l'article,
   ``note`` = rappel libre pour le propriétaire.
3. Pour lever : poser ``fin`` au dernier jour de suspension. Une ``fin``
   déjà passée (strictement avant le jour du calcul) est ignorée : le titre
   redevient coté. Un ``depuis`` dans le futur ne s'applique pas encore.
   On peut ensuite supprimer la clé.
4. Merger la PR. Le fichier entre dans l'empreinte des faits. L'empreinte
   retient les entrées actives ce jour-là : le lendemain d'une ``fin``,
   ou le jour où un ``depuis`` arrive, la note est recalculée en séance
   même si le fichier n'a pas bougé.

SONOCO Metal Packaging SIEM (ex-Crown SIEM / Eviosys, ISIN CI0000000345)
est le ticker SEMC. Le site l'appelle Crown Siem CI.

Détection (alerte seulement) :
- ``SEANCES_COURS_FIGE`` séances de clôture de suite au même cours, et
  volume 0 quand l'historique porte un volume, → ``cours_fige``.
  Le statut reste ``cote`` et le conseil ne bouge pas.
- Titre listé suspendu : on ne regarde que les séances à partir de
  ``depuis``, comparées à la dernière clôture d'avant ``depuis``.
  Si ce cours a bougé, ``reprise_probable``. Un historique plus ancien
  qui a varié ne déclenche rien.

Lecture des cours : ``price_history_builder.load_history`` (module
protégé, non modifié). ``price_sanity.resolve_price`` garde le dernier
bon prix si le cours live s'écarte de plus de 20 % de la référence, et
peut donc ne jamais écrire un cours aberrant. Cette détection ne passe
pas par ce sas : elle ne voit que les séances déjà enregistrées dans
l'historique. Un vrai mouvement, dans la limite de séance, n'est visible
qu'une fois le point ajouté (job vers 18h00 UTC).
"""

import json
import logging
import os
from datetime import datetime, timezone

from verdict import normaliser_statut

logger = logging.getLogger(__name__)

# Séances de clôture consécutives au même cours avant l'alerte cours_fige.
# 5 séances de Bourse : un trou d'un jour férié sans point enregistré
# ne compte pas, seuls les points d'historique comptent.
SEANCES_COURS_FIGE = 5

CHEMIN_LISTE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "statuts_cotation.json",
)

_CACHE = {"cle": None, "liste": {}}


def invalider_cache():
    """Oublie la liste lue. Les tests s'en servent ; le classement aussi
    si le fichier change de chemin."""
    _CACHE["cle"] = None
    _CACHE["liste"] = {}


def _jour(moment):
    """Date UTC ``AAAA-MM-JJ`` du calcul. ``moment`` vide = maintenant."""
    if moment is None:
        return datetime.now(timezone.utc).date().isoformat()
    if isinstance(moment, datetime):
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        else:
            moment = moment.astimezone(timezone.utc)
        return moment.date().isoformat()
    if isinstance(moment, str) and len(moment) >= 10:
        return moment[:10]
    return datetime.now(timezone.utc).date().isoformat()


def _date_iso(valeur):
    if not isinstance(valeur, str) or len(valeur) < 10:
        return None
    texte = valeur[:10]
    try:
        datetime.strptime(texte, "%Y-%m-%d")
    except ValueError:
        return None
    return texte


def _cle_fichier(chemin):
    try:
        st = os.stat(chemin)
    except OSError:
        return (chemin, None)
    return (chemin, st.st_mtime_ns, st.st_size)


def _valider_entree(ticker, brut):
    if not isinstance(ticker, str) or not ticker.strip():
        return None
    if not isinstance(brut, dict):
        return None
    if normaliser_statut(brut.get("statut")) != "suspendu":
        return None
    depuis = _date_iso(brut.get("depuis"))
    if not depuis:
        return None
    fin_brut = brut.get("fin", None)
    if fin_brut in (None, ""):
        fin = None
    else:
        fin = _date_iso(fin_brut)
        if not fin:
            return None
    source = brut.get("source")
    if not isinstance(source, str):
        source = "" if source is None else str(source)
    return {
        "ticker": ticker.strip().upper(),
        "statut": "suspendu",
        "depuis": depuis,
        "fin": fin,
        "source": source,
    }


def charger_liste(chemin=None):
    """Dict ticker → entrée valide.

    Fichier absent : dict vide et un warning (rien à suspendre).
    Fichier illisible ou qui n'est pas un objet JSON : dict vide et un
    warning. Ne lève pas.
    """
    if chemin is None:
        chemin = CHEMIN_LISTE
    cle = _cle_fichier(chemin)
    if _CACHE["cle"] == cle:
        return _CACHE["liste"]
    liste = _lire_liste(chemin)
    _CACHE["cle"] = cle
    _CACHE["liste"] = liste
    return liste


def _lire_liste(chemin):
    try:
        with open(chemin, encoding="utf-8") as f:
            brut = json.load(f)
    except FileNotFoundError:
        logger.warning(
            "statuts_cotation absent, liste vide: %s",
            os.path.basename(chemin),
        )
        return {}
    except (OSError, ValueError, UnicodeError):
        logger.warning(
            "statuts_cotation illisible, traite comme vide: %s",
            os.path.basename(chemin),
        )
        return {}
    if not isinstance(brut, dict):
        logger.warning(
            "statuts_cotation mal forme (pas un objet), traite comme vide: %s",
            os.path.basename(chemin),
        )
        return {}
    liste = {}
    for ticker, entree in brut.items():
        propre = _valider_entree(ticker, entree)
        if propre is None:
            logger.warning("statuts_cotation: entree ignoree %s", ticker)
            continue
        liste[propre["ticker"]] = propre
    return liste


def _en_vigueur(entree, jour):
    """Active si ``depuis`` est déjà atteint et ``fin`` n'est pas passée.

    ``depuis`` égal au jour : oui. ``depuis`` futur : non.
    ``fin`` égale au jour : encore oui. ``fin`` strictement avant : non.
    """
    depuis = entree.get("depuis")
    if not depuis or depuis > jour:
        return False
    fin = entree.get("fin")
    if fin and fin < jour:
        return False
    return True


def entree_active(ticker, moment=None, chemin=None):
    """Entrée encore en vigueur à ``moment``, ou None."""
    if not isinstance(ticker, str) or not ticker.strip():
        return None
    liste = charger_liste(chemin)
    entree = liste.get(ticker.strip().upper())
    if not entree:
        return None
    if not _en_vigueur(entree, _jour(moment)):
        return None
    return entree


def empreinte_actives(moment=None, chemin=None):
    """Signature des entrées actives ce jour-là.

    Le fichier peut rester identique : le lendemain d'une ``fin``, ou le
    jour où un ``depuis`` tombe, la signature change. Ce n'est pas la date
    toute seule : un jour sans changement d'entrées actives ne bouge pas.
    """
    jour = _jour(moment)
    liste = charger_liste(chemin)
    morceaux = []
    for ticker in sorted(liste):
        entree = liste[ticker]
        if not _en_vigueur(entree, jour):
            continue
        morceaux.append("%s:%s:%s" % (ticker, entree["depuis"], entree.get("fin") or ""))
    if not morceaux:
        return "aucune"
    return ",".join(morceaux)


def statut_de(ticker, moment=None, chemin=None):
    """``suspendu`` si la liste manuelle est active, sinon None.

    None veut dire : la liste ne tranche pas, l'appelant garde le statut
    déduit du prix.
    """
    entree = entree_active(ticker, moment, chemin)
    if not entree:
        return None
    return entree["statut"]


def _volume(point):
    if not isinstance(point, dict) or "volume" not in point:
        return None
    volume = point.get("volume")
    if isinstance(volume, bool) or not isinstance(volume, (int, float)):
        return None
    return volume


def _seances(points, moment=None):
    """Points de séance triés, hors points annuels ``historical``.

    La liste vient de l'appelant (le classement l'a déjà lue avec
    ``price_history_builder.load_history``). None = aucune séance.
    """
    jour = _jour(moment) if moment is not None else None
    propres = []
    for point in points or []:
        if not isinstance(point, dict):
            continue
        if point.get("source") == "historical":
            continue
        date = point.get("date")
        prix = point.get("price")
        if not isinstance(date, str) or len(date) < 10:
            continue
        date = date[:10]
        if jour is not None and date > jour:
            continue
        if isinstance(prix, bool) or not isinstance(prix, (int, float)):
            continue
        if prix <= 0:
            continue
        propres.append({
            "date": date,
            "price": float(prix),
            "volume": _volume(point),
            "_volume_connu": "volume" in point and _volume(point) is not None,
        })
    propres.sort(key=lambda p: p["date"])
    par_date = {}
    for point in propres:
        par_date[point["date"]] = point
    return [par_date[date] for date in sorted(par_date)]


def _serie_finale(seances):
    """Séances finales au même cours que la dernière, de la plus ancienne
    à la plus récente."""
    if not seances:
        return []
    cours = seances[-1]["price"]
    run = []
    for point in reversed(seances):
        if point["price"] != cours:
            break
        run.append(point)
    run.reverse()
    return run


def detecter_alerte(points, suspendu=False, moment=None, depuis=None):
    """None ou ``{type, depuis, seances}``.

    Ne décide pas du statut. ``suspendu`` True cherche ``reprise_probable``
    à partir de ``depuis`` seulement. False cherche ``cours_fige``.
    """
    seances = _seances(points, moment)
    if suspendu:
        return _reprise_probable(seances, depuis)
    return _cours_fige(seances)


def _cours_fige(seances):
    run = _serie_finale(seances)
    if len(run) < SEANCES_COURS_FIGE:
        return None
    # Volume connu et non nul : quelqu'un a traité, le cours n'est pas figé.
    for point in run:
        if point.get("_volume_connu") and point.get("volume") != 0:
            return None
    return {
        "type": "cours_fige",
        "depuis": run[0]["date"],
        "seances": len(run),
    }


def _reprise_probable(seances, depuis):
    """Mouvement à partir de ``depuis``, contre la dernière clôture d'avant.

    Les séances antérieures ne comptent pas : un titre qui a coté normalement
    puis est resté figé après la suspension ne doit pas alerter.
    """
    if not isinstance(depuis, str) or len(depuis) < 10:
        return None
    depuis = depuis[:10]
    avant = [point for point in seances if point["date"] < depuis]
    apres = [point for point in seances if point["date"] >= depuis]
    if not apres:
        return None
    if avant:
        reference = avant[-1]["price"]
        if all(point["price"] == reference for point in apres):
            return None
    else:
        reference = None
        if all(point["price"] == apres[0]["price"] for point in apres):
            return None
    run = _serie_finale(apres)
    if not run:
        return None
    if reference is not None and run[-1]["price"] == reference:
        return None
    return {
        "type": "reprise_probable",
        "depuis": run[0]["date"],
        "seances": len(run),
    }


def appliquer(ligne, points=None, moment=None):
    """Pose les champs de cotation sur une ligne de classement.

    La liste manuelle, si elle est active, force ``statut`` = suspendu et
    retire le conseil. ``note10`` et ``composite_adj`` restent. Retourne
    l'alerte (ou None). Ne lève pas si la liste est illisible.
    """
    if not isinstance(ligne, dict):
        return None
    ticker = ligne.get("ticker")
    try:
        entree = entree_active(ticker, moment)
    except Exception:
        logger.warning("statuts_cotation illisible, liste vide")
        entree = None
    try:
        alerte = detecter_alerte(
            points,
            suspendu=bool(entree),
            moment=moment,
            depuis=entree.get("depuis") if entree else None,
        )
    except Exception:
        logger.warning("detection cotation ignoree pour %s", ticker)
        alerte = None
    if entree:
        ligne["statut"] = "suspendu"
        ligne["conseil"] = None
        ligne["conseil_libelle"] = None
        ligne["conseil_couleur"] = None
        ligne["statut_depuis"] = entree.get("depuis")
        ligne["statut_source"] = entree.get("source") or ""
    else:
        ligne["statut_depuis"] = None
        ligne["statut_source"] = None
    ligne["alerte_cotation"] = alerte
    return alerte


def lire_seances_ticker(ticker, moment=None):
    """Séances d'un ticker lues par ``price_history_builder.load_history``."""
    from price_history_builder import load_history
    historique = load_history()
    points = []
    if isinstance(historique, dict) and isinstance(ticker, str):
        points = historique.get(ticker.strip().upper()) or []
    return _seances(points, moment)
