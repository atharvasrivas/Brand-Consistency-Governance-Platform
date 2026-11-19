import React, { useState } from "react";
import Icon from "./Icon.jsx";
import { Pill, SourceTag, Meter } from "./ui.jsx";
import { CATEGORY_COLOR } from "../util.js";

// Interactive when `act` is given; read-only otherwise (used by reviewers).
export default function FindingCard({ f, selected, onSelect, act, readOnly }) {
  const [mode, setMode] = useState(null); // "edit" | "reject"
  const [text, setText] = useState(f.suggestion || "");
  const [reason, setReason] = useState("");
  const [alt, setAlt] = useState("");
  const open = f.status === "open";
  const mandatory = f.strictness === "mandatory" || f.strictness === "critical";
  const canAct = open && !readOnly && act;

  const reject = () => {
    if (mandatory && !reason.trim()) return;
    act.reject(f, reason.trim());
    setMode(null);
  };

  return (
    <article id={`f-${f.id}`} className={`fcard st-${f.status} ${selected ? "sel" : ""}`} style={{ "--cat": CATEGORY_COLOR[f.category] || "var(--accent)" }} onClick={onSelect}>
      <header className="fc-head">
        <span className="fc-dot" />
        <b className="fc-title">{f.label}</b>
        <Pill tone={mandatory ? "bad" : "info"}>{mandatory ? "Mandatory" : "Guidance"}</Pill>
        {f.needsHuman && open && <Pill tone="warn" title="Low confidence or conflicting sources: a person decides">Needs a person</Pill>}
        {f.status === "accepted" && <Pill tone="ok">Accepted</Pill>}
        {f.status === "rejected" && <Pill tone={mandatory ? "bad" : "muted"}>{mandatory ? "Overridden" : "Dismissed"}</Pill>}
      </header>
      <div className="fc-cat">{f.category}</div>

      {f.kind === "replace" && f.suggestion !== undefined && f.suggestion !== "" ? (
        <div className="swap">
          <div><span className="swap-l">In your draft</span><del>{f.quote}</del></div>
          <Icon name="arrow" size={16} className="swap-ar" />
          <div><span className="swap-l">Change to</span><ins>{f.suggestion}</ins></div>
        </div>
      ) : (
        <div className="quote">
          <span className="swap-l">{f.scope === "image" ? "In your image" : "In your draft"}</span>
          <q>{f.quote}</q>
          {f.suggestion && <p className="advice"><Icon name="sparkle" size={14} /> {f.suggestion}</p>}
        </div>
      )}
      {f.orSource && f.kind === "replace" && open && <p className="hint">Or attach an approved source for the stronger claim.</p>}
      {f.why && <p className="why">{f.why}</p>}
      <div className="fc-meta"><SourceTag source={f.source} />{f.confidence != null && <Meter value={f.confidence} />}</div>

      {f.status === "accepted" && f.applied && <p className="note ok-note">Applied: “{f.applied}”</p>}
      {f.status === "rejected" && f.note && <p className="note">{mandatory ? "Override reason" : "Note"}: {f.note}</p>}

      {canAct && (
        <div className="fc-actions" onClick={(e) => e.stopPropagation()}>
          {mode === "edit" ? (
            <>
              <input className="input grow" value={text} onChange={(e) => setText(e.target.value)} aria-label="Your wording" />
              <button className="btn btn-primary sm" onClick={() => { act.accept(f, text); setMode(null); }}>Apply</button>
              <button className="btn sm" onClick={() => setMode(null)}>Cancel</button>
            </>
          ) : mode === "reject" ? (
            <>
              <input className="input grow" value={reason} onChange={(e) => setReason(e.target.value)} placeholder={mandatory ? "Reason (required for mandatory rules)" : "Reason (optional)"} aria-label="Reason" />
              <button className="btn btn-danger sm" disabled={mandatory && !reason.trim()} onClick={reject}>Confirm</button>
              <button className="btn sm" onClick={() => setMode(null)}>Cancel</button>
            </>
          ) : f.kind === "conflict" ? (
            <div className="conflict-opts">
              {f.options.map((o, i) => (
                <button key={i} className="btn sm" onClick={() => act.choose(f, o)}>{o.label}</button>
              ))}
            </div>
          ) : f.fix && f.fix.type === "alt" ? (
            <>
              <input className="input grow" value={alt} onChange={(e) => setAlt(e.target.value)} placeholder="Describe the image in one sentence" aria-label="Alt text" />
              <button className="btn btn-primary sm" disabled={!alt.trim()} onClick={() => act.setAlt(f, alt.trim())}>Save alt text</button>
              <button className="btn sm" onClick={() => setMode("reject")}>Reject</button>
            </>
          ) : (
            <>
              {f.kind === "replace" && <button className="btn btn-primary sm" onClick={() => act.accept(f, f.suggestion)}><Icon name="check" size={14} /> Accept</button>}
              {f.fix && (f.fix.type === "append" || f.fix.type === "prepend") && <button className="btn btn-primary sm" onClick={() => act.fixDoc(f)}><Icon name="check" size={14} /> Accept</button>}
              {f.kind === "replace" && <button className="btn sm" onClick={() => { setText(f.suggestion); setMode("edit"); }}><Icon name="edit" size={14} /> Edit</button>}
              {f.kind === "advice" && f.scope === "text" && <button className="btn sm" onClick={() => act.editInDraft(f)}><Icon name="edit" size={14} /> Edit in draft</button>}
              {f.kind === "advice" && !f.fix && <button className="btn sm" onClick={() => act.done(f)}><Icon name="check" size={14} /> Mark as fixed</button>}
              <button className="btn sm" onClick={() => setMode("reject")}><Icon name="x" size={14} /> Reject</button>
            </>
          )}
        </div>
      )}
      {!open && !readOnly && act && f.status === "rejected" && (
        <div className="fc-actions" onClick={(e) => e.stopPropagation()}>
          <button className="btn sm" onClick={() => act.undo(f)}>Undo</button>
        </div>
      )}
    </article>
  );
}
