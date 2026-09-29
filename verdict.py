# -*- coding: utf-8 -*-
"""Source unique de la note /10, du conseil et de la couleur.

Le composite reste interne, sur 80. La note affichee est composite / 8.
Aucune lecture disque, aucun reseau : PR-05 (gel a la cloture) pourra
rappeler ces fonctions avec un composite deja fige, sans les modifier.

Decisions encodees ici :
- D-1 : trois niveaux sur les seuils 60 / 40 du composite.
  "Intéressant" (>= 60), "À surveiller" (40 inclus, 60 exclus),
  "Prudence" (< 40). Une valeur suspendue ou non notee n'a pas de conseil.
- D-2 : l'amortisseur historique est conserve (57,6 / 37,6 / 42,4).
  Les anciens jetons acheter / attendre / eviter restent reconnus comme
  conseil precedent, pour le fichier deja en production.
"""

import math

STATUT_COTE = "cote"
STATUT_SUSPENDU = "suspendu"
STATUT_NON_NOTE = "non_note"

CONSEIL_INTERESSANT = "Intéressant"
CONSEIL_SURVEILLER = "À surveiller"
CONSEIL_PRUDENCE = "Prudence"

COULEUR_VERT = "vert"
COULEUR_ORANGE = "orange"
COULEUR_ROUGE = "rouge"

# Bornes de couleur sur la note affichee /10 (7,5 et 5).
SEUIL_COULEUR_VERT = 7.5
SEUIL_COULEUR_ORANGE = 5.0

# Bornes du conseil sur le composite /80, et amortisseur historique.
# Literaux (pas 60 * 0,96) : 60 * 0,96 vaut 57,5999... en flottant.
SEUIL_HAUT = 60.0
SEUIL_BAS = 40.0
BANDE_RESTER_HAUT = 57.6
BANDE_SORTIR_MILIEU = 37.6
BANDE_SORTIR_BAS = 42.4

_ABSENT = object()

_STATUTS = {
    "cote": STATUT_COTE,
    "coté": STATUT_COTE,
    "cotee": STATUT_COTE,
    "cotée": STATUT_COTE,
    "suspendu": STATUT_SUSPENDU,
    "suspendue": STATUT_SUSPENDU,
    "suspended": STATUT_SUSPENDU,
    "non_note": STATUT_NON_NOTE,
    "non note": STATUT_NON_NOTE,
    "non_noté": STATUT_NON_NOTE,
    "non_notee": STATUT_NON_NOTE,
    "non noté": STATUT_NON_NOTE,
    "non notee": STATUT_NON_NOTE,
}

_HAUT = ("acheter", "interessant", "intéressant")
_MILIEU = ("attendre", "surveiller", "a surveiller", "à surveiller")
_BAS = ("eviter", "éviter", "prudence")


def note10(composite):
    """Note affichee /10 = composite / 8.

    Meme arrondi que v10fmt du navigateur : Math.round(v/8*10)/10
    (moitie superieure), pas l'arrondi bancaire de round() en Python 3.
    """
    valeur = _flottant(composite)
    if valeur is None:
        return None
    return math.floor(valeur / 8.0 * 10.0 + 0.5) / 10.0


def conseil(composite, precedent, statut):
    """Conseil D-1, avec l'amortisseur D-2.

    Retourne None si le statut n'est pas "cote" (suspendu, non note,
    absent ou inconnu) : pas de conseil sans cotation exploitable.
    `precedent` accepte le libelle courant ou l'ancien jeton
    (acheter / attendre / eviter).
    """
    if normaliser_statut(statut) != STATUT_COTE:
        return None
    adj = _flottant(composite)
    if adj is None:
        return None

    standard = _conseil_brut(adj)
    famille = _famille(precedent)
    if famille == "haut":
        if adj >= BANDE_RESTER_HAUT:
            return CONSEIL_INTERESSANT
        return standard
    if famille == "milieu":
        if adj >= SEUIL_HAUT:
            return CONSEIL_INTERESSANT
        if adj < BANDE_SORTIR_MILIEU:
            return CONSEIL_PRUDENCE
        return CONSEIL_SURVEILLER
    if famille == "bas":
        if adj < BANDE_SORTIR_BAS:
            return CONSEIL_PRUDENCE
        return standard
    return standard


def libelle_conseil(code=_ABSENT):
    """Libelle affiche.

    Sans argument : les trois libelles officiels, du plus haut au plus bas.
    Avec un code (libelle ou ancien jeton) : le libelle, ou None.
    """
    if code is _ABSENT:
        return (CONSEIL_INTERESSANT, CONSEIL_SURVEILLER, CONSEIL_PRUDENCE)
    if code is None:
        return None
    if code in (CONSEIL_INTERESSANT, CONSEIL_SURVEILLER, CONSEIL_PRUDENCE):
        return code
    famille = _famille(code)
    if famille == "haut":
        return CONSEIL_INTERESSANT
    if famille == "milieu":
        return CONSEIL_SURVEILLER
    if famille == "bas":
        return CONSEIL_PRUDENCE
    return None


def couleur(note=_ABSENT):
    """Couleur de la note /10 : vert >= 7,5, orange >= 5, rouge en dessous.

    Sans argument : le couple de seuils (vert, orange).
    """
    if note is _ABSENT:
        return (SEUIL_COULEUR_VERT, SEUIL_COULEUR_ORANGE)
    valeur = _flottant(note)
    if valeur is None:
        return None
    if valeur >= SEUIL_COULEUR_VERT:
        return COULEUR_VERT
    if valeur >= SEUIL_COULEUR_ORANGE:
        return COULEUR_ORANGE
    return COULEUR_ROUGE


def normaliser_statut(statut):
    """Jeton canonique cote / suspendu / non_note, ou None si inconnu."""
    if not isinstance(statut, str):
        return None
    return _STATUTS.get(statut.strip().lower())


def _conseil_brut(adj):
    if adj >= SEUIL_HAUT:
        return CONSEIL_INTERESSANT
    if adj >= SEUIL_BAS:
        return CONSEIL_SURVEILLER
    return CONSEIL_PRUDENCE


def _famille(precedent):
    if not isinstance(precedent, str):
        return None
    cle = precedent.strip().lower()
    if cle in _HAUT:
        return "haut"
    if cle in _MILIEU:
        return "milieu"
    if cle in _BAS:
        return "bas"
    return None


def _flottant(valeur):
    if valeur is None or isinstance(valeur, bool):
        return None
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return None
    if math.isnan(nombre) or math.isinf(nombre):
        return None
    return nombre
