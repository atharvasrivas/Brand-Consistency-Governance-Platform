"""Fact-sheet assistant. Produces DRAFT items only. Nothing here is saved or becomes an approved fact on its own:
every item is status "draft" and marked generated until an Owner approves it in the editor."""
from ..auth import ApiError
from . import brands as B

BRAND_QUESTIONS = [
    {"id": "description", "label": "What does the brand do, and for whom?", "hint": "A short description."},
    {"id": "heritage", "label": "Heritage and history", "hint": "Founding story, milestones."},
    {"id": "personality", "label": "Brand personality", "hint": "Comma-separated, e.g. warm, precise, bold."},
    {"id": "toneGuidance", "label": "How should the brand sound?", "hint": "Tone and voice guidance."},
    {"id": "previousNames", "label": "Previous brand names", "hint": "One per line. Leave empty if none."},
    {"id": "approvedClaims", "label": "Claims you can make, with their source", "hint": "One per line: claim | source"},
    {"id": "restrictedClaims", "label": "Claims that must NOT be made", "hint": "One per line: claim | reason"},
    {"id": "terminology", "label": "Preferred wording", "hint": "One per line: avoid -> prefer"},
]
PRODUCT_QUESTIONS = [
    {"id": "description", "label": "What is the product?", "hint": "Short description."},
    {"id": "previousNames", "label": "Previous product names", "hint": "One per line. Leave empty if none."},
    {"id": "specs", "label": "Specifications", "hint": "One per line: name: value | source (e.g. Capacity: 1.7 litres | spec sheet)"},
    {"id": "approvedClaims", "label": "Claims you can make, with evidence", "hint": "One per line: claim | evidence"},
    {"id": "restrictedClaims", "label": "Claims that must NOT be made", "hint": "One per line: claim | reason"},
    {"id": "terminology", "label": "Product-specific wording", "hint": "One per line: avoid -> prefer"},
]
DRAFT_NOTE = "Draft — verify before approval"


def questions(scope):
    return PRODUCT_QUESTIONS if scope == "product" else BRAND_QUESTIONS


def _lines(v):
    return [ln.strip(" -•\t") for ln in str(v or "").splitlines() if ln.strip(" -•\t")]


def _parse(answers, scope):
    a = {k: str(v or "") for k, v in (answers or {}).items()}
    out = {k: B.s(a.get(k), 3000) for k in ("description", "heritage", "toneGuidance") if a.get(k, "").strip()}
    if a.get("personality", "").strip():
        out["personality"] = [p.strip() for p in a["personality"].replace("\n", ",").split(",") if p.strip()]
    if a.get("previousNames", "").strip():
        out["previousNames"] = _lines(a["previousNames"])
    for key, field, sep in (("approvedClaims", "text", "|"), ("restrictedClaims", "text", "|")):
        items = []
        for ln in _lines(a.get(key)):
            t, _, rest = ln.partition(sep)
            if t.strip():
                items.append({"text": t.strip(), ("source" if key == "approvedClaims" else "reason"): rest.strip()})
        if items:
            out[key] = items
    terms = []
    for ln in _lines(a.get("terminology")):
        x, _, y = ln.partition("->")
        if x.strip() and y.strip():
            terms.append({"avoid": x.strip(), "prefer": y.strip()})
    if terms:
        out["terminology"] = terms
    specs = []
    for ln in _lines(a.get("specs")):
        head, _, src = ln.partition("|")
        n, _, v = head.partition(":")
        if n.strip() and v.strip():
            specs.append({"name": n.strip(), "value": v.strip(), "source": src.strip()})
    if specs:
        out["specs"] = specs
    return out


def _mark(draft, origin):
    for k in ("approvedClaims", "restrictedClaims", "terminology", "specs"):
        for it in draft.get(k, []) or []:
            it["status"], it["generated"], it["id"] = "draft", True, B.nid("i")
            if k in ("approvedClaims", "specs") and not it.get("source"):
                it["source"] = f"{origin} (unverified)"
    return draft


def make_draft(ai, scope, name, answers, document_text):
    if scope not in ("brand", "product"):
        raise ApiError(422, "scope must be brand or product")
    parsed, used_ai, origin = _parse(answers, scope), False, "Owner answer"
    model = ai.draft_factsheet(scope, name, {k: str(v)[:3000] for k, v in (answers or {}).items()}, document_text) if (ai.enabled and (document_text or answers)) else None
    if model:
        used_ai, origin = True, "AI draft from your input"
        for k, v in model.items():
            if v and k not in parsed:
                parsed[k] = v
    elif document_text and not ai.enabled:
        note = "Reading documents needs the AI service, which is not configured. Your typed answers were used; the document text was not."
        return {"draft": _mark(parsed, origin), "usedAI": False, "notice": DRAFT_NOTE, "warning": note}
    if scope == "product" and "specs" not in parsed and "approvedClaims" not in parsed and not parsed:
        raise ApiError(422, "Answer at least one question first")
    return {"draft": _mark(parsed, origin), "usedAI": used_ai, "notice": DRAFT_NOTE}
