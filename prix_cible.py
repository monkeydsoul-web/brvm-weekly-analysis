# -*- coding: utf-8 -*-
"""Prix cible, écart en % et libellé, calculés ensemble.

À côté de verdict.py (note et conseil). Cette fonction ne lit pas la
note et n'écrit ni la note ni le conseil.

Règle unique :
- Graham = racine de (22,5 × BNA × BVPA), si les deux sont positifs.
  Cette formule ne dépend pas du secteur.
- EPV = BNA × P/E de référence du groupe. Le P/E de référence est la
  médiane des P/E historiques (pe_hist) des sociétés du secteur, si le
  secteur compte au moins 5 sociétés. Sinon, médiane de tout le marché.
- P/B = BVPA × P/B justifié. Le P/B de référence est la médiane des
  P/B historiques (pb_hist), avec la même règle d'effectif. Il est
  ensuite ajusté au ROE du jour :
  P/B justifié = P/B de référence × (ROE du jour / ROE médian du groupe).
  Le ROE du jour est bénéfice / actif net, pour la société et pour
  chaque pair du groupe. Ce n'est pas le ROE enregistré en dur.
  Le facteur est borné entre 0,5 et 2. Sans ROE du jour, le facteur
  vaut 1.
- Secteur inconnu : médianes de toutes les sociétés.
- Prix cible = moyenne des modèles disponibles, arrondie.
- Écart % = (prix cible / cours − 1) × 100, arrondi au dixième.
- Le libellé lit CET écart, pas un autre chiffre :
  plus de +30 % → « Forte décote »
  de +10 % à +30 % → « Décote modérée »
  de −10 % à +10 % → « Proche du prix cible »
  en dessous de −10 % → « Au-dessus du prix cible »
- « incertain » (écran : « Cible à vérifier ») seulement si le prix
  cible est inférieur au tiers du cours, ou supérieur à 3 fois le
  cours.
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
EFFECTIF_MIN = 5
FACTEUR_ROE_MIN = 0.5
FACTEUR_ROE_MAX = 2.0

_GRAHAM = 22.5

_reperes_cache = None


def estimer_prix_cible(ligne, roe_median=None):
    """Retourne prix, écart et libellé pour une ligne de classement.

    ``roe_median`` est le ROE du jour du milieu du groupe (ou du
    marché), déjà calculé sur les mêmes bénéfices et actifs nets.
    Sans ce chiffre, le facteur vaut 1 : une ligne seule ne connaît
    pas ses pairs. Aucune clé de note ou de conseil n'est lue, ni écrite.
    """
    if not isinstance(ligne, dict):
        ligne = {}
    pe, pb_mult = multiples_pour(ligne.get("sector"))
    roe_ref = _positif(roe_median)
    facteur = _facteur_roe(roe_du_jour(ligne), roe_ref)
    pb_ajuste = (pb_mult * facteur) if pb_mult else None
    epv, graham, pb = _trois_modeles(ligne, pe, pb_ajuste)
    exceptionnel = _dividende_exceptionnel(ligne)
    if exceptionnel:
        return _paquet(
            epv, graham, pb, None, None, LIBELLE_EXCEPT, 0, False, True,
            pe, pb_mult, facteur, roe_ref,
        )

    disponibles = [v for v in (epv, graham, pb) if v]
    n = len(disponibles)
    cible = round(sum(disponibles) / float(n)) if n else None
    cours = _positif(ligne.get("price"))
    ecart = None
    if cible and cours:
        ecart = round((float(cible) / cours - 1.0) * 100.0, 1)
    incertain = _est_incertain(ecart, n, cible, cours)
    return _paquet(
        epv, graham, pb, cible, ecart,
        _libelle(ecart, incertain), n, incertain, False,
        pe, pb_mult, facteur, roe_ref,
    )


def multiples_pour(secteur):
    """P/E et P/B de référence du groupe, ou ceux de tout le marché.

    Ces deux chiffres viennent des historiques enregistrés. Le ROE
    n'en fait pas partie : il se calcule sur les données du jour.
    """
    table = reperes()
    cle = _cle_secteur(secteur)
    ligne = table["secteurs"].get(cle) if cle else None
    if ligne and ligne.get("pe") and ligne.get("pb"):
        return ligne["pe"], ligne["pb"]
    return table["pe_defaut"], table["pb_defaut"]


def reperes():
    """Médianes pe_hist / pb_hist / roe, calculées une fois."""
    global _reperes_cache
    if _reperes_cache is None:
        from scraper import STOCK_FUNDAMENTALS
        _reperes_cache = calculer_reperes(STOCK_FUNDAMENTALS)
    return _reperes_cache


def calculer_reperes(fond):
    """Médianes de P/E et de P/B enregistrées, et multiples utilisés.

    ``fond`` est un dictionnaire ticker → {sector, pe_hist, pb_hist}.
    On ne lit pas le cours du jour, ni le ROE en dur. Un secteur de
    moins de 5 sociétés utilise les médianes de tout le marché.
    ``pe_observe`` et ``pb_observe`` gardent le calcul du secteur.
    """
    pe_par = {}
    pb_par = {}
    noms = {}
    effectifs = {}
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
        effectifs[cle] = effectifs.get(cle, 0) + 1
        pe = _positif(rec.get("pe_hist"))
        pb = _positif(rec.get("pb_hist"))
        if pe:
            pe_par.setdefault(cle, []).append(pe)
            tous_pe.append(pe)
        if pb:
            pb_par.setdefault(cle, []).append(pb)
            tous_pb.append(pb)
    pe_defaut = _mediane(tous_pe)
    pb_defaut = _mediane(tous_pb)
    secteurs = {}
    for cle, nom in noms.items():
        pe_obs = _mediane(pe_par.get(cle, []))
        pb_obs = _mediane(pb_par.get(cle, []))
        petit = effectifs.get(cle, 0) < EFFECTIF_MIN
        secteurs[cle] = {
            "secteur": nom,
            "pe_observe": pe_obs,
            "pb_observe": pb_obs,
            "pe": pe_defaut if petit else pe_obs,
            "pb": pb_defaut if petit else pb_obs,
            "n": effectifs.get(cle, 0),
            "n_pe": len(pe_par.get(cle, [])),
            "n_pb": len(pb_par.get(cle, [])),
            "utilise_marche": petit,
        }
    return {
        "secteurs": secteurs,
        "pe_defaut": pe_defaut,
        "pb_defaut": pb_defaut,
        "n": len(tous_pe),
        "effectif_min": EFFECTIF_MIN,
    }


def roe_du_jour(ligne):
    """Bénéfice / actif net, en %. Même formule pour chaque société.

    On ne lit pas la clé ``roe`` : elle peut être un chiffre enregistré
    en dur, différent du bénéfice et de l'actif net du jour.
    """
    if not isinstance(ligne, dict):
        return None
    bna = _positif(ligne.get("eps_est") or ligne.get("eps") or ligne.get("bna"))
    bvpa = _positif(ligne.get("book_value_per_share") or ligne.get("bvpa"))
    if not bna or not bvpa:
        return None
    return bna / bvpa * 100.0


def medianes_roe_du_jour(lignes):
    """ROE du jour du milieu, par groupe, ou du marché si le groupe a moins de 5 sociétés.

    Le compte des sociétés est celui du classement passé ici, pas le
    fichier de repères. Une société sans bénéfice ou sans actif net
    compte dans l'effectif, mais pas dans la médiane.
    """
    if not isinstance(lignes, (list, tuple)):
        lignes = []
    roe_par = {}
    effectifs = {}
    tous = []
    for ligne in lignes:
        if not isinstance(ligne, dict):
            continue
        cle = _cle_secteur(ligne.get("sector") or "")
        roe = roe_du_jour(ligne)
        if cle:
            effectifs[cle] = effectifs.get(cle, 0) + 1
            if roe:
                roe_par.setdefault(cle, []).append(roe)
        if roe:
            tous.append(roe)
    marche = _mediane(tous)
    utilise = {}
    observe = {}
    for cle, n in effectifs.items():
        obs = _mediane(roe_par.get(cle, []))
        observe[cle] = obs
        if n < EFFECTIF_MIN:
            utilise[cle] = marche
        else:
            utilise[cle] = obs if obs is not None else marche
    return {
        "utilise": utilise,
        "observe": observe,
        "marche": marche,
        "effectifs": effectifs,
    }


def roe_median_pour(ligne, table):
    """Médiane de ROE du jour à appliquer à cette ligne."""
    if not isinstance(table, dict):
        return None
    cle = _cle_secteur((ligne or {}).get("sector") or "") if isinstance(ligne, dict) else ""
    if cle and cle in (table.get("utilise") or {}):
        return table["utilise"][cle]
    return table.get("marche")


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


def _facteur_roe(roe_societe, roe_ref):
    """ROE du jour / ROE médian du jour, borné entre 0,5 et 2. Sans ROE : 1."""
    societe = _positif(roe_societe)
    ref = _positif(roe_ref)
    if not societe or not ref:
        return 1.0
    brut = societe / ref
    if brut < FACTEUR_ROE_MIN:
        return FACTEUR_ROE_MIN
    if brut > FACTEUR_ROE_MAX:
        return FACTEUR_ROE_MAX
    return brut


def _dividende_exceptionnel(ligne):
    return bool(
        ligne.get("div_is_exceptional")
        or ligne.get("div_flag") == "exceptionnel_non_recurrent"
    )


def _est_incertain(ecart, n_modeles, cible, cours):
    """Cible à vérifier seulement si elle sort de la fourchette 1/3 à 3×.

    ``ecart`` et ``n_modeles`` ne décident plus : un écart de 139 %
    reste un libellé normal tant que la cible est entre le tiers du
    cours et 3 fois le cours.
    """
    del ecart, n_modeles
    if not cible or not cours:
        return False
    return float(cible) * 3.0 < cours or float(cible) > cours * 3.0


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


def _paquet(epv, graham, pb, cible, ecart, libelle, n, incertain, exceptionnel,
            pe, pb_mult, facteur, roe_ref):
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
        "facteur_roe": facteur,
        "roe_secteur": roe_ref,
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
