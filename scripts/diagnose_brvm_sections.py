#!/usr/bin/env python3
"""
diagnose_brvm_sections.py — Teste les URLs BRVM pour trouver celles qui fonctionnent.
Usage : python3 scripts/diagnose_brvm_sections.py
"""
import requests, urllib3, re
from bs4 import BeautifulSoup
urllib3.disable_warnings()

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

URLS_TO_TEST = [
    # Sections type-document actuelles (testées → vides)
    "https://www.brvm.org/fr/type-document/rapports-annuels",
    "https://www.brvm.org/fr/type-document/rapports-semestriels",
    "https://www.brvm.org/fr/type-document/rapports-trimestriels",
    "https://www.brvm.org/fr/type-document/rapport-brvm",
    # Variantes sans tiret / autres slugs
    "https://www.brvm.org/fr/rapports-annuels",
    "https://www.brvm.org/fr/rapports-semestriels",
    "https://www.brvm.org/fr/publications-marche",
    "https://www.brvm.org/fr/documents-marche",
    "https://www.brvm.org/fr/publications/rapports",
    "https://www.brvm.org/fr/rapports",
    # Filtres sur la page principale (field_type_document_tid)
    "https://www.brvm.org/fr/rapports-societes-cotees?field_type_document_tid=1",
    "https://www.brvm.org/fr/rapports-societes-cotees?field_type_document_tid=2",
    "https://www.brvm.org/fr/rapports-societes-cotees?field_type_document_tid=3",
    "https://www.brvm.org/fr/rapports-societes-cotees?field_type_document_tid=4",
    "https://www.brvm.org/fr/rapports-societes-cotees?field_type_document_tid=5",
    "https://www.brvm.org/fr/rapports-societes-cotees?field_type_document_tid=6",
    # Filtres secteur
    "https://www.brvm.org/fr/rapports-societes-cotees?field_secteur_emeteur_tid=1&page=0",
    # Page principale sans filtre (déjà fonctionnelle)
    "https://www.brvm.org/fr/rapports-societes-cotees?field_secteur_emeteur_tid=All&page=0",
    # Paginée pour vérifier si plus de pages existent
    "https://www.brvm.org/fr/rapports-societes-cotees?field_secteur_emeteur_tid=All&page=3",
    "https://www.brvm.org/fr/rapports-societes-cotees?field_secteur_emeteur_tid=All&page=10",
    "https://www.brvm.org/fr/rapports-societes-cotees?field_secteur_emeteur_tid=All&page=20",
]

print(f"{'Status':6} | {'Size':7} | {'views':5} | {'pdf':3} | {'rows':4} | URL")
print("-"*90)

for url in URLS_TO_TEST:
    try:
        r = requests.get(url, headers=HEADERS, verify=False, timeout=15)
        html = r.text
        soup = BeautifulSoup(html, "html.parser")
        size = len(html)
        has_views = "views-row" in html
        has_pdf = ".pdf" in html.lower()
        rows = len(soup.select(".views-row"))
        print(f"{r.status_code:6} | {size:7d} | {str(has_views):5} | {str(has_pdf):3} | {rows:4} | {url}")
    except Exception as e:
        print(f"{'ERR':6} | {'?':>7} | {'?':5} | {'?':3} | {'?':4} | {url} — {e}")
