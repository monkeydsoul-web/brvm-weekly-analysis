"""
boc_scraper.py — Extrait données depuis Bulletins Officiels de la Cote BRVM
Données: cours, volumes, PER, dividendes, dates ex-div, variations annuelles
"""
import requests, pdfplumber, io, json, os, re, logging
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings('ignore')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOC_CACHE_PATH = os.path.join(BASE_DIR, 'data', 'boc_data.json')
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
logger = logging.getLogger(__name__)

def get_boc_urls(n=5):
    """Récupère les URLs des n derniers BOC."""
    try:
        r = requests.get('https://www.brvm.org/fr/bulletins-officiels-de-la-cote', 
                        headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        urls = [a['href'] for a in soup.find_all('a', href=True) 
                if '.pdf' in a['href'].lower() and 'boc_' in a['href'].lower()]
        return urls[:n]
    except Exception as e:
        logger.error(f"Erreur récupération URLs BOC: {e}")
        return []

def parse_boc_pdf(url):
    """Extrait les données d'un PDF BOC."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        results = {}
        
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ''
                if not text: continue
                
                # Extraire date du BOC
                date_match = re.search(r'(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})', text, re.IGNORECASE)
                boc_date = None
                if date_match:
                    months = {'janvier':1,'février':2,'mars':3,'avril':4,'mai':5,'juin':6,
                             'juillet':7,'août':8,'septembre':9,'octobre':10,'novembre':11,'décembre':12}
                    try:
                        boc_date = f"{date_match.group(3)}-{months[date_match.group(2).lower()]:02d}-{int(date_match.group(1)):02d}"
                    except: pass
                
                # Parser lignes de cours
                # Format: TICKER NOM COURS_PREV COURS_OUV COURS_CLOT VARIATION VOLUME VALEUR COURS_REF VAR_ANNEE DIV_MONTANT DIV_DATE DIV_RDT PER
                lines = text.split('\n')
                for line in lines:
                    # Chercher lignes avec ticker (4 lettres majuscules au début)
                    m = re.match(r'^([A-Z]{2,6})\s+(.+?)\s+(\d[\d\s]+)\s+(\d[\d\s]+)\s+(\d[\d\s]+)\s+([+-]?\d+[,.]?\d*)\s*%', line)
                    if not m:
                        continue
                    
                    ticker = m.group(1)
                    if len(ticker) < 2 or len(ticker) > 6:
                        continue
                    
                    try:
                        def clean_num(s):
                            return float(s.replace(' ','').replace(',','.'))
                        
                        cours_prev = clean_num(m.group(3))
                        cours_ouv  = clean_num(m.group(4))
                        cours_clot = clean_num(m.group(5))
                        variation  = clean_num(m.group(6))
                        
                        if cours_clot <= 0: continue
                        
                        entry = {
                            'date':       boc_date or datetime.now().strftime('%Y-%m-%d'),
                            'cours_prev': cours_prev,
                            'cours_ouv':  cours_ouv,
                            'cours_clot': cours_clot,
                            'variation':  variation,
                        }
                        
                        # Extraire PER si présent à la fin de la ligne
                        per_m = re.search(r'(\d+[,.]\d+)\s*$', line)
                        if per_m:
                            try:
                                entry['per_boc'] = float(per_m.group(1).replace(',','.'))
                            except: pass
                        
                        # Extraire dividende et date (format: 721,6 18-août-25 6,19%)
                        div_m = re.search(r'(\d+[,.]?\d*)\s+(\d{1,2}-\w+-\d{2})\s+(\d+[,.]\d+)\s*%', line)
                        if div_m:
                            try:
                                entry['div_net']  = float(div_m.group(1).replace(',','.'))
                                entry['div_date'] = div_m.group(2)
                                entry['div_rdt']  = float(div_m.group(3).replace(',','.'))
                            except: pass
                        
                        # Variation annuelle
                        van_m = re.search(r'([+-]?\d+[,.]\d+)\s*%\s+\d', line)
                        if van_m:
                            try:
                                entry['var_annee'] = float(van_m.group(1).replace(',','.'))
                            except: pass
                        
                        results[ticker] = entry
                        
                    except Exception:
                        continue
        
        return results
    except Exception as e:
        logger.error(f"Erreur parse BOC {url}: {e}")
        return {}

def parse_boc_tables(url):
    """Extraction précise des données BOC."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        results = {}
        boc_date = None
        SKIP = {'CB','ENE','COMP','PRES','PRIN','BOC','CODE','SECT','ACT','OUV'}

        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ''
                if not text or len(text) < 50: continue

                # Extraire date BOC
                if not boc_date:
                    dm = re.search(r'(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})', text, re.I)
                    if dm:
                        months = {'janvier':1,'février':2,'mars':3,'avril':4,'mai':5,'juin':6,
                                 'juillet':7,'août':8,'septembre':9,'octobre':10,'novembre':11,'décembre':12}
                        boc_date = f"{dm.group(3)}-{months[dm.group(2).lower()]:02d}-{int(dm.group(1)):02d}"

                for line in text.split('\n'):
                    m = re.match(r'^([A-Z]{2,6})\s+', line)
                    if not m: continue
                    ticker = m.group(1)
                    if ticker in SKIP: continue

                    rest = line[len(ticker):].strip()
                    nums_raw = re.findall(r'\b(\d{1,3}(?:\s\d{3})*(?:[,.]\d+)?)\b', rest)
                    try:
                        nums = [float(s.replace(' ','').replace(',','.')) for s in nums_raw]
                    except: continue
                    if len(nums) < 3: continue

                    try:
                        entry = {
                            'date':       boc_date or datetime.now().strftime('%Y-%m-%d'),
                            'cours_prev': nums[0],
                            'cours_ouv':  nums[1],
                            'cours_clot': nums[2],
                        }
                        var_m = re.search(r'([+-]?\d+[,.]\d+)\s*%', rest)
                        if var_m: entry['variation'] = float(var_m.group(1).replace(',','.'))
                        per_m = re.search(r'(\d+[,.]\d+)\s*$', line.strip())
                        if per_m:
                            per = float(per_m.group(1).replace(',','.'))
                            if 0 < per < 200: entry['per_boc'] = per
                        div_m = re.search(r'(\d+[,.]?\d*)\s+(\d{1,2}-\w{3,4}\.?-\d{2,4})\s+(\d+[,.]\d+)\s*%', line)
                        if div_m:
                            entry['div_net']  = float(div_m.group(1).replace(',','.'))
                            entry['div_date'] = div_m.group(2)
                            entry['div_rdt']  = float(div_m.group(3).replace(',','.'))
                        van_m = re.search(r'(\d+[,.]\d+)\s*%\s+(?:\d+[,.]?\d*)\s+\d{1,2}-\w', line)
                        if van_m: entry['var_annee'] = float(van_m.group(1).replace(',','.'))
                        if entry['cours_clot'] > 100 and ticker not in results:
                            results[ticker] = entry
                    except: continue

        return results, boc_date
    except Exception as e:
        logger.error(f"Erreur parse BOC: {e}")
        return {}, None

def update_from_boc():
    """Met à jour les données depuis les derniers BOC."""
    urls = get_boc_urls(n=3)
    if not urls:
        logger.warning("Aucun BOC trouvé")
        return {}
    
    # Charger cache
    cache = {}
    if os.path.exists(BOC_CACHE_PATH):
        try:
            with open(BOC_CACHE_PATH) as f:
                cache = json.load(f)
        except: pass
    
    all_data = {}
    for url in urls:
        logger.info(f"Parsing BOC: {url.split('/')[-1]}")
        data, boc_date = parse_boc_tables(url)
        if data:
            logger.info(f"  → {len(data)} tickers extraits pour {boc_date}")
            for ticker, entry in data.items():
                if ticker not in all_data:
                    all_data[ticker] = entry
    
    # Fusionner avec cache
    cache.update(all_data)
    cache['last_update'] = datetime.now().isoformat()
    
    with open(BOC_CACHE_PATH, 'w') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    
    logger.info(f"BOC: {len(all_data)} tickers mis à jour")
    return all_data

def enrich_scores_from_boc():
    """Enrichit les scores avec PER et dividendes du BOC."""
    if not os.path.exists(BOC_CACHE_PATH):
        update_from_boc()
    
    with open(BOC_CACHE_PATH) as f:
        boc = json.load(f)
    
    from scraper import STOCK_FUNDAMENTALS
    enriched = 0
    for ticker, data in boc.items():
        if ticker == 'last_update': continue
        if ticker in STOCK_FUNDAMENTALS:
            fund = STOCK_FUNDAMENTALS[ticker]
            # PER du BOC
            if data.get('per_boc') and not fund.get('pe_hist'):
                fund['pe_hist'] = data['per_boc']
                enriched += 1
            # Dividende du BOC
            if data.get('div_net') and not fund.get('div_hist'):
                fund['div_hist'] = data['div_net']
    
    logger.info(f"Enrichissement BOC: {enriched} tickers mis à jour")
    return enriched

def get_boc_price_history():
    """Retourne l'historique de prix depuis les BOC."""
    if not os.path.exists(BOC_CACHE_PATH):
        return {}
    with open(BOC_CACHE_PATH) as f:
        return json.load(f)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print("Scraping Bulletins Officiels de la Cote BRVM...")
    data = update_from_boc()
    print(f"\nDonnées extraites: {len(data)} tickers")
    for ticker, d in list(data.items())[:10]:
        print(f"  {ticker:6}: cours={d.get('cours_clot')} per={d.get('per_boc')} div={d.get('div_net')} date={d.get('date')}")
