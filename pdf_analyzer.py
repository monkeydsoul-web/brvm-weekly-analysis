"""
pdf_analyzer.py — Analyse IA des rapports financiers BRVM
Télécharge le PDF depuis brvm.org, extrait le texte, envoie à Claude.
Cache JSON 30 jours par rapport (url hash).
"""

import os
import json
import hashlib
import logging
import tempfile
import time
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR   = os.path.join(BASE_DIR, "data", "pdf_analyses")
CACHE_TTL   = 60 * 60 * 24 * 30  # 30 jours

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

PROMPT_ANALYSE = """Tu es un analyste financier expert des marchés boursiers africains (BRVM/UEMOA).
Analyse ce rapport financier et extrait les informations suivantes de façon structurée en JSON.

IMPORTANT : Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ou après.

Format attendu :
{
  "annee": 2024,
  "type_rapport": "Etats financiers annuels",
  "kpis": {
    "chiffre_affaires": {"valeur": 123456, "unite": "MFCFA", "variation": "+5.2%"},
    "resultat_net": {"valeur": 45678, "unite": "MFCFA", "variation": "+3.1%"},
    "resultat_exploitation": {"valeur": 67890, "unite": "MFCFA", "variation": null},
    "total_bilan": {"valeur": null, "unite": "MFCFA", "variation": null},
    "capitaux_propres": {"valeur": null, "unite": "MFCFA", "variation": null},
    "dividende_par_action": {"valeur": null, "unite": "FCFA", "variation": null},
    "roe": {"valeur": null, "unite": "%", "variation": null},
    "marge_nette": {"valeur": null, "unite": "%", "variation": null},
    "dette_nette": {"valeur": null, "unite": "MFCFA", "variation": null},
    "ebitda": {"valeur": null, "unite": "MFCFA", "variation": null}
  },
  "points_cles": [
    "Point clé 1 en une phrase",
    "Point clé 2 en une phrase",
    "Point clé 3 en une phrase"
  ],
  "risques": [
    "Risque 1",
    "Risque 2"
  ],
  "perspectives": "Résumé des perspectives en 2-3 phrases max.",
  "verdict_investisseur": "POSITIF | NEUTRE | NEGATIF",
  "resume": "Résumé exécutif en 3 phrases max pour un investisseur."
}

REGLES CRITIQUES SUR LES UNITES:
- chiffre_affaires, resultat_net, ebitda, capitaux_propres, dette_nette: TOUJOURS en MILLIONS de FCFA (MFCFA)
- dividende_par_action: FCFA PAR ACTION (montant unitaire, ex: 1740), JAMAIS le dividende total
- roe, marge_nette: en POURCENTAGE (ex: 29.6 pour 29.6%)
- Si le rapport donne des chiffres en milliards, convertis en millions (×1000)
- Si le rapport donne des chiffres en milliers, convertis en millions (÷1000)
- Vérifie la cohérence: dividende_par_action doit être << chiffre_affaires

Si une donnée est absente du rapport, mets null.
Les valeurs numériques doivent être des nombres (pas des chaînes).
Les montants en millions de FCFA (MFCFA) sauf indication contraire.
"""


def _cache_path(url):
    h = hashlib.md5(url.encode()).hexdigest()[:12]
    return os.path.join(CACHE_DIR, f"{h}.json")


def _load_cache(url):
    path = _cache_path(url)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        age = time.time() - data.get("cached_at", 0)
        if age < CACHE_TTL:
            return data
    except Exception:
        pass
    return None


def _save_cache(url, data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(url)
    data["cached_at"] = time.time()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _download_pdf(url, max_mb=15):
    """Télécharge le PDF dans un fichier temporaire. Retourne le path."""
    r = requests.get(url, headers=HEADERS, timeout=30, stream=True)
    r.raise_for_status()

    size = 0
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    for chunk in r.iter_content(chunk_size=65536):
        size += len(chunk)
        if size > max_mb * 1024 * 1024:
            tmp.close()
            os.unlink(tmp.name)
            raise ValueError(f"PDF trop volumineux (>{max_mb}MB)")
        tmp.write(chunk)
    tmp.close()
    logger.info(f"PDF téléchargé: {size/1024:.0f}KB → {tmp.name}")
    return tmp.name


def _extract_text_from_pdf(pdf_path, max_pages=30, max_chars=40000):
    """
    Extrait le texte du PDF avec pypdf.
    Limite à max_pages pages et max_chars caractères pour éviter de dépasser le contexte.
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        total = len(reader.pages)
        pages_to_read = min(total, max_pages)

        # Stratégie : lire les 5 premières pages (intro/résumé) + pages financières
        # Les états financiers sont souvent dans la 2ème moitié du rapport
        priority_pages = list(range(min(5, pages_to_read)))
        remaining = list(range(5, pages_to_read))
        pages_order = priority_pages + remaining

        text_parts = []
        total_chars = 0

        for i in pages_order:
            if total_chars >= max_chars:
                break
            try:
                page_text = reader.pages[i].extract_text() or ""
                if page_text.strip():
                    text_parts.append(f"[Page {i+1}]\n{page_text}")
                    total_chars += len(page_text)
            except Exception:
                continue

        text = "\n\n".join(text_parts)
        logger.info(f"Texte extrait: {total_chars} chars, {pages_to_read}/{total} pages")
        return text[:max_chars], total

    except ImportError:
        raise ImportError("pypdf non installé: pip install pypdf --break-system-packages")


def _call_claude_api(text, ticker, doc_type, year, api_key):
    """Envoie le texte à Claude Sonnet et retourne l'analyse JSON."""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    user_msg = f"""Ticker BRVM: {ticker}
Type de document: {doc_type}
Année: {year or 'inconnue'}

--- CONTENU DU RAPPORT ---
{text}
--- FIN DU RAPPORT ---

Analyse ce rapport et réponds uniquement en JSON selon le format demandé."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=PROMPT_ANALYSE,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = response.content[0].text.strip()

    # Nettoyer si Claude a mis des backticks
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)


def analyze_report(url, ticker, doc_type="Document", year=None, force=False):
    """
    Point d'entrée principal.
    Télécharge, extrait, analyse le PDF et retourne le résultat JSON.
    Utilise le cache si disponible.
    """
    # Vérifier le cache
    if not force:
        cached = _load_cache(url)
        if cached:
            logger.info(f"Cache hit: {url[-50:]}")
            return cached

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY non défini")

    pdf_path = None
    try:
        # 1. Télécharger le PDF
        logger.info(f"Download: {url[-60:]}")
        pdf_path = _download_pdf(url)

        # 2. Extraire le texte
        text, n_pages = _extract_text_from_pdf(pdf_path)
        if not text.strip():
            raise ValueError("PDF sans texte extractible (probablement scanné)")

        # 3. Analyser avec Claude
        logger.info(f"Claude analyse: {ticker} {doc_type} {year}")
        result = _call_claude_api(text, ticker, doc_type, year, api_key)

        # 4. Enrichir avec métadonnées
        result.update({
            "ticker":     ticker,
            "doc_type":   doc_type,
            "year":       year,
            "url":        url,
            "n_pages":    n_pages,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "status":     "ok",
        })

        # 5. Sauvegarder en cache
        _save_cache(url, result)
        logger.info(f"Analyse terminée: {ticker} {year} — verdict: {result.get('verdict_investisseur')}")
        return result

    except Exception as e:
        logger.error(f"Erreur analyse {ticker}: {e}")
        error_result = {
            "ticker":   ticker,
            "doc_type": doc_type,
            "year":     year,
            "url":      url,
            "status":   "error",
            "error":    str(e),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }
        return error_result

    finally:
        if pdf_path and os.path.exists(pdf_path):
            os.unlink(pdf_path)


def get_analyses_for_ticker(ticker, reports_list, max_reports=3, force=False):
    """
    Analyse les N rapports les plus récents d'un ticker.
    Priorité : états financiers annuels > rapports annuels > autres.
    """
    # Trier par priorité et année
    priority = {"Etats financiers": 0, "Rapport annuel": 1}
    sorted_reports = sorted(
        reports_list,
        key=lambda r: (priority.get(r.get("type", ""), 2), -(r.get("year") or 0))
    )

    results = []
    for report in sorted_reports[:max_reports]:
        result = analyze_report(
            url=report["url"],
            ticker=ticker,
            doc_type=report.get("type", "Document"),
            year=report.get("year"),
            force=force,
        )
        results.append(result)
        time.sleep(0.5)  # Respecter brvm.org

    return results


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Test rapide sur SNTS états financiers 2024
    test_url = "https://www.brvm.org/sites/default/files/20250221_-_etats_financiers_-_exercice_2024_-_sonatel_sn.pdf"
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "SNTS"

    print(f"\nAnalyse IA: {ticker}")
    result = analyze_report(test_url, ticker, "Etats financiers", 2024, force=True)

    if result.get("status") == "ok":
        print(f"\nVERDICT: {result.get('verdict_investisseur')}")
        print(f"RESUME: {result.get('resume')}")
        print(f"\nKPIS:")
        for k, v in (result.get("kpis") or {}).items():
            if v and v.get("valeur") is not None:
                print(f"  {k:30s}: {v['valeur']} {v.get('unite','')}  {v.get('variation','')}")
        print(f"\nPOINTS CLES:")
        for p in (result.get("points_cles") or []):
            print(f"  • {p}")
    else:
        print(f"ERREUR: {result.get('error')}")
