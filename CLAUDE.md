# Doctrine BRVM Analyzer — règles permanentes pour Claude Code

## Contexte technique
- App Flask + JS vanilla, Python 3.9 (INTERDIT: types `X|Y`), port 5000.
- Relance Flask : `source ~/.zprofile; pkill -9 -f app.py; sleep 1; python3 app.py > /tmp/flask_brvm.log 2>&1 &`
- Branche de travail : feature/refonte-nav-v2. JAMAIS de push (verrouillé par settings).

## Git
- `git add` CIBLÉ uniquement, fichier par fichier. JAMAIS `git add -A`, `--all` ou `git add .` (verrouillés).
- 1 objectif = 1 commit, message en français.
- Les `data/*.json` sont des caches réécrits par Flask : ne JAMAIS les committer ni les add.

## Obéissance aux prompts
- Suivre les prompts À LA LETTRE : ne pas réécrire les phases, ne pas étendre ou réduire le périmètre, ne pas « compléter » les listes de fichiers.
- Un prompt marqué ⏸ STOP ou LECTURE SEULE = AUCUNE édition, AUCUN commit, AUCUN rm.
- Toute preuve demandée (diff, status, diagnostic) = sortie BRUTE (`git --no-pager ...`) écrite dans `dashboard/_diag_<sujet>.txt`. Jamais de synthèse à coches à la place. Ces fichiers ne sont JAMAIS committés.

## Code
- JS contenant des apostrophes françaises → fichier `.js` séparé sous `dashboard/`, jamais inline dans index.html.
- Ne JAMAIS réindenter ou reformater le gros bloc inline de `dashboard/index.html` : éditions chirurgicales uniquement.
- Modules VIVANTS, interdiction de les supprimer : scraper.py, backtesting.py, portfolio_optimizer.py, candlestick.py, price_history.py.
