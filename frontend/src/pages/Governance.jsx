import React, { useCallback, useEffect, useRef, useState } from "react";
import { Empty, PageHead, Pill, Tabs } from "../components/ui.jsx";
import { useStore } from "../store.jsx";
import { apiFetch, API_CONFIGURED } from "../api.js";

const SEV = { critical: "danger", warning: "warn", suggestion: "muted" };
const LEVEL = { high: "danger", medium: "warn", low: "muted" };
const RES = [
  ["keep_first", "Keep the first rule"], ["keep_second", "Keep the second rule"],
  ["both_intended", "Both are intended"], ["needs_rewrite", "Needs rewriting"],
];

function useLoad(path, brandId, enabled) {
  const [s, setS] = useState({ loading: true, data: null, error: "" });
  const n = useRef(0);
  const load = useCallback(() => {
    if (!enabled) return;
    const mine = ++n.current;
    setS((x) => ({ ...x, loading: true, error: "" }));
    apiFetch("GET", `${path}${brandId ? `?brandId=${encodeURIComponent(brandId)}` : ""}`)
      .then((data) => { if (mine === n.current) setS({ loading: false, data, error: "" }); })
      .catch((e) => { if (mine === n.current) setS((x) => ({ loading: false, data: x.data, error: e.message || "Could not load" })); });
  }, [path, brandId, enabled]);
  useEffect(load, [load]);
  return [s, load];
}

const Retry = ({ error, load }) => (
  <div className="panel"><p className="err">{error}</p><button className="btn" onClick={load}>Try again</button></div>
);

function Drift({ brandId }) {
  const [s, load] = useLoad("/api/governance/drift", brandId, true);
  const d = s.data;
  if (s.loading && !d) return <p className="muted">Analysing submissions…</p>;
  if (s.error && !d) return <Retry error={s.error} load={load} />;
  if (!d || !d.recurring.length) return <Empty icon="chart" title="No drift detected">Drift appears when the same issue recurs across two or more submissions. Analysed {d ? d.analysed : 0} submissions.</Empty>;
  const max = Math.max(1, ...d.trend.map((t) => t.count));
  return (
    <div className="stack">
      <p className="muted small">{d.analysed} submissions analysed · consistency {d.consistency == null ? "n/a" : `${Math.round(d.consistency * 100)}%`} (share of submissions with no recurring pattern) · {d.definition}</p>
      {d.alerts.length > 0 && <div className="panel">{d.alerts.map((a, i) => <p key={i}>⚠ {a}</p>)}</div>}
      <div className="grid2">
        <div className="panel">
          <h3>Recurring issues</h3>
          {d.recurring.map((r, i) => (
            <div key={i} className="row-item">
              <div><b>{r.label}</b> <Pill tone={SEV[r.severity]}>{r.severity}</Pill></div>
              <small>{r.brandName}{r.productName ? ` / ${r.productName}` : ""} · {r.submissions} submissions · {r.occurrences} occurrences · {r.pattern}</small>
              <small> · {r.domain === "visual" ? "Visual pattern" : "Text pattern"} · in {Math.round((r.share || 0) * 100)}% of submissions</small>
              {(r.examples || []).map((e, k) => <p key={k} className="snip">“{e.text}” <small>({e.title})</small></p>)}
              {r.guideline && <small>Rule violated: {r.guideline}</small>}
              {r.recommendation && (
                <div className="muted small">
                  <p style={{ margin: "4px 0" }}><b>Why it matters:</b> {r.recommendation.explanation}</p>
                  {r.recommendation.correction && <p style={{ margin: "4px 0" }}><b>{r.domain === "visual" ? "Visual direction" : "Preferred wording"}:</b> {r.recommendation.correction}</p>}
                  <p style={{ margin: "4px 0" }}><b>Guidance for future content:</b> {r.recommendation.guidance}</p>
                </div>
              )}
            </div>
          ))}
        </div>
        <div className="panel">
          <h3>Weekly trend</h3>
          {d.trend.map((t) => (
            <div key={t.week} className="bar-row"><small>{t.week}</small><span className="bar" style={{ width: `${(t.count / max) * 100}%` }} /><small>{t.count}</small></div>
          ))}
          <h3>Hotspots</h3>
          {d.hotspots.map((h, i) => <p key={i}>{h.brandName}{h.productName ? ` / ${h.productName}` : ""}: <b>{h.issues}</b> issues</p>)}
        </div>
      </div>
    </div>
  );
}

function Impact({ brandId }) {
  const [s, load] = useLoad("/api/governance/impact", brandId, !!brandId);
  const [err, setErr] = useState("");
  if (!brandId) return <Empty icon="file" title="Select a brand">Impact is calculated per brand.</Empty>;
  const decide = async (key, decision) => {
    try { await apiFetch("POST", "/api/governance/impact/decision", { key, decision }); setErr(""); load(); } catch (e) { setErr(e.message); }
  };
  if (s.loading && !s.data) return <p className="muted">Scanning earlier submissions…</p>;
  if (s.error && !s.data) return <Retry error={s.error} load={load} />;
  const list = s.data ? s.data.affected : [];
  if (!list.length) return <Empty icon="check" title="No submissions are affected">When a fact sheet changes, earlier submissions that depend on the changed fact appear here.</Empty>;
  return (
    <div className="stack">
      {err && <p className="err">{err}</p>}
      {s.error && <Retry error={s.error} load={load} />}
      {(s.data.warnings || []).length > 0 && <p className="warn-note">Some records were skipped: {s.data.warnings.join("; ")}</p>}
      <p className="muted">{s.data.scanned ? `${s.data.scanned.submissions} submissions scanned · ` : ""}{s.data.open} open · A person decides what happens to each affected submission; nothing is changed automatically.</p>
      {list.map((r) => (
        <div key={r.key} className="panel">
          <div><b>{r.title}</b> <Pill tone={LEVEL[r.level]}>{r.level}</Pill> <Pill>{r.status}</Pill></div>
          <small>{r.author} · {r.subject} v{r.version} · {r.kind} {r.change}</small>
          <p>{r.before && <del>{r.before}</del>} {r.after && <ins>{r.after}</ins>}</p>
          {r.reason && <small><b>Why flagged:</b> {r.reason}</small>}
          {r.snippet && <p className="snip">…{r.snippet}…</p>}
          <small>{r.recommendation}</small>
          {r.decision && r.decision.decision !== "reopen" ? (
            <p><Pill tone="ok">Decision: {r.decision.decision}</Pill> <small>by {r.decision.by}</small> <button className="btn ghost" onClick={() => decide(r.key, "reopen")}>Reopen</button></p>
          ) : (
            <div className="row-actions">
              <button className="btn" onClick={() => decide(r.key, "recheck")}>Recheck needed</button>
              <button className="btn ghost" onClick={() => decide(r.key, "resolved")}>Mark resolved</button>
              <button className="btn ghost" onClick={() => decide(r.key, "dismiss")}>Dismiss</button>
              <button className="btn ghost" onClick={() => decide(r.key, "withdraw")}>Withdraw</button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function Conflicts({ brandId, isOwner }) {
  const [s, load] = useLoad("/api/governance/conflicts", brandId, !!brandId);
  const [err, setErr] = useState("");
  if (!brandId) return <Empty icon="file" title="Select a brand">Conflicts are detected within one brand and its products.</Empty>;
  const resolve = async (key, resolution) => {
    try { await apiFetch("POST", "/api/governance/conflicts/resolve", { key, resolution }); setErr(""); load(); } catch (e) { setErr(e.message); }
  };
  if (s.loading) return <p className="muted">Comparing approved guidelines…</p>;
  if (s.error) return <p className="err">{s.error}</p>;
  const list = s.data ? s.data.conflicts : [];
  if (!list.length) return <Empty icon="check" title="No conflicts found">Only approved items are compared; drafts are ignored.</Empty>;
  return (
    <div className="stack">
      {err && <p className="err">{err}</p>}
      <p className="muted">{s.data.open} unresolved · The platform never picks a winner. {isOwner ? "Choose how to resolve each one." : "Only a Brand Owner can resolve conflicts."}</p>
      {list.map((c) => (
        <div key={c.key} className="panel">
          <div><b>{c.type}</b> <small>{c.productName ? `${c.brandName} / ${c.productName}` : c.brandName}</small></div>
          <p>{c.explanation}</p>
          <div className="grid2">
            {c.rules.map((r, i) => <div key={i} className="panel"><small>{i === 0 ? "First rule" : "Second rule"} · {r.where}</small><p>{r.text}</p></div>)}
          </div>
          {c.decision ? <p><Pill tone="ok">Resolved: {(RES.find((x) => x[0] === c.decision.resolution) || [])[1]}</Pill> <small>by {c.decision.by}</small></p>
            : isOwner && <div className="row-actions">{RES.map(([k, l]) => <button key={k} className="btn ghost" onClick={() => resolve(c.key, k)}>{l}</button>)}</div>}
        </div>
      ))}
    </div>
  );
}

export default function Governance() {
  const { state } = useStore();
  const [tab, setTab] = useState("drift");
  const [brandId, setBrandId] = useState(state.activeBrandId || "");
  const isOwner = state.role === "owner";
  if (!API_CONFIGURED) return <Empty icon="shield" title="Governance tools need the server">Connect the backend to analyse real submissions.</Empty>;
  return (
    <div>
      <PageHead eyebrow="Governance" title="Brand Governance Tools">
        <select className="inp" value={brandId} onChange={(e) => setBrandId(e.target.value)} aria-label="Brand">
          <option value="">All brands (drift only)</option>
          {state.brands.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>
      </PageHead>
      <Tabs value={tab} onChange={setTab} tabs={[
        { id: "drift", label: "Brand Drift Radar" }, { id: "impact", label: "Change Impact Scanner" }, { id: "conflicts", label: "Guideline Conflicts" },
      ]} />
      {tab === "drift" && <Drift brandId={brandId} />}
      {tab === "impact" && <Impact brandId={brandId} />}
      {tab === "conflicts" && <Conflicts brandId={brandId} isOwner={isOwner} />}
    </div>
  );
}
