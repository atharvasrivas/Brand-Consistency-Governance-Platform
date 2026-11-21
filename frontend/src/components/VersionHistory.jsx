import React, { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../api.js";
import { Pill } from "./ui.jsx";
import { timeAgo } from "../util.js";

const TONE = { added: "ok", modified: "warn", removed: "danger" };

function Changes({ changes }) {
  if (!changes || !changes.length) return <p className="muted small">No field changes.</p>;
  return (
    <div>
      {changes.map((c, i) => (
        <div key={i} className="row-item">
          <b>{c.label}</b> <Pill tone={TONE[c.change]}>{c.change}</Pill>
          {c.before != null && <p style={{ margin: "2px 0" }}><small>Before:</small> <del>{c.before}</del></p>}
          {c.after != null && <p style={{ margin: "2px 0" }}><small>After:</small> <ins>{c.after}</ins></p>}
        </div>
      ))}
    </div>
  );
}

// Full history of a brand profile or product fact sheet: open any version, compare two, restore as a NEW version.
export default function VersionHistory({ base, canRestore, currentVersion, onRestored }) {
  const [list, setList] = useState(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(null);
  const [pick, setPick] = useState({ from: "", to: "" });
  const [cmp, setCmp] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setErr("");
    apiFetch("GET", `${base}/versions`).then((d) => setList(d.versions)).catch((e) => setErr(e.message));
  }, [base]);
  useEffect(load, [load, currentVersion]);

  const view = (n) => { setCmp(null); apiFetch("GET", `${base}/versions/${n}`).then((d) => setOpen({ n, ...d })).catch((e) => setErr(e.message)); };
  const compare = () => {
    if (!pick.from || !pick.to) return;
    setOpen(null);
    apiFetch("GET", `${base}/versions/compare?from=${pick.from}&to=${pick.to}`).then(setCmp).catch((e) => setErr(e.message));
  };
  const restore = async (n) => {
    if (!window.confirm(`Restore version ${n}? It will be saved as a new version; nothing is deleted.`)) return;
    setBusy(true);
    try {
      const r = await apiFetch("POST", `${base}/versions/${n}/restore`, { version: currentVersion });
      onRestored && onRestored(r);
      load();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };

  if (err && !list) return <div className="panel"><p className="err">{err}</p><button className="btn" onClick={load}>Try again</button></div>;
  if (!list) return <p className="muted">Loading version history…</p>;
  return (
    <div className="stack">
      {err && <p className="err">{err}</p>}
      <div className="panel">
        <b>Compare two versions</b>
        <div className="row-actions" style={{ marginTop: 8 }}>
          {["from", "to"].map((k) => (
            <select key={k} className="inp" style={{ width: 140 }} value={pick[k]} onChange={(e) => setPick({ ...pick, [k]: e.target.value })} aria-label={k}>
              <option value="">{k === "from" ? "From version…" : "To version…"}</option>
              {list.map((v) => <option key={v.version} value={v.version}>Version {v.version}</option>)}
            </select>
          ))}
          <button className="btn" disabled={!pick.from || !pick.to || pick.from === pick.to} onClick={compare}>Compare</button>
        </div>
      </div>
      {cmp && (
        <div className="panel">
          <h3>Version {cmp.from.version} → {cmp.to.version}</h3>
          <p className="muted small">{cmp.counts.added} added · {cmp.counts.modified} modified · {cmp.counts.removed} removed · {cmp.to.updatedBy} {cmp.to.updatedAt ? timeAgo(cmp.to.updatedAt) : ""}</p>
          <Changes changes={cmp.changes} />
        </div>
      )}
      {open && (
        <div className="panel">
          <h3>Version {open.n} in full</h3>
          <p className="muted small">{open.previous ? `Changes since version ${open.previous}:` : "First version."}</p>
          <Changes changes={open.changes} />
          <details style={{ marginTop: 8 }}><summary>Everything saved in this version</summary><pre className="snip" style={{ whiteSpace: "pre-wrap", maxHeight: 320, overflow: "auto" }}>{JSON.stringify(open.version, null, 2)}</pre></details>
        </div>
      )}
      <ol className="timeline">
        {list.map((v) => (
          <li key={v.version}>
            <span className="tl-dot" />
            <div>
              <b>Version {v.version}</b> {v.version === currentVersion && <Pill tone="ok">current</Pill>} {v.restoredFrom && <Pill>restored from v{v.restoredFrom}</Pill>}
              <span className="muted small"> · {v.updatedBy || "unknown"} · {v.updatedAt ? timeAgo(v.updatedAt) : ""}</span>
              <p>{v.changeNote || (v.initial ? "Initial version" : "No note")}</p>
              {v.changedFields.length > 0 && <p className="muted small">Changed: {v.changedFields.map((f) => f.label).join(", ")}</p>}
              <div className="row-actions">
                <button className="btn ghost" onClick={() => view(v.version)}>Open</button>
                {canRestore && v.version !== currentVersion && <button className="btn ghost" disabled={busy} onClick={() => restore(v.version)}>Restore as new version</button>}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
