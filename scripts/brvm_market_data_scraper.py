#!/usr/bin/env python3
"""
brvm_market_data_scraper.py
Scrape et structure :
  A) Notations financières BRVM → data/brvm_ratings.json
  B) Statistiques de marché    → data/brvm_market_stats.json
  C) Données fondamentales     → data/brvm_fundamentals.json

Sources :
  - data/brvm_docs/notations/ (PDFs déjà téléchargés)
  - https://www.brvm.org/fr/emetteurs/type-annonces/notations-financieres (nouvelles pages)
  - https://www.brvm.org/fr/emetteurs/{slug} (pages emetteurs)
  - live_cache.json + market_cache.json (données locales)
"""
import os, re, sys, json, time, logging, datetime, warnings, unicodedata, calendar
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

warnings.filterwarnings("ignore")
import requests
from bs4 import BeautifulSoup

try:
    import pdfplumber
    HAS_PDF = True
except ImportError:
    HAS_PDF = False
    logging.warning("pdfplumber non disponible — skip lecture PDF")

BASE_DIR    = Path(__file__).parent.parent
DATA_DIR    = Path(os.environ.get("BRVM_DATA_DIR", str(BASE_DIR / "data")))  # dupliqué depuis paths.py (racine) — script lancé en subprocess isolé
DOCS_DIR    = DATA_DIR / "brvm_docs"
LOG_DIR     = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

RATINGS_PATH     = DATA_DIR / "brvm_ratings.json"
MARKET_PATH      = DATA_DIR / "brvm_market_stats.json"
FUNDAMENT_PATH   = DATA_DIR / "brvm_fundamentals.json"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; BRVMBot/2.0)"})
RATE_LIMIT = 1.5
_last_req  = 0.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_DIR / "brvm_market.log"),
        logging.StreamHandler(sys.stdout),
    ],
)

# ── Alias émetteur coté → ticker (mot entier, jamais un bout de mot) ────────
# Noms officiels recopiés de STOCK_FUNDAMENTALS (scraper.py, lecture seule)
# plus les raisons sociales lues dans les communiqués de notation.
# « eti » dans « marketing » et « cie » dans « financière » ne doivent plus matcher.
_ALIAS_BRUTS: List[Tuple[str, str]] = [
    # Noms STOCK_FUNDAMENTALS (47)
    ("Société Générale CI", "SGBC"),
    ("Société Ivoirienne de Banque", "SIBC"),
    ("Sonatel Senegal", "SNTS"),
    ("NSIA Banque CI", "NSBC"),
    ("Coris Bank International", "CBIBF"),
    ("BOA Benin", "BOAB"),
    ("BOA Burkina Faso", "BOABF"),
    ("BOA Côte d'Ivoire", "BOAC"),
    ("BOA Mali", "BOAM"),
    ("BOA Niger", "BOAN"),
    ("BOA Sénégal", "BOAS"),
    ("Ecobank CI", "ECOC"),
    ("BICI CI", "BICC"),
    ("Ecobank Transnational", "ETIT"),
    ("Oragroup Togo", "ORGT"),
    ("SAFCA CI", "SAFC"),
    ("Orange CI", "ORAC"),
    ("Onatel Burkina Faso", "ONTBF"),
    ("Nestlé CI", "NTLC"),
    ("SITAB CI", "STBC"),
    ("Unilever CI", "UNLC"),
    ("SOLIBRA CI", "SLBC"),
    ("SMB CI", "SMBC"),
    ("Uniwax CI", "UNXC"),
    ("Loterie Nationale Bénin", "LNBB"),
    ("NEI-CEDA CI", "NEIC"),
    ("Palm CI", "PALC"),
    ("SAPH CI", "SPHC"),
    ("SOGB CI", "SOGC"),
    ("Sucrivoire CI", "SCRC"),
    ("TotalEnergies CI", "TTLC"),
    ("TotalEnergies Sénégal", "TTLS"),
    ("Vivo Energy CI", "SHEC"),
    ("Crown Siem CI", "SEMC"),
    ("CIE CI", "CIEC"),
    ("SODECI CI", "SDCC"),
    ("Filtisac CI", "FTSC"),
    ("Africa Global Logistics CI", "SDSC"),
    ("Sicable CI", "CABC"),
    ("CFAO Motors CI", "CFAC"),
    ("Bernabé CI", "BNBC"),
    ("Sicor CI", "SICC"),
    ("Tractafric Motors CI", "PRSC"),
    ("Servair Abidjan CI", "ABJC"),
    ("Setao CI", "STAC"),
    ("Erium CI (Air Liquide)", "SIVC"),
    ("BIIC Bénin", "BICB"),
    # Raisons sociales et noms courants des mêmes 47
    ("Société Générale de Banques en Côte d'Ivoire", "SGBC"),
    ("Société Générale Côte d'Ivoire", "SGBC"),
    ("Société Générale", "SGBC"),
    ("SGBCI", "SGBC"),
    ("SGB CI", "SGBC"),
    ("SGBC", "SGBC"),
    ("Société Ivoirienne de Banque SA", "SIBC"),
    ("SIB", "SIBC"),
    ("Sonatel", "SNTS"),
    ("Sonatel Sénégal", "SNTS"),
    ("Orange Sénégal", "SNTS"),
    ("SNTS", "SNTS"),
    ("NSIA Banque Côte d'Ivoire", "NSBC"),
    ("NSIA Banque", "NSBC"),
    ("NSBC", "NSBC"),
    ("Coris Bank International Burkina", "CBIBF"),
    ("Coris Bank International", "CBIBF"),
    ("Coris Bank", "CBIBF"),
    ("CBIBF", "CBIBF"),
    ("Bank of Africa Bénin", "BOAB"),
    ("Bank of Africa Benin", "BOAB"),
    ("BOA Bénin", "BOAB"),
    ("BOAB", "BOAB"),
    ("Bank of Africa Burkina Faso", "BOABF"),
    ("Bank of Africa Burkina", "BOABF"),
    ("BOA Burkina", "BOABF"),
    ("BOABF", "BOABF"),
    ("Bank of Africa Côte d'Ivoire", "BOAC"),
    ("Bank of Africa CI", "BOAC"),
    ("BOA CI", "BOAC"),
    ("BOAC", "BOAC"),
    ("Bank of Africa Mali", "BOAM"),
    ("BOAM", "BOAM"),
    ("Bank of Africa Niger", "BOAN"),
    ("BOAN", "BOAN"),
    ("Bank of Africa Sénégal", "BOAS"),
    ("Bank of Africa Senegal", "BOAS"),
    ("BOAS", "BOAS"),
    ("Ecobank Côte d'Ivoire", "ECOC"),
    ("ECOC", "ECOC"),
    ("Banque Internationale pour le Commerce et l'Industrie de la Côte d'Ivoire", "BICC"),
    ("BICICI", "BICC"),
    ("BICI", "BICC"),
    ("BICC", "BICC"),
    ("Ecobank Transnational Incorporated", "ETIT"),
    ("Groupe Ecobank", "ETIT"),
    ("ETI", "ETIT"),
    ("ETIT", "ETIT"),
    ("Oragroup", "ORGT"),
    ("ORGT", "ORGT"),
    ("SAFCA", "SAFC"),
    ("Société Africaine de Crédit Automobile", "SAFC"),
    ("SAFC", "SAFC"),
    ("Orange Côte d'Ivoire", "ORAC"),
    ("ORAC", "ORAC"),
    ("Onatel", "ONTBF"),
    ("Moov Africa Burkina Faso", "ONTBF"),
    ("Office National des Télécommunications du Burkina Faso", "ONTBF"),
    ("ONTBF", "ONTBF"),
    ("Nestlé Côte d'Ivoire", "NTLC"),
    ("Nestle CI", "NTLC"),
    ("Nestle Côte d'Ivoire", "NTLC"),
    ("Nestlé", "NTLC"),
    ("Nestle", "NTLC"),
    ("NTLC", "NTLC"),
    ("Société Ivoirienne des Tabacs", "STBC"),
    ("SITAB", "STBC"),
    ("STBC", "STBC"),
    ("Unilever Côte d'Ivoire", "UNLC"),
    ("Huilerie Savonnerie Lipochimie", "UNLC"),
    ("Unilever", "UNLC"),
    ("UNLC", "UNLC"),
    ("Solibra", "SLBC"),
    ("Société de Limonaderies et Brasseries d'Afrique", "SLBC"),
    ("SLBC", "SLBC"),
    ("Société Multinationale de Bitumes", "SMBC"),
    ("SMB", "SMBC"),
    # Slug BRVM de SMB (TICKER_SLUGS, google_news_scraper) : pas une autre société.
    ("SOACII", "SMBC"),
    ("SMBC", "SMBC"),
    ("Uniwax", "UNXC"),
    ("UNXC", "UNXC"),
    ("LONAB", "LNBB"),
    ("Loterie Nationale du Bénin", "LNBB"),
    ("LNBB", "LNBB"),
    ("NEI CEDA", "NEIC"),
    ("Nouvelles Editions Ivoiriennes", "NEIC"),
    ("NEIC", "NEIC"),
    ("PALMCI", "PALC"),
    ("PALC", "PALC"),
    ("SAPH", "SPHC"),
    ("Société Africaine de Plantations d'Hévéas", "SPHC"),
    ("SPHC", "SPHC"),
    ("SOGB", "SOGC"),
    ("Caoutchoucs de Grand-Béréby", "SOGC"),
    ("Société des Caoutchoucs de Grand-Béréby", "SOGC"),
    ("SOGC", "SOGC"),
    ("Sucrivoire", "SCRC"),
    ("SCRC", "SCRC"),
    ("TotalEnergies Marketing Côte d'Ivoire", "TTLC"),
    ("Total Energies Marketing Côte d'Ivoire", "TTLC"),
    ("TotalEnergies Marketing CI", "TTLC"),
    ("Total Energies Marketing CI", "TTLC"),
    ("Total CI", "TTLC"),
    ("TotalEnergies CI", "TTLC"),
    ("TTLC", "TTLC"),
    ("TotalEnergies Marketing Sénégal", "TTLS"),
    ("Total Energies Marketing Sénégal", "TTLS"),
    ("TotalEnergies Marketing Senegal", "TTLS"),
    ("Total Sénégal", "TTLS"),
    ("Total Senegal", "TTLS"),
    ("TTLS", "TTLS"),
    ("Vivo Energy Côte d'Ivoire", "SHEC"),
    ("Vivo Energy", "SHEC"),
    ("Shell CI", "SHEC"),
    ("SHEC", "SHEC"),
    ("Crown Siem", "SEMC"),
    ("SEMC", "SEMC"),
    ("Compagnie Ivoirienne d'Électricité", "CIEC"),
    ("Compagnie Ivoirienne d'Electricite", "CIEC"),
    ("CIE", "CIEC"),
    ("CIEC", "CIEC"),
    ("SODECI", "SDCC"),
    ("Société de Distribution d'Eau de Côte d'Ivoire", "SDCC"),
    ("SDCC", "SDCC"),
    ("Filtisac", "FTSC"),
    ("Filature Tissage Sacs de Côte d'Ivoire", "FTSC"),
    ("FTSC", "FTSC"),
    ("Africa Global Logistics", "SDSC"),
    ("SDSC", "SDSC"),
    ("Sicable", "CABC"),
    ("CABC", "CABC"),
    ("CFAO Motors", "CFAC"),
    ("Compagnie Française de l'Afrique Occidentale en Côte d'Ivoire", "CFAC"),
    ("CFAO", "CFAC"),
    ("CFAC", "CFAC"),
    ("Bernabé", "BNBC"),
    ("Bernabe", "BNBC"),
    ("BNBC", "BNBC"),
    ("Sicor", "SICC"),
    ("SICC", "SICC"),
    ("Tractafric Motors", "PRSC"),
    ("Tractafric", "PRSC"),
    ("PRSC", "PRSC"),
    ("Servair Abidjan", "ABJC"),
    ("ABJC", "ABJC"),
    ("Setao", "STAC"),
    ("SETACI", "STAC"),
    ("STAC", "STAC"),
    ("Erium CI", "SIVC"),
    ("Erium", "SIVC"),
    ("Air Liquide", "SIVC"),
    # Slug BRVM d'Erium (TICKER_SLUGS, google_news_scraper).
    ("SIVOP", "SIVC"),
    ("SIVC", "SIVC"),
    ("BIIC", "BICB"),
    ("BIC Bénin", "BICB"),
    ("BIC Benin", "BICB"),
    ("BICB", "BICB"),
]

# Émetteurs non cotés : un communiqué à leur nom ne doit pas être affiché
# comme la note d'une société de la cote (CRRH-UEMOA, BOAD, États, filiales).
_NON_COTES_BRUTS: List[str] = [
    "CRRH-UEMOA",
    "CRRH",
    "BOAD",
    "Banque Ouest Africaine de Développement",
    "Etat de Côte d'Ivoire",
    "État de Côte d'Ivoire",
    "Etat du Sénégal",
    "État du Sénégal",
    "Etat du Mali",
    "Etat du Bénin",
    "Etat du Burkina",
    "Etat du Niger",
    "Etat du Togo",
    "République de Côte d'Ivoire",
    "Republique de Côte d'Ivoire",
    "République du Sénégal",
    "Trésor public",
    "Ecobank Ghana",
    "Ecobank Nigeria",
    "Ecobank Cameroun",
    "NSIA Banque Bénin",
    "NSIA Banque Benin",
    "NSIA Banque Sénégal",
    "NSIA Assurances",
    "Société Générale Sénégal",
    "Société Générale Cameroun",
    "Coris Bank Sénégal",
    "Coris Bank Senegal",
    "Unilever Ghana",
    "Nestlé Sénégal",
    "Nestle Senegal",
]

# Si ce mot suit immédiatement un alias court, ce n'est pas la société cotée.
_PAYS_HORS_FILIALE_CI: Tuple[str, ...] = (
    "Sénégal", "Senegal", "Mali", "Niger", "Bénin", "Benin", "Togo",
    "Burkina", "Guinée", "Guinee", "Ghana", "Cameroun", "Nigeria",
)
_PAYS_HORS_CORIS: Tuple[str, ...] = (
    "Sénégal", "Senegal", "Mali", "Niger", "Côte d'Ivoire", "Cote d'Ivoire",
    "Bénin", "Benin", "Togo", "Guinée", "Guinee", "Ghana", "Cameroun",
)
_SUITE_REJETEE_BRUTE: Dict[str, Tuple[str, ...]] = {
    "NSIA Banque": _PAYS_HORS_FILIALE_CI,
    "NSIA": ("Assurances", "Vie", "Bénin", "Benin", "Sénégal", "Senegal", "Ghana", "Guinée", "Guinee"),
    "Société Générale": _PAYS_HORS_FILIALE_CI + ("France", "Maroc"),
    "Coris Bank International": _PAYS_HORS_CORIS,
    "Coris Bank": _PAYS_HORS_CORIS,
    "Unilever": ("Ghana", "Nigeria", "France", "Sénégal", "Senegal", "Kenya"),
    "Nestlé": ("Sénégal", "Senegal", "Ghana", "France", "Nigeria", "Cameroun"),
    "Nestle": ("Sénégal", "Senegal", "Ghana", "France", "Nigeria", "Cameroun"),
    "Vivo Energy": ("Ghana", "Sénégal", "Senegal", "Kenya", "Maroc"),
    "CFAO": ("Sénégal", "Senegal", "Cameroun", "Ghana", "Nigeria"),
}


def _fold_indexe(text: str) -> Tuple[str, List[int]]:
    """Texte plié et, pour chaque caractère plié, son index dans l'original.

    Minuscules, sans accent, d'/l' retirés, séparateurs en espaces.
    """
    if not text:
        return "", []
    t = text.replace("\u2019", "'").replace("\u2018", "'").replace("`", "'")
    decomposes: List[str] = []
    origines: List[int] = []
    for i, ch in enumerate(t):
        for c in unicodedata.normalize("NFD", ch):
            if unicodedata.category(c) == "Mn":
                continue
            decomposes.append(c.lower())
            origines.append(i)
    out: List[str] = []
    out_orig: List[int] = []
    n = len(decomposes)
    j = 0
    while j < n:
        ch = decomposes[j]
        prev_sep = j == 0 or not decomposes[j - 1].isalnum()
        if prev_sep and ch in ("d", "l") and j + 1 < n and decomposes[j + 1] == "'":
            j += 2
            continue
        if ("a" <= ch <= "z") or ("0" <= ch <= "9"):
            out.append(ch)
            out_orig.append(origines[j])
        elif not out or out[-1] != " ":
            out.append(" ")
            out_orig.append(origines[j])
        j += 1
    while out and out[0] == " ":
        out.pop(0)
        out_orig.pop(0)
    while out and out[-1] == " ":
        out.pop()
        out_orig.pop()
    return "".join(out), out_orig


def _fold(text: str) -> str:
    return _fold_indexe(text)[0]


def _construire_alias():
    # type: () -> Tuple[Dict[str, str], List[Tuple[str, str]], List[str], Dict[str, frozenset]]
    table: Dict[str, str] = {}
    for phrase, ticker in _ALIAS_BRUTS:
        cle = _fold(phrase)
        if len(cle) < 3:
            continue
        deja = table.get(cle)
        if deja and deja != ticker:
            raise RuntimeError("alias %r pointe vers %s et %s" % (cle, deja, ticker))
        table[cle] = ticker
    items = list(table.items())
    non_cotes = []
    vus = set()
    for phrase in _NON_COTES_BRUTS:
        cle = _fold(phrase)
        if len(cle) < 3 or cle in vus:
            continue
        vus.add(cle)
        non_cotes.append(cle)
    suites: Dict[str, frozenset] = {}
    for phrase, mots in _SUITE_REJETEE_BRUTE.items():
        cle = _fold(phrase)
        if cle not in table:
            continue
        suites[cle] = frozenset(_fold(m) for m in mots if _fold(m))
    return table, items, non_cotes, suites


COMPANY_TO_TICKER, _ALIAS_ITEMS, _NON_COTES, _SUITE_REJETEE = _construire_alias()
_TICKERS_CONNUS = frozenset(COMPANY_TO_TICKER.values())

RATING_GRADES = {
    "AAA":10,"AA+":9.5,"AA":9,"AA-":8.5,
    "A+":8,"A":7.5,"A-":7,
    "BBB+":6.5,"BBB":6,"BBB-":5.5,
    "BB+":5,"BB":4.5,"BB-":4,
    "B+":3.5,"B":3,"B-":2.5,
    "CCC+":2.25,"CCC":2,"CC":1.5,"C":1,"D":0,
}

# ── Helpers réseau ───────────────────────────────────────────────────────────
def _get(url: str, timeout=20) -> Optional[requests.Response]:
    global _last_req
    wait = RATE_LIMIT - (time.time() - _last_req)
    if wait > 0:
        time.sleep(wait)
    _last_req = time.time()
    try:
        r = SESSION.get(url, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        logging.warning(f"GET {url}: {e}")
        return None

def _soup(url: str) -> Optional[BeautifulSoup]:
    r = _get(url)
    if r:
        return BeautifulSoup(r.content, "html.parser")
    return None

# ── Lecture PDF ──────────────────────────────────────────────────────────────
def _resoudre_pdf(pdf_path: str) -> str:
    """Chemin disque d'un PDF. Un chemin relatif est lu sous DATA_DIR."""
    if not pdf_path:
        return ""
    if pdf_path.startswith("http://") or pdf_path.startswith("https://"):
        return ""
    chemin = Path(pdf_path)
    if not chemin.is_absolute():
        chemin = DATA_DIR / chemin
    return str(chemin)


def _read_pdf(path: str) -> str:
    if not HAS_PDF or not os.path.exists(path):
        return ""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join(
                p.extract_text() or "" for p in pdf.pages[:4]
            )[:6000]
    except Exception:
        return ""

def _positions_phrase(padded: str, phrase: str) -> List[int]:
    needle = " " + phrase + " "
    trouvees: List[int] = []
    debut = 0
    while True:
        at = padded.find(needle, debut)
        if at < 0:
            return trouvees
        trouvees.append(at)
        debut = at + len(phrase) + 1


def _rejete_suite(norm: str, alias: str, at: int) -> bool:
    """Le mot ou le pays qui suit l'alias désigne une autre société."""
    phrases = _SUITE_REJETEE.get(alias)
    if not phrases:
        return False
    reste = norm[at + len(alias):].strip()
    if not reste:
        return False
    for phrase in phrases:
        if reste == phrase or reste.startswith(phrase + " "):
            return True
    return False


def _cie_accepte(original: str, origines: List[int], at: int) -> bool:
    """« CIE » en capitales, ou « Cie » collé à Compagnie Ivoirienne.

    « et Cie » et « & Cie » ne sont pas la compagnie d'électricité.
    """
    if at < 0 or at >= len(origines):
        return False
    origine = origines[at]
    m = re.match(r"[A-Za-z]+", original[origine:])
    jeton = m.group(0) if m else ""
    if jeton == "CIE":
        return True
    debut = max(0, origine - 80)
    fin = min(len(original), origine + len(jeton) + 80)
    return re.search(r"Compagnie\s+Ivoirienne", original[debut:fin], re.I) is not None


# Segment sans émetteur nommé (ni coté, ni bloqué).
_SANS_EMETTEUR = object()


def _segment_ticker(text: str) -> Any:
    """Ticker du segment, None si l'émetteur n'est pas coté, _SANS_EMETTEUR sinon.

    À position égale, l'alias le plus long gagne. Sinon le plus tôt dans le texte.
    """
    if not text or not str(text).strip():
        return _SANS_EMETTEUR
    norm, origines = _fold_indexe(text)
    if not norm:
        return _SANS_EMETTEUR
    padded = " " + norm + " "

    bloque_at: Optional[int] = None
    for phrase in _NON_COTES:
        for at in _positions_phrase(padded, phrase):
            if bloque_at is None or at < bloque_at:
                bloque_at = at

    rejetes: List[Tuple[int, int]] = []
    valides: List[Tuple[int, int, str]] = []
    for alias, ticker in _ALIAS_ITEMS:
        for at in _positions_phrase(padded, alias):
            if alias == "cie" and not _cie_accepte(text, origines, at):
                continue
            if _rejete_suite(norm, alias, at):
                rejetes.append((at, len(alias)))
                continue
            valides.append((at, len(alias), ticker))

    gardes: List[Tuple[int, int, str]] = []
    for at, longueur, ticker in valides:
        masque = False
        for r_at, r_len in rejetes:
            if at == r_at and longueur < r_len:
                masque = True
                break
        if not masque:
            gardes.append((at, longueur, ticker))

    if gardes:
        gardes.sort(key=lambda item: (item[0], -item[1]))
        at, _longueur, ticker = gardes[0]
        if bloque_at is not None and bloque_at < at:
            return None
        return ticker
    if bloque_at is not None:
        return None

    for m in re.finditer(r"\b([A-Z]{3,5}C|[A-Z]{4,5})\b", text):
        candidat = m.group(1)
        if candidat in _TICKERS_CONNUS:
            return candidat
    return _SANS_EMETTEUR


# ── Extraire ticker depuis texte ─────────────────────────────────────────────
def _extract_ticker(text: str, titre: Optional[str] = None) -> Optional[str]:
    """Rattache un communiqué à un ticker coté.

    Le titre de l'annonce prime. Sinon le premier nom du texte. À la même
    position, le nom le plus long gagne. Un bout de mot ne compte pas.
    """
    if titre and str(titre).strip():
        decision = _segment_ticker(titre)
        if decision is not _SANS_EMETTEUR:
            return decision
    if text and str(text).strip():
        decision = _segment_ticker(text)
        if decision is not _SANS_EMETTEUR:
            return decision
    return None


_MOIS_FR = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12, "janv": 1, "fevr": 2, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _fold_accents(text: str) -> str:
    t = text.replace("\u2019", "'").replace("\u2018", "'").replace("`", "'")
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _iso_date(jour: int, mois: int, annee: int) -> Optional[str]:
    if not (1 <= jour <= 31 and 1 <= mois <= 12 and 1990 <= annee <= 2100):
        return None
    return "%04d-%02d-%02d" % (annee, mois, jour)


# Une date isolée. Le point est permis (jj.mm.aaaa) ; la phrase s'arrête avant.
_FRAGMENT_DATE = (
    r"(?:"
    r"\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}[./-]\d{1,2}[./-]\d{4}"
    r"|\d{1,2}(?:er)?\s+[A-Za-z]{3,12}\.?\s+\d{4}"
    r"|[A-Za-z]{3,12}\.?\s+\d{4}"
    r")"
)


def _parse_fragment_date(fragment: str) -> Optional[str]:
    if not fragment:
        return None
    f = _fold_accents(fragment)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", f)
    if m:
        return _iso_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", f)
    if m:
        return _iso_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{1,2})(?:er)?\s+([A-Za-z]+)\.?\s+(\d{4})", f)
    if m:
        mois = _MOIS_FR.get(m.group(2).lower().rstrip("."))
        if mois:
            return _iso_date(int(m.group(1)), mois, int(m.group(3)))
    m = re.search(r"(?<![A-Za-z])([A-Za-z]+)\.?\s+(\d{4})", f)
    if m:
        mois = _MOIS_FR.get(m.group(1).lower().rstrip("."))
        if mois:
            annee = int(m.group(2))
            if 1990 <= annee <= 2100:
                dernier = calendar.monthrange(annee, mois)[1]
                return _iso_date(dernier, mois, annee)
    return None


def _extraire_date_validite(text: str) -> Optional[str]:
    """Date de validité du cran, si le communiqué la donne.

    « du X au Y » retient Y. Un mois et une année retiennent le dernier jour.
    """
    if not text:
        return None
    plat = _fold_accents(text)
    motifs = (
        r"(?<![A-Za-z])(?:date\s+de\s+)?validite\s*:?\s*(" + _FRAGMENT_DATE + r")",
        r"valable\s+jusqu[' ]?au\s+(" + _FRAGMENT_DATE + r")",
        r"(?:valable\s+|(?<![A-Za-z])(?:date\s+de\s+)?validite\s*:?\s*)"
        r"du\s+.+?\s+au\s+(" + _FRAGMENT_DATE + r")",
        r"(?<![A-Za-z])echeance\s*:?\s*(" + _FRAGMENT_DATE + r")",
    )
    for motif in motifs:
        m = re.search(motif, plat, re.I)
        if not m:
            continue
        iso = _parse_fragment_date(m.group(1))
        if iso:
            return iso
    return None


def _motif_cran(grade: str) -> str:
    # « + » et « - » ne sont pas des caractères de mot : \b après le signe ne matche jamais.
    # \w (unicode) évite de lire le C de « Côte » comme le cran C.
    # L'apostrophe évite de lire le D de « D'Ivoire » ou « D'OBLIGATIONS ».
    return r"(?<![\w'’])" + re.escape(grade) + r"(?![\w'’])"


def _expr_grade() -> str:
    """Un cran, éventuellement suivi de (WU) ou (SF), sans capturer le suffixe."""
    tokens = sorted(RATING_GRADES, key=len, reverse=True)
    alt = "|".join(re.escape(t) for t in tokens)
    return (
        r"(?<!\w)(" + alt + r")(?!\w)"
        r"(?:\s*\((?:WU|SF)\))*"
    )


# Guillemets et espaces autour d'un cran : de ‘A- ’ à ‘AA- ’, ou de ‘BBB ’à ‘BBB+ ’.
_CITE_CRAN = r"[\s‘’'\"«»]*"


def _note_mouvement(text: str) -> Optional[str]:
    """Cran nouveau dans « de X à Y », « à Y (contre X) », « à Y, de X », « précédemment X ».

    Le groupe 1 est l'ancien cran seulement pour « de X à Y ». Partout ailleurs, c'est le nouveau.
    À défaut, la ligne de tableau « Emetteur/Note de long terme Régionale X ».
    """
    if not text:
        return None
    grade = _expr_grade()
    cite = _CITE_CRAN
    de_a = re.search(
        r"\bde\s+" + cite + grade + cite + r"[àa]" + cite + grade,
        text,
        re.I,
    )
    if de_a:
        return de_a.group(2).upper()
    for motif in (
        r"\b[àa]\s+" + cite + grade + r"\s*\(\s*contre\s+" + cite + grade,
        r"\b[àa]\s+" + cite + grade + r"\s*,\s*de\s+" + cite + grade,
        cite + grade + cite + r"[\(,]\s*pr[ée]c[ée]demment\s+" + cite + grade,
        cite + grade + cite + r".{0,20}?pr[ée]c[ée]dente\s*:?\s+" + cite + grade,
    ):
        m = re.search(motif, text, re.I)
        if m:
            return m.group(1).upper()
    tableau = re.search(
        r"(?:[eé]metteur|note)\s+de\s+long\s+terme\s+r[eé]gionale\s+" + cite + grade,
        text,
        re.I,
    )
    if tableau:
        return tableau.group(1).upper()
    return None


def _fin_ancre_long_terme(text: str) -> Optional[int]:
    """Fin de la première ancre « note de long terme », « long terme » ou « LT »."""
    motifs = (
        r"note\s+de\s+long\s+terme",
        r"long\s+terme",
        r"(?<!\w)LT(?!\w)",
    )
    debut_min = None
    fin = None
    for motif in motifs:
        m = re.search(motif, text, re.I)
        if not m:
            continue
        if debut_min is None or m.start() < debut_min:
            debut_min = m.start()
            fin = m.end()
    return fin


def _suit_mot_note(text: str, debut: int) -> bool:
    """Le cran suit de près « note », « notation » ou « rating »."""
    gauche = text[max(0, debut - 40):debut]
    return re.search(
        r"(?<!\w)(?:notation|rating|note|obtient)(?!\w)[\s:;,\-]*$",
        gauche,
        re.I,
    ) is not None


def _crans_de_legende(text: str, crans: List[Tuple[int, str]]) -> set:
    """Positions d'une échelle (AAA, AA, A, BBB…) : au moins trois crans serrés."""
    legend = set()
    run: List[int] = []
    for i, (debut, grade) in enumerate(crans):
        if not run:
            run = [i]
            continue
        prev = crans[i - 1][0] + len(crans[i - 1][1])
        gap = text[prev:debut]
        if len(gap) <= 8 and re.fullmatch(r"[\s,;/\.…·\-]*", gap or ""):
            run.append(i)
            continue
        if len(run) >= 3:
            legend.update(crans[j][0] for j in run)
        run = [i]
    if len(run) >= 3:
        legend.update(crans[j][0] for j in run)
    return legend


def _choisir_note(text: str) -> Optional[str]:
    """Premier cran après l'ancre de long terme, sinon le premier du texte.

    À la même position, le cran le plus long gagne (A+ plutôt que A, CCC+ plutôt que CCC).
    Sans ancre de long terme, un C, D ou B isolé cède devant le cran qui suit
    « note », « notation » ou « rating ».
    """
    if not text:
        return None
    mouvement = _note_mouvement(text)
    if mouvement:
        return mouvement
    par_pos: Dict[int, Tuple[int, str]] = {}
    for grade in RATING_GRADES:
        for m in re.finditer(_motif_cran(grade), text):
            deja = par_pos.get(m.start())
            if deja is None or len(grade) > deja[0]:
                par_pos[m.start()] = (len(grade), grade)
    if not par_pos:
        return None
    crans = sorted((debut, grade) for debut, (_longueur, grade) in par_pos.items())
    ancre = _fin_ancre_long_terme(text)
    if ancre is not None:
        for debut, grade in crans:
            if debut >= ancre:
                return grade
        return None
    legend = _crans_de_legende(text, crans)
    utiles = [(debut, grade) for debut, grade in crans if debut not in legend] or crans
    if legend:
        for debut, grade in utiles:
            if _suit_mot_note(text, debut):
                return grade
    premier_at, premier = utiles[0]
    if premier in ("C", "D", "B") and not _suit_mot_note(text, premier_at):
        for debut, grade in utiles:
            if _suit_mot_note(text, debut):
                return grade
    return premier


# ── Extraire note depuis texte ───────────────────────────────────────────────
def _notation_retiree(text: str) -> bool:
    """La notation est retirée : ce n'est pas le cran D."""
    if not text:
        return False
    if re.search(r"\bWD\b", text):
        return True
    if re.search(r"\bwithdrawn\b", text, re.I):
        return True
    return re.search(
        r"(?:\bretire\b|\bretir(?:é|e|ée|és|ees)s?\b|\bretrait\b).{0,80}\bnotations?\b"
        r"|\bnotations?\b.{0,50}\bretir",
        text,
        re.I,
    ) is not None


def _libelle_perspective(mot: str) -> Optional[str]:
    brut = _fold_accents(mot).lower()
    if brut.startswith("positiv"):
        return "Positive"
    if brut.startswith("negativ"):
        return "Négative"
    if brut.startswith("stable"):
        return "Stable"
    if "developpement" in brut:
        return "En développement"
    if "evolution" in brut:
        return "En évolution"
    if "surveillance" in brut:
        return "Surveillance"
    return None


def _extraire_perspective(text: str) -> Optional[str]:
    """Perspective seulement si le texte l'attribue, pas si le mot « stable » passe.

    Une liste « positive, stable ou négative » est une légende : elle ne compte pas.
    """
    if not text:
        return None
    mot = (
        r"(?<!\w)(?:positives?|n[ée]gatives?|stables?"
        r"|en\s+d[ée]veloppement|en\s+[eé]volution|sous\s+surveillance)(?!\w)"
    )
    for ancre in re.finditer(r"perspectives?|outlooks?", text, re.I):
        fenetre = text[ancre.end():ancre.end() + 120]
        point = re.search(r"\.\s", fenetre)
        if point and point.start() >= 8:
            fenetre = fenetre[:point.start()]
        trouves = re.findall(mot, fenetre, re.I)
        distincts = set()
        for item in trouves:
            libelle = _libelle_perspective(item)
            if libelle:
                distincts.add(libelle)
        if len(distincts) == 1:
            return distincts.pop()
    return None


def _extract_rating_info(text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "note": None, "perspective": None, "agence": None, "date_validite": None,
    }

    # Agence
    agences = [
        ("Bloomfield", "Bloomfield Investment"),
        ("bloomfield", "Bloomfield Investment"),
        ("GCR", "GCR Ratings"),
        ("Moody", "Moody's"),
        ("S&P", "S&P Global"),
        ("Fitch", "Fitch Ratings"),
        ("RAM Ratings", "RAM Ratings"),
        ("Agusto", "Agusto & Co"),
    ]
    for kw, name in agences:
        if kw in text:
            result["agence"] = name
            break

    if _notation_retiree(text):
        result["note"] = None
        result["statut"] = "retirée"
    else:
        note = _choisir_note(text)
        if note:
            result["note"] = note
            result["score_notation"] = RATING_GRADES[note]

    result["perspective"] = _extraire_perspective(text)

    result["date_validite"] = _extraire_date_validite(text)
    return result


def _ticker_connu(value: Any) -> Optional[str]:
    if value is None:
        return None
    brut = str(value).strip().upper()
    if brut in _TICKERS_CONNUS:
        return brut
    return None


def _date_depuis_nom_pdf(nom: str) -> Optional[str]:
    """20260303_-_notation_….pdf -> 2026-03-03. None si le nom n'a pas ce préfixe."""
    if not nom:
        return None
    base = Path(str(nom).split("?")[0]).name
    m = re.match(r"(20\d{2})(\d{2})(\d{2})", base)
    if not m:
        return None
    annee, mois, jour = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mois <= 12):
        return None
    if jour < 1 or jour > calendar.monthrange(annee, mois)[1]:
        return None
    return _iso_date(jour, mois, annee)


def _date_annonce(date: Any, *noms: str) -> Optional[str]:
    """Date de l'annonce, sinon le préfixe AAAAMMJJ du nom de PDF."""
    if date is not None and str(date).strip():
        return str(date).strip()
    for nom in noms:
        trouve = _date_depuis_nom_pdf(nom or "")
        if trouve:
            return trouve
    return None


def _document_hors_emetteur(texte: str, titre: str = "", source: str = "") -> bool:
    """Titrisation, FCTC, RMBS ou emprunt obligataire : pas la note de la société cotée.

    Un communiqué qui note l'émetteur et, en plus, son emprunt obligataire est conservé.
    Le cartouche GCR « Responsable de groupe – Titrisation » est vers le caractère 900 :
    on ne regarde que le titre, le nom du PDF et les 400 premiers caractères.
    """
    nom = Path(str(source).split("?")[0]).name if source else ""
    tete = (texte or "")[:400]
    zones = "\n".join(p for p in (titre or "", nom, source or "", tete) if p)
    if not zones.strip():
        return False
    # « _ » colle les mots dans un nom de fichier : fctc_ept n'a pas de frontière \b.
    if re.search(
        r"(?<![A-Za-z])(?:FCTC|RMBS)(?![A-Za-z])|titrisations?",
        zones,
        re.I,
    ):
        return True
    if re.search(
        r"emprunts?\s+obligataires?|[eé]missions?\s+obligataires?|\btranches?\b",
        zones,
        re.I,
    ):
        if not re.search(
            r"notes?\s+d['’]?\s*[eé]metteur|[eé]metteur\s+de\s+long\s+terme",
            zones,
            re.I,
        ):
            return True
    return False


def _choisir_ticker(texte: str, indice: Any = None, titre: Optional[str] = None) -> Optional[str]:
    """Ticker lu dans le titre, sinon dans le texte. L'indice ne sert que si les deux sont vides."""
    if (titre and str(titre).strip()) or (texte and str(texte).strip()):
        return _extract_ticker(texte or "", titre=titre)
    return _ticker_connu(indice)


def _dedoublonner_notations(notations: List[Dict]) -> List[Dict]:
    """Une même source ne compte qu'une fois : ticker, agence, note, url ou date."""
    vus = set()
    gardes: List[Dict] = []
    for fiche in notations:
        source = fiche.get("source_url") or fiche.get("date") or ""
        cle = (fiche.get("ticker"), fiche.get("agence"), fiche.get("note"), source)
        if cle in vus:
            continue
        vus.add(cle)
        gardes.append(fiche)
    return gardes


def _fiche_notation(
    corps: str,
    contexte: str,
    ticker: str,
    date: Optional[str],
    source_url: str,
    note_repli: Any = None,
) -> Dict[str, Any]:
    """Entrée au format historique de brvm_ratings.json, plus date_validite."""
    info = _extract_rating_info(contexte or corps or "")
    retiree = info.get("statut") == "retirée"
    if retiree:
        # /api/ratings ne renvoie que les lignes qui ont une note : le D n'est pas affiché.
        note = None
        score = None
    else:
        note = info.get("note") or note_repli
        score = info.get("score_notation")
        if note != info.get("note"):
            score = RATING_GRADES.get(note) if isinstance(note, str) else None
    fiche = {
        "ticker": ticker,
        "agence": info.get("agence"),
        "note": note,
        "score_notation": score,
        "perspective": info.get("perspective"),
        "date": date,
        "date_validite": info.get("date_validite"),
        "source_url": source_url or "",
        "resume": (corps or "")[:500],
    }
    if retiree:
        fiche["statut"] = "retirée"
    return fiche

# ═══════════════════════════════════════════════════════════════════════════════
# A) NOTATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def scrape_ratings() -> List[Dict]:
    """Parse PDFs de notations existants + télécharge nouveaux."""
    ratings: Dict[str, Dict] = {}   # keyed by pdf_path

    # 1. Exploiter brvm_announcements.json existant
    annc_path = DATA_DIR / "brvm_announcements.json"
    if annc_path.exists():
        with open(annc_path, encoding="utf-8") as f:
            annc = json.load(f)
        for item in annc.get("notations", []):
            pdf = item.get("pdf_path") or ""
            url = item.get("source_url") or ""
            key = pdf or url
            if not key or key in ratings:
                continue
            # Lire PDF si disponible (chemin relatif : sous DATA_DIR)
            pdf_disque = _resoudre_pdf(pdf)
            text = _read_pdf(pdf_disque) if pdf_disque else ""
            if not text and item.get("contenu"):
                text = item["contenu"]
            titre = item.get("titre") or ""
            contexte = " ".join(p for p in (titre, text) if p)
            if _document_hors_emetteur(text, titre, pdf or url):
                continue
            ticker = _choisir_ticker(text, item.get("ticker"), titre=titre)
            # Émetteur non coté ou illisible : pas d'entrée ticker null dans le fichier.
            if not ticker:
                continue
            ratings[key] = _fiche_notation(
                text, contexte, ticker,
                _date_annonce(item.get("date"), pdf, url),
                url, item.get("notation"),
            )

    # 2. Scraper nouvelles notations depuis brvm.org
    logging.info("Scraping notations BRVM...")
    for page in range(0, 3):
        url = f"https://www.brvm.org/fr/emetteurs/type-annonces/notations-financieres?page={page}"
        soup = _soup(url)
        if not soup:
            break
        pdf_links = [
            a.get("href", "")
            for a in soup.find_all("a", href=True)
            if ".pdf" in a.get("href", "").lower()
               and "default/files" in a.get("href", "")
        ]
        if not pdf_links:
            break
        for pdf_url in pdf_links:
            if pdf_url in {v.get("source_url","") for v in ratings.values()}:
                continue
            # Télécharger PDF si pas déjà présent
            fname = pdf_url.split("/")[-1]
            local = DOCS_DIR / "notations" / "UNKNOWN" / fname
            local.parent.mkdir(parents=True, exist_ok=True)
            text = ""
            if not local.exists():
                r = _get(pdf_url)
                if r:
                    local.write_bytes(r.content)
                    logging.info(f"  ↓ {fname}")
            text = _read_pdf(str(local))
            if _document_hors_emetteur(text, "", pdf_url):
                continue
            ticker = _choisir_ticker(text, None)
            if not ticker:
                continue
            ratings[pdf_url] = _fiche_notation(
                text, text, ticker, _date_annonce(None, fname, pdf_url), pdf_url, None,
            )
        # Vérifier pagination
        next_links = [a for a in soup.find_all("a", href=True)
                      if f"page={page+1}" in a.get("href","")]
        if not next_links:
            break

    result = _dedoublonner_notations(list(ratings.values()))
    logging.info(f"Notations: {len(result)} entrées")
    return result

# ═══════════════════════════════════════════════════════════════════════════════
# B) STATISTIQUES DE MARCHÉ
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_num(s: str) -> Optional[float]:
    """Convertit '16 101 667 934 513' → 16101667934513.0"""
    s = re.sub(r"[^\d.,]", "", s.replace(" ", ""))
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def scrape_market_stats() -> Dict:
    """Récupère stats de marché depuis brvm.org + market_cache.json local."""
    stats: Dict[str, Any] = {"date": datetime.date.today().isoformat()}

    # 1. Depuis market_cache.json local
    mc_path = DATA_DIR / "market_cache.json"
    if mc_path.exists():
        try:
            with open(mc_path, encoding="utf-8") as f:
                mc = json.load(f)
            stats["brvm_c"]    = mc.get("brvm_c")
            stats["brvm_30"]   = mc.get("brvm_30")
            stats["brvm_pres"] = mc.get("brvm_pres")
        except Exception:
            pass

    # 2. Scraper brvm.org pour données fraîches
    soup = _soup("https://www.brvm.org/fr")
    if soup:
        # Table "Activités du marché"
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
                if len(cells) >= 2:
                    label = cells[0].lower()
                    val   = cells[1] if len(cells) > 1 else ""
                    if "transactions" in label or "volume" in label:
                        v = _parse_num(val)
                        if v:
                            stats["volume_total_fcfa"] = v
                    elif "capitalisation actions" in label or "cap. actions" in label:
                        v = _parse_num(val)
                        if v:
                            stats["capitalisation_actions_fcfa"] = v
                    elif "capitalisation" in label and "oblig" in label:
                        v = _parse_num(val)
                        if v:
                            stats["capitalisation_obligations_fcfa"] = v
                    elif "brvm-c" in label:
                        m = re.search(r"[\d.,]+", val)
                        if m:
                            stats["brvm_c"] = float(m.group().replace(",","."))
                    elif "brvm-30" in label:
                        m = re.search(r"[\d.,]+", val)
                        if m:
                            stats["brvm_30"] = float(m.group().replace(",","."))

    # 3. Indices sectoriels depuis /fr/indices
    soup_idx = _soup("https://www.brvm.org/fr/indices")
    if soup_idx:
        secteur_indices: Dict[str, float] = {}
        tables = soup_idx.find_all("table")
        for table in tables:
            for row in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
                if len(cells) >= 2 and cells[0]:
                    v = _parse_num(cells[1])
                    if v and any(c.isdigit() for c in cells[1]):
                        secteur_indices[cells[0][:40]] = v
        if secteur_indices:
            stats["indices_sectoriels"] = secteur_indices

    logging.info(f"Market stats: {list(stats.keys())}")
    return stats

# ═══════════════════════════════════════════════════════════════════════════════
# C) DONNÉES FONDAMENTALES
# ═══════════════════════════════════════════════════════════════════════════════

TICKER_SLUGS: Dict[str, str] = {
    "ABJC":"air-burkina","BICB":"bic-benin","BICC":"bici-ci","BNBC":"baci",
    "BOAB":"boa-benin","BOABF":"boa-burkina-faso","BOAC":"boa-cote-divoire",
    "BOAM":"boa-mali","BOAN":"boa-niger","BOAS":"boa-senegal",
    "CABC":"sicable-ci","CBIBF":"coris-bank-international","CFAC":"cfao-motors-ci",
    "CIEC":"cie","ECOC":"ecobank-ci","ETIT":"ecobank-transnational",
    "FTSC":"filtisac","LNBB":"lonab","NEIC":"nei-ceda",
    "NSBC":"nsia-banque","NTLC":"nestle-ci","ONTBF":"onatel",
    "ORAC":"orange-ci","ORGT":"oragroup","PALC":"palmci",
    "PRSC":"prestige-ci","SAFC":"safca","SCRC":"sucrivoire",
    "SDCC":"sodeci","SDSC":"sds-ci","SEMC":"setao-ci",
    "SGBC":"sgbc","SHEC":"vivo-energy-ci","SIBC":"sibc",
    "SICC":"sicogi","SIVC":"sivop","SLBC":"solibra",
    "SMBC":"soacii","SNTS":"sonatel","SOGC":"sogb",
    "SPHC":"saph","STAC":"setaci","STBC":"sitab",
    "TTLC":"total-ci","TTLS":"total-senegal",
    "UNLC":"unilever-ci","UNXC":"uniwax",
}

def scrape_emetteur(ticker: str, slug: str) -> Dict[str, Any]:
    """Scrape la page emetteur BRVM pour un ticker."""
    url = f"https://www.brvm.org/fr/emetteurs/{slug}"
    soup = _soup(url)
    result: Dict[str, Any] = {"ticker": ticker, "source_url": url}
    if not soup:
        return result

    text = soup.get_text(" ", strip=True)

    # Capital social
    m = re.search(r"[Cc]apital\s+(?:social)?[^0-9]*([0-9][0-9 .,]+)\s*(?:F\.?C\.?F\.?A|FCFA|CFA|F CFA)", text)
    if m:
        v = _parse_num(m.group(1))
        if v:
            result["capital_social_fcfa"] = v

    # Nombre d'actions
    m = re.search(r"[Nn]ombre\s+d.actions?[^0-9]*([0-9][0-9 .,]+)", text)
    if m:
        v = _parse_num(m.group(1))
        if v:
            result["nb_actions"] = v

    # Date d'introduction
    m = re.search(r"[Ii]ntroduction[^0-9]*(\d{2}/\d{2}/\d{4}|\d{4})", text)
    if m:
        result["date_introduction"] = m.group(1)

    # Flottant
    m = re.search(r"[Ff]lottant[^0-9%]*([0-9,.]+)\s*%?", text)
    if m:
        result["flottant_pct"] = _parse_num(m.group(1))

    # Secteur
    m = re.search(r"[Ss]ecteur[^:]*:\s*([^\n·|<]{5,60})", text)
    if m:
        result["secteur_detail"] = m.group(1).strip()

    # Capitalisation depuis tables
    tables = soup.find_all("table")
    for table in tables:
        for row in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
            if len(cells) >= 2:
                label = cells[0].lower()
                val   = cells[1]
                if "capitalisation" in label:
                    v = _parse_num(val)
                    if v:
                        result["capitalisation_fcfa"] = v
                elif "actions" in label and "nombre" in label:
                    v = _parse_num(val)
                    if v:
                        result["nb_actions"] = v

    return result

def scrape_fundamentals(tickers: Optional[List[str]] = None) -> Dict[str, Dict]:
    """Scrape données fondamentales pour tous les tickers (ou liste fournie)."""
    target = tickers or list(TICKER_SLUGS.keys())
    result: Dict[str, Dict] = {}

    # Charger données existantes pour merge
    if FUNDAMENT_PATH.exists():
        try:
            with open(FUNDAMENT_PATH, encoding="utf-8") as f:
                result = json.load(f)
        except Exception:
            pass

    # Enrichir depuis live_cache (capitalisation si dispo)
    lc_path = DATA_DIR / "live_cache.json"
    if lc_path.exists():
        try:
            with open(lc_path, encoding="utf-8") as f:
                lc = json.load(f)
            for item in lc:
                t = item.get("ticker","")
                if t:
                    if t not in result:
                        result[t] = {"ticker": t}
                    result[t].setdefault("prix_actuel", item.get("price"))
                    result[t].setdefault("variation_pct", item.get("change_pct"))
        except Exception:
            pass

    # Scraper pages emetteurs
    for ticker in target:
        slug = TICKER_SLUGS.get(ticker)
        if not slug:
            continue
        logging.info(f"  Fondamentaux {ticker}...")
        data = scrape_emetteur(ticker, slug)
        # Merge avec existant
        existing = result.get(ticker, {})
        existing.update({k: v for k, v in data.items() if v is not None})
        result[ticker] = existing

    logging.info(f"Fondamentaux: {len(result)} tickers")
    return result

def _compter_notations(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            ancien = json.load(f)
    except Exception:
        logging.warning("Notations illisibles dans %s", path)
        return 0
    if isinstance(ancien, list):
        return len(ancien)
    return 0


def _ecrire_notations(path, nouvelles, force: bool = False) -> bool:
    """Écrit la liste atomiquement. Refuse le vide ou moins de la moitié, sauf --force."""
    path = Path(path)
    if nouvelles is None:
        nouvelles = []
    avant = _compter_notations(path)
    apres = len(nouvelles)
    logging.info("Notations : %d avant, %d après", avant, apres)
    if not force and (apres == 0 or (avant > 0 and apres * 2 < avant)):
        logging.warning(
            "Écriture refusée (%d → %d). Relancer avec --force pour écraser.",
            avant, apres,
        )
        return False
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(nouvelles, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp), str(path))
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="BRVM Market Data Scraper")
    parser.add_argument("--ratings-only",     action="store_true")
    parser.add_argument("--market-only",      action="store_true")
    parser.add_argument("--fundamentals-only",action="store_true")
    parser.add_argument("--ticker", default=None, help="Un seul ticker pour --fundamentals-only")
    parser.add_argument(
        "--force", action="store_true",
        help="Écrase brvm_ratings.json même si la nouvelle liste est vide ou trop courte",
    )
    args = parser.parse_args()

    LOG_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)

    run_all = not (args.ratings_only or args.market_only or args.fundamentals_only)

    if run_all or args.ratings_only:
        print("\n━━━ A) Notations ━━━")
        ratings = scrape_ratings()
        if _ecrire_notations(RATINGS_PATH, ratings, force=args.force):
            print(f"  → {RATINGS_PATH} ({len(ratings)} notations)")
        else:
            print(f"  → écriture refusée, fichier conservé ({RATINGS_PATH})")
            sys.exit(1)

    if run_all or args.market_only:
        print("\n━━━ B) Statistiques de marché ━━━")
        stats = scrape_market_stats()
        # Historiser
        history: List[Dict] = []
        if MARKET_PATH.exists():
            try:
                with open(MARKET_PATH, encoding="utf-8") as f:
                    old = json.load(f)
                if isinstance(old, list):
                    history = old
                else:
                    history = [old]
            except Exception:
                pass
        # Ne pas dupliquer si même date
        today = stats["date"]
        history = [h for h in history if h.get("date") != today]
        history.append(stats)
        history = history[-365:]   # garder 1 an max
        with open(MARKET_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        print(f"  → {MARKET_PATH} (today: {today})")

    if run_all or args.fundamentals_only:
        print("\n━━━ C) Données fondamentales ━━━")
        tickers = [args.ticker.upper()] if args.ticker else None
        funds = scrape_fundamentals(tickers)
        with open(FUNDAMENT_PATH, "w", encoding="utf-8") as f:
            json.dump(funds, f, ensure_ascii=False, indent=2)
        print(f"  → {FUNDAMENT_PATH} ({len(funds)} tickers)")

    print("\n✓ Terminé\n")

if __name__ == "__main__":
    main()
