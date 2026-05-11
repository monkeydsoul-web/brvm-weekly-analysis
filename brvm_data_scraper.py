"""
brvm_data_scraper.py — Scrape données enrichies depuis brvm.org
- Indices sectoriels BRVM
- Annonces émetteurs (AG, dividendes, résultats)
- Résumé journalier de marché
"""
import requests, json, os, re, logging
from datetime import datetime
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings('ignore')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
logger = logging.getLogger(__name__)

SECTOR_INDICES_PATH = os.path.join(BASE_DIR, 'data', 'sector_indices.json')
ANNOUNCEMENTS_PATH  = os.path.join(BASE_DIR, 'data', 'announcements.json')

# Map indices sectoriels -> secteur dashboard
SECTOR_MAP = {
    'CONSOMMATION DE BASE':        'Consommation',
    'CONSOMMATION DISCRETIONNAIRE':'Industriel',
    'ENERGIE':                     'Énergie',
    'INDUSTRIELS':                 'Industriel',
    'SERVICES FINANCIERS':         'Banque',
    'SERVICES PUBLICS':            'Utilités',
    'TELECOMMUNICATIONS':          'Télécoms',
    'AGRICULTURE':                 'Agriculture',
}

# Map sociétés -> tickers
COMPANY_TICKER_MAP = {
    'TOTAL':'TTLC','TOTALENERGIES':'TTLC','PALM CI':'PALC','SAPH CI':'SPHC',
    'SONATEL':'SNTS','ORANGE':'ORAC','ECOBANK CI':'ECOC','ECOBANK TOGO':'ETIT',
    'ECOBANK TRANSNATIONAL':'ETIT','SOCIÉTÉ GÉNÉRALE':'SGBC','SIB':'SIBC',
    'NSIA BANQUE':'NSBC','CORIS BANK':'CBIBF','BICI':'BICC','BANK OF AFRICA CI':'BOAC',
    'BANK OF AFRICA BF':'BOABF','BANK OF AFRICA SN':'BOAS','BANK OF AFRICA ML':'BOAM',
    'BANK OF AFRICA NG':'BOAN','BANK OF AFRICA BN':'BOAB','BOA CI':'BOAC',
    'NESTLE':'NTLC','UNILEVER':'UNLC','SITAB':'STBC','SOLIBRA':'SLBC',
    'SMB CI':'SMBC','FILTISAC':'FTSC','CFAO':'CABC','TRACTAFRIC':'PRSC',
    'SETAO CI':'STAC','SICOR':'SICC','BERNABE':'BNBC','SERVAIR':'ABJC',
    'SUCRIVOIRE':'SCRC','NEI-CEDA':'NEIC','NEI CEDA':'NEIC','UNIWAX':'UNXC',
    'ONATEL':'ONTBF','ORAGROUP':'ORGT','CIE CI':'CIEC','SODECI':'SDCC',
    'AFRICA GLOBAL':'SDSC','EVIOSYS':'SEMC','SAFCA':'SAFC','VIVO ENERGY':'SHEC',
    'TOTALENERGIES SN':'TTLS','PALMCI':'PALC','AIR LIQUIDE':'SIVC',
}

def find_ticker(company_name):
    name_up = company_name.upper().strip()
    for key, ticker in COMPANY_TICKER_MAP.items():
        if key in name_up:
            return ticker
    return None

def scrape_sector_indices():
    """Scrape les indices sectoriels depuis /fr/resume."""
    try:
        r = requests.get('https://www.brvm.org/fr/resume', headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        tables = soup.find_all('table')
        
        indices = {}
        for table in tables:
            headers = [th.text.strip() for th in table.find_all('th')]
            if 'Fermeture' not in str(headers): continue
            
            for row in table.find_all('tr')[1:]:
                cols = [td.text.strip() for td in row.find_all('td')]
                if len(cols) < 4: continue
                name = cols[0].replace('BRVM - ','').replace('BRVM-','').strip()
                try:
                    current = float(cols[2].replace(',','.').replace(' ',''))
                    change  = float(cols[3].replace(',','.').replace(' ','').replace('%',''))
                    ytd     = float(cols[4].replace(',','.').replace(' ','').replace('%','')) if len(cols)>4 else 0
                    indices[name] = {
                        'current': current,
                        'change':  change,
                        'ytd':     ytd,
                        'sector':  SECTOR_MAP.get(name, name)
                    }
                except: continue
        
        if indices:
            data = {'indices': indices, 'updated_at': datetime.now().isoformat()}
            with open(SECTOR_INDICES_PATH, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Indices sectoriels: {len(indices)} mis à jour")
        return indices
    except Exception as e:
        logger.error(f"Erreur indices sectoriels: {e}")
        return {}

def scrape_announcements(pages=3):
    """Scrape les annonces émetteurs (AG, dividendes, résultats)."""
    try:
        all_annonces = []
        
        for ann_type in ['convocations-assemblees-generales']:
            for page in range(pages):
                url = f'https://www.brvm.org/fr/emetteurs/type-annonces/{ann_type}?page={page}'
                r = requests.get(url, headers=HEADERS, timeout=15)
                soup = BeautifulSoup(r.text, 'html.parser')
                
                for table in soup.find_all('table'):
                    headers = [th.text.strip() for th in table.find_all('th')]
                    if 'Date' not in headers and 'Société' not in headers: continue
                    
                    for row in table.find_all('tr')[1:]:
                        cols = [td.text.strip() for td in row.find_all('td')]
                        if len(cols) < 3: continue
                        
                        date_str = cols[0]
                        company  = cols[1]
                        title    = cols[2]
                        
                        # Trouver lien PDF
                        pdf_link = None
                        for a in row.find_all('a', href=True):
                            if '.pdf' in a['href'].lower():
                                pdf_link = a['href']
                                break
                        
                        ticker = find_ticker(company)
                        
                        # Extraire dividende si mentionné
                        div_amount = None
                        div_m = re.search(r'(\d+[,.]?\d*)\s*(?:FCFA|francs)', title, re.I)
                        if div_m:
                            div_amount = float(div_m.group(1).replace(',','.'))
                        
                        all_annonces.append({
                            'date':       date_str,
                            'company':    company,
                            'ticker':     ticker,
                            'title':      title,
                            'type':       ann_type,
                            'pdf_url':    pdf_link,
                            'div_amount': div_amount,
                        })
        
        # Trier par date décroissante
        all_annonces.sort(key=lambda x: x.get('date',''), reverse=True)
        
        with open(ANNOUNCEMENTS_PATH, 'w') as f:
            json.dump(all_annonces, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Annonces: {len(all_annonces)} sauvegardées")
        return all_annonces
    except Exception as e:
        logger.error(f"Erreur annonces: {e}")
        return []

def get_sector_indices():
    if os.path.exists(SECTOR_INDICES_PATH):
        with open(SECTOR_INDICES_PATH) as f:
            return json.load(f)
    return scrape_sector_indices()

def get_announcements():
    if os.path.exists(ANNOUNCEMENTS_PATH):
        with open(ANNOUNCEMENTS_PATH) as f:
            return json.load(f)
    return scrape_announcements()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print("=== Indices sectoriels ===")
    indices = scrape_sector_indices()
    for name, data in indices.items():
        print(f"  {name:35} {data['current']:8.2f} {data['change']:+.2f}% YTD:{data['ytd']:+.2f}%")
    
    print("\n=== Annonces émetteurs ===")
    annonces = scrape_announcements()
    for a in annonces[:10]:
        print(f"  {a['date']:12} {a.get('ticker','?'):6} {a['title'][:60]}")
