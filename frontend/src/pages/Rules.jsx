import React, { useState } from "react";
import { Empty, PageHead, Pill, Tabs } from "../components/ui.jsx";
import { useStore } from "../store.jsx";

const nid = () => `n${Math.random().toString(36).slice(2, 9)}`;

function ListEditor({ title, hint, items, onChange, canEdit, fields }) {
  const [draft, setDraft] = useState({});
  const add = () => {
    if (!draft[fields[0].k]?.trim()) return;
    onChange([...items, { id: nid(), ...draft }]);
    setDraft({});
  };
  return (
    <div className="panel">
      <h3>{title}</h3>
      <small className="muted">{hint}</small>
      {items.length === 0 && <p className="muted">None recorded yet.</p>}
      {items.map((it, i) => (
        <div key={it.id || i} className="row-item">
          {fields.map((f) => <span key={f.k}>{f.label ? <small>{f.label}: </small> : null}{String(it[f.k] ?? "") || <i>—</i>} </span>)}
          {it.status === "draft" && <Pill tone="warn">Draft — verify</Pill>}
          {canEdit && <button className="btn ghost" onClick={() => onChange(items.filter((_, j) => j !== i))}>Remove</button>}
        </div>
      ))}
      {canEdit && (
        <div className="row-actions">
          {fields.map((f) => (
            <input key={f.k} className="inp" placeholder={f.label} value={draft[f.k] || ""} onChange={(e) => setDraft({ ...draft, [f.k]: e.target.value })} />
          ))}
          <button className="btn" onClick={add}>Add</button>
        </div>
      )}
    </div>
  );
}

export default function Rules() {
  const { state, dispatch } = useStore();
  const isOwner = state.role === "owner";
  const brand = state.brands.find((b) => b.id === state.activeBrandId) || state.brands[0];
  const [tab, setTab] = useState("claims");
  const [msg, setMsg] = useState("");
  if (!brand) return <Empty icon="book" title="No brand yet">A Brand Owner needs to create a brand first.</Empty>;

  const srv = brand._srv || {};
  const save = async (patch, summary) => {
    const next = { ...brand, ...patch.top, _srv: { ...srv, ...patch.srv } };
    const r = await dispatch({ type: "saveBrand", brand: next, summary });
    setMsg(r ? "Saved." : "");
  };
  const top = (key) => (items) => save({ top: { [key]: items } }, `Updated ${key}`);
  const nested = (key) => (items) => save({ srv: { [key]: items } }, `Updated ${key}`);

  const restricted = (brand.restrictedClaims || []).map((t) => ({ id: t, text: t }));
  return (
    <div>
      <PageHead eyebrow="Governance" title={`Brand Rules & Knowledge · ${brand.name}`}>
        {!isOwner && <Pill>Read only — Brand Owners edit rules</Pill>}
      </PageHead>
      {msg && <p className="muted">{msg}</p>}
      <Tabs value={tab} onChange={setTab} tabs={[
        { id: "claims", label: "Claims" }, { id: "terms", label: "Terminology & words to avoid" },
        { id: "guides", label: "Communication guidelines" }, { id: "legal", label: "Legal & compliance" },
      ]} />
      {tab === "claims" && (
        <div className="grid2">
          <ListEditor title="Approved claims" hint="Each needs a source." canEdit={isOwner}
            items={brand.approvedClaims || []} fields={[{ k: "claim", label: "Claim" }, { k: "source", label: "Source" }]}
            onChange={(items) => top("approvedClaims")(items.map((c) => ({ ...c, status: c.status || "approved" })))} />
          <ListEditor title="Restricted claims" hint="Claims that must never be made." canEdit={isOwner}
            items={restricted} fields={[{ k: "text", label: "Claim" }]}
            onChange={(items) => top("restrictedClaims")(items.map((x) => x.text))} />
        </div>
      )}
      {tab === "terms" && (
        <ListEditor title="Terminology" hint="Words to avoid and the wording to use instead." canEdit={isOwner}
          items={brand.terminology || []} fields={[{ k: "from", label: "Avoid" }, { k: "to", label: "Prefer" }]}
          onChange={(items) => top("terminology")(items.map((t) => ({ ...t, strictness: t.strictness || "flexible", status: t.status || "approved" })))} />
      )}
      {tab === "guides" && (
        <ListEditor title="Communication guidelines" hint="Tone, formatting and style rules." canEdit={isOwner}
          items={srv.guidelines || []} fields={[{ k: "text", label: "Guideline" }, { k: "source", label: "Source" }]}
          onChange={(items) => nested("guidelines")(items.map((g) => ({ ...g, status: g.status || "approved" })))} />
      )}
      {tab === "legal" && (
        <ListEditor title="Legal & compliance" hint="Disclaimers, regulatory and product restrictions." canEdit={isOwner}
          items={srv.legal || []} fields={[{ k: "text", label: "Requirement" }, { k: "source", label: "Source" }]}
          onChange={(items) => nested("legal")(items.map((g) => ({ ...g, status: g.status || "approved" })))} />
      )}
      <p className="muted">Product-specific rules live on each product's fact sheet and are never shared across brands.</p>
    </div>
  );
}
