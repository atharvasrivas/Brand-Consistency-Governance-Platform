"""Visual brand-consistency review of an uploaded image or advertisement.

An attached image is never silently accepted. Either it is analysed by the vision model against the selected brand's approved
visual identity (colours, fonts, logo, guidelines, approved reference images), or the person is told exactly why it was not and
a finding routes the image to a human reviewer. AI visual findings are never mandatory and never claim a source the profile
does not contain. A text brief for a corrected asset is offered, not a generated image; anything produced from it still has to be
checked against the approved assets and approved by a person.
"""
from ..ai.gemini import IMAGE_MIMES, GeminiError
from ..engine import review as engine

NO_IDENTITY = ("no approved visual identity (colours, fonts, logo, reference images or visual guidelines) is set for this brand. "
               "Add them in Brand Profile so uploaded images can be compared with the brand")


def references(store, ctx, limit=3, max_bytes=600_000):
    """Approved logo / product image / image assets of THIS brand and product, as (base64, mime, label)."""
    names = {a["assetId"]: a["name"] for a in ctx.get("assetRefs", [])}
    order = [ctx.get("logoAssetId"), ctx.get("imageAssetId")] + [a["assetId"] for a in ctx.get("assetRefs", [])]
    out, seen = [], set()
    for aid in order:
        if not aid or aid in seen or len(out) >= limit:
            continue
        seen.add(aid)
        a = store.get("asset", aid)
        if not a or a.get("mime") not in IMAGE_MIMES or a.get("size", 0) > max_bytes:
            continue
        label = names.get(aid) or a.get("name") or "asset"
        if aid == ctx.get("logoAssetId"):
            label = f"approved logo: {label}"
        out.append((a["data"], a["mime"], label))
    return out


def _unanalysed(image, reason, status):
    f = {"id": "IMG-UNANALYSED", "key": "IMG-UNANALYSED|image", "ruleId": "IMG-UNANALYSED", "label": "Image not visually analysed", "category": "Visual identity",
         "severity": "warning", "strictness": "flexible", "kind": "advice", "scope": "image", "quote": image.get("name") or "uploaded image",
         "suggestion": "A person must check the logo, colours, typography and product imagery by eye before this is approved.",
         "why": f"The image was not visually analysed because {reason}. Only its file name, alt text and declared fonts were checked.",
         "source": {"doc": "Platform checks", "ref": "Visual analysis"}, "confidence": 1.0, "needsHuman": True, "occurrences": 1}
    return [f], {"status": status, "reason": reason}


def review_image(ai, store, image, ctx, content, meta):
    """Returns (findings, analysis). `analysis` is None when there is no image."""
    if not image:
        return [], None
    if image.get("unsupported"):
        return _unanalysed(image, f"images of type {image['unsupported']} cannot be analysed (use PNG, JPEG, WebP or GIF)", "unsupported")
    if not image.get("data"):
        return _unanalysed(image, "the image itself was not sent with the request (only its details were)", "not_sent")
    if not ai.enabled:
        return _unanalysed(image, "the Gemini API key is not configured on the server", "unavailable")
    if not ctx.get("hasVisual"):
        return _unanalysed(image, NO_IDENTITY, "no_identity")
    refs = references(store, ctx)
    try:
        res = ai.analyse_image(image["data"], image["mime"], ctx, content, meta, refs)
    except GeminiError as e:
        return _unanalysed(image, f"the vision request failed: {e.message}", "failed")
    analysis, findings = res["analysis"], res["findings"]
    det = analysis["detected"].get("textInImage", "").strip()
    if det and not (image.get("textInImage") or "").strip() and ctx.get("hasApproved"):
        # text the model read from the picture goes through the same fact / terminology / claim rules as the copy
        for f in engine.review("", meta, {**{k: v for k, v in image.items() if k != "data"}, "textInImage": det}, ctx):
            if f["key"].startswith("img-"):
                f["label"] = f["label"].replace("(in image)", "(read from the image)")
                findings.append(f)
    analysis["model"] = ai.model
    return findings, analysis
