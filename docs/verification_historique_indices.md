# Vérification en production — historique des indices

Branche `feature/refonte-nav-v2`. À contrôler après déploiement, sans fusionner cette PR tant que les points ci-dessous ne sont pas vus sur le service Render.

Le fichier n'est pas dans git (`data/` est ignoré). Il vit sur le disque persistant, dans le répertoire `BRVM_DATA_DIR` (sur Render, le disque monté, en pratique `/var/data`).

Nom du fichier : `index_history.json`.

## Ce qui est enregistré

Une fois par séance, après la clôture (15h30 UTC) :

- la valeur `current` de BRVM-C, BRVM-30, Prestige et Principal, lue dans le cache qui alimente `GET /api/market` ;
- le rang et la note `/10` déjà calculés de chaque société du classement (`rank`, `note10`). La note n'est pas recalculée. Les conseils et les prix cibles ne sont ni lus pour être réécrits, ni modifiés.

Le job du planificateur s'appelle `Index history 18h10` (lundi–vendredi, 18h10, heure d'Abidjan, identique à UTC). Un redémarrage après cette heure refait la même tentative 30 secondes plus tard : le créneau du cron a une grâce de 60 secondes, un redéploiement le raterait sinon. Le second passage le même jour ne crée pas de deuxième ligne et ne change pas la clôture déjà écrite.

Rien n'est écrit le week-end, avant 15h30 UTC, ni un jour sans séance. Un jour sans séance est reconnu comme dans l'historique des cours : le cache de cours du jour recopie le cours et le volume de la séance précédente pour toutes les valeurs vues. Il n'y a pas de calendrier de jours fériés dans le code. Si le serveur n'a pas tourné ce jour-là, le jour manque : il n'est pas reconstitué.

## Pas de rattrapage du passé

L'historique part vide. Aucune série fiable des quatre indices n'est dans le dépôt ni dans le code.

| Candidat | Pourquoi il n'est pas repris |
|---|---|
| `GET /api/market-stats` (`brvm_market_stats.json`) | Un relevé périmé (2026-05-20). Les clés `brvm_c` / `brvm_30` ne correspondent pas au cache marché actuel (`indices[]`). Ce n'est pas une série de clôtures. |
| `GET /api/sector-indices` | Indices sectoriels, pas BRVM-C, BRVM-30, Prestige, Principal. Déjà incohérent. |
| `GET /api/sparklines` | Cours d'actions, réponse vide. |
| `price_history.json` et les PDF du bulletin | Cours des titres. Les indices n'y sont pas extraits. |

Ne pas copier le relevé du 2026-05-20 dans `index_history.json`.

## Juste après le déploiement

Le fichier est absent, ou bien `seances` est une liste vide.

```bash
curl -sS -D - "https://brvm-weekly-analysis.onrender.com/api/index-history?index=BRVM-C&range=1A" -o /tmp/idx.json
```

Attendu :

- HTTP 200
- en-tête `Cache-Control: public, max-age=300`
- corps `{"index":"BRVM-C","range":"1A","points":[]}`

Même réponse vide pour `BRVM-30`, `Prestige` et `Principal`. Un index inconnu (`CAC40`) ou une plage inconnue (`5A`) renvoie 400 et `Cache-Control: no-store`.

`GET /api/scheduler/status` contient un job nommé `Index history 18h10`.

Les notes, conseils et prix cibles de `GET /api/live-ranking` sont inchangés par rapport à l'instant d'avant le déploiement.

## Après la première séance (le soir, après 18h10 UTC, un jour ouvré)

Sur le shell du service :

```bash
python3 -c "
import json, os
p = os.path.join(os.environ['BRVM_DATA_DIR'], 'index_history.json')
d = json.load(open(p, encoding='utf-8'))
der = d['seances'][-1]
print(p)
print(der['date'], der['indices'])
print('societes', len(der['societes']), der['societes'][:2])
print('dates', [s['date'] for s in d['seances']])
"
```

Attendu :

- une seule entrée pour la date du jour (format `AAAA-MM-JJ`) ;
- `indices` contient les clés présentes sur brvm.org ce jour-là, parmi `BRVM-C`, `BRVM-30`, `Prestige`, `Principal` (une clé absente de la page n'est pas inventée) ;
- les valeurs collent au bandeau du site (deux décimales) ;
- `societes` a une ligne par société notée : `ticker`, `rang`, `note` ;
- pas de clé `conseil`, `composite_adj` ni `prix_cible` ;
- la liste `dates` ne contient pas de samedi ni de dimanche.

Relancer la commande une heure plus tard, ou redémarrer le service : la même date n'apparaît qu'une fois, avec les mêmes valeurs.

```bash
curl -sS "https://brvm-weekly-analysis.onrender.com/api/index-history?index=BRVM-C&range=1S"
```

Le corps ne contient que `index`, `range` et `points`. `points` est une liste de paires `["AAAA-MM-JJ", niveau]`, triée, sans les rangs des sociétés.

Plages, jour de référence = aujourd'hui UTC, bornes incluses :

| `range` | Début |
|---|---|
| `1S` | aujourd'hui moins 6 jours |
| `1M` | le même quantième, un mois plus tôt |
| `YTD` | 1er janvier |
| `1A` | le même quantième, un an plus tôt |

## Jour où il ne faut rien voir de plus

- Samedi ou dimanche : pas de nouvelle date dans `seances`.
- Jour férié où brvm.org republie le cours et le volume de la veille pour toutes les valeurs : pas de nouvelle date. Le job le dit dans les logs : `pas de seance`.
- Avant 15h30 UTC : le fichier ne gagne pas la date du jour.

## Si ça ne s'écrit pas

`scheduler_history.json` (même disque), clé `index_history` : `status` et `error`.

| Log | Lecture |
|---|---|
| `week-end` ou `avant la cloture` | Normal hors séance. |
| `pas de seance` | Cours et volumes identiques à la séance précédente, ou cache de cours qui n'est pas d'aujourd'hui. |
| `cache marche anterieur a la cloture` | `market_cache.json` n'a pas été rafraîchi après 15h30. Le job tente un rafraîchissement avant d'écrire ; s'il échoue, rien n'est écrit pour ne pas figer un niveau d'avant la clôture. |
| `aucun indice reconnu` | La table `indices` du cache ne contient aucun des quatre noms. |
| `ecriture annulee` | Le JSON est illisible. Le fichier n'est pas écrasé. À regarder avant de le supprimer. |

Le site continue de servir les cours et les notes même si ce fichier est absent : `GET /api/index-history` renvoie alors `points: []`.
