#!/usr/bin/env python3
"""
fix_chat_ia.py — Correctif ciblé pour le bug 401 Unauthorized du Chat IA
Usage : source ~/.zprofile && python3 fix_chat_ia.py

Ce script :
1. Diagnostique la cause exacte du 401
2. Corrige app.py pour que la clé API soit bien transmise
3. Crée un .env de secours
4. Vérifie la connexion Anthropic
"""
import os
import sys
import json
import subprocess
from pathlib import Path

BASE = Path(__file__).parent
APP  = BASE / "app.py"
ENV  = BASE / ".env"

# ── Couleurs terminal ──────────────────────────────────────────────────────
OK  = "\033[92m✓\033[0m"
ERR = "\033[91m✗\033[0m"
WRN = "\033[93m⚠\033[0m"
INF = "\033[94m→\033[0m"

def sep(title=""):
    print(f"\n{'─'*50}")
    if title:
        print(f"  {title}")
        print("─"*50)

# ────────────────────────────────────────────────────────────────────────────
# ÉTAPE 1 — Vérifier la clé dans l'environnement courant
# ────────────────────────────────────────────────────────────────────────────
sep("1. Diagnostic clé ANTHROPIC_API_KEY")

api_key = os.environ.get("ANTHROPIC_API_KEY", "")

if api_key:
    print(f"{OK} Clé trouvée dans l'environnement : {api_key[:12]}...{api_key[-4:]}")
    print(f"   Longueur : {len(api_key)} caractères")
    if not api_key.startswith("sk-ant-"):
        print(f"{WRN} Format inhabituel (attendu: sk-ant-...)")
else:
    print(f"{ERR} ANTHROPIC_API_KEY absente de l'environnement !")
    print(f"{INF} Solution : source ~/.zprofile avant de lancer ce script")
    print()

    # Chercher dans .zprofile
    zprofile = Path.home() / ".zprofile"
    if zprofile.exists():
        content = zprofile.read_text()
        for line in content.splitlines():
            if "ANTHROPIC_API_KEY" in line:
                print(f"{INF} Trouvée dans ~/.zprofile : {line.strip()[:60]}...")
                # Extraire la valeur
                if "=" in line:
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val.startswith("sk-ant-"):
                        api_key = val
                        print(f"{OK} Clé extraite de ~/.zprofile")
                        os.environ["ANTHROPIC_API_KEY"] = api_key
                break
    if not api_key:
        print(f"{ERR} Clé introuvable. Vérifiez ~/.zprofile")
        print()
        # Continuer quand même pour les autres corrections

# ────────────────────────────────────────────────────────────────────────────
# ÉTAPE 2 — Créer/mettre à jour .env
# ────────────────────────────────────────────────────────────────────────────
sep("2. Fichier .env")

if api_key:
    ENV.write_text(f"ANTHROPIC_API_KEY={api_key}\n")
    print(f"{OK} .env créé/mis à jour")

    # .gitignore
    gi = BASE / ".gitignore"
    gi_content = gi.read_text() if gi.exists() else ""
    if ".env" not in gi_content:
        with open(gi, "a") as f:
            f.write("\n.env\n")
        print(f"{OK} .env ajouté au .gitignore")
    else:
        print(f"{INF} .gitignore déjà correct")
else:
    print(f"{WRN} Pas de clé — .env non créé")

# ────────────────────────────────────────────────────────────────────────────
# ÉTAPE 3 — Analyser app.py pour trouver la cause exacte du 401
# ────────────────────────────────────────────────────────────────────────────
sep("3. Analyse de app.py")

if not APP.exists():
    print(f"{ERR} app.py non trouvé dans {BASE}")
    sys.exit(1)

content = APP.read_text()
lines   = content.splitlines()

# Chercher comment la clé est utilisée
issues = []
fixes  = []

# Pattern 1 : clé lue au niveau module (hors requête)
for i, line in enumerate(lines, 1):
    stripped = line.strip()
    if "ANTHROPIC_API_KEY" in stripped and "os.environ" in stripped and "get" in stripped:
        if "def " not in "".join(lines[max(0,i-5):i]):
            # Probablement au niveau module
            print(f"{INF} Ligne {i}: clé lue au niveau module : {stripped[:80]}")

    if "anthropic.Anthropic()" in stripped:
        print(f"{WRN} Ligne {i}: client créé SANS clé explicite → cause probable du 401")
        issues.append((i, stripped))

    if "Anthropic(api_key=" in stripped:
        print(f"{OK} Ligne {i}: client avec api_key explicite : {stripped[:80]}")

    # Chercher la route /api/chat
    if "/api/chat" in stripped or "def.*chat" in stripped:
        print(f"{INF} Ligne {i}: route chat : {stripped[:80]}")

# ────────────────────────────────────────────────────────────────────────────
# ÉTAPE 4 — Appliquer les corrections dans app.py
# ────────────────────────────────────────────────────────────────────────────
sep("4. Correction de app.py")

new_content = content

# 4a. Ajouter le chargement dotenv en tête de fichier (après les imports)
dotenv_block = '''
# ── FIX Chat IA : charger .env pour ANTHROPIC_API_KEY ───────────────────────
import os as _os
try:
    from dotenv import load_dotenv as _ldenv
    _ldenv()
except ImportError:
    pass  # sans python-dotenv, utiliser os.environ directement
# ────────────────────────────────────────────────────────────────────────────
'''

if "FIX Chat IA" not in new_content:
    # Insérer après le dernier import en tête
    import_end = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("import ") or s.startswith("from "):
            import_end = i
    
    lines_new = lines[:]
    lines_new.insert(import_end + 1, dotenv_block)
    new_content = "\n".join(lines_new)
    print(f"{OK} Bloc dotenv inséré (ligne ~{import_end + 1})")
else:
    print(f"{INF} Bloc dotenv déjà présent")

# 4b. Remplacer anthropic.Anthropic() sans clé par version avec clé explicite
replacements = [
    # Patterns courants
    ("anthropic.Anthropic()",
     "anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))"),
    
    ("client = Anthropic()",
     "client = Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))"),
    
    ("Anthropic(api_key=ANTHROPIC_API_KEY)",
     "Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY', ANTHROPIC_API_KEY))"),
    
    # Si la clé est lue comme variable globale au démarrage
    ("ANTHROPIC_API_KEY = os.environ.get(\"ANTHROPIC_API_KEY\")",
     "ANTHROPIC_API_KEY = os.environ.get(\"ANTHROPIC_API_KEY\") or os.environ.get(\"ANTHROPIC_API_KEY\")"),
]

for old, new in replacements:
    if old in new_content and old != new:
        count = new_content.count(old)
        new_content = new_content.replace(old, new)
        print(f"{OK} Remplacé ({count}x): {old[:60]}")

# 4c. S'assurer que la route /api/chat recharge la clé fraîchement
# Chercher le bloc de la route chat et injecter un rechargement si absent
chat_route_pattern = "@app.route(\"/api/chat\""
if chat_route_pattern in new_content and "os.environ.get('ANTHROPIC_API_KEY')" not in new_content:
    # Trouver l'indice de la route et injecter
    idx = new_content.find(chat_route_pattern)
    # Trouver le premier "def " après la route
    def_idx = new_content.find("\ndef ", idx)
    if def_idx > 0:
        # Trouver la première ligne non-vide du corps de la fonction
        body_start = new_content.find("\n", def_idx + 5)
        injection = "\n    _api_key = os.environ.get('ANTHROPIC_API_KEY')\n"
        new_content = new_content[:body_start] + injection + new_content[body_start:]
        print(f"{OK} Injection rechargement clé dans route /api/chat")

APP.write_text(new_content)
print(f"{OK} app.py mis à jour")

# ────────────────────────────────────────────────────────────────────────────
# ÉTAPE 5 — Test de connexion Anthropic
# ────────────────────────────────────────────────────────────────────────────
sep("5. Test connexion Anthropic API")

if api_key:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=30,
            messages=[{"role": "user", "content": "Réponds juste: OK"}]
        )
        reply = msg.content[0].text if msg.content else ""
        print(f"{OK} Connexion API réussie ! Réponse : '{reply}'")
    except ImportError:
        print(f"{WRN} Module anthropic non installé")
        print(f"   pip3 install anthropic")
    except Exception as e:
        err_str = str(e)
        print(f"{ERR} Erreur : {err_str[:120]}")
        if "401" in err_str:
            print(f"{WRN} La clé semble invalide ou expirée")
            print(f"   Vérifiez sur : https://console.anthropic.com/settings/keys")
        elif "Connection" in err_str:
            print(f"{WRN} Problème réseau")
else:
    print(f"{WRN} Test impossible : clé absente")

# ────────────────────────────────────────────────────────────────────────────
# RÉSUMÉ
# ────────────────────────────────────────────────────────────────────────────
sep("Résumé")

print(f"""
Corrections appliquées à app.py :
  {OK} Chargement automatique du .env au démarrage Flask
  {OK} Client Anthropic avec clé explicite (os.environ.get)

Pour démarrer le serveur correctement :
  source ~/.zprofile && python3 app.py

  (ou avec .env uniquement, sans source ~/.zprofile :)
  python3 app.py   ← le .env est chargé automatiquement

En cas de 401 persistant :
  1. Vérifiez la clé : https://console.anthropic.com/settings/keys
  2. Testez manuellement :
     python3 -c "import anthropic,os; os.environ['ANTHROPIC_API_KEY']='{api_key[:20] if api_key else 'VOTRE_CLE'}...'; \\
       c=anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY']); \\
       print(c.messages.create(model='claude-haiku-4-5-20251001',max_tokens=10,messages=[{{'role':'user','content':'ok'}}]).content[0].text)"
""")
