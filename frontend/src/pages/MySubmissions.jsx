import React, { useState } from "react";
import { Empty, PageHead, Pill, StatusPill } from "../components/ui.jsx";
import { useStore } from "../store.jsx";
import { navigate, timeAgo } from "../util.js";

// The author's own view: status, reviewer feedback, every revision and decision, plus revise & resubmit.
export default function MySubmissions() {
  const { state, dispatch } = useStore();
  const uid = state.user && state.user.id;
  const mine = state.submissions.filter((s) => s.authorId === uid).sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt)));
  const [sel, setSel] = useState(null);
  const s = mine.find((x) => x.id === sel) || mine[0];

  if (!mine.length) {
    return (
      <div>
        <PageHead eyebrow="Workflow" title="My Submissions" />
        <Empty icon="file" title="No submissions yet">Content you submit for review appears here with its status and reviewer feedback.</Empty>
      </div>
    );
  }
  const canRevise = ["changes_requested", "rejected"].includes(s.status);
  const revise = () => { dispatch({ type: "edit", id: s.id }); navigate("/review"); };
  const sendDraft = async () => { await dispatch({ type: "submitDraft", id: s.id, findings: s.findings }); };

  return (
    <div>
      <PageHead eyebrow="Workflow" title="My Submissions" />
      <div className="g-resp" style={{ "--cols": "minmax(220px, 1fr) 2.2fr" }}>
        <div className="stack">
          {mine.map((x) => (
            <button key={x.id} type="button" className="panel" style={{ textAlign: "left", cursor: "pointer", outline: x.id === s.id ? "2px solid var(--accent)" : "none" }} onClick={() => setSel(x.id)}>
              <div><b>{x.title}</b></div>
              <div style={{ margin: "6px 0" }}><StatusPill status={x.status} /></div>
              <small className="muted">{x.brandName}{x.productName ? ` / ${x.productName}` : ""} · {x.id} · {timeAgo(x.updatedAt)}</small>
            </button>
          ))}
        </div>
        <div className="panel">
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
            <StatusPill status={s.status} />
            <Pill tone="ok">{s.brandName}</Pill>
            {s.productName && <Pill tone="muted">{s.productName}</Pill>}
            <span className="mono small muted">{s.id} · {s.versions.length} version{s.versions.length === 1 ? "" : "s"}</span>
          </div>
          <h3>{s.title}</h3>
          {s.status === "changes_requested" && <p className="warn-txt">A reviewer asked for changes. Read the feedback below, then revise and resubmit.</p>}
          {s.status === "rejected" && <p className="err">This submission was rejected. You can revise and resubmit it.</p>}
          {s.status === "approved" && <p className="ok-txt">Approved.</p>}
          <div className="row-actions">
            {canRevise && <button className="btn btn-primary" onClick={revise}>Revise & resubmit</button>}
            {s.status === "draft" && <button className="btn btn-primary" onClick={sendDraft}>Submit for review</button>}
          </div>
          <h3>Reviewer feedback & comments</h3>
          {s.comments.length === 0 ? <p className="muted">No comments yet.</p> : s.comments.map((c, i) => (
            <div key={i} className="row-item">
              <div><b>{c.by}</b> <small className="muted">({c.role}) · version {c.version || 1} · {timeAgo(c.at)}</small></div>
              <p style={{ margin: 0 }}>{c.text}</p>
            </div>
          ))}
          <h3>Decisions</h3>
          {(s.decisions || []).length === 0 ? <p className="muted">No decision yet.</p> : s.decisions.map((d) => (
            <div key={d.n} className="row-item">
              <div><StatusPill status={d.status} /> <small className="muted">by {d.by} on version {d.version} · {new Date(d.at).toLocaleString()}</small></div>
              {d.comment && <p style={{ margin: 0 }}>{d.comment}</p>}
            </div>
          ))}
          <h3>Versions</h3>
          {[...s.versions].reverse().map((v) => (
            <details key={v.n} className="row-item" open={v.n === s.versions.length}>
              <summary>Version {v.n} · {v.by} · {timeAgo(v.at)} · {v.note}</summary>
              <p style={{ whiteSpace: "pre-wrap" }}>{v.content}</p>
            </details>
          ))}
          <h3>History</h3>
          {[...(s.activity || [])].reverse().map((a, i) => <div key={i} className="row-item"><small><b>{a.by}</b> · {new Date(a.at).toLocaleString()} · {a.text}</small></div>)}
        </div>
      </div>
    </div>
  );
}
