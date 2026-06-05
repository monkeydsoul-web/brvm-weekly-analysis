# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.  
Les entrées sont dérivées de `git log --oneline` — aucune entrée inventée.  
Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/).

---

## [Non publié]

### Refactorisation
- `cbc88cf` — **refactor(settings)** : déplace activation notifications push du tiroir vers Paramètres
- `853a55b` — **chore** : sécuriser fallback scores + supprimer snapshot figé
- `0c71da7` — **chore** : suppression code mort

### Corrections
- `8f23c78` — **fix(fiche)** : verdict analyste conforme termino débutant (Sprint 19)
- `4b258aa` — **fix(fiche)** : badges BNA/BVPA suivent la devise sélectionnée (Sprint 16)
- `39cb5a7` — **fix(nav)** : libellés propres du fil d'Ariane — Apprendre, Accueil (Sprint 15-B)
- `3092584` — **fix(devise)** : conversion des prix + sparklines du Classement (Sprint 15-A)
- `137f9ff` — **fix(fiche)** : normalise an.perspectives en tableau dans toggleStockAnalyse (Sprint 11-fix-3)
- `edb54dc` — **fix(fiche)** : retire le bouton Comparer en doublon dans la barre d'actions (Sprint 11-fix-2)
- `87ef194` — **fix(fiche)** : dédoublonne rapports + scoring dans Chiffres, onglets remontés (Sprint 11-fix)
- `aac86dc` — **fix(stock)** : fiche société responsive mobile, colonne principale clippée
- `3245153` — **fix(stock)** : repositionne le bloc storytelling au-dessus du contenu technique
- `1a4ba7b` — **fix(nav)** : renderGlossaire jamais déclenchée lors de la navigation
- `fddd01e` — **fix(mobile)** : doublon "XOF XOF" sur le prix des cartes Classement
- `cd94c33` — **fix(mobile)** : cartes Classement écrasées par redéfinition silencieuse
- `a0da12c` — **fix(css)** : mobile responsiveness — viewport zoom, footer, tap targets
- `b8d9b51` — **fix(stock)** : bouton Partager affichait du JSON brut au lieu de son libellé
- `3dc9bf1` — **fix(js)** : supprime doublon de déclaration bcEl ligne 7282
- `0412185` — **fix(data)** : BICB + CABC + SIBC — shares et RN corrigés, P/E pilotés per_boc officiel
- `53851ed` — **fix(data)** : correction nombre d'actions SIBC — 10M → 65M (erreur de saisie)
- `3c027ff` — **fix(valorisation)** : garde-fou cibles aberrantes (Option A sanity check)
- `00c586f` — **fix(valorisation)** : FTSC — ne plus afficher Bonne affaire pour dividende exceptionnel
- `046adbc` — **fix(startup)** : exécuter validate_dividend au démarrage Flask avant de servir
- `42c89e2` — **fix(api)** : /api/dividends manquait les champs div_confidence et div_flag

### Nouvelles fonctionnalités
- `b47b377` — **merge** : menu en tiroir ☰ épuré (Sprints 17-18)
- `aa3f795` — **feat(nav)** : tiroir épuré — 4 sections, gros boutons, footer rangé (Sprint 18)
- `e9141ee` — **feat(nav)** : navigation en tiroir ☰ sur tous les écrans (Sprint 17)
- `3fad9dd` — **feat(nav)** : bouton retour sur toutes les pages + fil d'Ariane « BRVM » cliquable (Sprint 14)
- `5e9d13e` — **feat(sidebar)** : masque outils experts en mode débutant — Valorisation, Marché, Alertes + lien marché (Sprint 13)
- `f059229` — **feat(dash)** : hiérarchie 3 niveaux (N1 épuré / N2 analyse&suivi / N3 statu quo) (Sprint 12)
- `73dfb03` — **feat(stock)** : refonte fiche société en 3 onglets (Comprendre / Chiffres / Documents)
- `befd7b3` — **feat(design)** : fondations du design system (tokens + composants réutilisables)
- `29971bc` — **feat(stock)** : affichage fiches storytelling au-dessus du contenu technique
- `246231e` — **feat(stories)** : script de génération des fiches storytelling (47 sociétés)
- `4fe2ca3` — **feat** : boot adaptatif + item sidebar Accueil (Sprint 8 commit 2)
- `2b300fd` — **feat** : page d'accueil 3 portes (welcome + apprendre) (Sprint 8 commit 1)
- `c93f6db` — **feat(ux)** : onboarding propre quand portefeuille vide en mode débutant
- `088ce51` — **feat(mobile)** : classement en cartes au lieu de tableau scrollable
- `247240c` — **feat(ui)** : navigation — page Marché unifiée, screener vide par défaut, Markowitz expert
- `836118e` — **feat(validation)** : 3e source externe african-markets.com + logique confiance 3 sources
