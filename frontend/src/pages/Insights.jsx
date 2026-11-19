import React, { useMemo, useState } from "react";
import Icon from "../components/Icon.jsx";
import { Empty, Field, PageHead, Pill, StatusPill, Tabs } from "../components/ui.jsx";
import { useStore } from "../store.jsx";
import { findConflicts } from "../engine/checker.js";
import { CONTENT_TYPES } from "../engine/seed.js";
import { CATEGORY_COLOR, navigate } from "../util.js";

const typeLabel = (t) => (CONTENT_TYPES.find((c) => c.id === t) || { label: t }).label;
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const termRe = (t) => new RegExp(`(?<![\\w-])${esc(t)}(?![\\w-])`, "gi");

function snippet(text, term, repl) {
  const m = termRe(term).exec(text);
  if (!m) return null;
  const a = Math.max(0, m.index - 36);
  const b = Math.min(text.length, m.index + m[0].length + 36);
  return {
    before: (a > 0 ? "…" : "") + text.slice(a, m.index),
    hit: m[0],
    after: text.slice(m.index + m[0].length, b) + (b < text.length ? "…" : ""),
    repl,
  };
}

function Snip({ s }) {
  return (
    <p className="snip">
      {s.before}<mark className="hl hl-m">{s.hit}</mark>{s.after}
      {s.repl && <span className="snip-r"><Icon name="arrow" size={13} /> <ins>{s.repl}</ins></span>}
    </p>
  );
}

function Bars({ rows, onPick, picked }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="hbars">
      {rows.map((r) => (
        <button
          key={r.id}
          className={`hbar ${picked === r.id ? "on" : ""}`}
          onClick={() => onPick && onPick(r.id)}
          disabled={!onPick}
        >
          <span className="hbar-l">{r.label}</span>
          <span className="hbar-track">
            <span className="hbar-fill" style={{ width: `${(r.value / max) * 100}%`, background: r.color || "var(--accent)" }} />
          </span>
          <span className="hbar-v">{r.value}</span>
        </button>
      ))}
    </div>
  );
}

function Radar({ brandFilter, onSelectBrand }) {
  const { state } = useStore();
  const { submissions, brands, profile } = state;
  const [picked, setPicked] = useState(null);

  const scopedSubmissions = useMemo(() => {
    if (brandFilter === "all") return submissions;
    return submissions.filter((s) => s.brandId === brandFilter);
  }, [submissions, brandFilter]);

  const groups = useMemo(() => {
    const m = new Map();
    scopedSubmissions.forEach((s) => (s.findings || []).forEach((f) => {
      const g = m.get(f.ruleId) || { id: f.ruleId, label: f.label, category: f.category, subs: new Map(), total: 0, rejected: 0, source: f.source };
      g.total += 1;
      if (f.status === "rejected") g.rejected += 1;
      g.subs.set(s.id, s);
      m.set(f.ruleId, g);
    }));
    return [...m.values()].sort((a, b) => b.subs.size - a.subs.size || b.total - a.total);
  }, [scopedSubmissions]);

  const top = groups.slice(0, 8);
  const sel = groups.find((g) => g.id === picked) || top[0];
  const byCat = useMemo(() => {
    const c = {};
    scopedSubmissions.forEach((s) => (s.findings || []).forEach((f) => {
      c[f.category] = (c[f.category] || 0) + 1;
    }));
    return Object.entries(c).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ id: k, label: k, value: v, color: CATEGORY_COLOR[k] || "var(--accent)" }));
  }, [scopedSubmissions]);

  const outcomes = ["in_review", "changes_requested", "approved", "rejected"].map((k) => ({
    id: k,
    label: k.replace("_", " ").replace(/^./, (c) => c.toUpperCase()),
    value: scopedSubmissions.filter((s) => s.status === k).length,
  }));

  const mandatoryOpen = scopedSubmissions.reduce(
    (n, s) => n + (s.findings || []).filter((f) => (f.strictness === "mandatory" || f.strictness === "critical") && f.status === "open").length,
    0
  );
  const decided = scopedSubmissions.filter((s) => s.status === "approved" || s.status === "rejected").length;
  const approved = scopedSubmissions.filter((s) => s.status === "approved").length;

  if (scopedSubmissions.length === 0) {
    return (
      <Empty icon="chart" title="No submissions found for this brand">
        Submit content from Review Studio to generate compliance analytics.
      </Empty>
    );
  }

  return (
    <>
      <div className="kpis">
        <div className="kpi"><b>{scopedSubmissions.length}</b><span>Submissions Checked</span></div>
        <div className="kpi"><b>{scopedSubmissions.reduce((n, s) => n + (s.findings || []).length, 0)}</b><span>Total Issues Flagged</span></div>
        <div className="kpi"><b>{mandatoryOpen}</b><span>Critical Items Open</span></div>
        <div className="kpi"><b>{decided ? `${Math.round((approved / decided) * 100)}%` : "–"}</b><span>First-Time Approval Rate</span></div>
      </div>

      <div className="cols-2">
        <section className="panel">
          <div className="panel-h">
            <h2>Brand Drift Radar</h2>
            <span className="muted small">Recurring issues across {brandFilter === "all" ? "all brands" : brands.find(b => b.id === brandFilter)?.name}</span>
          </div>
          <Bars rows={top.map((g) => ({ id: g.id, label: g.label, value: g.subs.size, color: CATEGORY_COLOR[g.category] || "var(--accent)" }))} onPick={setPicked} picked={sel && sel.id} />
          <p className="muted small">Bar length = number of submissions affected. Click a bar to see affected copy.</p>
          {sel && (
            <div className="fixonce">
              <b><Icon name="target" size={16} /> {sel.label}</b>
              <p>
                Triggered {sel.total} time(s) across {sel.subs.size} submission(s). Update the fact sheet or add an approved example to eliminate this root cause.
              </p>
              <div className="chips-row">
                {[...sel.subs.values()].map((s) => (
                  <button key={s.id} className="fchip" onClick={() => navigate(`/approvals?id=${s.id}`)}>
                    {s.title} <span>{typeLabel(s.type)}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>

        <div className="stack">
          <section className="panel">
            <div className="panel-h"><h2>Findings by Governance Category</h2></div>
            <Bars rows={byCat} />
          </section>
          <section className="panel">
            <div className="panel-h"><h2>Review Outcomes</h2></div>
            <Bars
              rows={outcomes.map((o) => ({
                ...o,
                color: { in_review: "var(--accent)", changes_requested: "#F5B84B", approved: "#3DD6B0", rejected: "var(--bad)" }[o.id],
              }))}
            />
          </section>
        </div>
      </div>
    </>
  );
}

export default function Insights() {
  const { state } = useStore();
  const { brands } = state;
  const [brandFilter, setBrandFilter] = useState("all");

  return (
    <div className="insights-page">
      <PageHead eyebrow="Governance Health & Risk Analysis" title="Brand Governance Insights">
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--muted)" }}>Filter by Brand:</span>
          <select
            className="inp"
            style={{ width: "auto", height: 34, fontSize: 13, fontWeight: 600 }}
            value={brandFilter}
            onChange={(e) => setBrandFilter(e.target.value)}
          >
            <option value="all">All Brands (Portfolio View)</option>
            {brands.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>
        </div>
      </PageHead>

      <Radar brandFilter={brandFilter} onSelectBrand={setBrandFilter} />
    </div>
  );
}
