import React, { useEffect, useMemo, useState } from "react";
import Icon from "../components/Icon.jsx";
import FindingCard from "../components/FindingCard.jsx";
import { Avatar, Empty, PageHead, Pill, StatusPill, Tabs } from "../components/ui.jsx";
import { useStore } from "../store.jsx";
import { recheck as recheckSubmission } from "../api.js";
import { CONTENT_TYPES } from "../engine/seed.js";
import { diffWords, getQuery, navigate, timeAgo } from "../util.js";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "in_review", label: "In review" },
  { id: "changes_requested", label: "Changes requested" },
  { id: "approved", label: "Approved" },
  { id: "rejected", label: "Rejected" },
];
const typeLabel = (t) => (CONTENT_TYPES.find((c) => c.id === t) || { label: t }).label;

function Detail({ s }) {
  const { state, dispatch } = useStore();
  const { role, brands } = state;
  const brand = brands.find((b) => b.id === s.brandId) || state.profile;
  const product = brand?.products?.find((p) => p.id === s.productId) || null;

  const [tab, setTab] = useState("content");
  const [comment, setComment] = useState("");
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [vFrom, setVFrom] = useState(Math.max(1, s.versions.length - 1));
  const latest = s.versions[s.versions.length - 1];

  useEffect(() => {
    setTab("content");
    setComment("");
    setAck(false);
    setVFrom(Math.max(1, s.versions.length - 1));
  }, [s.id]);

  const unresolved = (s.findings || []).filter((f) => f.status === "open" && (f.strictness === "mandatory" || f.strictness === "critical"));
  const overridden = (s.findings || []).filter((f) => f.status === "rejected" && (f.strictness === "mandatory" || f.strictness === "critical"));
  const routed = (s.findings || []).filter((f) => f.status === "open" && f.needsHuman);
  const stale = s.profileVersion < (brand?.version || 1);
  const isDecider = role === "reviewer" || role === "owner" || role === "manager";
  const pending = s.status === "in_review";
  const currentUserName = state.user?.name || "Reviewer";
  const isAuthor = s.author === currentUserName;
  // Non-negotiable rule: author cannot decide their own submission
  const canDecide = isDecider && (!isAuthor || role === "owner");

  async function decide(status) {
    if (status !== "approved" && !comment.trim()) {
      alert("A comment explaining the required changes or rejection is required.");
      return;
    }
    const text = comment.trim();
    const done = await dispatch({
      type: "decide",
      id: s.id,
      status,
      comment: text,
      by: currentUserName,
      role,
      acknowledged: ack,
    });
    if (!done) return;
    setComment("");
    setAck(false);
  }

  async function recheck() {
    setBusy(true);
    try {
      const { findings, added } = await recheckSubmission(s, brand, product);
      dispatch({
        type: "recheck",
        id: s.id,
        findings,
        by: currentUserName,
        text: `Re-checked against ${s.brandName || brand.name} v${brand.version}: ${added} new finding(s)`,
      });
    } finally {
      setBusy(false);
    }
  }

  const diff = useMemo(() => {
    const a = s.versions.find((v) => v.n === vFrom);
    return a && s.versions.length > 1 ? diffWords(a.content, latest.content) : null;
  }, [s, vFrom, latest]);

  return (
    <div className="detail panel">
      <div className="d-head">
        <div>
          <div className="row-gap wrap" style={{ gap: 8, marginBottom: 8 }}>
            <StatusPill status={s.status} />
            <Pill tone="ok">Brand: {s.brandName || brand.name}</Pill>
            {s.productName && <Pill tone="muted">Product: {s.productName}</Pill>}
            <Pill tone="muted">{typeLabel(s.type)}</Pill>
            <span className="mono small muted">{s.id} · v{latest.n} (Profile v{s.profileVersion})</span>
          </div>
          <h2 className="serif d-title">{s.title}</h2>
          <p className="muted small">
            Submitted by <b>{s.author}</b> · {s.audience || "No audience"} · {s.purpose || "No purpose"} · updated {timeAgo(s.updatedAt)}
          </p>
        </div>
      </div>

      {stale && (
        <div className="banner banner-warn">
          <Icon name="alert" size={16} />
          <div>
            <b>Brand fact sheet changed since this was checked</b>
            <p>Checked against v{s.profileVersion}; current {s.brandName || brand.name} profile is v{brand.version}. Re-check to verify rules.</p>
          </div>
          <button className="btn sm" disabled={busy} onClick={recheck}>
            <Icon name="refresh" size={14} /> {busy ? "Checking…" : "Re-check now"}
          </button>
        </div>
      )}

      <div className="summary-chips">
        <span className="chip chip-m"><b>{unresolved.length}</b> critical unresolved</span>
        <span className="chip chip-o"><b>{overridden.length}</b> critical overridden</span>
        <span className="chip chip-h"><b>{routed.length}</b> routed to a person</span>
      </div>

      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "content", label: "Content", icon: "file" },
          { id: "findings", label: "Findings", icon: "search", count: (s.findings || []).length },
          { id: "comments", label: "Comments", icon: "chat", count: (s.comments || []).length },
          { id: "history", label: "History", icon: "clock", count: (s.versions || []).length },
        ]}
      />

      {tab === "content" && (
        <div className="d-content">
          {s.versions.length > 1 && (
            <div className="version-diff-bar">
              <span className="muted small">Compare version:</span>
              <select className="inp" style={{ width: "auto", height: 28 }} value={vFrom} onChange={(e) => setVFrom(Number(e.target.value))}>
                {s.versions.slice(0, -1).map((v) => (
                  <option key={v.n} value={v.n}>v{v.n} ({v.note || "Revision"})</option>
                ))}
              </select>
              <span className="muted small">with latest (v{latest.n})</span>
            </div>
          )}

          {diff ? (
            <div className="cmp-text" style={{ padding: 14, background: "var(--panel2)", borderRadius: 10 }}>
              {diff.map((d, i) => (
                d.t === "del" ? <del key={i}>{d.v}</del> : d.t === "add" ? <ins key={i}>{d.v}</ins> : <span key={i}>{d.v}</span>
              ))}
            </div>
          ) : (
            <div className="draft-view" style={{ whiteSpace: "pre-wrap" }}>{latest.content}</div>
          )}
        </div>
      )}

      {tab === "findings" && (
        <div className="findings-list">
          {(s.findings || []).length === 0 ? (
            <Empty icon="check" title="No compliance issues found" />
          ) : (
            s.findings.map((f) => (
              <FindingCard key={f.id} f={f} readOnly selected={false} onSelect={() => {}} />
            ))
          )}
        </div>
      )}

      {tab === "comments" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {(s.comments || []).map((c, i) => (
            <div key={i} style={{ background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 8, padding: "10px 14px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                <span style={{ fontWeight: 600, fontSize: 13 }}>{c.by} <span className="muted small">({c.role})</span></span>
                <span className="muted small">{timeAgo(c.at)}</span>
              </div>
              <p style={{ margin: 0, fontSize: 13.5, color: "var(--fg)" }}>{c.text}</p>
            </div>
          ))}
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <input
              type="text"
              className="inp"
              placeholder="Add review feedback..."
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
            <button
              className="btn btn-primary"
              disabled={!comment.trim()}
              onClick={() => {
                dispatch({ type: "comment", id: s.id, text: comment.trim(), by: currentUserName, role });
                setComment("");
              }}
            >
              Post Comment
            </button>
          </div>
        </div>
      )}

      {tab === "history" && (
        <ol className="timeline">
          {[...(s.activity || [])].reverse().map((act, i) => (
            <li key={i}>
              <span className="tl-dot" />
              <div>
                <b>{act.by}</b> <span className="muted small">· {timeAgo(act.at)}</span>
                <p>{act.text}</p>
              </div>
            </li>
          ))}
        </ol>
      )}

      {/* Reviewer & Owner Action Bar */}
      {isDecider && pending && (
        <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--line)", display: "flex", flexDirection: "column", gap: 10 }}>
          {unresolved.length > 0 && (
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--warn)", cursor: "pointer" }}>
              <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              Acknowledge open critical findings before approval
            </label>
          )}

          <textarea
            className="inp"
            rows={2}
            placeholder="Decision note (required to request changes or reject)"
            aria-label="Decision note"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button
              className="btn btn-primary"
              disabled={!canDecide || (unresolved.length > 0 && !ack)}
              onClick={() => decide("approved")}
            >
              <Icon name="check" size={16} /> Approve Submission
            </button>
            <button
              className="btn"
              disabled={!canDecide}
              onClick={() => decide("changes_requested")}
            >
              <Icon name="edit" size={16} /> Request Changes
            </button>
            <button
              className="btn"
              disabled={!canDecide}
              style={{ color: "var(--bad)" }}
              onClick={() => decide("rejected")}
            >
              <Icon name="x" size={16} /> Reject
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Approvals() {
  const { state, dispatch } = useStore();
  const { submissions, brands, role, suggestions } = state;
  const isOwner = role === "owner" || role === "manager";

  const [topTab, setTopTab] = useState("submissions"); // "submissions" or "suggestions"
  const [filter, setFilter] = useState("all");
  const [brandFilter, setBrandFilter] = useState("all");
  const [selectedId, setSelectedId] = useState(submissions[0]?.id || null);

  const filteredSubs = useMemo(() => {
    return submissions.filter((s) => {
      const matchStatus = filter === "all" || s.status === filter;
      const matchBrand = brandFilter === "all" || s.brandId === brandFilter;
      return matchStatus && matchBrand;
    });
  }, [submissions, filter, brandFilter]);

  const selected = submissions.find((s) => s.id === selectedId) || filteredSubs[0] || null;

  return (
    <div className="approvals-page">
      <PageHead eyebrow="Quality & Brand Compliance Governance" title="Review & Approvals Hub">
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className={`tab ${topTab === "submissions" ? "on" : ""}`}
            onClick={() => setTopTab("submissions")}
          >
            Submissions ({submissions.filter((s) => s.status === "in_review").length} pending)
          </button>
          <button
            className={`tab ${topTab === "suggestions" ? "on" : ""}`}
            onClick={() => setTopTab("suggestions")}
          >
            Fact Sheet Suggestions ({(suggestions || []).filter((s) => s.status === "pending").length})
          </button>
        </div>
      </PageHead>

      {topTab === "submissions" ? (
        <div className="approvals">
          <aside className="queue panel">
            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span className="serif" style={{ fontSize: 16, fontWeight: 700 }}>Submission Queue</span>
                <span className="muted small">{filteredSubs.length} items</span>
              </div>

              {/* Brand Filter */}
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: 11.5, color: "var(--muted)", fontWeight: 600 }}>Brand:</span>
                <select
                  className="inp"
                  style={{ height: 28, fontSize: 12, padding: "0 6px" }}
                  value={brandFilter}
                  onChange={(e) => setBrandFilter(e.target.value)}
                >
                  <option value="all">All Brands</option>
                  {brands.map((b) => (
                    <option key={b.id} value={b.id}>{b.name}</option>
                  ))}
                </select>
              </div>

              {/* Status Filter */}
              <div className="tabs" style={{ fontSize: 12 }}>
                {FILTERS.map((f) => (
                  <button
                    key={f.id}
                    className={`tab ${filter === f.id ? "on" : ""}`}
                    style={{ fontSize: 12, padding: "4px 8px" }}
                    onClick={() => setFilter(f.id)}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="q-list">
              {filteredSubs.length === 0 ? (
                <Empty icon="inbox" title="No submissions found">
                  Adjust filters or submit new content from Review Studio.
                </Empty>
              ) : (
                filteredSubs.map((s) => (
                  <div
                    key={s.id}
                    className={`q-item ${selectedId === s.id ? "on" : ""}`}
                    onClick={() => setSelectedId(s.id)}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 4 }}>
                      <span style={{ fontWeight: 600, fontSize: 14 }}>{s.title}</span>
                      <StatusPill status={s.status} />
                    </div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
                      <span className="pill pill-ok" style={{ fontSize: 11 }}>{s.brandName || "Nova"}</span>
                      {s.productName && <span className="pill pill-muted" style={{ fontSize: 11 }}>{s.productName}</span>}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--muted)" }}>
                      By {s.author} · updated {timeAgo(s.updatedAt)}
                    </div>
                  </div>
                ))
              )}
            </div>
          </aside>

          <main className="detail-col">
            {selected ? (
              <Detail s={selected} />
            ) : (
              <Empty icon="file" title="Select a submission to review" />
            )}
          </main>
        </div>
      ) : (
        <div className="panel" style={{ maxWidth: 880, margin: "0 auto" }}>
          <div className="panel-h" style={{ marginBottom: 16 }}>
            <div>
              <h2>Creator Fact Sheet Suggestions</h2>
              <p className="muted small">
                Proposals submitted by creators. Brand Owners review and decide whether to merge them into official brand profiles.
              </p>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {(suggestions || []).length === 0 ? (
              <Empty icon="sparkles" title="No pending suggestions">
                Creators can submit suggestions for brand guidelines from the Brand Profile tab.
              </Empty>
            ) : (
              suggestions.map((sug) => (
                <div
                  key={sug.id}
                  style={{
                    background: "var(--panel2)",
                    border: "1px solid var(--line)",
                    borderRadius: 10,
                    padding: "16px 20px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span className="pill pill-ok">Brand: {sug.brandName}</span>
                      {sug.productName && <span className="pill pill-muted">Product: {sug.productName}</span>}
                      <span style={{ fontWeight: 700, fontSize: 14.5 }}>{sug.title}</span>
                    </div>
                    <StatusPill status={sug.status === "pending" ? "in_review" : sug.status} />
                  </div>

                  <p style={{ margin: 0, fontSize: 13.5, color: "var(--fg)", background: "color-mix(in srgb, var(--text) 4%, transparent)", padding: 10, borderRadius: 6 }}>
                    "{sug.proposed}"
                  </p>

                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span className="muted small">Proposed by <b>{sug.author}</b> · {timeAgo(sug.at)}</span>
                    {isOwner && sug.status === "pending" && (
                      <div style={{ display: "flex", gap: 8 }}>
                        <button
                          className="btn btn-primary sm"
                          onClick={() => {
                            dispatch({ type: "decideSuggestion", id: sug.id, status: "approved" });
                            alert("Suggestion approved! You can now edit the official fact sheet in Brand Profile.");
                          }}
                        >
                          <Icon name="check" size={14} /> Accept Proposal
                        </button>
                        <button
                          className="btn sm"
                          style={{ color: "var(--bad)" }}
                          onClick={() => dispatch({ type: "decideSuggestion", id: sug.id, status: "rejected" })}
                        >
                          <Icon name="x" size={14} /> Reject
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
