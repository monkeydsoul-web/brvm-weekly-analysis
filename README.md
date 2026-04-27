# 📈 BRVM Weekly Analyzer

Système d'analyse automatique hebdomadaire de toutes les actions cotées à la **Bourse Régionale des Valeurs Mobilières (BRVM)**.

Chaque vendredi soir, le système :
1. **Scrape** les cours officiels depuis brvm.org
2. **Calcule** 7 scores de valorisation (Graham, DCF, DDM, EPV, Buffett, Reverse DCF, Relatif)
3. **Génère** un rapport PDF complet avec graphiques et classement
4. **Commit** le rapport sur GitHub automatiquement

---

## 🚀 Installation rapide

### 1. Prérequis
- Python 3.10+ ([télécharger](https://python.org))
- Git ([télécharger](https://git-scm.com))
- Un compte GitHub

### 2. Cloner et installer

```bash
# Cloner ce repo
git clone https://github.com/TON_USERNAME/brvm-weekly-analysis.git
cd brvm-weekly-analysis

# Installer les dépendances
pip install -r requirements.txt
```

### 3. Configurer ton username GitHub

Dans `main.py`, ligne 20 :
```python
"github_username": "TON_USERNAME_GITHUB",
```

### 4. Initialiser le repo GitHub

```bash
# Initialiser git (si pas déjà fait)
git init
git add .
git commit -m "🎉 Initialisation du projet BRVM Analyzer"

# Créer le repo sur GitHub (via GitHub CLI ou manuellement sur github.com)
# Puis:
git remote add origin https://github.com/TON_USERNAME/brvm-weekly-analysis.git
git branch -M main
git push -u origin main
```

---

## 📋 Utilisation

### Lancer une analyse immédiatement
```bash
python main.py
```

### Lancer en mode hors-ligne (utilise le cache)
```bash
python main.py --offline
```

### Lancer sans push GitHub
```bash
python main.py --no-github
```

### Activer l'automatisation hebdomadaire
```bash
# Option A: Planificateur Python (laisser tourner)
python scheduler.py

# Option B: Cron (Linux/Mac) — toujours plus fiable
# Ouvrir le crontab:
crontab -e
# Ajouter cette ligne (vendredi à 20h00):
0 20 * * 5 cd /CHEMIN/VERS/brvm-weekly-analysis && python main.py >> logs/cron.log 2>&1

# Option C: Planificateur Windows
# Utiliser le Planificateur de tâches Windows:
# - Action: python main.py
# - Déclencheur: chaque vendredi à 20:00
# - Répertoire de démarrage: C:\CHEMIN\VERS\brvm-weekly-analysis
```

---

## 📁 Structure du projet

```
brvm-weekly-analysis/
├── main.py              # Orchestrateur principal
├── scraper.py           # Récupération des cours BRVM
├── valuation.py         # Moteur de scoring (7 modèles)
├── report_generator.py  # Générateur de rapport PDF
├── scheduler.py         # Planificateur hebdomadaire
├── requirements.txt     # Dépendances Python
├── data/
│   ├── prices_cache.json     # Cache des cours
│   └── scores_YYYYMMDD.json  # Historique des scores
├── reports/
│   └── BRVM_Analyse_YYYY_MM_DD.pdf  # Rapports hebdomadaires
└── logs/
    └── brvm_YYYYMMDD.log    # Logs d'exécution
```

---

## 📊 Les 7 modèles de valorisation

| Modèle | Description | Score |
|--------|-------------|-------|
| **Graham** | P/E≤15, P/B≤1.5, P/E×P/B≤22.5, dividende≥4% | /10 |
| **DCF/FCF** | Rendement des bénéfices + ROE | /10 |
| **DDM** | Dividend Discount Model (Gordon Growth) | /10 |
| **EPV** | Earnings Power Value (Greenwald) | /10 |
| **Buffett** | ROE, moat, stabilité, prix raisonnable | /10 |
| **Rev. DCF** | Croissance implicite vs réaliste | /10 |
| **Relatif** | Décote vs médiane sectorielle | /10 |
| **TOTAL** | Score composite (avec pénalité géopolitique) | /70 |

---

## 🔄 Mise à jour des données fondamentales

Les ratios P/E, P/B, ROE et dividendes de référence sont dans `scraper.py` (dictionnaire `STOCK_FUNDAMENTALS`).
**Mettre à jour une fois par an** après la publication des résultats annuels (généralement mars-avril).

---

## ⚠️ Avertissement

Ce système est produit à des fins **éducatives et informatives uniquement**.
Il ne constitue pas un conseil en investissement.
Consultez un conseiller financier avant toute décision d'investissement.

---

## 📝 Licence

MIT — Libre d'utilisation et de modification.
