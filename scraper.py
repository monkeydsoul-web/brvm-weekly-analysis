"""
BRVM Scraper — récupère tous les cours et données des actions cotées
Sources: brvm.org (cours officiels) + afx.kwayisi.org (données complémentaires)
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import os
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

# Données de référence statiques (enrichies manuellement)
# Mises à jour lors de chaque publication de résultats annuels
STOCK_FUNDAMENTALS = {
    "SGBC":  {"name": "Société Générale CI",          "sector": "Banque",        "country": "Côte d'Ivoire", "shares": 31_111_110,  "pe_hist": 8.5,  "pb_hist": 1.96, "roe": 24, "div_hist": 1863, "debt": "Faible",   "stable": True},
    "SIBC":  {"name": "Société Ivoirienne de Banque", "sector": "Banque",        "country": "Côte d'Ivoire", "shares": 10_000_000,  "pe_hist": 10.7, "pb_hist": 2.2,  "roe": 31, "div_hist": 338,  "debt": "Faible",   "stable": True},
    "SNTS":  {"name": "Sonatel Senegal",               "sector": "Télécoms",     "country": "Sénégal",       "shares": 100_000_000, "pe_hist": 8.33, "pb_hist": 3.5,  "roe": 34, "div_hist": 1933, "debt": "Faible",   "stable": True},
    "NSBC":  {"name": "NSIA Banque CI",                "sector": "Banque",        "country": "Côte d'Ivoire", "shares": 20_000_000,  "pe_hist": 7.05, "pb_hist": 1.0,  "roe": 15, "div_hist": 759,  "debt": "Faible",   "stable": True},
    "CBIBF": {"name": "Coris Bank International",     "sector": "Banque",        "country": "Burkina Faso",  "shares": 19_232_000,  "pe_hist": 5.0,  "pb_hist": 1.2,  "roe": 18, "div_hist": 900,  "debt": "Faible",   "stable": True},
    "BOAB":  {"name": "BOA Benin",                     "sector": "Banque",        "country": "Bénin",         "shares": 40_600_000,  "pe_hist": 8.0,  "pb_hist": 1.5,  "roe": 14, "div_hist": 468,  "debt": "Faible",   "stable": True},
    "BOABF": {"name": "BOA Burkina Faso",              "sector": "Banque",        "country": "Burkina Faso",  "shares": 23_856_000,  "pe_hist": 10.2, "pb_hist": 1.52, "roe": 13, "div_hist": 428,  "debt": "Faible",   "stable": True},
    "BOAC":  {"name": "BOA Côte d'Ivoire",             "sector": "Banque",        "country": "Côte d'Ivoire", "shares": 27_500_000,  "pe_hist": 9.5,  "pb_hist": 2.2,  "roe": 14, "div_hist": 375,  "debt": "Faible",   "stable": True},
    "BOAM":  {"name": "BOA Mali",                      "sector": "Banque",        "country": "Mali",          "shares": 12_000_000,  "pe_hist": 8.0,  "pb_hist": 1.4,  "roe": 13, "div_hist": 280,  "debt": "Faible",   "stable": True},
    "BOAN":  {"name": "BOA Niger",                     "sector": "Banque",        "country": "Niger",         "shares": 10_000_000,  "pe_hist": 8.5,  "pb_hist": 1.3,  "roe": 12, "div_hist": 350,  "debt": "Faible",   "stable": True},
    "BOAS":  {"name": "BOA Sénégal",                   "sector": "Banque",        "country": "Sénégal",       "shares": 15_000_000,  "pe_hist": 9.0,  "pb_hist": 1.7,  "roe": 13, "div_hist": 300,  "debt": "Faible",   "stable": True},
    "ECOC":  {"name": "Ecobank CI",                    "sector": "Banque",        "country": "Côte d'Ivoire", "shares": 64_788_600,  "pe_hist": 10.5, "pb_hist": 3.0,  "roe": 20, "div_hist": 800,  "debt": "Faible",   "stable": True},
    "BICC":  {"name": "BICI CI",                       "sector": "Banque",        "country": "Côte d'Ivoire", "shares": 9_000_000,   "pe_hist": 10.5, "pb_hist": 2.6,  "roe": 16, "div_hist": 900,  "debt": "Faible",   "stable": True},
    "ETIT":  {"name": "Ecobank Transnational",         "sector": "Banque",        "country": "Togo",          "shares": 28_000_000_000, "pe_hist": 30.0, "pb_hist": 0.5, "roe": 4, "div_hist": 0,   "debt": "Élevée",   "stable": False},
    "ORGT":  {"name": "Oragroup Togo",                 "sector": "Banque",        "country": "Togo",          "shares": 39_200_000,  "pe_hist": 15.0, "pb_hist": 1.4,  "roe": 9,  "div_hist": 0,    "debt": "Modérée",  "stable": False},
    "SAFC":  {"name": "SAFCA CI",                      "sector": "Banque",        "country": "Côte d'Ivoire", "shares": 5_000_000,   "pe_hist": 20.0, "pb_hist": 1.8,  "roe": 10, "div_hist": 200,  "debt": "Faible",   "stable": False},
    "ORAC":  {"name": "Orange CI",                     "sector": "Télécoms",     "country": "Côte d'Ivoire", "shares": 141_174_476, "pe_hist": 15.0, "pb_hist": 4.5,  "roe": 25, "div_hist": 700,  "debt": "Modérée",  "stable": True},
    "ONTBF": {"name": "Onatel Burkina Faso",           "sector": "Télécoms",     "country": "Burkina Faso",  "shares": 157_500_000, "pe_hist": 12.0, "pb_hist": 2.0,  "roe": 15, "div_hist": 155,  "debt": "Faible",   "stable": True},
    "NTLC":  {"name": "Nestlé CI",                     "sector": "Consommation", "country": "Côte d'Ivoire", "shares": 36_364_848,  "pe_hist": 18.0, "pb_hist": 5.0,  "roe": 28, "div_hist": 410,  "debt": "Faible",   "stable": True},
    "STBC":  {"name": "SITAB CI",                      "sector": "Consommation", "country": "Côte d'Ivoire", "shares": 18_000_000,  "pe_hist": 14.0, "pb_hist": 2.8,  "roe": 16, "div_hist": 2096, "debt": "Faible",   "stable": True},
    "UNLC":  {"name": "Unilever CI",                   "sector": "Consommation", "country": "Côte d'Ivoire", "shares": 6_884_660,   "pe_hist": 22.0, "pb_hist": 8.0,  "roe": 22, "div_hist": 900,  "debt": "Faible",   "stable": True},
    "SLBC":  {"name": "SOLIBRA CI",                    "sector": "Consommation", "country": "Côte d'Ivoire", "shares": 11_852_972,  "pe_hist": 11.7, "pb_hist": 1.3,  "roe": 13, "div_hist": 1500, "debt": "Faible",   "stable": False},
    "SMBC":  {"name": "SMB CI",                        "sector": "Industriel",   "country": "Côte d'Ivoire", "shares": 4_900_000,   "pe_hist": 8.79, "pb_hist": 1.1,  "roe": 14, "div_hist": 1200, "debt": "Faible",   "stable": True},
    "UNXC":  {"name": "Uniwax CI",                     "sector": "Consommation", "country": "Côte d'Ivoire", "shares": 12_816_480,  "pe_hist": 22.0, "pb_hist": 2.0,  "roe": 10, "div_hist": 200,  "debt": "Modérée",  "stable": False},
    "LNBB":  {"name": "Loterie Nationale Bénin",       "sector": "Consommation", "country": "Bénin",         "shares": 45_000_000,  "pe_hist": 9.0,  "pb_hist": 2.0,  "roe": 16, "div_hist": 120,  "debt": "Faible",   "stable": True},
    "NEIC":  {"name": "NEI-CEDA CI",                   "sector": "Consommation", "country": "Côte d'Ivoire", "shares": 18_974_000,  "pe_hist": 18.0, "pb_hist": 1.5,  "roe": 8,  "div_hist": 50,   "debt": "Faible",   "stable": False},
    "PALC":  {"name": "Palm CI",                       "sector": "Agriculture",  "country": "Côte d'Ivoire", "shares": 11_021_655,  "pe_hist": 14.0, "pb_hist": 2.0,  "roe": 8,  "div_hist": 300,  "debt": "Modérée",  "stable": False},
    "SPHC":  {"name": "SAPH CI",                       "sector": "Agriculture",  "country": "Côte d'Ivoire", "shares": 23_745_000,  "pe_hist": 16.6, "pb_hist": 2.0,  "roe": 6,  "div_hist": 250,  "debt": "Élevée",   "stable": False},
    "SOGC":  {"name": "SOGB CI",                       "sector": "Agriculture",  "country": "Côte d'Ivoire", "shares": 15_000_000,  "pe_hist": 15.0, "pb_hist": 1.8,  "roe": 8,  "div_hist": 300,  "debt": "Modérée",  "stable": False},
    "SCRC":  {"name": "Sucrivoire CI",                 "sector": "Agriculture",  "country": "Côte d'Ivoire", "shares": 27_591_750,  "pe_hist": 18.0, "pb_hist": 1.5,  "roe": 7,  "div_hist": 50,   "debt": "Élevée",   "stable": False},
    "TTLC":  {"name": "TotalEnergies CI",              "sector": "Énergie",      "country": "Côte d'Ivoire", "shares": 75_676_670,  "pe_hist": 11.0, "pb_hist": 3.5,  "roe": 14, "div_hist": 100,  "debt": "Faible",   "stable": True},
    "TTLS":  {"name": "TotalEnergies Sénégal",         "sector": "Énergie",      "country": "Sénégal",       "shares": 38_750_000,  "pe_hist": 12.0, "pb_hist": 2.5,  "roe": 14, "div_hist": 80,   "debt": "Faible",   "stable": True},
    "SHEC":  {"name": "Vivo Energy CI",                "sector": "Énergie",      "country": "Côte d'Ivoire", "shares": 120_000_000, "pe_hist": 13.0, "pb_hist": 3.0,  "roe": 12, "div_hist": 70,   "debt": "Faible",   "stable": True},
    "SEMC":  {"name": "Crown Siem CI",                 "sector": "Énergie",      "country": "Côte d'Ivoire", "shares": 10_000_000,  "pe_hist": 20.0, "pb_hist": 2.0,  "roe": 6,  "div_hist": 20,   "debt": "Élevée",   "stable": False},
    "CIEC":  {"name": "CIE CI",                        "sector": "Utilités",     "country": "Côte d'Ivoire", "shares": 65_536_000,  "pe_hist": 14.0, "pb_hist": 2.5,  "roe": 12, "div_hist": 120,  "debt": "Modérée",  "stable": True},
    "SDCC":  {"name": "SODECI CI",                     "sector": "Utilités",     "country": "Côte d'Ivoire", "shares": 12_000_000,  "pe_hist": 14.0, "pb_hist": 2.0,  "roe": 10, "div_hist": 250,  "debt": "Élevée",   "stable": True},
    "FTSC":  {"name": "Filtisac CI",                   "sector": "Industriel",   "country": "Côte d'Ivoire", "shares": 45_294_490,  "pe_hist": 5.5,  "pb_hist": 1.2,  "roe": 12, "div_hist": 150,  "debt": "Faible",   "stable": False},
    "SDSC":  {"name": "Africa Global Logistics CI",    "sector": "Industriel",   "country": "Côte d'Ivoire", "shares": 33_000_000,  "pe_hist": 16.0, "pb_hist": 2.2,  "roe": 8,  "div_hist": 50,   "debt": "Élevée",   "stable": False},
    "CABC":  {"name": "Sicable CI",                    "sector": "Industriel",   "country": "Côte d'Ivoire", "shares": 14_000_000,  "pe_hist": 12.0, "pb_hist": 2.0,  "roe": 10, "div_hist": 120,  "debt": "Modérée",  "stable": False},
    "CFAC":  {"name": "CFAO Motors CI",                "sector": "Industriel",   "country": "Côte d'Ivoire", "shares": 35_200_000,  "pe_hist": 14.0, "pb_hist": 1.8,  "roe": 8,  "div_hist": 50,   "debt": "Modérée",  "stable": False},
    "BNBC":  {"name": "Bernabé CI",                    "sector": "Industriel",   "country": "Côte d'Ivoire", "shares": 30_000_000,  "pe_hist": 15.0, "pb_hist": 2.0,  "roe": 8,  "div_hist": 50,   "debt": "Modérée",  "stable": False},
    "SICC":  {"name": "Sicor CI",                      "sector": "Industriel",   "country": "Côte d'Ivoire", "shares": 18_000_000,  "pe_hist": 16.0, "pb_hist": 2.2,  "roe": 8,  "div_hist": 80,   "debt": "Modérée",  "stable": False},
    "PRSC":  {"name": "Tractafric Motors CI",          "sector": "Industriel",   "country": "Côte d'Ivoire", "shares": 20_000_000,  "pe_hist": 18.0, "pb_hist": 2.0,  "roe": 9,  "div_hist": 80,   "debt": "Modérée",  "stable": False},
    "ABJC":  {"name": "Servair Abidjan CI",            "sector": "Industriel",   "country": "Côte d'Ivoire", "shares": 7_000_000,   "pe_hist": 25.0, "pb_hist": 3.5,  "roe": 7,  "div_hist": 50,   "debt": "Modérée",  "stable": False},
    "STAC":  {"name": "Setao CI",                      "sector": "Industriel",   "country": "Côte d'Ivoire", "shares": 17_000_000,  "pe_hist": 22.0, "pb_hist": 3.0,  "roe": 8,  "div_hist": 30,   "debt": "Élevée",   "stable": False},
    "SIVC":  {"name": "Erium CI (Air Liquide)",        "sector": "Industriel",   "country": "Côte d'Ivoire", "shares": 60_000_000,  "pe_hist": 20.0, "pb_hist": 3.0,  "roe": 10, "div_hist": 60,   "debt": "Faible",   "stable": True},
    "BICB":  {"name": "BICB Bénin",                    "sector": "Banque",        "country": "Bénin",         "shares": 10_000_000,  "pe_hist": 12.0, "pb_hist": 1.5,  "roe": 12, "div_hist": 200,  "debt": "Faible",   "stable": True},
}


def fetch_brvm_prices() -> dict:
    """Scrape les cours officiels de brvm.org"""
    url = "https://www.brvm.org/en/cours-actions/0"
    prices = {}
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Chercher les données dans les tableaux ou divs
        rows = soup.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 3:
                ticker = cells[0].get_text(strip=True)
                price_text = cells[1].get_text(strip=True).replace(" ", "").replace("\xa0", "")
                change_text = cells[2].get_text(strip=True).replace(" ", "").replace("%", "")
                try:
                    price = float(price_text.replace(",", "."))
                    change = float(change_text.replace(",", ".").replace("+", ""))
                    if ticker and price > 0:
                        prices[ticker] = {"price": price, "change_pct": change}
                except ValueError:
                    continue

        logger.info(f"brvm.org: {len(prices)} cours récupérés")
    except Exception as e:
        logger.warning(f"brvm.org inaccessible: {e}")

    return prices


def fetch_kwayisi_price(ticker: str) -> dict | None:
    """Récupère les données d'un ticker depuis afx.kwayisi.org"""
    url = f"https://afx.kwayisi.org/brvm/{ticker.lower()}.html"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        data = {}

        # Extraire le cours actuel
        price_tag = soup.find("span", class_="price") or soup.find("td", string=lambda t: t and "XOF" in t)
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["th", "td"])
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True).lower()
                    val = cells[1].get_text(strip=True).replace(" ", "").replace(",", ".")
                    if "price" in key or "cours" in key or "close" in key:
                        try:
                            data["price"] = float(val.replace("xof", "").replace("fcfa", ""))
                        except:
                            pass
                    elif "earn" in key or "eps" in key or "bpa" in key:
                        try:
                            data["eps"] = float(val)
                        except:
                            pass
                    elif "dividend" in key or "dividende" in key:
                        try:
                            data["dividend"] = float(val)
                        except:
                            pass
                    elif "p/e" in key or "per" in key:
                        try:
                            data["pe"] = float(val)
                        except:
                            pass

        return data if data else None
    except Exception as e:
        logger.debug(f"kwayisi {ticker}: {e}")
        return None


def build_stock_dataset(use_cache: bool = False, cache_path: str = "data/prices_cache.json") -> pd.DataFrame:
    """
    Construit le dataset complet en combinant:
    - Cours live de brvm.org
    - Données fondamentales statiques (mis à jour annuellement)
    - Cache local si disponible
    """
    # Essayer le cache d'abord si demandé
    if use_cache and os.path.exists(cache_path):
        with open(cache_path) as f:
            cached = json.load(f)
        logger.info(f"Cache chargé: {cache_path}")
        return pd.DataFrame(cached)

    logger.info("Récupération des cours BRVM...")
    live_prices = fetch_brvm_prices()

    rows = []
    tickers = list(STOCK_FUNDAMENTALS.keys())

    for ticker in tickers:
        fund = STOCK_FUNDAMENTALS[ticker]
        price_data = live_prices.get(ticker, {})

        # Si pas dans le scrape brvm.org, essayer kwayisi
        if not price_data:
            logger.info(f"  Tentative kwayisi pour {ticker}...")
            kw = fetch_kwayisi_price(ticker)
            if kw and "price" in kw:
                price_data = kw
            time.sleep(0.3)

        price = price_data.get("price", None)
        change = price_data.get("change_pct", 0.0)

        row = {
            "ticker": ticker,
            "name": fund["name"],
            "sector": fund["sector"],
            "country": fund["country"],
            "price": price,
            "change_pct": change,
            "pe_ref": fund["pe_hist"],
            "pb_ref": fund["pb_hist"],
            "roe": fund["roe"],
            "div_per_share": fund["div_hist"],
            "debt_level": fund["debt"],
            "earnings_stable": fund["stable"],
            "shares_outstanding": fund["shares"],
            "fetched_at": datetime.now().isoformat(),
        }

        # Calculs dérivés si prix disponible
        if price:
            row["div_yield"] = round((fund["div_hist"] / price) * 100, 2) if fund["div_hist"] else 0
            row["market_cap_xof"] = price * fund["shares"]
            # EPS estimé = prix / PE de référence
            row["eps_est"] = round(price / fund["pe_hist"], 0) if fund["pe_hist"] else None
        else:
            row["div_yield"] = None
            row["market_cap_xof"] = None
            row["eps_est"] = None

        rows.append(row)

    df = pd.DataFrame(rows)

    # Sauvegarder le cache
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    df.to_json(cache_path, orient="records", indent=2)
    logger.info(f"Cache sauvegardé: {cache_path}")

    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    df = build_stock_dataset()
    print(df[["ticker", "name", "price", "change_pct", "div_yield"]].to_string())
