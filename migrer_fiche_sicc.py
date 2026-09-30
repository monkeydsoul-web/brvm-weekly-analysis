# -*- coding: utf-8 -*-
"""Recopie stories/sicc.json dans l'entrée SICC du fichier disque.

Le fichier ``companies_stories.json`` généré le 30 mai 2026 décrit encore
SICC comme un câblier (Sicable). La fiche versionnée ``stories/sicc.json``
décrit SICOR (coco râpé). Cette migration écrit cette fiche dans la seule
clé SICC. Elle ne relance pas ``scripts/generate_company_stories.py`` et
ne modifie aucune autre société, ni ``_meta``.

Idempotente : si SICC est déjà cette fiche, aucun fichier n'est réécrit
et aucune sauvegarde n'est ajoutée. Sinon, copie horodatée du fichier
entier, puis remplacement atomique (fichier temporaire dans le même
dossier, fsync, ``os.replace``).

Au démarrage de l'application (gunicorn importe ``app``), voir ``_init_app``.
L'appel est avant le court-circuit ``BRVM_DISABLE_SCHEDULER`` : ce drapeau
coupe le planificateur, pas cette correction disque. Le verrou est pris
en ``LOCK_NB`` ; au bout de 10 s la migration s'arrête, logue, et le
process continue.
À la main, depuis la racine du dépôt, une fois ou après un échec :

    python3 migrer_fiche_sicc.py --data-dir /var/data

La route ``/data/companies_stories.json`` continue d'écraser SICC avec
``stories/sicc.json`` : le disque Render n'est relu qu'après le déploiement.
L'écrasement et cette migration lisent la même fiche. On retire l'écrasement
seulement quand une lecture du fichier disque montre que SICC parle de coco,
pas de câbles.
"""

import argparse
import fcntl
import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.abspath(__file__))
FICHE_SICC = os.path.join(ROOT, "stories", "sicc.json")
NOM_FICHIER = "companies_stories.json"
DELAI_VERROU_S = 10.0
_PAUSE_VERROU_S = 0.05

_RAISONS_ECHEC = (
    "json_illisible",
    "structure_inattendue",
    "fiche_absente",
    "fiche_illisible",
    "verrou_occupe",
)


def _resultat(modifie, raison, sauvegarde, chemin):
    return {
        "modifie": modifie,
        "raison": raison,
        "sauvegarde": sauvegarde,
        "chemin": chemin,
    }


def _data_dir():
    from paths import DATA_DIR
    return DATA_DIR


def _charger_fiche():
    if not os.path.isfile(FICHE_SICC):
        return None, "fiche_absente"
    try:
        with open(FICHE_SICC, encoding="utf-8") as fichier:
            fiche = json.load(fichier)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "fiche_illisible"
    if not isinstance(fiche, dict):
        return None, "fiche_illisible"
    return fiche, None


def _ecrire_sauvegarde(chemin, brut):
    """Copie octet pour octet, horodatée en UTC, écrite atomiquement."""
    horodatage = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    dest = "%s.bak-%s" % (chemin, horodatage)
    n = 2
    while os.path.exists(dest):
        dest = "%s.bak-%s-%d" % (chemin, horodatage, n)
        n += 1
    dossier = os.path.dirname(chemin) or "."
    tmp_fd, tmp_path = tempfile.mkstemp(dir=dossier, suffix=".bak.tmp")
    try:
        with os.fdopen(tmp_fd, "wb") as tmp:
            tmp.write(brut)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, dest)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return dest


def _ecrire_atomique(chemin, payload):
    dossier = os.path.dirname(chemin) or "."
    tmp_fd, tmp_path = tempfile.mkstemp(dir=dossier, suffix=".json.tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp:
            json.dump(payload, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, chemin)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _appliquer(chemin, fiche):
    if not os.path.isfile(chemin):
        return _resultat(False, "fichier_absent", None, chemin)
    with open(chemin, "rb") as fichier:
        brut = fichier.read()
    try:
        payload = json.loads(brut.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return _resultat(False, "json_illisible", None, chemin)
    if not isinstance(payload, dict):
        return _resultat(False, "structure_inattendue", None, chemin)
    stories = payload.get("stories")
    if not isinstance(stories, dict):
        return _resultat(False, "structure_inattendue", None, chemin)
    if stories.get("SICC") == fiche:
        return _resultat(False, "deja_a_jour", None, chemin)
    sauvegarde = _ecrire_sauvegarde(chemin, brut)
    stories["SICC"] = json.loads(json.dumps(fiche, ensure_ascii=False))
    _ecrire_atomique(chemin, payload)
    return _resultat(True, "migre", sauvegarde, chemin)


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


def migrer_fiche_sicc(data_dir=None, delai_verrou_s=DELAI_VERROU_S):
    """Recopie la fiche SICOR dans SICC, ou ne fait rien si c'est déjà le cas.

    ``data_dir`` est le dossier du disque (``BRVM_DATA_DIR`` en production,
    souvent ``/var/data`` ou ``/data``). Sans argument, ``paths.DATA_DIR``.
    Si le verrou reste pris pendant ``delai_verrou_s`` secondes, la fonction
    logue un avertissement et retourne sans écrire.
    """
    dossier = data_dir if data_dir else _data_dir()
    chemin = os.path.join(dossier, NOM_FICHIER)
    if not os.path.isfile(chemin):
        return _resultat(False, "fichier_absent", None, chemin)
    fiche, erreur = _charger_fiche()
    if erreur:
        return _resultat(False, erreur, None, chemin)
    verrou_path = chemin + ".lock"
    verrou = open(verrou_path, "a")
    acquis = False
    try:
        acquis = _acquerir_verrou(verrou, delai_verrou_s)
        if not acquis:
            logger.warning(
                "Migration fiche SICC abandonnée : verrou occupé après %.0f s (%s)",
                delai_verrou_s,
                verrou_path,
            )
            return _resultat(False, "verrou_occupe", None, chemin)
        return _appliquer(chemin, fiche)
    finally:
        if acquis:
            fcntl.flock(verrou.fileno(), fcntl.LOCK_UN)
        verrou.close()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Recopie stories/sicc.json dans l'entrée SICC de "
            "companies_stories.json. Idempotent. Ne modifie aucune autre "
            "société. Sauvegarde horodatée, puis écriture atomique. "
            "Le même traitement tourne au démarrage de l'application."
        ),
        epilog=(
            "Vérification en production : lire le fichier disque "
            "(BRVM_DATA_DIR, sinon /var/data ou /data), pas la réponse HTTP. "
            "La route écrase encore SICC. Attendu : en_bref parle de coco, "
            "pas de câbles ; une sauvegarde companies_stories.json.bak-* ; "
            "la seule société différente entre la sauvegarde et le fichier "
            "est SICC. Ne pas relancer scripts/generate_company_stories.py."
        ),
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Dossier du fichier disque. Défaut : BRVM_DATA_DIR, sinon data/.",
    )
    args = parser.parse_args(argv)
    resultat = migrer_fiche_sicc(args.data_dir)
    print(json.dumps(resultat, ensure_ascii=False, indent=2))
    if resultat["raison"] in _RAISONS_ECHEC or resultat["raison"] == "fichier_absent":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
