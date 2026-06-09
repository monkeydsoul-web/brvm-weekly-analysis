"""price_sanity.py — Sas prix avant scoring (politique décidée v7).
live → sinon dernier bon prix connu (réf), jamais 0 ; rejet si |live/réf-1|>20% ;
quarantaine si aucun prix. BRVM plafonne à ±7,5%/j, donc >20% = donnée fausse."""
MAX_DEV = 0.20

def resolve_price(live_price, ref_price, boc_last=None):
    ref = None
    for c in (boc_last, ref_price):
        try:
            if c and float(c) > 0:
                ref = float(c); break
        except (TypeError, ValueError):
            pass
    lp = None
    try:
        if live_price and float(live_price) > 0:
            lp = float(live_price)
    except (TypeError, ValueError):
        lp = None
    if lp is not None and ref is not None and abs(lp / ref - 1) > MAX_DEV:
        return {"price": ref, "source": "repli_aberration", "verified": False}
    if lp is not None:
        return {"price": lp, "source": "live", "verified": True}
    if ref is not None:
        return {"price": ref, "source": "repli", "verified": False}
    return {"price": None, "source": "quarantaine", "verified": False}


import json as _json
import time as _time

_REF_CACHE = {"t": 0.0, "refs": {}}

def load_reference_prices():
    try:
        boc = _json.load(open('data/boc_data.json'))
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
