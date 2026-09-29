# -*- coding: utf-8 -*-
"""Prix cible, écart en % et libellé, calculés ensemble.

À côté de verdict.py (note et conseil). Cette fonction ne lit pas la
note et n'écrit ni la note ni le conseil.

Règle unique :
- Graham = racine de (22,5 × BNA × BVPA), si les deux sont positifs.
  Cette formule ne dépend pas du secteur.
- EPV = BNA × P/E de référence du secteur. Le P/E de référence est la
  médiane des P/E historiques (pe_hist) des sociétés de ce secteur.
  Ce n'est plus un P/E fixe de 10.
- P/B = BVPA × P/B de référence du secteur. Même idée : médiane des
  P/B historiques (pb_hist). Ce n'est plus BVPA × (ROE / 10), qui
  revenait aussi à un P/E de 10.
- Secteur inconnu, ou sans historique : médiane de toutes les sociétés.
- Prix cible = moyenne des modèles disponibles, arrondie.
- Écart % = (prix cible / cours − 1) × 100, arrondi au dixième.
- Le libellé lit CET écart, pas un autre chiffre :
  plus de +30 % → « Forte décote »
  de +10 % à +30 % → « Décote modérée »
  de −10 % à +10 % → « Proche du prix cible »
  en dessous de −10 % → « Au-dessus du prix cible »
- Écart trop grand pour être cru (|écart| > 80 %, ou > 50 % avec un
  seul modèle) → « incertain », affiché « Cible à vérifier ».
- Dividende exceptionnel : pas de prix cible, libellé « exceptional_div ».
- Pas assez de données : pas de prix, pas de libellé.
"""
import unicodedata


LIBELLE_FORT = "Forte décote"
LIBELLE_MODERE = "Décote modérée"
LIBELLE_PROCHE = "Proche du prix cible"
LIBELLE_CHER = "Au-dessus du prix cible"
LIBELLE_INCERTAIN = "incertain"
LIBELLE_EXCEPT = "exceptional_div"

SEUIL_FORT = 30.0
SEUIL_MODERE = 10.0
SEUIL_PROCHE_BAS = -10.0
SEUIL_INCERTAIN = 80.0
SEUIL_INCERTAIN_UN_MODELE = 50.0

_GRAHAM = 22.5

_reperes_cache = None


def estimer_prix_cible(ligne):
    """Retourne prix, écart et libellé pour une ligne de classement.

    Le dictionnaire contient aussi les trois modèles, le P/E et le P/B
    du secteur utilisés, le nombre de modèles, et deux drapeaux.
    Aucune clé de note ou de conseil n'est lue pour décider, ni écrite.
    """
    if not isinstance(ligne, dict):
        ligne = {}
    pe, pb_mult = multiples_pour(ligne.get("sector"))
    epv, graham, pb = _trois_modeles(ligne, pe, pb_mult)
    exceptionnel = _dividende_exceptionnel(ligne)
    if exceptionnel:
        return _paquet(
            epv, graham, pb, None, None, LIBELLE_EXCEPT, 0, False, True,
            pe, pb_mult,
        )

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
        pe, pb_mult,
    )


def multiples_pour(secteur):
    """P/E et P/B de référence pour ce secteur, ou la médiane globale."""
    table = reperes()
    cle = _cle_secteur(secteur)
    ligne = table["secteurs"].get(cle) if cle else None
    if ligne and ligne.get("pe") and ligne.get("pb"):
        return ligne["pe"], ligne["pb"]
    return table["pe_defaut"], table["pb_defaut"]


def reperes():
    """Médianes pe_hist / pb_hist, calculées une fois sur les 47 sociétés."""
    global _reperes_cache
    if _reperes_cache is None:
        from scraper import STOCK_FUNDAMENTALS
        _reperes_cache = calculer_reperes(STOCK_FUNDAMENTALS)
    return _reperes_cache


def calculer_reperes(fond):
    """Médiane des P/E et P/B historiques, par secteur.

    ``fond`` est un dictionnaire ticker → {sector, pe_hist, pb_hist}.
    On ne lit pas le cours du jour : ces historiques sont les repères
    déjà enregistrés pour chaque société.
    """
    pe_par = {}
    pb_par = {}
    noms = {}
    tous_pe = []
    tous_pb = []
    if not isinstance(fond, dict):
        fond = {}
    for rec in fond.values():
        if not isinstance(rec, dict):
            continue
        nom = rec.get("sector") or ""
        cle = _cle_secteur(nom)
        if not cle:
            continue
        noms.setdefault(cle, nom)
        pe = _positif(rec.get("pe_hist"))
        pb = _positif(rec.get("pb_hist"))
        if pe:
            pe_par.setdefault(cle, []).append(pe)
            tous_pe.append(pe)
        if pb:
            pb_par.setdefault(cle, []).append(pb)
            tous_pb.append(pb)
    secteurs = {}
    for cle, nom in noms.items():
        secteurs[cle] = {
            "secteur": nom,
            "pe": _mediane(pe_par.get(cle, [])),
            "pb": _mediane(pb_par.get(cle, [])),
            "n_pe": len(pe_par.get(cle, [])),
            "n_pb": len(pb_par.get(cle, [])),
        }
    return {
        "secteurs": secteurs,
        "pe_defaut": _mediane(tous_pe),
        "pb_defaut": _mediane(tous_pb),
        "n": len(tous_pe),
    }


def formater_multiple(valeur):
    """9.85 → « 9,85 ». 14.0 → « 14 ». Pour la page Méthodologie."""
    if valeur is None:
        return ""
    texte = f"{float(valeur):.2f}".rstrip("0").rstrip(".")
    return texte.replace(".", ",")


def _trois_modeles(ligne, pe, pb_mult):
    bna = _positif(ligne.get("eps_est") or ligne.get("eps") or ligne.get("bna"))
    bvpa = _positif(ligne.get("book_value_per_share") or ligne.get("bvpa"))
    epv = round(bna * pe) if bna and pe else None
    graham = round((_GRAHAM * bna * bvpa) ** 0.5) if bna and bvpa else None
    pb = round(bvpa * pb_mult) if bvpa and pb_mult else None
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


def _paquet(epv, graham, pb, cible, ecart, libelle, n, incertain, exceptionnel, pe, pb_mult):
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
        "pe_secteur": pe,
        "pb_secteur": pb_mult,
    }


def _mediane(valeurs):
    vals = sorted(valeurs)
    n = len(vals)
    if not n:
        return None
    milieu = n // 2
    if n % 2:
        return vals[milieu]
    return (vals[milieu - 1] + vals[milieu]) / 2.0


def _cle_secteur(nom):
    if not isinstance(nom, str):
        return ""
    decomp = unicodedata.normalize("NFD", nom.strip())
    sans = "".join(c for c in decomp if unicodedata.category(c) != "Mn")
    return sans.casefold()


def _positif(valeur):
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    if valeur != valeur or valeur in (float("inf"), float("-inf")):
        return None
    if valeur <= 0:
        return None
    return float(valeur)
