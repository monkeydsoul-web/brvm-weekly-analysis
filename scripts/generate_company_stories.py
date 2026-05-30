#!/usr/bin/env python3
"""
Sprint 9A — Génération des fiches storytelling pour les 47 sociétés BRVM.

Usage :
  python3 scripts/generate_company_stories.py            # génère les tickers manquants
  python3 scripts/generate_company_stories.py --ticker SNTS   # un seul ticker
  python3 scripts/generate_company_stories.py --force         # tout régénérer
  python3 scripts/generate_company_stories.py --dry-run       # voir le prompt, pas d'appel API
  python3 scripts/generate_company_stories.py --dry-run --ticker SNTS
"""

import argparse
import json
import os
import pathlib
import sys
import tempfile
import time
from datetime import datetime, timezone

import anthropic

# ── Chemins ───────────────────────────────────────────────────────────────────

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LIVE_RANKING_PATH = DATA_DIR / "live_ranking.json"
ANALYSES_SUMMARY_PATH = DATA_DIR / "analyses_summary.json"
OUTPUT_PATH = DATA_DIR / "companies_stories.json"

# ── Constantes ────────────────────────────────────────────────────────────────

MODEL = "claude-sonnet-4-6"
REQUIRED_KEYS = {"en_bref", "points_forts", "points_attention", "activites", "presence"}
MAX_RETRIES = 3
RETRY_BACKOFF = [2, 5, 10]   # secondes entre tentatives
SLEEP_BETWEEN_CALLS = 1.0    # secondes entre tickers (rate limit)

# Emoji drapeaux UEMOA + autres pays BRVM
COUNTRY_FLAGS = {
    "Sénégal":        "🇸🇳",
    "Côte d'Ivoire":  "🇨🇮",
    "Burkina Faso":   "🇧🇫",
    "Mali":           "🇲🇱",
    "Niger":          "🇳🇪",
    "Togo":           "🇹🇬",
    "Bénin":          "🇧🇯",
    "Guinée-Bissau":  "🇬🇼",
    "France":         "🇫🇷",
    "Maroc":          "🇲🇦",
}

# ── Chargement des données ─────────────────────────────────────────────────────

def load_existing_stories(path: pathlib.Path) -> dict:
    """Retourne le dict complet stories ou un squelette vide."""
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] Impossible de lire {path} : {e} — repartir de zéro")
    return {"_meta": {}, "stories": {}}


def save_stories(stories: dict, path: pathlib.Path) -> None:
    """Écriture atomique via fichier temporaire dans le même répertoire."""
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".json.tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(stories, f, ensure_ascii=False, indent=2)
        pathlib.Path(tmp_path).replace(path)
    except Exception:
        pathlib.Path(tmp_path).unlink(missing_ok=True)
        raise


def load_ticker_metadata() -> dict:
    """
    Fusionne live_ranking.json et analyses_summary.json.
    Retourne un dict {ticker: {name, sector, country, ...champs narratifs...}}.
    """
    with open(LIVE_RANKING_PATH, encoding="utf-8") as f:
        lr = json.load(f)
    ranking = lr.get("ranking", [])

    with open(ANALYSES_SUMMARY_PATH, encoding="utf-8") as f:
        summary = json.load(f)

    metadata = {}
    for rec in ranking:
        ticker = rec.get("ticker")
        if not ticker:
            continue
        summ = summary.get(ticker, {})
        metadata[ticker] = {
            # Identité
            "ticker":   ticker,
            "name":     rec.get("name", ""),
            "sector":   rec.get("sector", ""),
            "country":  rec.get("country", ""),
            # Verdict
            "pdf_verdict": rec.get("pdf_verdict", ""),
            # Narratif depuis live_ranking (extrait du rapport PDF)
            "pdf_resume":       rec.get("pdf_resume", ""),
            "pdf_points_cles":  rec.get("pdf_points_cles") or [],
            # Narratif depuis analyses_summary (analyse IA plus riche)
            "resume":       summ.get("resume", ""),
            "points_cles":  summ.get("points_cles") or [],
            "risques":      summ.get("risques") or [],
            "perspectives": summ.get("perspectives", ""),
            "verdict_investisseur": summ.get("verdict_investisseur", ""),
        }
    return metadata


# ── Construction du prompt ─────────────────────────────────────────────────────

def _fmt_list(items, max_items: int = 5) -> str:
    if not items:
        return "  (non disponible)"
    return "\n".join(f"  - {it}" for it in items[:max_items])


def build_prompt(ticker: str, meta: dict) -> str:
    name      = meta.get("name", ticker)
    sector    = meta.get("sector", "Non précisé")
    country   = meta.get("country", "Non précisé")
    verdict   = meta.get("verdict_investisseur") or meta.get("pdf_verdict") or "Non disponible"

    # Résumé : préférer celui d'analyses_summary (plus riche), fallback sur pdf_resume
    resume = (meta.get("resume") or meta.get("pdf_resume") or "").strip()

    # Points clés : fusionner les deux sources (dédoublonnage naïf)
    pts_a = meta.get("points_cles") or []
    pts_b = meta.get("pdf_points_cles") or []
    all_pts = list({p for p in pts_a + pts_b if p})[:6]

    risques = meta.get("risques") or []
    perspectives = (meta.get("perspectives") or "").strip()

    # Drapeau du pays
    flag = COUNTRY_FLAGS.get(country, "🌍")
    presence_hint = f"{flag} {country}"

    sections = []

    if resume:
        sections.append(f"Résumé d'activité :\n{resume[:600]}")

    if all_pts:
        sections.append("Points clés (extraits des rapports officiels) :\n" + _fmt_list(all_pts))

    if risques:
        sections.append("Risques identifiés :\n" + _fmt_list(risques))

    if perspectives:
        sections.append(f"Perspectives :\n{perspectives[:400]}")

    context_block = "\n\n".join(sections) if sections else "(Données narratives non disponibles — reste très général)"

    prompt = f"""Tu vas rédiger une fiche descriptive pour une société cotée à la BRVM (Bourse Régionale des Valeurs Mobilières d'Afrique de l'Ouest, marché commun aux 8 pays UEMOA).

Cible du texte : un investisseur débutant francophone basé en Afrique de l'Ouest, qui ne connaît pas cette société.

=== DONNÉES FACTUELLES DISPONIBLES ===
Ticker     : {ticker}
Nom        : {name}
Secteur    : {sector}
Pays       : {country}
Verdict    : {verdict}
Pays (présence connue) : {presence_hint}

{context_block}

=== RÈGLES STRICTES ===
- Utilise UNIQUEMENT les informations ci-dessus. N'ajoute aucun fait externe.
- Ne mentionne AUCUN chiffre précis (montants, dates, nombres d'employés) qui ne figure pas dans le contexte fourni.
- Ne mentionne AUCUN nom de personne (PDG, fondateurs, dirigeants).
- Ne mentionne AUCUN événement précis daté non présent dans le contexte.
- Style : descriptif, accessible, sans jargon financier. Phrases courtes.
- Si une section manque d'information, rédige "À enrichir." (une phrase).
- Pour la liste "presence", inclure uniquement les pays UEMOA/africains confirmés dans le contexte, avec leur emoji drapeau. Format : "🇸🇳 Sénégal".

Réponds en JSON strict, SANS markdown, SANS préambule, SANS texte après le JSON :

{{
  "en_bref": "Paragraphe de 2-3 phrases présentant la société : qui c'est, ce qu'elle fait, sa place dans le marché.",
  "points_forts": ["Point fort 1 (1 phrase)", "Point fort 2", "Point fort 3"],
  "points_attention": ["Risque ou limite 1 (1 phrase)", "Risque 2"],
  "activites": ["Activité principale 1", "Activité 2"],
  "presence": ["{presence_hint}"]
}}"""

    return prompt


# ── Appel API ──────────────────────────────────────────────────────────────────

def call_claude(client: anthropic.Anthropic, prompt: str, ticker: str) -> dict:
    """
    Appelle Claude avec retry/backoff. Retourne le dict JSON validé.
    Lève une exception si tous les retries échouent.
    """
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            extra = "\n\nRéponds avec un JSON valide uniquement, sans préambule ni markdown." if attempt > 0 else ""
            message = client.messages.create(
                model=MODEL,
                max_tokens=800,
                messages=[{"role": "user", "content": prompt + extra}],
            )
            raw = message.content[0].text.strip()

            # Nettoyer un éventuel bloc ```json ... ```
            if raw.startswith("```"):
                lines = raw.splitlines()
                raw = "\n".join(
                    l for l in lines
                    if not l.strip().startswith("```")
                )

            data = json.loads(raw)
            if validate_response(data):
                return data

            last_error = f"JSON valide mais clés manquantes : {REQUIRED_KEYS - set(data.keys())}"

        except json.JSONDecodeError as e:
            last_error = f"JSONDecodeError: {e}"
        except anthropic.APIError as e:
            last_error = f"APIError: {e}"
        except Exception as e:
            last_error = f"Erreur inattendue: {e}"

        if attempt < MAX_RETRIES - 1:
            wait = RETRY_BACKOFF[attempt]
            print(f"  [retry {attempt + 1}/{MAX_RETRIES}] {ticker} — {last_error} — attente {wait}s")
            time.sleep(wait)

    raise RuntimeError(f"Échec après {MAX_RETRIES} tentatives pour {ticker} : {last_error}")


def validate_response(data: dict) -> bool:
    """Vérifie que toutes les clés requises sont présentes et non vides."""
    if not isinstance(data, dict):
        return False
    for key in REQUIRED_KEYS:
        if key not in data:
            return False
        val = data[key]
        if not val:
            return False
        if key in ("points_forts", "points_attention", "activites", "presence"):
            if not isinstance(val, list) or len(val) == 0:
                return False
    return True


# ── Logique principale ─────────────────────────────────────────────────────────

def generate_story(
    client: anthropic.Anthropic,
    ticker: str,
    meta: dict,
    dry_run: bool = False,
) -> dict:
    """Génère et retourne la fiche pour un ticker."""
    prompt = build_prompt(ticker, meta)

    if dry_run:
        print(f"\n{'=' * 70}")
        print(f"PROMPT pour {ticker} ({meta.get('name', '')})")
        print('=' * 70)
        print(prompt)
        return {}

    data = call_claude(client, prompt, ticker)
    data["reviewed"] = False
    data["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Génère les fiches storytelling BRVM via Claude Sonnet 4.6",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--ticker", metavar="TICKER", help="Régénère uniquement ce ticker")
    parser.add_argument("--force", action="store_true", help="Régénère tous les tickers (écrase l'existant)")
    parser.add_argument("--dry-run", action="store_true", help="Affiche le prompt sans appeler l'API")
    args = parser.parse_args()

    # Charger les métadonnées
    print("[load] Chargement des métadonnées...")
    try:
        metadata = load_ticker_metadata()
    except FileNotFoundError as e:
        print(f"[ERREUR] Fichier source introuvable : {e}", file=sys.stderr)
        sys.exit(1)

    all_tickers = sorted(metadata.keys())
    print(f"[load] {len(all_tickers)} tickers disponibles")

    # Charger les stories existantes
    stories_doc = load_existing_stories(OUTPUT_PATH)
    existing = stories_doc.get("stories", {})

    # Déterminer la liste à traiter
    if args.ticker:
        ticker_upper = args.ticker.upper()
        if ticker_upper not in metadata:
            print(f"[ERREUR] Ticker inconnu : {ticker_upper}. Disponibles : {', '.join(all_tickers)}", file=sys.stderr)
            sys.exit(1)
        to_process = [ticker_upper]
    elif args.force:
        to_process = all_tickers
    else:
        to_process = [t for t in all_tickers if t not in existing or "error" in existing.get(t, {})]

    if not to_process:
        print("[OK] Toutes les fiches sont déjà générées. Utilisez --force pour tout réécrire.")
        return

    print(f"[plan] {len(to_process)} ticker(s) à traiter : {', '.join(to_process)}")

    if args.dry_run:
        # Dry-run : affiche le prompt du premier ticker (ou du ticker ciblé)
        target = to_process[0]
        generate_story(None, target, metadata[target], dry_run=True)
        return

    # Initialiser le client Anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[ERREUR] Variable d'environnement ANTHROPIC_API_KEY non définie.", file=sys.stderr)
        sys.exit(1)
    client = anthropic.Anthropic(api_key=api_key)

    # Boucle principale
    ok_count = 0
    err_count = 0
    for i, ticker in enumerate(to_process, 1):
        meta = metadata[ticker]
        print(f"[{i:02d}/{len(to_process)}] {ticker} — {meta.get('name', '')} ({meta.get('sector', '')})", end=" ", flush=True)
        try:
            story = generate_story(client, ticker, meta, dry_run=False)
            existing[ticker] = story
            ok_count += 1
            print("✓")
        except RuntimeError as e:
            existing[ticker] = {
                "error": str(e),
                "reviewed": False,
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            err_count += 1
            print(f"✗ {e}")

        # Sauvegarde incrémentale après chaque ticker
        stories_doc["stories"] = existing
        stories_doc["_meta"] = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": MODEL,
            "version": 1,
        }
        save_stories(stories_doc, OUTPUT_PATH)

        if i < len(to_process):
            time.sleep(SLEEP_BETWEEN_CALLS)

    # Résumé final
    print(f"\n[done] {ok_count} fiches générées, {err_count} erreurs")
    print(f"[done] Fichier : {OUTPUT_PATH}")
    if err_count > 0:
        failed = [t for t in to_process if "error" in existing.get(t, {})]
        print(f"[done] Tickers en erreur (à relancer) : {', '.join(failed)}")
        print(f"[done] Commande : python3 scripts/generate_company_stories.py --ticker <TICKER>")


if __name__ == "__main__":
    main()
