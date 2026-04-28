"""
BRVM News & Dividend Scraper — Phase 1
Sources: SikaFinance · RichBourse · Dabafinance · EcofinAgency · African-Markets · AllaAfrica
Récupère : news par ticker · dividendes confirmés · indices BRVM · contexte macro
"""

import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TIMEOUT = 15

# ── Mapping ticker → mots-clés de recherche ──────────────────────────────────
TICKER_KEYWORDS = {
    "SGBC": ["SGBCI", "Société Générale CI", "SGB"],
    "SIBC": ["SIB", "Société Ivoirienne de Banque"],
    "SNTS": ["Sonatel", "Orange Sénégal", "SNTS"],
    "NSBC": ["NSIA Banque", "NSBC"],
    "CBIBF": ["Coris Bank", "CBIBF"],
    "BOAB":  ["BOA Bénin", "Bank of Africa Benin"],
    "BOABF": ["BOA Burkina", "Bank of Africa Burkina"],
    "BOAC":  ["BOA CI", "Bank of Africa Côte d'Ivoire"],
    "BOAM":  ["BOA Mali", "Bank of Africa Mali"],
    "BOAN":  ["BOA Niger", "Bank of Africa Niger"],
    "BOAS":  ["BOA Sénégal", "Bank of Africa Sénégal"],
    "ECOC":  ["Ecobank CI", "Ecobank Côte d'Ivoire"],
    "BICC":  ["BICI", "Banque Internationale"],
    "ETIT":  ["ETI", "Ecobank Transnational"],
    "ORAC":  ["Orange CI", "Orange Côte d'Ivoire"],
    "ONTBF": ["Onatel", "ONTBF"],
    "STBC":  ["SITAB", "Société Ivoirienne des Tabacs"],
    "SLBC":  ["SOLIBRA"],
    "NTLC":  ["Nestlé CI", "Nestlé Côte d'Ivoire"],
    "SMBC":  ["SMB CI", "SMB Côte d'Ivoire"],
    "PALC":  ["Palm CI", "PALMCI"],
    "SPHC":  ["SAPH"],
    "TTLC":  ["TotalEnergies CI", "Total CI"],
    "TTLS":  ["TotalEnergies Sénégal", "Total Sénégal"],
    "FTSC":  ["Filtisac"],
    "LNBB":  ["Loterie Nationale Bénin", "LNBB"],
    "UNLC":  ["Unilever CI"],
    "CIEC":  ["CIE CI", "Compagnie Ivoirienne d'Électricité"],
    "STAC":  ["Setao"],
    "ABJC":  ["Servair Abidjan"],
}


# ── SIKAFINANCE ───────────────────────────────────────────────────────────────
def fetch_sikafinance_news(max_articles: int = 30) -> list[dict]:
    """Scrape les actualités BRVM depuis SikaFinance"""
    url = "https://www.sikafinance.com/marches/actualites_bourse_brvm"
    articles = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "html.parser")

        # Chercher les liens d'articles
        for link in soup.find_all("a", href=True)[:max_articles * 3]:
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if len(text) < 20:
                continue
            if "sikafinance.com" in href or href.startswith("/"):
                full_url = href if href.startswith("http") else f"https://www.sikafinance.com{href}"
                articles.append({
                    "source": "SikaFinance",
                    "title": text[:200],
                    "url": full_url,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "summary": "",
                })
                if len(articles) >= max_articles:
                    break

        logger.info(f"SikaFinance: {len(articles)} articles récupérés")
    except Exception as e:
        logger.warning(f"SikaFinance news: {e}")
    return articles


def fetch_sikafinance_dividends() -> list[dict]:
    """Scrape les dividendes BRVM depuis SikaFinance"""
    url = "https://www.sikafinance.com/marches/dividendes"
    divs = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "html.parser")
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) >= 3:
                    ticker = cells[0].get_text(strip=True)
                    div_str = cells[1].get_text(strip=True).replace(" ", "").replace("\xa0", "")
                    yield_str = cells[2].get_text(strip=True).replace("%", "").replace(",", ".")
                    try:
                        div_val = float(re.sub(r"[^\d.]", "", div_str))
                        yield_val = float(yield_str) if yield_str else None
                        if ticker and div_val > 0:
                            divs.append({
                                "ticker": ticker,
                                "dividend": div_val,
                                "yield_pct": yield_val,
                                "source": "SikaFinance",
                                "confirmed": True,
                            })
                    except (ValueError, TypeError):
                        continue
        logger.info(f"SikaFinance dividendes: {len(divs)} entrées")
    except Exception as e:
        logger.warning(f"SikaFinance dividendes: {e}")
    return divs


def fetch_sikafinance_indices() -> dict:
    """Récupère les indices BRVM Composite et BRVM-30"""
    url = "https://www.sikafinance.com/bourse/"
    indices = {}
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text()

        # Chercher BRVM Composite et BRVM 30
        for pattern, key in [
            (r"BRVM\s*Composite[^\d]*([\d\s,.]+)", "BRVM_COMPOSITE"),
            (r"BRVM[-\s]*30[^\d]*([\d\s,.]+)", "BRVM_30"),
        ]:
            m = re.search(pattern, text)
            if m:
                val_str = m.group(1).replace(" ", "").replace(",", ".")
                try:
                    indices[key] = float(re.findall(r"[\d.]+", val_str)[0])
                except Exception:
                    pass

        logger.info(f"Indices BRVM: {indices}")
    except Exception as e:
        logger.warning(f"Indices BRVM: {e}")
    return indices


# ── RICHBOURSE ────────────────────────────────────────────────────────────────
def fetch_richbourse_dividends() -> list[dict]:
    """Scrape les dividendes officiels depuis RichBourse"""
    url = "https://www.richbourse.com/common/dividende/index"
    divs = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table")
        if table:
            rows = table.find_all("tr")
            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) >= 3:
                    name_cell = cells[1].get_text(strip=True)
                    div_str = cells[2].get_text(strip=True).replace(" ", "").replace(",", ".")
                    yield_str = cells[3].get_text(strip=True).replace("%", "").replace(",", ".") if len(cells) > 3 else ""
                    ex_date = cells[4].get_text(strip=True) if len(cells) > 4 else ""

                    # Extraire le ticker depuis le nom
                    ticker_match = re.search(r"\(([A-Z]{3,6})\)", name_cell)
                    ticker = ticker_match.group(1) if ticker_match else ""

                    try:
                        div_val = float(re.sub(r"[^\d.]", "", div_str))
                        if div_val > 0:
                            divs.append({
                                "ticker": ticker,
                                "name": name_cell,
                                "dividend": div_val,
                                "yield_pct": float(yield_str) if yield_str else None,
                                "ex_date": ex_date,
                                "source": "RichBourse",
                                "confirmed": True,
                            })
                    except (ValueError, TypeError):
                        continue

        logger.info(f"RichBourse dividendes: {len(divs)} entrées")
    except Exception as e:
        logger.warning(f"RichBourse dividendes: {e}")
    return divs


def fetch_richbourse_news(max_articles: int = 20) -> list[dict]:
    """Scrape les publications officielles BRVM depuis RichBourse"""
    url = "https://www.richbourse.com/common/actualite/index"
    articles = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if len(text) < 15:
                continue
            if "actualite" in href or "dividende" in href or "rapport" in href:
                full_url = href if href.startswith("http") else f"https://www.richbourse.com{href}"
                articles.append({
                    "source": "RichBourse",
                    "title": text[:200],
                    "url": full_url,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "summary": "",
                })
                if len(articles) >= max_articles:
                    break
        logger.info(f"RichBourse: {len(articles)} articles")
    except Exception as e:
        logger.warning(f"RichBourse news: {e}")
    return articles


# ── DABAFINANCE ───────────────────────────────────────────────────────────────
def fetch_dabafinance_news(max_articles: int = 20) -> list[dict]:
    """Scrape les news depuis Dabafinance"""
    urls = [
        "https://dabafinance.com/en/news",
        "https://dabafinance.com/fr/nouvelles",
    ]
    articles = []
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            soup = BeautifulSoup(r.text, "html.parser")
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True)
                if len(text) < 20:
                    continue
                if "news" in href or "nouvelles" in href or "insight" in href:
                    full_url = href if href.startswith("http") else f"https://dabafinance.com{href}"
                    articles.append({
                        "source": "Dabafinance",
                        "title": text[:200],
                        "url": full_url,
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "summary": "",
                    })
                    if len(articles) >= max_articles:
                        break
            if articles:
                break
        except Exception as e:
            logger.warning(f"Dabafinance: {e}")
        time.sleep(0.5)
    logger.info(f"Dabafinance: {len(articles)} articles")
    return articles


# ── ECOFINAGENCY ──────────────────────────────────────────────────────────────
def fetch_ecofin_news(max_articles: int = 20) -> list[dict]:
    """Scrape les news depuis EcofinAgency"""
    url = "https://www.ecofinagency.com/news-finances"
    articles = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if len(text) < 20:
                continue
            if "ecofinagency" in href or href.startswith("/"):
                full_url = href if href.startswith("http") else f"https://www.ecofinagency.com{href}"
                articles.append({
                    "source": "EcofinAgency",
                    "title": text[:200],
                    "url": full_url,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "summary": "",
                })
                if len(articles) >= max_articles:
                    break
        logger.info(f"EcofinAgency: {len(articles)} articles")
    except Exception as e:
        logger.warning(f"EcofinAgency: {e}")
    return articles


# ── AFRICAN-MARKETS ───────────────────────────────────────────────────────────
def fetch_african_markets_profile(ticker: str) -> dict:
    """Récupère le profil d'une société depuis African-Markets"""
    url = f"https://www.african-markets.com/en/stock-markets/brvm/listed-companies/company?code={ticker}"
    data = {}
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text()

        # Extraire quelques métriques
        for pattern, key in [
            (r"P/E\s*[:\-]?\s*([\d.]+)", "pe"),
            (r"P/B\s*[:\-]?\s*([\d.]+)", "pb"),
            (r"Dividend.*?([\d.]+)%", "div_yield"),
            (r"ROE\s*[:\-]?\s*([\d.]+)%", "roe"),
        ]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                try:
                    data[key] = float(m.group(1))
                except ValueError:
                    pass

        data["ticker"] = ticker
        data["source"] = "African-Markets"
    except Exception as e:
        logger.debug(f"African-Markets {ticker}: {e}")
    return data


# ── AGRÉGATEUR PRINCIPAL ──────────────────────────────────────────────────────
def match_news_to_tickers(articles: list[dict]) -> list[dict]:
    """Associe chaque article à une ou plusieurs actions BRVM"""
    enriched = []
    for article in articles:
        title_lower = article["title"].lower()
        tickers_found = []
        for ticker, keywords in TICKER_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in title_lower:
                    tickers_found.append(ticker)
                    break
        article["tickers"] = list(set(tickers_found))
        article["is_dividend_news"] = any(
            w in title_lower for w in ["dividend", "dividende", "rendement", "détachement"]
        )
        article["is_results_news"] = any(
            w in title_lower for w in ["résultat", "bénéfice", "profit", "chiffre d'affaires",
                                       "résultats", "performance", "trimestre", "semestre"]
        )
        article["is_macro_news"] = not tickers_found and any(
            w in title_lower for w in ["brvm", "côte d'ivoire", "sénégal", "uemoa", "bceao",
                                       "afrique de l'ouest", "waemu", "fcfa"]
        )
        enriched.append(article)
    return enriched


def fetch_confirmed_dividends() -> dict:
    """
    Agrège les dividendes confirmés de toutes les sources.
    Retourne un dict: ticker -> {dividend, yield_pct, ex_date, source}
    """
    all_divs = {}

    # RichBourse (priorité haute — données officielles BRVM)
    for d in fetch_richbourse_dividends():
        if d.get("ticker") and d.get("dividend", 0) > 0:
            all_divs[d["ticker"]] = d

    time.sleep(0.5)

    # SikaFinance (complément)
    for d in fetch_sikafinance_dividends():
        ticker = d.get("ticker", "")
        if ticker and ticker not in all_divs and d.get("dividend", 0) > 0:
            all_divs[ticker] = d

    logger.info(f"Dividendes confirmés agrégés: {len(all_divs)} actions")
    return all_divs


def fetch_all_news() -> list[dict]:
    """Agrège toutes les news de toutes les sources"""
    all_articles = []

    sources = [
        ("SikaFinance", fetch_sikafinance_news),
        ("RichBourse", fetch_richbourse_news),
        ("Dabafinance", fetch_dabafinance_news),
        ("EcofinAgency", fetch_ecofin_news),
    ]

    for name, fn in sources:
        try:
            articles = fn()
            all_articles.extend(articles)
            logger.info(f"  ✓ {name}: {len(articles)} articles")
        except Exception as e:
            logger.warning(f"  ✗ {name}: {e}")
        time.sleep(0.5)

    # Déduplications par titre
    seen_titles = set()
    unique_articles = []
    for a in all_articles:
        title_key = a["title"][:60].lower()
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_articles.append(a)

    # Association aux tickers
    enriched = match_news_to_tickers(unique_articles)
    logger.info(f"Total news agrégées: {len(enriched)} articles uniques")
    return enriched


def fetch_macro_context() -> dict:
    """Récupère le contexte macro de la semaine"""
    macro = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "week": datetime.now().strftime("Semaine %W/%Y"),
    }

    # Indices BRVM
    indices = fetch_sikafinance_indices()
    macro.update(indices)

    # Taux de change FCFA (proxy via ECB — FCFA est arrimé à l'EUR)
    try:
        r = requests.get(
            "https://api.exchangerate-api.com/v4/latest/EUR",
            timeout=10, headers=HEADERS
        )
        data = r.json()
        rates = data.get("rates", {})
        eur_usd = rates.get("USD", 1.08)
        macro["FCFA_per_EUR"] = 655.957  # taux fixe CFA
        macro["FCFA_per_USD"] = round(655.957 / eur_usd, 2)
        macro["EUR_USD"] = round(eur_usd, 4)
    except Exception as e:
        logger.debug(f"Taux de change: {e}")
        macro["FCFA_per_USD"] = 610.0
        macro["EUR_USD"] = 1.076

    logger.info(f"Contexte macro: {macro}")
    return macro


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print("\n=== TEST NEWS SCRAPER ===")
    news = fetch_all_news()
    print(f"\n{len(news)} articles récupérés")
    ticker_news = [a for a in news if a["tickers"]]
    print(f"{len(ticker_news)} articles liés à des tickers spécifiques")
    for a in ticker_news[:5]:
        print(f"  {a['tickers']} — {a['title'][:70]}")

    print("\n=== TEST DIVIDENDES ===")
    divs = fetch_confirmed_dividends()
    for t, d in list(divs.items())[:5]:
        print(f"  {t}: {d['dividend']} XOF ({d.get('yield_pct','?')}%) — {d['source']}")

    print("\n=== TEST MACRO ===")
    macro = fetch_macro_context()
    print(macro)
