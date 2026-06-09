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
