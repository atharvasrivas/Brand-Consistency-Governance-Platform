"""Analytics computed only from stored submissions. Nothing is sample data."""
from collections import Counter, defaultdict
from datetime import datetime

from . import governance


def compute(subs, brand_id=None, product_id=None):
    if brand_id:
        subs = [s for s in subs if s.get("brandId") == brand_id]
    if product_id:
        subs = [s for s in subs if s.get("productId") == product_id]
    all_subs = subs
    subs = [{**s, "status": "submitted" if s["status"] == "in_review" else s["status"]} for s in subs]
    n_draft = sum(1 for s in subs if s["status"] == "draft")
    subs = governance.live(subs)  # drafts are private work in progress: never counted
    by_status = Counter(s["status"] for s in subs)
    pending = by_status["submitted"] + by_status["under_review"] + by_status["resubmitted"]
    rules = defaultdict(lambda: {"count": 0, "submissions": set(), "category": ""})
    for s in subs:
        for f in s["findings"]:
            if f.get("category") == "Content patterns":
                continue
            key = f.get("guideline") or f.get("source") or f.get("label")
            key = key if isinstance(key, str) else (key.get("text") or key.get("name") or str(key.get("id", "")) if isinstance(key, dict) else str(key))
            r = rules[key]
            r["count"] += f.get("occurrences") or 1
            r["submissions"].add(s["id"])
            r["category"] = f.get("category") or ""
    decided = [s for s in subs if s["status"] in ("approved", "rejected", "changes_requested") or len(s["versions"]) > 1]
    first_time = [s for s in subs if s["status"] == "approved" and len(s["versions"]) == 1]
    # first-time approval = approved on the first version without being sent back, among submissions that have had a decision or a revision
    first_time = [s for s in first_time if not any("Requested changes" in a.get("text", "") for a in s.get("activity", []))]
    ever_changes = [s for s in subs if len(s["versions"]) > 1 or s["status"] in ("changes_requested", "rejected")]
    rec = defaultdict(lambda: {"count": 0, "submissions": set(), "category": "", "severity": "suggestion"})
    cats, brands = Counter(), {}
    rank = {"critical": 3, "warning": 2, "suggestion": 1}
    for s in subs:
        b = brands.setdefault((s.get("brandId"), s.get("productId")), {"brandId": s.get("brandId"), "brandName": s.get("brandName"), "productId": s.get("productId"),
                                                                       "productName": s.get("productName"), "submissions": 0, "approved": 0, "changesOrRejected": 0, "issues": 0})
        b["submissions"] += 1
        b["approved"] += s["status"] == "approved"
        b["changesOrRejected"] += s["status"] in ("changes_requested", "rejected")
        for f in s["findings"]:
            if f.get("category") == "Content patterns":
                continue
            n = f.get("occurrences") or 1
            r = rec[f["label"]]
            r["count"] += n
            r["submissions"].add(s["id"])
            r["category"] = f.get("category")
            if rank.get(f.get("severity"), 0) > rank.get(r["severity"], 0):
                r["severity"] = f["severity"]
            cats[f.get("category")] += n
            b["issues"] += n
    weeks = defaultdict(lambda: {"submissions": 0, "approved": 0, "changes": 0, "issues": 0})
    corrections, reviewers, by_type = Counter(), Counter(), defaultdict(lambda: {"submissions": 0, "issues": 0})
    for s in subs:
        y, w, _ = datetime.fromisoformat(s["createdAt"].replace("Z", "+00:00")).isocalendar()
        wk = weeks[f"{y}-W{w:02d}"]
        wk["submissions"] += 1
        wk["approved"] += s["status"] == "approved"
        wk["changes"] += s["status"] in ("changes_requested", "rejected")
        n_issues = sum(f.get("occurrences") or 1 for f in s["findings"] if f.get("category") != "Content patterns")
        wk["issues"] += n_issues
        by_type[s.get("type") or "other"]["submissions"] += 1
        by_type[s.get("type") or "other"]["issues"] += n_issues
        for f in s["findings"]:
            if f.get("status") == "accepted":
                corrections[f["label"]] += 1
        for a in s.get("activity", []):
            if any(k in a.get("text", "") for k in ("Approved", "Requested changes", "Rejected")):
                reviewers[a["by"]] += 1
    recurring = sorted(({"label": k, "category": v["category"], "severity": v["severity"], "count": v["count"], "submissions": len(v["submissions"])}
                        for k, v in rec.items() if len(v["submissions"]) >= 2), key=lambda x: (-x["count"], x["label"]))[:12]  # same definition as Drift Radar
    return {"totals": {"submissions": len(subs), "pending": pending, "inReview": pending, "draft": by_status["draft"], "submitted": by_status["submitted"],
                       "underReview": by_status["under_review"], "resubmitted": by_status["resubmitted"], "approved": by_status["approved"], "changesRequested": by_status["changes_requested"],
                       "rejected": by_status["rejected"], "approvedFirstTime": len(first_time), "neededRevisions": len(ever_changes),
                       "decided": len(decided), "draftsExcluded": n_draft,
                       "firstTimeRate": round(len(first_time) / len(decided), 2) if decided else None},
            "definitions": {"submissions": "All non-draft submissions in scope", "firstTimeRate": "Approved on version 1 and never sent back, divided by submissions that have had a decision or a revision",
                            "recurring": "Same finding in two or more submissions (identical to Drift Radar)"},
            "topRules": [{"rule": k, "category": v["category"], "count": v["count"], "submissions": len(v["submissions"])}
                         for k, v in sorted(rules.items(), key=lambda kv: (-kv[1]["count"], str(kv[0])))[:10]],
            "recurring": recurring, "byCategory": [{"category": k, "count": v} for k, v in cats.most_common()],
            "timeline": [{"week": k, **v} for k, v in sorted(weeks.items())],
            "corrections": [{"label": k, "count": v} for k, v in corrections.most_common(8)],
            "reviewActivity": [{"reviewer": k, "decisions": v} for k, v in reviewers.most_common()],
            "byContentType": sorted(({"type": k, **v} for k, v in by_type.items()), key=lambda x: -x["issues"]),
            "byBrand": sorted(({**b, "complianceRate": round(b["approved"] / b["submissions"], 2) if b["submissions"] else None} for b in brands.values()),
                              key=lambda x: -x["submissions"])}
