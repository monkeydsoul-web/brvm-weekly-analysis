#!/usr/bin/env python3
"""
brvm_reports_full_scraper.py — Scraper exhaustif des rapports BRVM.

Parcourt 5 sections avec pagination, extrait PDFs, construit reports_full.json.

Usage :
    python3 scripts/brvm_reports_full_scraper.py
    python3 scripts/brvm_reports_full_scraper.py --max-pages 5
    python3 scripts/brvm_reports_full_scraper.py --skip-download
"""

import requests, re, json, hashlib, time, os, sys, argparse
from pathlib import Path
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Chemins ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
PDF_DIR  = BASE_DIR / "data" / "reports_pdf"
OUT_FILE = BASE_DIR / "data" / "reports_full.json"
LOG_DIR  = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)

# ── Configuration ──────────────────────────────────────────────────────────────
BASE = "https://www.brvm.org"

SECTIONS = [
    ("rapports-societes-cotees",
     "/fr/rapports-societes-cotees?field_secteur_emeteur_tid=All&page="),
    ("rapports-annuels",
     "/fr/type-document/rapports-annuels?page="),
    ("rapports-semestriels",
     "/fr/type-document/rapports-semestriels?page="),
    ("rapports-trimestriels",
     "/fr/type-document/rapports-trimestriels?page="),
    ("rapport-brvm",
     "/fr/type-document/rapport-brvm?page="),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 BRVMAnalyzer/14.1",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Mapping abréviations pays → ticker suffix (pour fallback ticker detection)
COUNTRY_TICKERS = {
    "ci": "C", "sn": "S", "bf": "BF", "ml": "M", "ng": "N", "bj": "B",
    "tg": "T", "gn": "G",
}

# ── Utilitaires ────────────────────────────────────────────────────────────────

def fetch_html(url: str, retries: int = 3) -> Optional[str]:
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, verify=False, timeout=25)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return None  # pas de retry sur 404
            print(f"  HTTP {r.status_code}: {url[-60:]}")
        except Exception as e:
            print(f"  [retry {i+1}/{retries}] {url[-50:]}: {e}")
        time.sleep(2 * (i + 1))
    return None


def _guess_ticker_from_text(text: str) -> Optional[str]:
    """Cherche un ticker BRVM (3-5 lettres maj + C/BF/S/etc.) dans le texte."""
    # Pattern typique: SIBC, SNTS, BOABF, ONTBF, CBIBF
    m = re.search(r'\b([A-Z]{3,5})\b', text)
    return m.group(1) if m else None


def _guess_ticker_from_filename(filename: str) -> Optional[str]:
    """Extrait le ticker depuis un nom de fichier BRVM standardisé."""
    # Exemple: 20260506_-_rapport_-_sibc_ci.pdf → SIBC
    name = filename.lower().replace(".pdf", "").replace("_-_", " ").replace("_", " ")
    # Ignorer les segments communs
    ignore = {
        "rapport", "dactivites", "annuel", "semestriel", "trimestriel",
        "etats", "financiers", "brvm", "1er", "2eme", "3eme", "4eme",
        "trimestre", "semestre", "exercice", "resultats", "consolides",
        "rse", "annuels", "de", "du", "des", "la", "le",
    }
    parts = name.split()
    # Sauter la date (8 chiffres en début)
    if parts and re.match(r'^\d{8}', parts[0]):
        parts = parts[1:]
    # Le premier mot non-ignoré de 2-6 chars peut être un slug de société
    for p in parts:
        p = p.strip()
        if 2 <= len(p) <= 6 and p not in ignore and not p.isdigit():
            # Vérifier que ça ressemble à un ticker (pas un mot français)
            if re.match(r'^[a-z]{2,6}$', p):
                return p.upper()
    return None


# ── Parsers ────────────────────────────────────────────────────────────────────

def parse_list_page(html: str, section_label: str) -> list[dict]:
    """
    Parse une page de liste Drupal. Retourne des entrées avec url_detail.
    Gère : .views-row, table tr, .view-content a directs sur PDF.
    """
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    seen_urls: set[str] = set()

    # Stratégie 1 : liens directs vers PDF dans la vue
    for a in soup.select(".view-content a[href]"):
        href = a["href"]
        if not href:
            continue
        full = href if href.startswith("http") else BASE + href

        # Lien direct vers un PDF
        if href.lower().endswith(".pdf"):
            if full not in seen_urls:
                seen_urls.add(full)
                titre = a.get_text(strip=True)
                filename = href.split("/")[-1]
                entries.append({
                    "url_detail": None,
                    "pdf_url_direct": full,
                    "ticker_hint": _guess_ticker_from_filename(filename),
                    "titre_hint": titre or filename,
                    "date_hint": None,
                    "section": section_label,
                })
            continue

        # Lien vers une page node/détail
        if "/node/" in href or "/rapports-" in href or "/type-document/" in href:
            if full not in seen_urls:
                seen_urls.add(full)
                titre = a.get_text(strip=True)
                entries.append({
                    "url_detail": full,
                    "pdf_url_direct": None,
                    "ticker_hint": _guess_ticker_from_text(titre),
                    "titre_hint": titre,
                    "date_hint": None,
                    "section": section_label,
                })

    # Stratégie 2 : lignes .views-row (structure Drupal classique)
    if not entries:
        for row in soup.select(".views-row"):
            a = row.find("a", href=True)
            if not a:
                continue
            href = a["href"]
            full = href if href.startswith("http") else BASE + href
            if full in seen_urls:
                continue
            seen_urls.add(full)
            titre = a.get_text(strip=True)
            date_m = re.search(r"(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})",
                               row.get_text())
            entries.append({
                "url_detail": full if not href.lower().endswith(".pdf") else None,
                "pdf_url_direct": full if href.lower().endswith(".pdf") else None,
                "ticker_hint": _guess_ticker_from_text(titre),
                "titre_hint": titre,
                "date_hint": date_m.group(1) if date_m else None,
                "section": section_label,
            })

    return entries


def parse_detail_page(html: str, entry: dict) -> dict:
    """Parse une page détail (node Drupal) pour extraire PDF, ticker, titre, année."""
    soup = BeautifulSoup(html, "html.parser")

    # PDF link
    pdf_url = None
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if h.lower().endswith(".pdf") and "/sites/default/files/" in h:
            pdf_url = h if h.startswith("http") else BASE + h
            break

    # Titre
    h1 = soup.find("h1")
    titre = h1.get_text(strip=True) if h1 else entry.get("titre_hint", "")

    # Ticker — chercher dans un champ Drupal d'abord
    ticker = entry.get("ticker_hint")
    for sel in [
        "[class*='field-ticker']",
        "[class*='field--name-field-emetteur']",
        "[class*='field--name-field-societe']",
        "[class*='field-name-field-emetteur']",
    ]:
        tf = soup.select_one(sel)
        if tf:
            m = re.search(r"\b([A-Z]{3,5})\b", tf.get_text())
            if m:
                ticker = m.group(1)
                break
    if not ticker:
        # Fallback: chercher dans le titre ou l'URL du PDF
        for text in [titre, pdf_url or ""]:
            m = _guess_ticker_from_text(text)
            if m:
                ticker = m
                break

    # Année
    annee = None
    for text in [titre, soup.get_text()[:500]]:
        m = re.search(r"\b(20\d{2})\b", text)
        if m:
            annee = int(m.group(1))
            break

    # Date
    date_str = entry.get("date_hint")
    if not date_str:
        m = re.search(r"(\d{2}/\d{2}/\d{4})", soup.get_text())
        if m:
            d, mo, y = m.group(1).split("/")
            date_str = f"{y}-{mo}-{d}"

    # Type
    section = entry.get("section", "")
    if "annuel" in section:
        type_doc = "Rapport annuel"
    elif "semestriel" in section:
        type_doc = "Rapport semestriel"
    elif "trimestriel" in section:
        type_doc = "Rapport trimestriel"
    elif "brvm" in section:
        type_doc = "Rapport BRVM"
    else:
        type_doc = _detect_type_from_filename((pdf_url or "").split("/")[-1])

    return {
        "titre": titre,
        "ticker": ticker,
        "annee": annee,
        "date": date_str,
        "type": type_doc,
        "pdf_url": pdf_url,
        "detail_url": entry.get("url_detail"),
        "section": section,
    }


def _detect_type_from_filename(filename: str) -> str:
    fn = filename.lower()
    if "rapport_annuel" in fn or "rapport_dactivites_annuel" in fn:
        return "Rapport annuel"
    if "etats_financiers" in fn or "resultats_financiers" in fn:
        return "Etats financiers"
    if "1er_semestre" in fn or "semestre" in fn:
        return "Rapport semestriel"
    if "trimestre" in fn or "trimestr" in fn:
        return "Rapport trimestriel"
    if "rapport_brvm" in fn:
        return "Rapport BRVM"
    return "Document"


def _enrich_from_filename(entry: dict) -> dict:
    """Enrichit un entry PDF direct depuis le nom de fichier."""
    pdf_url = entry.get("pdf_url_direct", "")
    filename = pdf_url.split("/")[-1] if pdf_url else ""
    if not filename:
        return entry

    annee = None
    date_str = None
    if len(filename) >= 8 and filename[:8].isdigit():
        raw = filename[:8]
        try:
            annee = int(raw[:4])
            date_str = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        except Exception:
            pass

    ticker = entry.get("ticker_hint") or _guess_ticker_from_filename(filename)
    type_doc = _detect_type_from_filename(filename)
    titre = entry.get("titre_hint") or filename.replace("_", " ")[:80]

    return {
        "titre": titre,
        "ticker": ticker,
        "annee": annee,
        "date": date_str,
        "type": type_doc,
        "pdf_url": pdf_url,
        "detail_url": None,
        "section": entry.get("section", ""),
    }


# ── Téléchargement PDF ─────────────────────────────────────────────────────────

def download_pdf(pdf_url: str, ticker: Optional[str], annee: Optional[int],
                 section: str, skip: bool = False) -> Optional[str]:
    """Télécharge le PDF si pas déjà en cache (par hash d'URL)."""
    if not pdf_url:
        return None
    if skip:
        # Retourner le chemin potentiel sans télécharger
        md5 = hashlib.md5(pdf_url.encode()).hexdigest()[:10]
        fname = f"{annee or '????'}_{section}_{md5}.pdf"
        fpath = PDF_DIR / (ticker or "UNKNOWN") / fname
        return str(fpath) if fpath.exists() else None

    md5 = hashlib.md5(pdf_url.encode()).hexdigest()[:10]
    fname = f"{annee or '????'}_{section}_{md5}.pdf"
    folder = ticker or "UNKNOWN"
    fpath = PDF_DIR / folder / fname
    fpath.parent.mkdir(parents=True, exist_ok=True)

    if fpath.exists() and fpath.stat().st_size > 1024:
        return str(fpath)

    try:
        r = requests.get(pdf_url, headers=HEADERS, verify=False,
                         timeout=60, stream=True)
        if r.status_code != 200:
            print(f"    PDF HTTP {r.status_code}: {pdf_url[-50:]}")
            return None
        content = b""
        for chunk in r.iter_content(65536):
            content += chunk
            if len(content) > 30 * 1024 * 1024:
                print(f"    PDF trop grand (>30MB): {pdf_url[-40:]}")
                return None
        if content[:4] != b"%PDF":
            print(f"    Pas un PDF: {pdf_url[-40:]}")
            return None
        fpath.write_bytes(content)
        print(f"    ↓ {fpath.name} ({len(content)//1024}KB)")
        return str(fpath)
    except Exception as e:
        print(f"    PDF error: {e}")
        return None


# ── Scraping principal ─────────────────────────────────────────────────────────

def scrape_all(max_pages: int = 20, skip_download: bool = False) -> list[dict]:
    """Scrape toutes les sections, parse les détails, télécharge les PDFs."""
    all_entries: list[dict] = []

    for label, base_path in SECTIONS:
        print(f"\n{'═'*60}")
        print(f"  Section : {label}")
        print(f"{'═'*60}")
        section_entries = 0

        for page in range(max_pages):
            url = BASE + base_path + str(page)
            html = fetch_html(url)
            if not html:
                print(f"  page {page}: fetch failed → stop")
                break

            entries = parse_list_page(html, label)
            if not entries:
                print(f"  page {page}: vide → stop")
                break

            print(f"  page {page}: {len(entries)} entrées")
            all_entries.extend(entries)
            section_entries += len(entries)
            time.sleep(0.8)

        print(f"  → {section_entries} entrées au total pour '{label}'")

    # Dédupliquer par url_detail ou pdf_url_direct
    seen: set[str] = set()
    uniq: list[dict] = []
    for e in all_entries:
        key = e.get("url_detail") or e.get("pdf_url_direct") or ""
        if key and key not in seen:
            seen.add(key)
            uniq.append(e)

    print(f"\n{'─'*60}")
    print(f"  Total unique : {len(uniq)} entrées après déduplication")
    print(f"{'─'*60}\n")

    # Parser les détails
    reports: list[dict] = []
    for i, e in enumerate(uniq):
        if i > 0 and i % 20 == 0:
            print(f"  [{i}/{len(uniq)}] rapports traités…")

        if e.get("url_detail"):
            # Besoin de parser la page de détail
            html = fetch_html(e["url_detail"])
            if not html:
                continue
            data = parse_detail_page(html, e)
            time.sleep(0.5)
        else:
            # Lien PDF direct : enrichir depuis le filename
            data = _enrich_from_filename(e)

        # Télécharger le PDF
        if data.get("pdf_url") or data.get("pdf_url_direct"):
            pdf_u = data.get("pdf_url") or data.get("pdf_url_direct")
            data["pdf_path"] = download_pdf(
                pdf_u, data.get("ticker"), data.get("annee"),
                data.get("section", ""), skip=skip_download
            )
            if not data.get("pdf_url"):
                data["pdf_url"] = pdf_u

        if data.get("pdf_url"):
            reports.append(data)

    # Sauvegarder
    OUT_FILE.write_text(json.dumps(reports, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"\n{'═'*60}")
    print(f"  ✓ {len(reports)} rapports sauvegardés dans {OUT_FILE.name}")
    # Breakdown par section
    from collections import Counter
    by_section = Counter(r.get("section", "?") for r in reports)
    for sec, n in sorted(by_section.items()):
        print(f"    {sec:<30s} {n:>4} rapports")
    print(f"{'═'*60}")
    return reports


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper exhaustif rapports BRVM")
    parser.add_argument("--max-pages", type=int, default=20,
                        help="Nombre max de pages par section (défaut: 20)")
    parser.add_argument("--skip-download", action="store_true",
                        help="Ne pas télécharger les PDFs (index seulement)")
    args = parser.parse_args()

    import logging
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "reports_scraper.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    print(f"\nBRVM Reports Full Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Max pages/section : {args.max_pages} | Download PDFs : {not args.skip_download}\n")

    reports = scrape_all(
        max_pages=args.max_pages,
        skip_download=args.skip_download,
    )

    # Statistiques
    with_ticker  = sum(1 for r in reports if r.get("ticker"))
    with_annee   = sum(1 for r in reports if r.get("annee"))
    with_pdf_dl  = sum(1 for r in reports if r.get("pdf_path"))
    print(f"\n  Avec ticker : {with_ticker}/{len(reports)}")
    print(f"  Avec année  : {with_annee}/{len(reports)}")
    print(f"  PDF téléchargés : {with_pdf_dl}/{len(reports)}")
