# -*- coding: utf-8 -*-
"""Source unique de la note /10, du conseil et de la couleur.

Le composite reste interne, sur 80. La note affichee est composite / 8.
Aucune lecture disque, aucun reseau : PR-05 (gel a la cloture) pourra
rappeler ces fonctions avec un composite deja fige, sans les modifier.

Decisions encodees ici :
- D-1 : trois niveaux sur la note affichee /10 (pas le composite brut,
  pour que le mot colle a ce qui est affiche).
  "Intéressant" (note10 >= 7,5), "À surveiller" (note10 >= 5),
  "Prudence" (note10 < 5). Une valeur suspendue ou non notee n'a pas de conseil.
- D-2 : amortisseur sur la meme note /10 : rester Intéressant tant que
  note10 >= 7,2 (57,6/8), quitter À surveiller vers Prudence sous 4,7
  (37,6/8), quitter Prudence des note10 >= 5,3 (42,4/8).
  Les anciens jetons acheter / attendre / eviter restent reconnus comme
  conseil precedent, pour le fichier deja en production.
- La couleur du conseil suit le libelle (vert / orange / rouge).
  couleur() reste la couleur de la note /10, distincte.
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

# Conseil et amortisseur sur la note affichee /10.
# 7,2 / 4,7 / 5,3 = 57,6 / 37,6 / 42,4 divises par 8.
SEUIL_NOTE_HAUT = 7.5
SEUIL_NOTE_BAS = 5.0
BANDE_NOTE_RESTER_HAUT = 7.2
BANDE_NOTE_SORTIR_MILIEU = 4.7
BANDE_NOTE_SORTIR_BAS = 5.3

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
    note = note10(composite)
    if note is None:
        return None

    standard = _conseil_brut(note)
    famille = _famille(precedent)
    if famille == "haut":
        if note >= BANDE_NOTE_RESTER_HAUT:
            return CONSEIL_INTERESSANT
        return standard
    if famille == "milieu":
        if note >= SEUIL_NOTE_HAUT:
            return CONSEIL_INTERESSANT
        if note < BANDE_NOTE_SORTIR_MILIEU:
            return CONSEIL_PRUDENCE
        return CONSEIL_SURVEILLER
    if famille == "bas":
        if note < BANDE_NOTE_SORTIR_BAS:
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


def couleur_conseil(avis):
    """Couleur du libelle. None s'il n'y a pas de conseil.

    Distinct de couleur(), qui colore la note /10.
    """
    if avis is None:
        return None
    libelle = libelle_conseil(avis)
    if libelle == CONSEIL_INTERESSANT:
        return COULEUR_VERT
    if libelle == CONSEIL_SURVEILLER:
        return COULEUR_ORANGE
    if libelle == CONSEIL_PRUDENCE:
        return COULEUR_ROUGE
    return None


def _conseil_brut(note):
    if note >= SEUIL_NOTE_HAUT:
        return CONSEIL_INTERESSANT
    if note >= SEUIL_NOTE_BAS:
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
