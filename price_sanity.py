"""price_sanity.py — Sas prix avant scoring (politique décidée v7).
live → sinon dernier bon prix connu (réf), jamais 0 ; rejet si |live/réf-1|>20% ;
quarantaine si aucun prix. BRVM plafonne à ±7,5%/j, donc >20% = donnée fausse."""
MAX_DEV = 0.20

def resolve_price(live_price, ref_price, boc_last=None):
    """Vote 2-sur-3 entre live / boc / hist (ref_price = dernier prix historique).
    Un prix n'est 'verified' que si le live est confirmé par une autre source à ±20%.
    BRVM plafonne à ±7,5%/j donc >20% d'écart = donnée fausse quelque part."""
    def _f(x):
        try:
            x = float(x)
            return x if x > 0 else None
        except (TypeError, ValueError):
            return None

    def _ok(a, b):
        return a is not None and b is not None and abs(a / b - 1) <= MAX_DEV

    live, hist, boc = _f(live_price), _f(ref_price), _f(boc_last)

    # 1. Live confirmé par au moins une référence → prix officiel
    if live is not None and (_ok(live, boc) or _ok(live, hist)):
        return {"price": live, "source": "live", "verified": True}
    # 2. Live contredit mais les 2 réfs concordent → le live est l'intrus
    if live is not None and _ok(boc, hist):
        return {"price": hist, "source": "repli_aberration", "verified": False}
    # 3. Live absent, les 2 réfs concordent → repli sur le plus frais (hist)
    if live is None and _ok(boc, hist):
        return {"price": hist, "source": "repli", "verified": False}
    # 4. Une seule source au monde, rien pour la contredire → affichée non vérifiée
    cands = [c for c in (live, hist, boc) if c is not None]
    if len(cands) == 1:
        src = "live" if live is not None else "repli"
        return {"price": cands[0], "source": src, "verified": False}
    # 5. Plusieurs sources, toutes discordantes (ou aucune) → quarantaine
    if not cands:
        return {"price": None, "source": "quarantaine", "verified": False}
    return {"price": None, "source": "quarantaine", "verified": False}


import json as _json
import time as _time
import os as _os
from paths import DATA_DIR

_REF_CACHE = {"t": 0.0, "refs": {}}

def load_reference_prices():
    try:
        boc = _json.load(open(_os.path.join(DATA_DIR, 'boc_data.json')))
    except Exception:
        boc = {}
    try:
        from price_history_builder import load_history
        ph = load_history()
    except Exception:
        ph = {}
    refs = {}
    for t in set(boc) | set(ph):
        b = boc.get(t) or {}
        pts = ph.get(t) or []
        last = pts[-1] if pts else {}
        refs[t] = {
            "boc":  b.get("cours_clot") if isinstance(b, dict) else None,
            "hist": last.get("price") if isinstance(last, dict) else None,
        }
    return refs

def get_reference_prices(ttl=300):
    now = _time.time()
    if now - _REF_CACHE["t"] > ttl or not _REF_CACHE["refs"]:
        _REF_CACHE["refs"] = load_reference_prices()
        _REF_CACHE["t"] = now
    return _REF_CACHE["refs"]
