"""
company_scraper.py — Scrape actualités BRVM via RSS et sites entreprises
"""
import requests, json, os, time, logging, re
from datetime import datetime
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings('ignore')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NEWS_PATH = os.path.join(BASE_DIR, 'data', 'news_cache.json')

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
}

# Flux RSS fiables
RSS_FEEDS = [
    {'url': 'https://www.brvm.org/fr/rss.xml',                              'source': 'BRVM Officiel'},
    {'url': 'https://www.financialafrik.com/tag/brvm/feed/',                'source': 'Financial Afrik BRVM'},
    {'url': 'https://www.financialafrik.com/tag/cote-divoire/feed/',        'source': 'Financial Afrik CI'},
    {'url': 'https://www.financialafrik.com/tag/senegal/feed/',             'source': 'Financial Afrik SN'},
    {'url': 'https://www.financialafrik.com/tag/burkina/feed/',             'source': 'Financial Afrik BF'},
    {'url': 'https://www.financialafrik.com/tag/mali/feed/',                'source': 'Financial Afrik ML'},
    {'url': 'https://www.financialafrik.com/tag/dividende/feed/',           'source': 'Financial Afrik Dividendes'},
    {'url': 'https://www.financialafrik.com/tag/bourse/feed/',              'source': 'Financial Afrik Bourse'},
    {'url': 'https://www.financialafrik.com/tag/banque/feed/',              'source': 'Financial Afrik Banque'},
    {'url': 'https://www.financialafrik.com/tag/telecom/feed/',             'source': 'Financial Afrik Telecom'},
    {'url': 'https://www.financialafrik.com/category/finance/feed/',        'source': 'Financial Afrik Finance'},
    {'url': 'https://www.financialafrik.com/tag/niger/feed/',               'source': 'Financial Afrik NE'},
    {'url': 'https://www.financialafrik.com/tag/benin/feed/',               'source': 'Financial Afrik BJ'},
    {'url': 'https://www.financialafrik.com/tag/togo/feed/',                'source': 'Financial Afrik TG'},
]

# Sites officiels entreprises — scraping direct
COMPANY_SITES = {
    'CIEC': 'https://www.cie.ci/actualites',
    'PALC': 'https://www.palmci.ci/actualites',
    'TTLC': 'https://totalenergies.ci/actualites',
    'SNTS': 'https://www.sonatel.com/actualites',
    'CBIBF': 'https://www.corisbankinter.com/actualites',
    'NTLC': 'https://www.nestle.ci/media/communiques-de-presse',
}

def detect_tickers(text):
    """Détecte les tickers BRVM mentionnés dans un texte."""
    try:
        from scraper import STOCK_FUNDAMENTALS
        tickers = list(STOCK_FUNDAMENTALS.keys())
    except:
        tickers = ['SIBC','BICC','SNTS','SMBC','BOAC','ETIT','NSBC','NTLC','ECOC','ORGT',
                   'SGBC','ORAC','CBIBF','CIEC','PALC','TTLC','SPHC','SOGC','STBC']
    
    # Chercher aussi les noms complets
    NAME_MAP = {
        'nestlé':'NTLC','nestle':'NTLC','sonatel':'SNTS','orange ci':'ORAC',
        'ecobank':'ECOC','société générale':'SGBC','sgbci':'SGBC',
        'palm ci':'PALC','saph':'SPHC','coris bank':'CBIBF','bici':'BICC',
        'sib ci':'SIBC','nsia banque':'NSBC','totalenergies':'TTLC',
        'cie ci':'CIEC','sodeci':'SDCC','solibra':'SLBC','sitab':'STBC',
        'unilever':'UNLC','smb ci':'SMBC','onatel':'ONTBF','oragroup':'ORGT',
    }
    found = []
    text_lower = text.lower()
    for t in tickers:
        if t in text.upper():
            found.append(t)
    for name, ticker in NAME_MAP.items():
        if name in text_lower and ticker not in found:
            found.append(ticker)
    return list(set(found))

def scrape_rss(feed_url, source_name):
    """Scrape un flux RSS et retourne les articles."""
    try:
        r = requests.get(feed_url, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.content, 'xml')
        items = soup.find_all(['item', 'entry'])
        articles = []
        for item in items[:10]:
            title = item.find('title')
            link  = item.find('link')
            desc  = item.find(['description', 'summary', 'content'])
            pubdate = item.find(['pubDate', 'published', 'updated', 'dc:date'])
            
            if not title or len(title.text.strip()) < 15:
                continue
            
            title_text = title.text.strip()
            desc_text  = BeautifulSoup(desc.text if desc else '', 'html.parser').text.strip()[:300]
            full_text  = title_text + ' ' + desc_text
            
            # Date
            date_str = datetime.now().strftime('%Y-%m-%d')
            if pubdate:
                try:
                    from email.utils import parsedate_to_datetime
                    date_str = parsedate_to_datetime(pubdate.text).strftime('%Y-%m-%d')
                except:
                    pass
            
            # URL
            href = ''
            if link:
                href = link.get('href') or link.text.strip()
            
            tickers = detect_tickers(full_text)
            
            articles.append({
                'title':            title_text,
                'url':              href,
                'date':             date_str,
                'source':           source_name,
                'description':      desc_text,
                'tickers':          tickers,
                'is_dividend_news': any(k in full_text.lower() for k in ['dividende','dividend','coupon']),
                'is_results_news':  any(k in full_text.lower() for k in ['résultat','bénéfice','chiffre d\'affaires','exercice 20']),
            })
        return articles
    except Exception as e:
        logger.debug(f"Erreur RSS {feed_url}: {e}")
        return []

def scrape_company_site(ticker, url):
    """Scrape le site officiel d'une entreprise."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, 'html.parser')
        articles = []
        
        for tag in soup.find_all(['article','div'], class_=lambda c: c and any(
            k in str(c).lower() for k in ['news','article','post','actu','press','communique']
        ))[:8]:
            title_tag = tag.find(['h1','h2','h3','h4'])
            if not title_tag or len(title_tag.text.strip()) < 20:
                continue
            title = title_tag.text.strip()
            link = tag.find('a', href=True)
            href = link['href'] if link else ''
            if href and not href.startswith('http'):
                from urllib.parse import urljoin
                href = urljoin(url, href)
            
            articles.append({
                'title':            title,
                'url':              href,
                'date':             datetime.now().strftime('%Y-%m-%d'),
                'source':           url.split('/')[2],
                'description':      '',
                'tickers':          [ticker],
                'is_dividend_news': any(k in title.lower() for k in ['dividende','résultat']),
                'is_results_news':  any(k in title.lower() for k in ['résultat','bénéfice','exercice']),
            })
        return articles
    except Exception as e:
        logger.debug(f"Erreur site {url}: {e}")
        return []

def load_news():
    if os.path.exists(NEWS_PATH):
        try:
            with open(NEWS_PATH, encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return []

def save_news(articles):
    with open(NEWS_PATH, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

def merge_news(existing, new_articles):
    existing_titles = {n.get('title','').lower().strip() for n in existing}
    added = 0
    for art in new_articles:
        t = art.get('title','').lower().strip()
        if t and t not in existing_titles and len(t) > 15:
            existing.insert(0, art)
            existing_titles.add(t)
            added += 1
    existing.sort(key=lambda x: x.get('date',''), reverse=True)
    return existing[:300], added

def run_company_scraper(tickers=None):
    logger.info("=== Scraping actualités BRVM ===")
    all_new = []
    
    # RSS feeds
    for feed in RSS_FEEDS:
        logger.info(f"RSS: {feed['source']}")
        arts = scrape_rss(feed['url'], feed['source'])
        logger.info(f"  → {len(arts)} articles")
        all_new.extend(arts)
        time.sleep(0.8)
    
    # Sites entreprises
    sites = {k:v for k,v in COMPANY_SITES.items() if tickers is None or k in tickers}
    for ticker, url in sites.items():
        logger.info(f"Site {ticker}: {url}")
        arts = scrape_company_site(ticker, url)
        logger.info(f"  → {len(arts)} articles")
        all_new.extend(arts)
        time.sleep(0.5)
    
    existing = load_news()
    merged, added = merge_news(existing, all_new)
    save_news(merged)
    
    logger.info(f"Total: {len(all_new)} trouvés, {added} nouveaux, {len(merged)} en cache")
    return added

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    n = run_company_scraper()
    print(f"\nNouveaux articles ajoutés: {n}")
    # Afficher les 10 premiers
    news = load_news()
    print(f"Total en cache: {len(news)}")
    for a in news[:10]:
        print(f"  [{a['source'][:20]:20}] {a['title'][:60]} {a.get('tickers',[])} ")
