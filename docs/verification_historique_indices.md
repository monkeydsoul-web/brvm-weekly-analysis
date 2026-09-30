# Vérification en production — historique des indices

Branche `feature/refonte-nav-v2`. À contrôler après le déploiement.

Le fichier n'est pas dans git (`data/` est ignoré). Il vit sur le disque persistant, dans le répertoire `BRVM_DATA_DIR` (sur Render, le disque monté, en pratique `/var/data`).

Nom du fichier : `index_history.json`.

## Ce qui est enregistré

Une fois par séance, après la clôture (15h30 UTC) :

- la valeur `current` de BRVM-C, BRVM-30, Prestige et Principal, lue dans le cache qui alimente `GET /api/market` ;
- le rang et la note `/10` déjà calculés de chaque société du classement (`rank`, `note10`). La note n'est pas recalculée. Les conseils et les prix cibles ne sont ni lus pour être réécrits, ni modifiés.

Le job du planificateur s'appelle `Index history 18h10` (lundi–vendredi, 18h10, heure d'Abidjan, identique à UTC). Il rafraîchit alors le cache marché, puis écrit. Un seul worker prend le verrou (`fcntl` `LOCK_NB`, réessayé 10 s). Les autres n'écrasent pas le fichier : ils fusionnent. Une société ou un indice déjà écrits ne sont jamais remplacés.

Un redémarrage après 18h10 retente 30 secondes plus tard, **sans** rappeler brvm.org. Il utilise `market_cache.json` seulement si `updated_at` est le jour même et à ou après 15h30 UTC. Sinon il ne fait rien et laisse le job de 18h10.

Rien n'est écrit le week-end, avant 15h30 UTC, ni un jour sans séance. Trois cas, sans calendrier de fériés :

- le cache de cours recopie le cours et le volume de la séance précédente ;
- les quatre indices qu'on s'apprête à écrire sont identiques à la dernière séance déjà dans le fichier (on n'ouvre pas une date neuve avec la valeur de la veille) ;
- `current == prev` pour les quatre indices du cache.

La date de la ligne est `session_date` du cache quand elle est lisible. brvm.org/fr/resume ne publie pas de date de séance à part l'horloge de l'en-tête (« 30 septembre 2026 ») : le scraper la recopie dans `session_date`. Seule l'absence de cette clé (vieux cache) retombe sur la date de l'appel. Une clé présente mais nulle, vide ou illisible, ou une date future, n'est pas remplacée par aujourd'hui : rien n'est écrit. Si le serveur n'a pas tourné ce jour-là, le jour manque : il n'est pas reconstitué.

Un indice absent, ou à plus de 15 % de sa dernière clôture enregistrée, n'est pas écrit. Un passage suivant le même jour peut l'ajouter. Il ne modifie pas un niveau déjà posé.

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

- une seule entrée pour la date de séance (format `AAAA-MM-JJ`), pas pour un jour où le tableau recopie la veille ;
- `indices` contient les clés plausibles parmi `BRVM-C`, `BRVM-30`, `Prestige`, `Principal` (une clé absente, ou à plus de 15 % de la clôture précédente, n'est pas inventée) ;
- les valeurs collent au bandeau du site (deux décimales) ;
- `societes` a une ligne par société notée : `ticker`, `rang`, `note` ;
- pas de clé `conseil`, `composite_adj` ni `prix_cible` ;
- la liste `dates` ne contient pas de samedi ni de dimanche.

Relancer la commande une heure plus tard, ou redémarrer le service : la même date n'apparaît qu'une fois. Les niveaux déjà écrits sont identiques. Un redémarrage ne doit pas produire de ligne `market_data:` neuve imputable à ce rattrapage (pas de `force_refresh`). Le job de 18h10, lui, rafraîchit le cache.

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
- Jour férié : pas de nouvelle date si les quatre indices recopient la dernière séance, ou si `current` égale `prev` pour les quatre. Le log dit `reprise de la veille` ou `current == prev`. Un férié vu seulement par les cours (volumes identiques) dit `pas de seance`.
- Avant 15h30 UTC : le fichier ne gagne pas la date du jour.
- Au démarrage, si `market_cache.json` n'est pas du jour après 15h30 : le log dit `laisse au job 18h10`, et le fichier ne change pas.

## Si ça ne s'écrit pas

`scheduler_history.json` (même disque), clé `index_history` : `status` et `error`.

| Log | Lecture |
|---|---|
| `week-end` ou `avant la cloture` | Normal hors séance. |
| `pas de seance` | Cours et volumes identiques à la séance précédente, ou cache de cours qui n'est pas d'aujourd'hui. |
| `reprise de la veille` / `current == prev` | Le tableau des indices est celui de la séance précédente. Rien n'est daté du jour. |
| `cache marche pas du jour apres 15h30, laisse au job 18h10` | Rattrapage au démarrage : le cache est trop vieux. Pas de scraping. |
| `cache marche anterieur a la cloture` | Le job de 18h10 a tenté un rafraîchissement, le cache reste d'avant 15h30. Rien n'est écrit. |
| `indice hors ecart ignore` | Un indice bouge de plus de 15 % par rapport à sa dernière clôture. Les autres peuvent être écrits. Un passage suivant peut compléter celui-là. |
| `verrou occupe` | Un autre worker tenait le fichier. Rien n'est écrasé. Le job de 18h10 ou le passage suivant réessaie. |
| `aucun indice reconnu` | La table `indices` du cache ne contient aucun des quatre noms. |
| `ecriture annulee` | Le JSON est illisible. Le log est au niveau ERROR et cite le chemin du fichier. Le fichier n'est pas écrasé. À regarder avant de le supprimer. Un temporaire orphelin se reconnaît au préfixe `index_history.` et au suffixe `.tmp`, dans le même dossier. |

Le site continue de servir les cours et les notes même si ce fichier est absent : `GET /api/index-history` renvoie alors `points: []`.
