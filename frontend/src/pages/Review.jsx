import React, { useEffect, useMemo, useRef, useState } from "react";
import Icon from "../components/Icon.jsx";
import FindingCard from "../components/FindingCard.jsx";
import { Pill, Field, PageHead, Empty, FileUploadField } from "../components/ui.jsx";
import { useStore } from "../store.jsx";
import { review, rewrite } from "../api.js";
import { CONTENT_TYPES, SAMPLE_DRAFTS_BY_BRAND } from "../engine/seed.js";
import { CATEGORY_COLOR, diffWords, navigate } from "../util.js";

const blankMeta = { title: "", type: "blog", audience: "", purpose: "" };
const imgSig = (i) => (i ? [i.name, i.alt, i.fonts, i.textInImage] : null);

function Highlighted({ text, findings, selectedId, onSelect }) {
  const spans = findings
    .filter((f) => f.scope === "text" && f.start !== undefined && f.status !== "accepted")
    .flatMap((f) => (f.spans && f.spans.length ? f.spans : [[f.start, f.end]]).map(([start, end]) => ({ ...f, start, end })))
    .sort((a, b) => a.start - b.start);
  const parts = [];
  let pos = 0;
  for (const f of spans) {
    if (f.start < pos) continue;
    if (f.start > pos) parts.push(text.slice(pos, f.start));
    const isCritical = f.strictness === "critical" || f.strictness === "mandatory" || f.severity === "critical";
    parts.push(
      <mark
        key={f.id}
        className={`hl ${isCritical ? "hl-m" : "hl-f"} ${f.status === "rejected" ? "hl-x" : ""} ${selectedId === f.id ? "hl-sel" : ""}`}
        style={{ "--cat": CATEGORY_COLOR[f.category] || "var(--accent)" }}
        onClick={() => onSelect(f.id)}
        title={`${f.label}: click to see rule & fix`}
      >
        {text.slice(f.start, f.end)}
      </mark>
    );
    pos = f.end;
  }
  parts.push(text.slice(pos));
  return <div className="draft-view" tabIndex={0}>{parts}</div>;
}

function RewriteModal({ original, rw, onAccept, onEdit, onClose, brandName }) {
  const diff = useMemo(() => diffWords(original, rw.text), [original, rw.text]);
  const changed = rw.text !== original;
  return (
    <div className="modal-bg" role="dialog" aria-modal="true" aria-label="Brand-aligned rewrite" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <div className="eyebrow-s">{brandName} Brand-aligned rewrite</div>
            <h2 className="serif">Compare, then accept, edit or reject</h2>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="x" /></button>
        </div>
        <div className="cmp">
          <div className="cmp-col">
            <span className="swap-l">Your original</span>
            <div className="cmp-text">{diff.filter((d) => d.t !== "add").map((d, i) => (d.t === "del" ? <del key={i}>{d.v}</del> : <span key={i}>{d.v}</span>))}</div>
          </div>
          <div className="cmp-col cmp-new">
            <span className="swap-l">On-brand version</span>
            <div className="cmp-text">{diff.filter((d) => d.t !== "del").map((d, i) => (d.t === "add" ? <ins key={i}>{d.v}</ins> : <span key={i}>{d.v}</span>))}</div>
          </div>
        </div>
        {changed ? (
          <div className="applied">
            <b>What changed, and why</b>
            <ul>
              {rw.applied.map((a, i) => (
                <li key={i}><span className="mono">{a.quote}</span> → <span className="mono">{a.suggestion}</span> <span className="muted small">· {a.label}</span></li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="hint">The draft already matches {brandName} guidelines, so there is nothing to rewrite.</p>
        )}
        {rw.skipped && rw.skipped.length > 0 && (
          <p className="warn-note"><Icon name="alert" size={15} /> {rw.skipped.length} item(s) left unchanged because approved sources disagree. Human review decides those.</p>
        )}
        <div className="modal-actions">
          <button className="btn btn-primary" disabled={!changed} onClick={onAccept}><Icon name="check" size={16} /> Accept rewrite</button>
          <button className="btn" onClick={onEdit}><Icon name="edit" size={16} /> Edit first</button>
          <button className="btn" onClick={onClose}><Icon name="x" size={16} /> Reject</button>
        </div>
      </div>
    </div>
  );
}

export default function Review() {
  const { state, dispatch } = useStore();
  const { brands, activeBrandId, activeProductId, role, editId } = state;
  const activeBrand = brands.find((b) => b.id === activeBrandId) || brands[0];
  const activeProduct = activeBrand?.products?.find((p) => p.id === activeProductId) || null;

  const editing = editId ? state.submissions.find((s) => s.id === editId) : null;
  const last = editing ? editing.versions[editing.versions.length - 1] : null;

  const [meta, setMeta] = useState(editing ? { title: editing.title, type: editing.type, audience: editing.audience, purpose: editing.purpose } : blankMeta);
  const [content, setContent] = useState(last ? last.content : "");
  const [image, setImage] = useState(editing && editing.image ? { ...editing.image } : null);
  const [raw, setRaw] = useState(null);
  const [checkedSig, setCheckedSig] = useState(null);
  const [engine, setEngine] = useState(null);
  const [busy, setBusy] = useState(false);
  const [statusMap, setStatusMap] = useState({});
  const [resolved, setResolved] = useState([]);
  const [mode, setMode] = useState("edit");
  const [selected, setSelected] = useState(null);
  const [rw, setRw] = useState(null);
  const [note, setNote] = useState("");
  const [toast, setToast] = useState("");

  const sig = JSON.stringify([activeBrand.id, activeProduct?.id, content, imgSig(image), meta.type]);
  const fresh = raw !== null && checkedSig === sig;

  const findings = useMemo(
    () => (raw || []).map((f) => ({
      ...f,
      status: (statusMap[f.key] && statusMap[f.key].status) || "open",
      note: statusMap[f.key] && statusMap[f.key].note,
    })),
    [raw, statusMap]
  );

  const open = findings.filter((f) => f.status === "open");
  const mandOpen = open.filter((f) => f.strictness === "critical" || f.strictness === "mandatory");
  const blocking = mandOpen.filter((f) => !f.needsHuman);
  const routed = open.filter((f) => f.needsHuman);
  const guideOpen = open.filter((f) => f.strictness !== "critical" && f.strictness !== "mandatory");
  const done = [...resolved, ...findings.filter((f) => f.status !== "open")];

  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(""), 3200);
    return () => clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    if (!selected) return;
    const el = document.getElementById(`f-${selected}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [selected]);

  async function runCheck(c = content, img = image, m = meta) {
    setBusy(true);
    try {
      const res = await review({
        content: c,
        meta: m,
        image: img ? { name: img.name, alt: img.alt, fonts: img.fonts, textInImage: img.textInImage, analysis: img.analysis } : null,
        brandId: activeBrand.id,
        productId: activeProduct ? activeProduct.id : null,
        profile: activeBrand,
        product: activeProduct,
      });
      setRaw(res.findings);
      setEngine(res.engine);
      if (res.notice) alert(res.notice);
      setCheckedSig(JSON.stringify([activeBrand.id, activeProduct?.id, c, imgSig(img), m.type]));
      setMode("review");
    } finally {
      setBusy(false);
    }
  }

  const setStatus = (key, status, noteText) => setStatusMap((m) => ({ ...m, [key]: { status, note: noteText } }));

  const act = {
    accept: async (f, text) => {
      const next = content.slice(0, f.start) + text + content.slice(f.end);
      setContent(next);
      setResolved((r) => [...r, { ...f, status: "accepted", applied: text }]);
      await runCheck(next);
    },
    choose: async (f, option) => {
      if (option.text) return act.accept(f, option.text);
      setStatus(f.key, "rejected", `Kept as written, following ${option.source.doc}`);
      return undefined;
    },
    override: (f, noteText) => {
      setStatus(f.key, "rejected", noteText);
      setToast("Override reason recorded for reviewer.");
    },
    dismiss: (f) => setStatus(f.key, "rejected", null),
    reopen: (f) => setStatus(f.key, "open", null),
    docFix: async (f) => {
      if (!f.fix) return;
      const next = f.fix.type === "append" ? content.replace(/\s+$/, "") + f.fix.text : f.fix.text + content;
      setContent(next);
      setResolved((r) => [...r, { ...f, status: "accepted", applied: f.fix.text }]);
      await runCheck(next);
    },
    reject: (f, noteText) => (noteText ? act.override(f, noteText) : act.dismiss(f)),
    fixDoc: (f) => act.docFix(f),
    setAlt: (f, text) => act.altFix(f, text),
    editInDraft: (f) => setSelected(f.id),
    done: (f) => setStatus(f.key, "accepted", null),
    undo: (f) => act.reopen(f),
    altFix: (f, text) => {
      setImage((i) => ({ ...i, alt: text }));
      setResolved((r) => [...r, { ...f, status: "accepted", applied: text }]);
    },
  };

  async function requestRewrite() {
    setBusy(true);
    try {
      const rejectedKeys = Object.entries(statusMap)
        .filter(([, v]) => v.status === "rejected")
        .map(([k]) => k);
      const res = await rewrite({
        content,
        meta,
        profile: activeBrand,
        product: activeProduct,
        dismissed: rejectedKeys,
        brandId: activeBrand.id,
        productId: activeProduct ? activeProduct.id : null,
      });
      setRw(res);
    } finally {
      setBusy(false);
    }
  }

  async function saveDraft() {
    const title = meta.title.trim() || `${meta.type.toUpperCase()}: ${content.slice(0, 30)}…`;
    const res = await dispatch({
      type: "submit", draft: true,
      submission: { title, brandId: activeBrand.id, productId: activeProduct ? activeProduct.id : null, type: meta.type, audience: meta.audience, purpose: meta.purpose,
        image, findings, versions: [{ n: 1, content }], comments: [] },
    });
    if (res) { setToast("Draft saved. Find it under My Submissions."); }
  }

  async function resubmitRevision() {
    if (blocking.length > 0) {
      alert("Please fix open critical/mandatory findings before resubmitting.");
      return;
    }
    const res = await dispatch({
      type: "resubmit", id: editing.id, content, findings, note: note || "Revised after feedback",
      fields: { title: meta.title, type: meta.type, audience: meta.audience, purpose: meta.purpose },
    });
    if (res) {
      dispatch({ type: "edit", id: null });
      navigate("/mine");
    }
  }

  async function submitForReview() {
    if (editing) return resubmitRevision();
    if (blocking.length > 0) {
      alert("Please fix open critical/mandatory findings or provide a written override reason before submitting.");
      return;
    }
    const title = meta.title.trim() || `${meta.type.toUpperCase()}: ${content.slice(0, 30)}…`;
    const res = await dispatch({
      type: "submit",
      submission: {
        title,
        brandId: activeBrand.id,
        brandName: activeBrand.name,
        productId: activeProduct ? activeProduct.id : null,
        productName: activeProduct ? activeProduct.name : "Brand-level content",
        type: meta.type,
        audience: meta.audience,
        purpose: meta.purpose,
        image,
        findings,
        author: state.user?.name || "Creator",
        profileVersion: activeBrand.version || 1,
        versions: [{ n: 1, content, at: new Date().toISOString(), by: state.user?.name || "Creator", note: note || "Initial draft" }],
        comments: note ? [{ id: "c-init", by: state.user?.name || "Creator", role: role || "creator", text: note, at: new Date().toISOString() }] : [],
        activity: [{ at: new Date().toISOString(), by: state.user?.name || "Creator", text: `Submitted for review under ${activeBrand.name}` }],
      },
    });
    if (res) {
      navigate(role === "owner" ? "/approvals" : "/mine");
    }
  }

  const loadSample = () => {
    const brandSamples = SAMPLE_DRAFTS_BY_BRAND[activeBrand.id] || SAMPLE_DRAFTS_BY_BRAND.nova;
    const s = brandSamples[meta.type] || Object.values(brandSamples)[0];
    setMeta({ ...meta, title: s.title, audience: s.audience, purpose: s.purpose });
    setContent(s.content);
    setRaw(null);
    setStatusMap({});
    setResolved([]);
  };

  return (
    <div className="studio">
      <div className="studio-main">
        {/* Step 1: Pre-Submission Brand & Product Context Picker */}
        <div style={{ background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 12, padding: "14px 18px", marginBottom: 18, display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--accent)" }}>
                Step 1: Governing Context
              </span>
              <span className="muted small">· Content is checked ONLY against the chosen brand & product fact sheet</span>
            </div>
            {SAMPLE_DRAFTS_BY_BRAND[activeBrand.id] && (
              <button type="button" className="btn" style={{ height: 28, fontSize: 12 }} onClick={loadSample}>
                <Icon name="sparkles" size={13} /> Load Sample {activeBrand.name} Draft
              </button>
            )}
          </div>

          <div className="g-resp" style={{ "--cols": "1fr 1.5fr" }}>
            <div>
              <label style={{ fontSize: 12.5, fontWeight: 600, color: "var(--muted)", display: "block", marginBottom: 4 }}>
                Selected Brand Profile
              </label>
              <select
                className="inp"
                value={activeBrand.id}
                onChange={(e) => {
                  dispatch({ type: "selectBrand", brandId: e.target.value });
                  setRaw(null);
                }}
                style={{ fontWeight: 600, color: "var(--fg)" }}
              >
                {brands.map((b) => (
                  <option key={b.id} value={b.id}>{b.name} (v{b.version || 1})</option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ fontSize: 12.5, fontWeight: 600, color: "var(--muted)", display: "block", marginBottom: 4 }}>
                Product Fact Sheet
              </label>
              <select
                className="inp"
                value={activeProductId || ""}
                onChange={(e) => {
                  dispatch({ type: "selectProduct", productId: e.target.value || null });
                  setRaw(null);
                }}
              >
                <option value="">Brand-level content (no specific product fact sheet)</option>
                {(activeBrand.products || []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} {p.previousName ? `(formerly ${p.previousName})` : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Step 2: Content Metadata */}
        <div className="g-resp" style={{ "--cols": "2fr 1fr" }}>
          <Field label="Submission Title">
            <input
              type="text"
              className="inp"
              placeholder={`e.g. ${activeBrand.name} Launch Announcement`}
              value={meta.title}
              onChange={(e) => setMeta({ ...meta, title: e.target.value })}
            />
          </Field>
          <Field label="Content Type">
            <select
              className="inp"
              value={meta.type}
              onChange={(e) => setMeta({ ...meta, type: e.target.value })}
            >
              {CONTENT_TYPES.map((t) => (
                <option key={t.id} value={t.id}>{t.label}</option>
              ))}
            </select>
          </Field>
        </div>

        <div className="g-resp" style={{ "--cols": "1fr 1fr" }}>
          <Field label="Intended Audience">
            <input
              type="text"
              className="inp"
              placeholder="e.g. Supercar collectors, Local businesses"
              value={meta.audience}
              onChange={(e) => setMeta({ ...meta, audience: e.target.value })}
            />
          </Field>
          <Field label="Business Purpose">
            <input
              type="text"
              className="inp"
              placeholder="e.g. Drive pre-orders, Build credibility"
              value={meta.purpose}
              onChange={(e) => setMeta({ ...meta, purpose: e.target.value })}
            />
          </Field>
        </div>

        {/* Step 3: Editor / Highlights View */}
        <div className="editor-wrap">
          <div className="editor-head">
            <div className="tabs" role="tablist">
              <button
                role="tab"
                aria-selected={mode === "edit"}
                className={`tab ${mode === "edit" ? "on" : ""}`}
                onClick={() => setMode("edit")}
              >
                <Icon name="edit" size={14} /> Edit Draft
              </button>
              <button
                role="tab"
                aria-selected={mode === "review"}
                className={`tab ${mode === "review" ? "on" : ""}`}
                onClick={() => {
                  if (!fresh) runCheck();
                  else setMode("review");
                }}
              >
                <Icon name="search" size={14} /> Review Highlights {findings.length > 0 && <span className="tab-count">{open.length}</span>}
              </button>
            </div>

            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy || !content.trim()}
                onClick={() => runCheck()}
              >
                <Icon name="search" size={15} /> {busy ? "Checking..." : `Run ${activeBrand.name} Checks`}
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy || !content.trim() || findings.length === 0}
                onClick={requestRewrite}
                title="Generate an automated on-brand rewrite"
              >
                <Icon name="sparkles" size={15} /> Rewrite
              </button>
            </div>
          </div>

          {mode === "edit" ? (
            <textarea
              className="draft-editor"
              rows={12}
              placeholder={`Write or paste content for ${activeBrand.name}${activeProduct ? ` · ${activeProduct.name}` : ""} here...`}
              value={content}
              onChange={(e) => setContent(e.target.value)}
            />
          ) : (
            <Highlighted
              text={content}
              findings={findings}
              selectedId={selected}
              onSelect={setSelected}
            />
          )}
        </div>

        {/* Visual Asset Attachment */}
        <div style={{ marginTop: 16 }}>
          <FileUploadField
            label="Visual Asset (Optional)"
            hint="Attach logo graphic, campaign banner, or product mockup to check against brand rules"
            file={image}
            onFileSelect={(f) => {
              setImage(f);
              if (f) runCheck(content, f);
            }}
          />
        </div>

        {/* Submission Bar */}
        <div className="submit-bar" style={{ marginTop: 24, padding: "16px 20px", background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 14 }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>Submit for Reviewer Approval</div>
            <div style={{ fontSize: 12.5, color: "var(--muted)" }}>
              {blocking.length > 0
                ? `${blocking.length} critical finding(s) must be resolved or justified before submission.`
                : `Ready to route under ${activeBrand.name} governance.`}
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <input
              type="text"
              className="inp"
              style={{ width: 240, height: 36, fontSize: 12.5 }}
              placeholder="Optional note for reviewer..."
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || !content.trim() || blocking.length > 0}
              onClick={submitForReview}
            >
              <Icon name="check" size={16} /> {editing ? `Resubmit as version ${editing.versions.length + 1}` : "Submit for Approval"}
            </button>
            {!editing && (
              <button type="button" className="btn" disabled={busy || !content.trim()} onClick={saveDraft}>
                Save draft
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Right Column: Findings & Compliance Sidebar */}
      <aside className="studio-out">
        <div className="fact-h">
          <span className="serif fact-title">Governance Findings</span>
          <Pill tone={fresh ? "ok" : "muted"}>
            {fresh ? `${engine === "api" ? "Flask API" : "Local Engine"}` : "Unchecked"}
          </Pill>
        </div>

        {/* Severity Filter Counters */}
        <div className="g-resp" style={{ "--cols": "1fr 1fr 1fr" }}>
          <div style={{ background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 8, padding: "6px 8px", textAlign: "center" }}>
            <div style={{ fontSize: 10.5, color: "var(--bad)", fontWeight: 700 }}>CRITICAL</div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>{mandOpen.length}</div>
          </div>
          <div style={{ background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 8, padding: "6px 8px", textAlign: "center" }}>
            <div style={{ fontSize: 10.5, color: "var(--warn)", fontWeight: 700 }}>REVIEW</div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>{routed.length}</div>
          </div>
          <div style={{ background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 8, padding: "6px 8px", textAlign: "center" }}>
            <div style={{ fontSize: 10.5, color: "var(--ok)", fontWeight: 700 }}>RESOLVED</div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>{done.length}</div>
          </div>
        </div>

        {open.length === 0 && done.length === 0 ? (
          <Empty icon="shield" title="Ready to check">
            Click "Run {activeBrand.name} Checks" to evaluate your copy against approved facts, specs, and guidelines.
          </Empty>
        ) : open.length === 0 ? (
          <div style={{ textAlign: "center", padding: "30px 16px", background: "color-mix(in srgb, var(--ok) 10%, transparent)", border: "1px solid color-mix(in srgb, var(--ok) 35%, transparent)", borderRadius: 12 }}>
            <Icon name="check" size={28} style={{ color: "var(--ok)", marginBottom: 8 }} />
            <h3 className="serif" style={{ margin: "4px 0", color: "var(--ok)" }}>All Findings Resolved</h3>
            <p className="muted small" style={{ margin: 0 }}>This copy is fully compliant with {activeBrand.name} approved standards.</p>
          </div>
        ) : (
          <div className="findings-list">
            {open.map((f) => (
              <FindingCard key={f.id} f={f} act={act} selected={selected === f.id} onSelect={() => setSelected(f.id)} />
            ))}
          </div>
        )}
      </aside>

      {/* On-Brand Rewrite Modal */}
      {rw && (
        <RewriteModal
          original={content}
          rw={rw}
          brandName={activeBrand.name}
          onAccept={() => {
            setContent(rw.text);
            setRw(null);
            runCheck(rw.text);
          }}
          onEdit={() => {
            setContent(rw.text);
            setRw(null);
            setMode("edit");
          }}
          onClose={() => setRw(null)}
        />
      )}
    </div>
  );
}
