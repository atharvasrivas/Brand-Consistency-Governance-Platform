"""Clearly labelled sample data so the product can be tried without typing a whole profile. Owner-triggered, never automatic.
The brand and product are fictional and marked demo; no people are created."""
from . import brands as B

BRAND = {
    "name": "Sample Brand (demo data)", "description": "A fictional kitchenware company used to try the platform.", "heritage": "Sample data, not a real company.",
    "personality": ["practical", "friendly"], "toneGuidance": "Plain, friendly and practical. No hype.",
    "approvedClaims": [{"text": "Designed for everyday home cooking", "source": "Sample brand guide"}],
    "restrictedClaims": [{"text": "cures colds", "reason": "Health claims are not allowed."}],
    "terminology": [{"avoid": "cheap", "prefer": "affordable", "strict": False, "source": "Sample brand guide"}],
    "colours": [{"name": "Sample Blue", "hex": "#2563EB"}, {"name": "Sample Ink", "hex": "#111827"}], "fonts": ["Inter"],
}
PRODUCT = {
    "name": "Sample Kettle (demo data)", "previousNames": ["Sample Pot"], "description": "A 1.7 litre electric kettle.",
    "specs": [{"name": "Capacity", "value": "1.7 litres", "source": "Sample spec sheet"}, {"name": "Boil time", "value": "3 minutes", "source": "Sample spec sheet"}],
    "approvedClaims": [{"text": "Boils a full kettle in about 3 minutes", "source": "Sample spec sheet"}],
    "restrictedClaims": [{"text": "boils in 30 seconds", "reason": "Not supported by testing."}],
}


def load(store, user):
    for b in store.list("brand"):
        if b.get("demo"):
            return b
    b = B.save_brand(store, user, BRAND)
    b["demo"] = True
    store.put("brand", b["id"], b)
    store.put("brand_version", f"{b['id']}:{b['version']}", b)
    p = B.save_product(store, user, b["id"], PRODUCT)
    p["demo"] = True
    store.put("product", p["id"], p)
    store.put("product_version", f"{p['id']}:{p['version']}", p)
    return b
