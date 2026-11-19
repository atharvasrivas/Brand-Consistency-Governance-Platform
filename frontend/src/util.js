export const STATUS = {
  draft: { label: "Draft", cls: "st-draft" },
  submitted: { label: "Submitted", cls: "st-review" },
  under_review: { label: "Under review", cls: "st-review" },
  resubmitted: { label: "Resubmitted", cls: "st-review" },
  in_review: { label: "In review", cls: "st-review" },
  changes_requested: { label: "Changes requested", cls: "st-changes" },
  approved: { label: "Approved", cls: "st-approved" },
  rejected: { label: "Rejected", cls: "st-rejected" },
};

// Statuses that are waiting for a reviewer.
export const PENDING = ["submitted", "under_review", "resubmitted", "in_review"];

export const CATEGORY_COLOR = {
  "Facts & claims": "#F5B84B",
  Terminology: "var(--accent)",
  "Language & tone": "#3DD6B0",
  "Brand aura": "var(--accent)",
  "Content patterns": "#5CC8FF",
  "Visual identity": "#FF8A7A",
  "Access & channel fit": "#7BE08F",
};

export function timeAgo(iso) {
  const s = Math.max(1, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 90) return "just now";
  const m = s / 60;
  if (m < 60) return `${Math.round(m)} min ago`;
  const h = m / 60;
  if (h < 24) return `${Math.round(h)} h ago`;
  const d = h / 24;
  return d < 2 ? "yesterday" : `${Math.round(d)} days ago`;
}

export function navigate(path) {
  window.location.hash = path;
}

export function getQuery() {
  const h = window.location.hash.replace(/^#/, "");
  const i = h.indexOf("?");
  return i < 0 ? {} : Object.fromEntries(new URLSearchParams(h.slice(i + 1)));
}

export function initials(name = "") {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("");
}

// Word-level diff: [{ t: "eq" | "add" | "del", v }]
export function diffWords(a, b) {
  const A = a.split(/(\s+)/).filter((x) => x !== "");
  const B = b.split(/(\s+)/).filter((x) => x !== "");
  const n = A.length;
  const m = B.length;
  if (n * m > 4e6) return [{ t: "del", v: a }, { t: "add", v: b }];
  const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out = [];
  const push = (t, v) => {
    const l = out[out.length - 1];
    if (l && l.t === t) l.v += v;
    else out.push({ t, v });
  };
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (A[i] === B[j]) { push("eq", A[i]); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) push("del", A[i++]);
    else push("add", B[j++]);
  }
  while (i < n) push("del", A[i++]);
  while (j < m) push("add", B[j++]);
  return out;
}

// Compact finding stored on a submission.
export function lightFinding(f) {
  return {
    key: f.key, ruleId: f.ruleId, label: f.label, category: f.category, strictness: f.strictness,
    quote: f.quote, severity: f.severity, count: f.count, status: f.status || "open", note: f.note, suggestion: f.suggestion, source: f.source,
    needsHuman: f.status === "open" ? !!f.needsHuman : false,
  };
}
