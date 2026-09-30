# Audit : données historiques P/E, P/B et bénéfices

Lecture seule du 30 septembre 2026, branche `feature/refonte-nav-v2`. Aucun calcul du site n'a été modifié. Les notes « corrigées » ci-dessous ont été rejouées en local, avec les fonctions déjà dans `valuation.py` et `verdict.py`.

Le classement consulté est celui servi par Render le 30 septembre 2026 à 08:24:46 UTC (`https://brvm-weekly-analysis.onrender.com/api/live-ranking`, 47 sociétés). Les pages Sika Finance ont été lues le même jour. Les PDF cités viennent de brvm.org.

Quand un chiffre n'a pas pu être lu, il est marqué **non vérifié**.

## 1. `pe_hist` et `pb_hist` dans `scraper.py`

Les 47 valeurs sont dans `STOCK_FUNDAMENTALS` (`scraper.py`, lignes 32-80). Le commentaire du fichier dit seulement « Données de référence statiques (enrichies manuellement) ». Aucune source, aucune date, aucun lien. La source de chaque constante est donc **non documentée dans le dépôt**.

Aucune de ces constantes ne coïncide, à 0,05 près, avec un PER annuel 2021-2025 publié par Sika Finance (pages `https://www.sikafinance.com/marches/societe/<code>`, lues le 30 septembre 2026).

### Ce que la note utilise vraiment

La note du classement ne lit pas ces constantes.

- `live_ranker.py` pose `pe_ref = cours / BNA` et `pb_ref = cours / BVPA` quand le BNA et le BVPA existent. Sinon la clé est retirée.
- `valuation.py` (Graham, DCF, EPV, Buffett, reverse DCF, relatif) lit `pe_ref` et `pb_ref`.
- `pe_hist` est recopié dans la ligne, puis écrasé par le PER du bulletin de la cote quand ce PER existe (`live_ranker.py`). `pb_hist` n'est pas écrasé : la valeur servie le 30 septembre 2026 est encore celle du code.
- `build_stock_dataset` copie encore `pe_hist` vers `pe_ref` et `pb_hist` vers `pb_ref`. Ce chemin n'alimente pas `/api/live-ranking`.

Rejeu local des 47 lignes du classement du 30 septembre, en gardant le score technique déjà calculé : le composite retrouve exactement celui du fichier (0 écart supérieur à 0,15 point).

### Valeurs génériques

Cinq P/E valent exactement 14 : STBC, PALC, CIEC, SDCC, CFAC.

Dix P/B valent exactement 2 : ONTBF, UNXC, LNBB, PALC, SPHC, SEMC, SDCC, CABC, BNBC, PRSC.

PALC et SDCC cumulent les deux. Pour les utilités, les deux sociétés ont un P/E de 14 : la médiane du secteur est donc 14, c'est-à-dire la valeur générique elle-même.

D'autres constantes sont des entiers ronds (8, 12, 15, 18, 20, 22). Elles ne sont pas pour autant classées « génériques » ici : le dépôt ne dit pas si elles viennent d'un calcul. Leur source reste non documentée.

### Médiane du secteur

Deux médianes distinctes existent. Il ne faut pas les mélanger.

1. **Médiane des constantes du secteur**, calculée sur `STOCK_FUNDAMENTALS` (nombre de sociétés entre parenthèses) :

| Secteur | Sociétés | Médiane `pe_hist` | Médiane `pb_hist` |
|---|---:|---:|---:|
| Banque | 16 | 9,85 | 1,51 |
| Télécoms | 3 | 12 | 3,5 |
| Consommation | 7 | 18 | 2 |
| Agriculture | 4 | 15,8 | 1,9 |
| Énergie | 4 | 12,5 | 2,75 |
| Industriel | 11 | 16 | 2 |
| Utilités | 2 | 14 | 2,25 |

2. **Médiane utilisée par le modèle relatif** (`valuation.py`, `score_relative`), elle aussi écrite en dur, et indépendante du tableau ci-dessus : Banque 10, Télécoms 13, Consommation 16, Agriculture 14, Énergie 12, Industriel 13, Utilités 12. Pas de médiane de P/B dans ce modèle : le P/B y est comparé au ROE / 10 %.

### Tableau des 47 sociétés

La colonne « Générique » ne marque que les valeurs exactement égales à 14 ou à 2. La médiane est celle des constantes du secteur (tableau précédent). Source : non documentée dans le dépôt, pour les 47.

| Ticker | Société | Secteur | `pe_hist` | `pb_hist` | Générique | Médiane P/E | Médiane P/B |
|---|---|---|---:|---:|---|---:|---:|
| SGBC | Société Générale CI | Banque | 8,5 | 1,96 | non | 9,85 | 1,51 |
| SIBC | Société Ivoirienne de Banque | Banque | 10,7 | 2,2 | non | 9,85 | 1,51 |
| SNTS | Sonatel Senegal | Télécoms | 8,33 | 3,5 | non | 12 | 3,5 |
| NSBC | NSIA Banque CI | Banque | 7,05 | 1 | non | 9,85 | 1,51 |
| CBIBF | Coris Bank International | Banque | 5 | 1,2 | non | 9,85 | 1,51 |
| BOAB | BOA Benin | Banque | 8 | 1,5 | non | 9,85 | 1,51 |
| BOABF | BOA Burkina Faso | Banque | 10,2 | 1,52 | non | 9,85 | 1,51 |
| BOAC | BOA Côte d'Ivoire | Banque | 9,5 | 2,2 | non | 9,85 | 1,51 |
| BOAM | BOA Mali | Banque | 8 | 1,4 | non | 9,85 | 1,51 |
| BOAN | BOA Niger | Banque | 8,5 | 1,3 | non | 9,85 | 1,51 |
| BOAS | BOA Sénégal | Banque | 9 | 1,7 | non | 9,85 | 1,51 |
| ECOC | Ecobank CI | Banque | 10,5 | 3 | non | 9,85 | 1,51 |
| BICC | BICI CI | Banque | 10,5 | 2,6 | non | 9,85 | 1,51 |
| ETIT | Ecobank Transnational | Banque | 30 | 0,5 | non | 9,85 | 1,51 |
| ORGT | Oragroup Togo | Banque | 15 | 1,4 | non | 9,85 | 1,51 |
| SAFC | SAFCA CI | Banque | 20 | 1,8 | non | 9,85 | 1,51 |
| BICB | BIIC Bénin | Banque | 12 | 1,5 | non | 9,85 | 1,51 |
| ORAC | Orange CI | Télécoms | 15 | 4,5 | non | 12 | 3,5 |
| ONTBF | Onatel Burkina Faso | Télécoms | 12 | 2 | P/B 2 | 12 | 3,5 |
| NTLC | Nestlé CI | Consommation | 18 | 5 | non | 18 | 2 |
| STBC | SITAB CI | Consommation | 14 | 2,8 | P/E 14 | 18 | 2 |
| UNLC | Unilever CI | Consommation | 22 | 8 | non | 18 | 2 |
| SLBC | SOLIBRA CI | Consommation | 11,7 | 1,3 | non | 18 | 2 |
| UNXC | Uniwax CI | Consommation | 22 | 2 | P/B 2 | 18 | 2 |
| LNBB | Loterie Nationale Bénin | Consommation | 9 | 2 | P/B 2 | 18 | 2 |
| NEIC | NEI-CEDA CI | Consommation | 18 | 1,5 | non | 18 | 2 |
| PALC | Palm CI | Agriculture | 14 | 2 | P/E 14, P/B 2 | 15,8 | 1,9 |
| SPHC | SAPH CI | Agriculture | 16,6 | 2 | P/B 2 | 15,8 | 1,9 |
| SOGC | SOGB CI | Agriculture | 15 | 1,8 | non | 15,8 | 1,9 |
| SCRC | Sucrivoire CI | Agriculture | 18 | 1,5 | non | 15,8 | 1,9 |
| TTLC | TotalEnergies CI | Énergie | 11 | 3,5 | non | 12,5 | 2,75 |
| TTLS | TotalEnergies Sénégal | Énergie | 12 | 2,5 | non | 12,5 | 2,75 |
| SHEC | Vivo Energy CI | Énergie | 13 | 3 | non | 12,5 | 2,75 |
| SEMC | Crown Siem CI | Énergie | 20 | 2 | P/B 2 | 12,5 | 2,75 |
| CIEC | CIE CI | Utilités | 14 | 2,5 | P/E 14 | 14 | 2,25 |
| SDCC | SODECI CI | Utilités | 14 | 2 | P/E 14, P/B 2 | 14 | 2,25 |
| SMBC | SMB CI | Industriel | 8,79 | 1,1 | non | 16 | 2 |
| FTSC | Filtisac CI | Industriel | 5,5 | 1,2 | non | 16 | 2 |
| SDSC | Africa Global Logistics CI | Industriel | 16 | 2,2 | non | 16 | 2 |
| CABC | Sicable CI | Industriel | 12 | 2 | P/B 2 | 16 | 2 |
| CFAC | CFAO Motors CI | Industriel | 14 | 1,8 | P/E 14 | 16 | 2 |
| BNBC | Bernabé CI | Industriel | 15 | 2 | P/B 2 | 16 | 2 |
| SICC | Sicor CI | Industriel | 16 | 2,2 | non | 16 | 2 |
| PRSC | Tractafric Motors CI | Industriel | 18 | 2 | P/B 2 | 16 | 2 |
| ABJC | Servair Abidjan CI | Industriel | 25 | 3,5 | non | 16 | 2 |
| STAC | Setao CI | Industriel | 22 | 3 | non | 16 | 2 |
| SIVC | Erium CI (Air Liquide) | Industriel | 20 | 3 | non | 16 | 2 |

SICC est classée « Industriel » dans `scraper.py`. La fiche `stories/sicc.json` dit que la BRVM la classe dans l'agriculture. Rejouer la note du 30 septembre avec le secteur Agriculture donne le même composite 23,0 et la même note 2,9 : au P/E courant de 105, les deux secteurs donnent 0 au modèle relatif, et aucun des deux n'est dans le « fossé » de Buffett.

### Impact sur la note

**Corriger ces constantes dans `scraper.py`, sans rien changer d'autre, ne change aucune note publiée aujourd'hui.** Le classement du 30 septembre ne s'en sert pas pour le composite.

Une valeur historique « corrigée » (PER ou P/B d'un exercice précis, avec une source) n'a pas été trouvée pour remplacer les 14 et les 2. Sika Finance publie un PER par année, pas un P/B, et ce PER ne retrouve aucune constante. La valeur corrigée est donc **non vérifiée**. Aucune note n'a été recalculée avec un multiple inventé.

Contrefactuel local, qui n'est pas le comportement du site : si `pe_hist` et `pb_hist` devenaient `pe_ref` et `pb_ref` (c'est ce que fait encore `build_stock_dataset`), et si l'amortisseur de conseil partait du conseil actuel, **12 sociétés changeraient de conseil**. Le rejeu est dans `scripts/audit_donnees_historiques.py --ranking`.

| Ticker | Note actuelle | Note avec les constantes | Conseil actuel | Conseil contrefactuel |
|---|---:|---:|---|---|
| BICC | 7,7 | 6,8 | Intéressant | À surveiller |
| ETIT | 7,3 | 5,0 | Intéressant | À surveiller |
| SNTS | 7,3 | 7,9 | À surveiller | Intéressant |
| ORGT | 6,6 | 4,5 | À surveiller | Prudence |
| SPHC | 5,9 | 3,8 | À surveiller | Prudence |
| PRSC | 5,4 | 3,4 | À surveiller | Prudence |
| ORAC | 5,1 | 5,5 | Prudence | À surveiller |
| LNBB | 4,8 | 6,8 | Prudence | À surveiller |
| NSBC | 4,4 | 6,1 | Prudence | À surveiller |
| BOAB | 3,9 | 6,0 | Prudence | À surveiller |
| CBIBF | 3,7 | 6,8 | Prudence | À surveiller |
| BOAM | 3,6 | 5,3 | Prudence | À surveiller |

SICC et SEMC sont suspendues : pas de conseil dans les deux cas. Les autres sociétés gardent leur conseil dans ce contrefactuel, même quand la note bouge à l'intérieur d'un palier.

## 2. Bénéfices du cache et rapports publiés

Le cache des bénéfices est `analyses_summary.json` et les analyses accrochées à `/api/reports/<ticker>` sur Render. Il n'est pas dans git (`data/` est ignoré). Les chiffres ci-dessous sont ceux servis le 30 septembre 2026.

La note utilise le résultat net seulement s'il devient le BNA (`résultat / nombre d'actions`), puis le P/E = cours / BNA. Un vieux cache qui n'est pas le BNA retenu ne bouge pas la note.

### Exemple CIEC : 10 555 et 13 127 sont tous les deux dans les PDF

Le cache de l'analyse « États financiers SYSCOHADA, exercice 2024 » (PDF du 30 avril 2025) contient **10 555** millions. Le classement du 30 septembre 2026 n'utilise plus ce chiffre. Il utilise **13 121** millions, exercice 2025, source « rapport », BNA 234, note 5,3, conseil « À surveiller ».

Les deux PDF BRVM, en millions de FCFA :

- Exercice 2025, `https://www.brvm.org/sites/default/files/20260520_-_etats_financiers_syscohada_et_ifrs_-_exercice_2025_-_cie_ci.pdf`
  - SYSCOHADA, résultat net : **13 127** en 2025 et **10 101** en 2024.
  - IFRS consolidé, résultat net total : **13 121** en 2025 et **10 555** en 2024.
- Exercice 2024, `https://www.brvm.org/sites/default/files/20250430_-_etats_financiers_-_norme_syscohada_-_exercice_2024_-_cie_ci.pdf`
  - SYSCOHADA : **10 101**.
  - IFRS consolidé : **10 555** (ligne « Résultat net total consolidé 10 555 »).

Sika Finance, page CIEC, mêmes exercices, en millions de FCFA : 10 101 en 2024 et 13 127 en 2025 (`https://www.sikafinance.com/marches/societe/CIEC.ci`). Ce sont les chiffres SYSCOHADA, pas l'IFRS.

Conséquences, sans arrondir au-delà de ce qui est écrit :

- 10 555 est le résultat consolidé IFRS 2024. Le cache de ce PDF l'a bien lu. Ce n'est pas 13 127, qui est le SYSCOHADA 2025. Les comparer donne (13 127 − 10 555) / 13 127 = 19,6 %, mais ce n'est ni le même exercice ni le même référentiel.
- Le chiffre qui alimente la note, 13 121, est le consolidé IFRS 2025 du PDF. Face au SYSCOHADA 13 127 : écart de 6 millions, soit 0,05 %, sous le seuil de 5 %.
- Rejeu local avec un BNA = 13 127 000 000 / 56 000 000 = 234,41 FCFA (le BNPA Sika est 234,41) : le P/E passe de 27,56 à 27,52. Composite inchangé à 42,0, note inchangée à 5,3, conseil inchangé.

Le cache 2023 de la CIE (11 508) est aussi le consolidé IFRS du PDF du 2 mai 2024 ; le SYSCOHADA du même PDF est 10 633. Écart 8,2 % entre référentiels, pas une erreur de lecture. Ce cache n'est pas le BNA du classement.

### Écarts de plus de 5 % vérifiés

Seuls les cas où le PDF BRVM, ou le nom du fichier joint au texte, permet de trancher. Les autres rapprochements Sika Finance dont le PDF n'a pas été relu sont **non vérifiés** et ne figurent pas ici.

| Société | Ce que le cache contient | Chiffre publié vérifié | Écart | Alimente la note du 30/09 ? |
|---|---|---|---|---|
| ORAC, analyse 2024 | 158,2 MFCFA | 158,2 dans le support Orange, et 158 200 M chez Sika pour 2024. Le comparatif 2023 du même support est 154,9 ; Sika 2023 est 154 890 M. L'unité du support est donc le milliard, pas le million. | 99,9 % | Non. La note utilise 167 800 M, exercice 2025, égal à Sika 2025. |
| SICC, analyse IFRS 2025 | 1 439,474 M, rangé sous SICC | Le PDF est celui de la Société ivoirienne de câbles (Sicable), pas de SICOR. Résultat net 1 439 474 milliers de FCFA. | Mauvaise société | Oui : BNA « rapport », exercice 2025, résultat 1 439,474 M. |
| ABJC, analyse 2025 | 179,293 M, rangé sous ABJC | Le PDF est celui d'Erium CI. Résultat net 179 293 282 FCFA, soit 179,293 M. Sika classe 179 M en 2025 sous SIVC (Erium) et 1 351 M sous ABJC (Servair). | 86,7 % face au résultat Servair publié par Sika. Le PDF Servair n'a pas été relu : **non vérifié** sur brvm.org. | Non pour le BNA : la source du BNA ABJC est le bulletin, pas ce PDF. Le `pdf_rn` affiché est celui d'Erium. |
| SDCC, analyse 2024 | 3 959 M | PDF SODECI, SYSCOHADA : « Résultat net 3.560.488 » en milliers de FCFA, soit 3 560,488 M. | 11,2 % | Non. La note utilise 4 663 M, égal au résultat 2025 de Sika. |
| CFAC, analyse « 2018 à 2023 » | 2 044,698 M | Le PDF dit « Résultat net de l'exercice 2 044 698 » en milliers, soit 2 044,698 M. Le nom de fichier est `tractafric_motors_ci`. Le corps extrait ne nomme pas la société : l'identité Tractafric est **non vérifiée** dans le texte. Sika, CFAO 2023 : 6 399 M. Sika, Tractafric 2023 : 2 084 M (écart 1,9 % avec 2 044,7, sous 5 %). | 68 % si on le compare à CFAO, la société sous laquelle il est rangé | Non pour le BNA : source bulletin. Le `pdf_rn` affiché est 2 044,698. |

Sources :

- ORAC : `https://www.brvm.org/sites/default/files/20250221_-_etats_financiers_-_exercice_2024_-_orange_ci.pdf` et `https://www.sikafinance.com/marches/societe/ORAC.ci`
- SICC / Sicable : `https://www.brvm.org/sites/default/files/20260311_-_etats_financiers_ifrs_-_exercice_2025_-_sicable_ci.pdf` (en-tête « SOCIÉTÉ IVOIRIENNE DE CÂBLES (SICABLE) »). Le SYSCOHADA Sicable 2025, 1 704 451 milliers, est aussi rangé sous SICC : `https://www.brvm.org/sites/default/files/20260310_-_etats_financiers_syscohada_-_exercice_2025_-_sicable_ci.pdf`. Sika Sicable (CABC) 2025 : 1 704 M. Sika SICOR (SICC) s'arrête à 2024 : −129 M. Le résultat SICOR 2025 est **non vérifié**.
- ABJC / Erium : `https://www.brvm.org/sites/default/files/20260626_-_etats_financiers_-_exercice_2025_-_erium_ci.pdf` et `https://www.sikafinance.com/marches/societe/ABJC.ci`, `https://www.sikafinance.com/marches/societe/SIVC.ci`
- SDCC : `https://www.brvm.org/sites/default/files/20250430_-_etats_financiers_-_exercice_2024_-_sode_ci.pdf` et `https://www.sikafinance.com/marches/societe/SDCC.ci`
- CFAC : `https://www.brvm.org/sites/default/files/20250617_-_etats_financiers_-_exercices_2018_a_2023_-_tractafric_motors_ci_annule_et_remplace_le_precedent.pdf` et `https://www.sikafinance.com/marches/societe/CFAC.ci`, `https://www.sikafinance.com/marches/societe/PRSC.ci`

Cause probable dans le dépôt, pas une preuve à elle seule : `reports_scraper.py` associe `SICC` au slug `sicable`, `ABJC` au slug `air-liquide-ci`, `CABC` au slug `crrh`. Servair est ABJC dans `scraper.py` et sur Sika ; Erium est SIVC. Sicable est CABC ; SICOR est SICC.

### SICC : retirer le bénéfice de Sicable ne change pas la note

Le P/E courant de SICC est 105 (cours 8 400 / BNA 80). Rejeu local en retirant ce BNA : composite toujours 23,0, note toujours 2,9. Un P/E de 105 et un P/E absent tombent dans les mêmes paliers des modèles. SICC est suspendue depuis le 16 septembre 2026 : le conseil reste vide. Le résultat SICOR 2025 qui permettrait un autre BNA est **non vérifié**.

### Deux référentiels, pas une erreur de lecture

Sucrivoire, exercice 2025, les deux PDF BRVM :

- SYSCOHADA : résultat net −6 131 800 226 FCFA, soit −6 131,8 M. Sika : −6 132 M. `https://www.brvm.org/sites/default/files/20260430_-_etats_financiers_syscohada_-_exercice_2025_-_sucrivoire_ci.pdf`
- IFRS : « Résultat net 7 953 932 » en milliers, soit −7 953,932 M, égal au cache. `https://www.brvm.org/sites/default/files/20260518_-_etats_financiers_-_exercice_2025_-_sucrivoire_ci_annule_et_remplace_le_precedent.pdf`

Écart 29,7 % entre les deux référentiels. Le classement retient l'IFRS, négatif : pas de BNA, pas de P/E. Changer de référentiel laisserait un résultat négatif et le même trou de P/E. Le conseil ne bouge pas pour cette raison.

### Ce qui n'a pas été vérifié

Beaucoup de BNA du classement viennent du bulletin (cours de clôture du bulletin / PER), pas du résultat net d'un état financier. Leur écart avec le résultat annuel Sika dépasse souvent 5 %. Le bulletin du jour n'a pas été relu ligne à ligne : ces écarts sont **non vérifiés** comme erreurs de cache. Ils ne sont pas ajoutés à la liste ci-dessus.

Le résultat 2025 de SIVC dans le classement est un estimé de 2 840 M. Le PDF Erium, rangé sous ABJC, dit 179,293 M. Le nombre d'actions de SIVC dans `scraper.py` (60 000 000) et le PER 2025 Sika (104,24) ne se réconcilient pas avec ce cours et ce résultat : l'impact chiffré sur la note de SIVC est **non vérifié**. Il n'a pas été calculé.

## 3. `companies_stories.json` sur Render et SICC

Le fichier sur disque n'est pas servi tel quel. `app.py` (`/data/companies_stories.json`) écrase la clé SICC avec `stories/sicc.json` avant de répondre. Le commentaire du code le dit : la fiche remplace un texte qui décrivait Sicable.

Vérification le 30 septembre 2026 :

- La réponse HTTP décrit SICOR, le coco râpé, l'huile de coprah et les tourteaux. Elle cite la fiche BRVM, le rapport annuel 2023 et Rich Bourse. C'est le contenu de `stories/sicc.json`.
- `_meta.generated_at` vaut `2026-05-30T17:54:09+00:00`, le même horodatage que le dernier fichier versionné (commit `73dfb03`, retiré du suivi par `2bbf3f6`).
- Les 46 autres fiches de la réponse sont identiques à ce fichier versionné, hors champs de génération.
- Dans ce fichier versionné, SICC commence par : « SICABLE est une société industrielle ivoirienne cotée à la BRVM, spécialisée dans la fabrication et la distribution de câbles. »

Le disque Render n'a pas été ouvert. L'identité des 46 fiches et de l'horodatage indique que le fichier généré le 30 mai 2026 est encore celui qui est lu, et que seul le remplacement à la volée corrige SICC. Le texte câblier de ce fichier est celui du commit `73dfb03`.

`stories/sicc.json` est la bonne fiche d'affichage : elle est déjà dans le dépôt, sourcée, et le test `test_fiche_sicc_decrit_sicor_et_ecrase_sicable` vérifie que la route écrase un texte « câbles ».

Même fichier, autre confusion, non écrasée par la route : la fiche ABJC servie le 30 septembre décrit « Erium Côte d'Ivoire ». `scraper.py` et Sika appellent ABJC Servair Abidjan, et SIVC Erium. Les PDF rangés sous ABJC sont ceux d'Erium (section 2).

### Recommandation

Remplacer, dans le fichier `companies_stories.json` du disque Render, la fiche SICC par le contenu de `stories/sicc.json`. Ne pas relancer `scripts/generate_company_stories.py` pour « réparer » SICC : c'est cette génération du 30 mai 2026 qui a écrit le texte câblier.

Garder l'écrasement dans `app.py` jusqu'à ce que le fichier disque soit relu et que SICC y parle de coco, pas de câbles. L'écrasement ne corrige pas ABJC.

Impact sur les notes et les conseils : aucun. Les fiches n'entrent pas dans le composite.

## 4. Recommandations

Classées de la correction la plus sûre à celle qui demande une décision. « Impact note » veut dire : ce qui changerait sur le classement du 30 septembre 2026 si on appliquait seulement cette correction, sans toucher aux formules.

### Corrections sûres

1. **Écrire la fiche SICOR dans le fichier disque** (section 3). Le visiteur la voit déjà, grâce à l'écrasement. Le fichier, lui, décrit encore un câblier. Impact : 0 société, 0 conseil.
2. **Ne pas traiter 10 555 comme le bénéfice à corriger dans la note CIE.** La note utilise déjà 13 121, qui est le consolidé IFRS 2025 du PDF. L'écarter de 13 127 (SYSCOHADA) ne change pas la note 5,3 ni le conseil « À surveiller ». Choisir SYSCOHADA ou IFRS pour l'affichage est une décision de libellé, pas un correctif de formule.

### À décider avant toute modification de note

3. **Laisser `pe_hist` et `pb_hist` hors de la note.** C'est déjà le cas. Les remplacer par des multiples « plausibles » inventés est refusé ici : la source historique est non vérifiée. Si ces constantes étaient rebranchées comme P/E et P/B de la note, **12 sociétés changeraient de conseil** (tableau de la section 1). Cette bascule n'est pas recommandée : elle remplacerait le P/E courant (cours / BNA) par des constantes sans source.
4. **SICC et les PDF Sicable.** Le BNA du 30 septembre vient du résultat IFRS de Sicable. Le retirer ne change pas la note 2,9, et il n'y a pas de conseil (suspension). Décider de ne plus analyser les PDF `sicable_ci` sous le ticker SICC. Le slug `SICC → sicable` dans `reports_scraper.py` est le candidat. Ne pas réanalyser tant que le slug n'est pas tranché : un nouveau PDF changerait le BNA.
5. **ABJC et les PDF Erium.** Le cache ABJC porte le résultat d'Erium (179,293 M). Le BNA de la note vient du bulletin, donc la note ne lit pas ce 179,293. Décider du slug (`ABJC` ne devrait pas être `air-liquide-ci`) avant une réanalyse. L'impact d'un futur BNA Servair est **non vérifié** : le PDF Servair n'a pas été relu.
6. **ORAC 2024 : 158,2 au lieu de 158 200.** Erreur d'unité dans une analyse qui n'alimente pas la note actuelle. La corriger dans le cache ne change pas le conseil du 30 septembre. Utile si une autre route relit encore cette analyse.
7. **SDCC 2024 : 3 959 au lieu de 3 560,488.** Même situation : l'analyse est fausse face au PDF, la note du jour utilise le résultat 2025 (4 663). Impact actuel : 0 conseil.
8. **CFAC et le PDF au nom de Tractafric.** Le résultat 2 044,698 M est rangé sous CFAO alors que le fichier s'appelle Tractafric. Il n'alimente pas le BNA du jour. Décider du rattachement avant de s'en servir. L'identité dans le corps du PDF est **non vérifiée**.
9. **Sucrivoire : IFRS −7 953,932 M ou SYSCOHADA −6 131,8 M.** Les deux sont publiés. Le site retient l'IFRS. Le résultat est négatif : pas de P/E, le conseil ne dépend pas de ce choix. À trancher seulement pour l'affichage du bénéfice.

Aucune de ces décisions n'a été appliquée au code de calcul.
