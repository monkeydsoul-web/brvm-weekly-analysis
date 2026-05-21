#!/usr/bin/env python3
"""
announcements_summarizer.py — Résumés IA des annonces BRVM avec sentiment colorisé.

Lit data/brvm_announcements.json, télécharge les PDFs, génère résumés + sentiment
via Claude, stocke dans data/announcements_summaries.json (cache MD5 par source_url).

Usage :
    python3 scripts/announcements_summarizer.py --dry-run
    python3 scripts/announcements_summarizer.py --max-cost 8.0
    python3 scripts/announcements_summarizer.py --type dividendes --max-cost 2.0
    python3 scripts/announcements_summarizer.py --limit 10
"""

import anthropic, json, hashlib, time, base64, argparse, sys, os
import requests, urllib3
from pathlib import Path
from typing import Optional

urllib3.disable_warnings()

BASE_DIR       = Path(__file__).parent.parent
ANNONCES_PATH  = BASE_DIR / "data" / "brvm_announcements.json"
SUMMARIES_PATH = BASE_DIR / "data" / "announcements_summaries.json"
PDF_CACHE_DIR  = BASE_DIR / "data" / "announcement_pdfs"
PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

PROMPT_TEMPLATE = """Tu lis un document officiel publié par la BRVM (Bourse Régionale des \
Valeurs Mobilières d'Afrique de l'Ouest). Type d'annonce : {type}. Société concernée : {ticker}.

Tâche :
1. Résumer en 2-3 phrases SIMPLES (langage accessible, pas de jargon financier) \
ce que dit ce document. L'utilisateur n'est pas expert financier.
2. Déterminer si c'est une BONNE, NEUTRE ou MAUVAISE nouvelle pour les actionnaires.

Critères de sentiment :
- bonne : paiement dividende supérieur au précédent, résultats en hausse, nouveau contrat, \
rachat d'actions, notation améliorée, augmentation capital positive
- neutre : AG ordinaire de routine, paiement dividende stable, simple avis de calendrier, \
document procédural standard
- mauvaise : dividende réduit ou supprimé, perte de l'exercice, dégradation notation, \
démission suspecte d'un dirigeant, suspension cotation, augmentation capital dilutive

Réponds STRICTEMENT en JSON (pas de markdown, pas de balises) :
{{"summary": "phrase 1. phrase 2.", "sentiment": "bonne"|"neutre"|"mauvaise", \
"sentiment_reason": "explication courte"}}"""


def _load_summaries() -> dict:
    if SUMMARIES_PATH.exists():
        try:
            return json.loads(SUMMARIES_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_summaries(summaries: dict):
    SUMMARIES_PATH.write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _ann_id(source_url: str) -> str:
    return hashlib.md5(source_url.encode()).hexdigest()[:12]


def download_pdf(url: str, ann_id: str) -> Optional[Path]:
    fpath = PDF_CACHE_DIR / f"{ann_id}.pdf"
    if fpath.exists() and fpath.stat().st_size > 100:
        return fpath
    try:
        r = requests.get(url, headers=HEADERS, verify=False, timeout=30)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            fpath.write_bytes(r.content)
            return fpath
        print(f"    [skip] HTTP {r.status_code} ou pas un PDF : {url[-60:]}")
    except Exception as e:
        print(f"    [skip] Download error: {e}")
    return None


def summarize_announcement(ann: dict, client, force: bool = False) -> Optional[dict]:
    source_url = ann.get("source_url") or ann.get("pdf_url") or ann.get("lien")
    if not source_url:
        return None

    aid = _ann_id(source_url)
    summaries = _load_summaries()

    if aid in summaries and not force:
        return summaries[aid]

    pdf_path = download_pdf(source_url, aid)
    if not pdf_path:
        return None

    pdf_b64 = base64.standard_b64encode(pdf_path.read_bytes()).decode()
    ann_type = ann.get("_type") or ann.get("type") or "annonce"
    ticker = ann.get("ticker") or "?"
    prompt = PROMPT_TEMPLATE.format(type=ann_type, ticker=ticker)

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{"role": "user", "content": [
                {"type": "document", "source": {
                    "type": "base64", "media_type": "application/pdf", "data": pdf_b64
                }},
                {"type": "text", "text": prompt},
            ]}],
        )
        raw = resp.content[0].text.strip()
        # Nettoyer les éventuels fences markdown
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw.strip())
        cost = (resp.usage.input_tokens / 1e6) * 3.0 + (resp.usage.output_tokens / 1e6) * 15.0
        result = {
            "summary": data.get("summary", ""),
            "sentiment": data.get("sentiment", "neutre"),
            "sentiment_reason": data.get("sentiment_reason", ""),
            "source_url": source_url,
            "ticker": ticker,
            "type": ann_type,
            "date": ann.get("date"),
            "analyzed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "model": "claude-sonnet-4-6",
            "cost_usd": round(cost, 4),
        }
        summaries[aid] = result
        _save_summaries(summaries)
        return result
    except json.JSONDecodeError as e:
        print(f"    [skip] JSON parse error: {e} — raw: {raw[:80]}")
        return None
    except Exception as e:
        print(f"    [skip] API error: {e}")
        return None


def _flatten_announcements(data: dict, type_filter: Optional[str] = None) -> list:
    """Flatten la structure {type: [items]} en liste avec _type injecté."""
    items = []
    for cat, sublist in data.items():
        if type_filter and cat.lower() != type_filter.lower():
            continue
        for ann in sublist:
            items.append({**ann, "_type": cat})
    return items


def main():
    parser = argparse.ArgumentParser(description="Résumés IA annonces BRVM")
    parser.add_argument("--limit", type=int, default=None, help="Nombre max d'annonces")
    parser.add_argument("--max-cost", type=float, default=10.0, help="Budget USD max")
    parser.add_argument("--dry-run", action="store_true", help="Afficher sans appeler l'API")
    parser.add_argument("--force", action="store_true", help="Ré-analyser même si en cache")
    parser.add_argument("--type", type=str, default=None,
                        help="Filtrer par type (ex: dividendes, convocations_ag)")
    args = parser.parse_args()

    if not ANNONCES_PATH.exists():
        print("brvm_announcements.json introuvable")
        sys.exit(1)

    data = json.loads(ANNONCES_PATH.read_text(encoding="utf-8"))
    anns = _flatten_announcements(data, args.type)

    # Filtrer celles qui ont une URL PDF
    anns = [a for a in anns if a.get("source_url") or a.get("pdf_url")]

    # Filtrer déjà en cache (sauf --force)
    summaries = _load_summaries()
    if not args.force:
        pending = [a for a in anns if _ann_id(
            a.get("source_url") or a.get("pdf_url") or ""
        ) not in summaries]
        cached = len(anns) - len(pending)
    else:
        pending = anns
        cached = 0

    if args.limit:
        pending = pending[:args.limit]

    est_cost = len(pending) * 0.05  # ~0.05$/annonce (PDF court, ~5k tokens)

    print(f"\n{'═'*60}")
    print(f"  Résumés IA annonces BRVM")
    print(f"  Total avec PDF         : {len(anns)}")
    if args.type:
        print(f"  Filtre type            : {args.type}")
    print(f"  Déjà en cache          : {cached}")
    print(f"  À analyser             : {len(pending)}")
    print(f"  Coût estimé            : ~${est_cost:.2f} USD")
    print(f"  Budget max             : ${args.max_cost:.2f} USD")
    print(f"{'═'*60}\n")

    if args.dry_run:
        print("  [dry-run] Annonces à analyser :")
        for a in pending[:20]:
            ticker = a.get("ticker") or "?"
            atype = a.get("_type") or "?"
            date = a.get("date") or "?"
            print(f"    [{ticker}] {atype} {date}")
        if len(pending) > 20:
            print(f"    ... et {len(pending)-20} autres")
        return

    if est_cost > args.max_cost:
        print(f"❌ Coût estimé ${est_cost:.2f} dépasse le budget de ${args.max_cost:.2f}")
        print(f"   Utilisez --limit ou --type pour réduire le scope")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("⚠️  ANTHROPIC_API_KEY non défini")
        sys.exit(1)

    if pending:
        try:
            input(f"⚠️  Continuer avec {len(pending)} analyses (~${est_cost:.2f}) ? "
                  f"[Enter / Ctrl-C] ")
        except KeyboardInterrupt:
            print("\nAnnulé.")
            sys.exit(0)

    client = anthropic.Anthropic(api_key=api_key)
    total_cost = ok = skip = 0
    dist = {"bonne": 0, "neutre": 0, "mauvaise": 0}

    for i, ann in enumerate(pending):
        ticker = ann.get("ticker") or "?"
        atype = ann.get("_type") or "?"
        date = ann.get("date") or "?"
        print(f"  [{i+1}/{len(pending)}] [{ticker}] {atype} {date}…", end=" ", flush=True)

        res = summarize_announcement(ann, client, force=args.force)
        if res:
            ok += 1
            total_cost += res.get("cost_usd", 0)
            sent = res.get("sentiment", "neutre")
            dist[sent] = dist.get(sent, 0) + 1
            icon = {"bonne": "🟢", "neutre": "🟡", "mauvaise": "🔴"}.get(sent, "⚪")
            print(f"✓ {icon} {sent}")
        else:
            skip += 1
            print("✗ skip")

        time.sleep(1.5)

    print(f"\n{'─'*60}")
    print(f"  Analysées   : {ok}")
    print(f"  Skip/erreur : {skip}")
    print(f"  Coût réel   : ${total_cost:.3f} USD")
    bonne = dist.get("bonne", 0)
    neutre = dist.get("neutre", 0)
    mauvaise = dist.get("mauvaise", 0)
    print(f"  Sentiments  : 🟢 bonne={bonne} · 🟡 neutre={neutre} · 🔴 mauvaise={mauvaise}")
    print(f"  Cache total : {len(_load_summaries())} résumés")
    print(f"  Sauvegardé → {SUMMARIES_PATH.name}")
    print(f"{'─'*60}")


if __name__ == "__main__":
    main()
