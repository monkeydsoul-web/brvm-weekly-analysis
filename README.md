# 📈 BRVM Analyzer

Tableau de bord d'analyse des 47 actions cotées à la **Bourse Régionale des Valeurs Mobilières (BRVM)** — marché financier commun à 8 pays d'Afrique de l'Ouest (UEMOA).

Application web locale (Flask, port 5000) à usage personnel. Interface en français, conçue pour être accessible aux débutants comme aux investisseurs expérimentés grâce à un mode d'affichage adaptatif.

---

## Présentation

BRVM Analyzer scrape les cours en temps réel depuis brvm.org, calcule 8 modèles de valorisation (Graham, DCF, DDM, EPV, Buffett, Reverse DCF, Relatif, Technique), génère un classement live des sociétés et propose une interface progressive disclosure adaptée au niveau de l'utilisateur.

**Fonctionnalités principales :**
- Classement live des 47 sociétés avec scores /10
- Fiche société : storytelling, ratios fondamentaux, analyse IA des rapports PDF (Claude Sonnet)
- Dashboard : KPIs, heatmap, opportunités, signaux du marché
- Portefeuille : suivi des positions, gains/pertes, dividendes
- Screener : filtres multi-critères (P/E, score, dividende, ROE…)
- Mode débutant / expert : affichage adaptatif
- Multi-devises : XOF, EUR, USD
- Alertes prix via notifications push (Service Worker)

---

## Stack & Architecture

| Couche | Technologie |
|--------|-------------|
| Backend | Python 3.9 · Flask · APScheduler (~12 jobs) |
| Scraping | `live_data.py`, `boc_scraper.py`, `reports_scraper.py` |
| IA | API Anthropic — Claude Sonnet (analyse PDF + contenu pédagogique) |
| Frontend | HTML/CSS/JS vanilla — `dashboard/index.html` (~8 000 lignes) + ~15 fichiers `.js` |
| Données | Fichiers JSON dans `data/` (cache cours, ranking, annonces, rapports…) |
| Notifications | Service Worker `dashboard/sw.js` — alertes prix en arrière-plan |

L'application tourne exclusivement en local (`localhost:5000`). Aucun déploiement en production.

---

## Prérequis

- Python 3.9+
- pip
- Clé API Anthropic (pour les analyses IA)

---

## Installation

```bash
git clone https://github.com/monkeydsoul-web/brvm-weekly-analysis.git
cd brvm-weekly-analysis
pip install -r requirements.txt
```

---

## Variables d'environnement

La clé API Anthropic doit être disponible dans le shell. Ajouter dans `~/.zprofile` :

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Puis recharger :

```bash
source ~/.zprofile
```

---

## Lancement

```bash
python3 app.py
```

L'application démarre sur **http://localhost:5000**.

Le port 5000 est fixe et ne doit pas être modifié (références hardcodées dans le frontend).

---

## Structure des dossiers

```
brvm-weekly-analysis/
├── app.py                   # Serveur Flask — routes API et serving du frontend
├── live_data.py             # Scraping live brvm.org (cours, indices)
├── boc_scraper.py           # Scraping BOC (données fondamentales officielles)
├── reports_scraper.py       # Téléchargement et indexation des rapports PDF
├── pdf_analyzer.py          # Analyse IA des rapports PDF (Claude)
├── live_ranker.py           # Calcul du score composite et classement
├── valuation.py             # Modèles de valorisation (Graham, DCF, DDM…)
├── auto_scheduler.py        # Planificateur APScheduler (~12 jobs)
├── requirements.txt
├── data/                    # Cache JSON (cours, scores, annonces, news…)
├── dashboard/
│   ├── index.html           # Frontend monolithique (~8 000 lignes)
│   ├── badges.js            # Badges rang et KPI cards fiche société
│   ├── ranking.js           # Classement live + auto-refresh
│   ├── screener.js          # Filtres screener
│   ├── dash-hierarchy.js    # Hiérarchie 3 niveaux dashboard
│   ├── alerts.js            # Alertes prix
│   ├── compare.js           # Comparaison multi-actions
│   └── sw.js                # Service Worker (notifications push)
├── reports/                 # Rapports PDF archivés
└── logs/                    # Logs d'exécution
```

---

## Conventions de code

### Port fixe
Le port Flask est **5000**. Ne pas le modifier.

### Mode débutant / expert
Le mode est contrôlé par l'attribut `data-mode` sur la balise `<html>` (`beginner` ou `expert`).  
La règle CSS suivante masque automatiquement les éléments réservés aux experts :

```css
[data-mode="beginner"] .expert-only { display: none !important; }
```

Tout élément réservé aux experts reçoit la classe `.expert-only`.

### Formatage monétaire
Utiliser systématiquement `fmtXOF(valeur)` — cette fonction formate selon la devise active (XOF / EUR / USD) malgré son nom. Ne jamais utiliser `.toLocaleString('fr-FR') + ' XOF'` en dur.

### Apostrophes françaises en JS
Tout nouveau code JS contenant des apostrophes françaises ou des caractères spéciaux doit aller dans un **fichier `.js` séparé** sous `dashboard/`. Jamais inline dans `index.html`.

### Bloc JS inline de index.html
Le bloc `<script>` inline de `dashboard/index.html` ne doit **jamais être restructuré, réindenté ou déplacé**. Seuls des edits minimaux et ciblés sont autorisés. Toute nouvelle logique va dans un fichier `.js` séparé.

---

## Avertissement

Ce projet est à usage **personnel et éducatif uniquement**.  
Il ne constitue pas un conseil en investissement.  
Consultez un conseiller financier avant toute décision d'investissement.
