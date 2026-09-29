# -*- coding: utf-8 -*-
"""Prix cible, écart en % et libellé, calculés ensemble.

À côté de verdict.py (note et conseil). Cette fonction ne lit pas le
disque et ne change ni la note ni le conseil : elle ne fait que dire
si le cours est loin du prix estimé.

Règle unique :
- EPV = BNA / 0,10, si le BNA est positif.
- Graham = racine de (22,5 × BNA × BVPA), si les deux sont positifs.
- P/B = BVPA × (ROE / 10), si les deux sont positifs.
- Prix cible = moyenne des modèles disponibles, arrondie.
- Écart % = (prix cible / cours − 1) × 100, arrondi au dixième.
- Le libellé lit CET écart, pas un autre chiffre :
  plus de 30 % → « Fort potentiel »
  plus de 10 % → « Potentiel modéré »
  de −10 % à +10 % → « Proche valeur juste »
  en dessous de −10 % → « Trop cher »
- Écart trop grand pour être cru (|écart| > 80 %, ou > 50 % avec un
  seul modèle) → « incertain ». Le prix reste affiché, le libellé
  ne dit pas que c'est proche.
- Dividende exceptionnel : pas de prix cible, libellé « exceptional_div ».
- Pas assez de données : pas de prix, pas de libellé. On ne dit pas
  « Proche valeur juste » sans chiffre.
"""

LIBELLE_FORT = "Fort potentiel"
LIBELLE_MODERE = "Potentiel modéré"
LIBELLE_PROCHE = "Proche valeur juste"
LIBELLE_CHER = "Trop cher"
LIBELLE_INCERTAIN = "incertain"
LIBELLE_EXCEPT = "exceptional_div"

# Bornes lues sur l'écart déjà arrondi au dixième, le même que l'écran.
SEUIL_FORT = 30.0
SEUIL_MODERE = 10.0
SEUIL_PROCHE_BAS = -10.0
SEUIL_INCERTAIN = 80.0
SEUIL_INCERTAIN_UN_MODELE = 50.0

_COUT_CAPITAL = 0.10
_GRAHAM = 22.5


def estimer_prix_cible(ligne):
    """Retourne prix, écart et libellé pour une ligne de classement.

    Le dictionnaire contient aussi les trois modèles (epv, graham, pb),
    le nombre de modèles, et deux drapeaux. Aucune clé de note ou de
    conseil n'est lue pour décider, ni écrite.
    """
    if not isinstance(ligne, dict):
        ligne = {}
    epv, graham, pb = _trois_modeles(ligne)
    exceptionnel = _dividende_exceptionnel(ligne)
    if exceptionnel:
        return _paquet(epv, graham, pb, None, None, LIBELLE_EXCEPT, 0, False, True)

    disponibles = [v for v in (epv, graham, pb) if v]
    n = len(disponibles)
    cible = round(sum(disponibles) / float(n)) if n else None
    cours = _positif(ligne.get("price"))
    ecart = None
    if cible and cours:
        ecart = round((float(cible) / cours - 1.0) * 100.0, 1)
    incertain = _est_incertain(ecart, n)
    return _paquet(
        epv, graham, pb, cible, ecart,
        _libelle(ecart, incertain), n, incertain, False,
    )


def _trois_modeles(ligne):
    bna = _positif(ligne.get("eps_est") or ligne.get("eps") or ligne.get("bna"))
    bvpa = _positif(ligne.get("book_value_per_share") or ligne.get("bvpa"))
    roe = _positif(ligne.get("roe"))
    epv = round(bna / _COUT_CAPITAL) if bna else None
    graham = round((_GRAHAM * bna * bvpa) ** 0.5) if bna and bvpa else None
    pb = round(bvpa * (roe / 10.0)) if bvpa and roe else None
    return epv, graham, pb


def _dividende_exceptionnel(ligne):
    return bool(
        ligne.get("div_is_exceptional")
        or ligne.get("div_flag") == "exceptionnel_non_recurrent"
    )


def _est_incertain(ecart, n_modeles):
    if ecart is None:
        return False
    if abs(ecart) > SEUIL_INCERTAIN:
        return True
    return n_modeles == 1 and abs(ecart) > SEUIL_INCERTAIN_UN_MODELE


def _libelle(ecart, incertain):
    if incertain:
        return LIBELLE_INCERTAIN
    if ecart is None:
        return None
    if ecart > SEUIL_FORT:
        return LIBELLE_FORT
    if ecart > SEUIL_MODERE:
        return LIBELLE_MODERE
    if ecart >= SEUIL_PROCHE_BAS:
        return LIBELLE_PROCHE
    return LIBELLE_CHER


def _paquet(epv, graham, pb, cible, ecart, libelle, n, incertain, exceptionnel):
    return {
        "epv": epv,
        "graham": graham,
        "pb": pb,
        "prix_cible": cible,
        "ecart_pct": ecart,
        "libelle": libelle,
        "n_modeles": n,
        "incertain": incertain,
        "dividende_exceptionnel": exceptionnel,
    }


def _positif(valeur):
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    if valeur != valeur or valeur in (float("inf"), float("-inf")):
        return None
    if valeur <= 0:
        return None
    return float(valeur)
