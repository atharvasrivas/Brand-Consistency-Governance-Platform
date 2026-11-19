import React, { useState } from "react";
import Icon from "./Icon.jsx";
import { ROLES } from "../engine/seed.js";

export default function OnboardingModal({ initialUser, onSave, onClose, isEdit = false }) {
  const [name, setName] = useState(initialUser?.name || "");
  const [role, setRole] = useState(initialUser?.role || "");
  const [error, setError] = useState("");

  const submit = (e) => {
    e.preventDefault();
    if (!name.trim()) return setError("Please enter your full name.");
    if (!role) return setError("Please choose a role.");
    onSave({ name: name.trim(), role, onboarded: true });
  };

  return (
    <div className="modal-bg" role="dialog" aria-modal="true" aria-label="Welcome">
      <div className="modal" style={{ maxWidth: 520 }}>
        <div className="modal-head">
          <div>
            <div className="eyebrow-s">{isEdit ? "Your details" : "Get started"}</div>
            <h2 className="serif" style={{ margin: "4px 0" }}>{isEdit ? "Update your details" : "Welcome to Brand Governance Platform"}</h2>
            <p className="muted small" style={{ margin: 0 }}>
              Prototype identity: your name and role are saved in this browser and sent with each request. This is not secure sign-in.
            </p>
          </div>
          {isEdit && onClose && (
            <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="x" size={18} /></button>
          )}
        </div>
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {error && <div role="alert" className="warn-txt small">{error}</div>}
          <label style={{ display: "grid", gap: 6, fontSize: 13, fontWeight: 600 }}>
            Full name
            <input className="inp" value={name} onChange={(e) => setName(e.target.value)} autoFocus autoComplete="name" />
          </label>
          <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 8 }}>
            <legend style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Role</legend>
            {ROLES.map((r) => (
              <label key={r.id} className="role-card" data-on={role === r.id}>
                <input type="radio" name="role" value={r.id} checked={role === r.id} onChange={() => setRole(r.id)} className="sr" />
                <span style={{ fontWeight: 600 }}>{r.label}</span>
                <span className="muted small">{r.description}</span>
              </label>
            ))}
          </fieldset>
          <button type="submit" className="btn btn-primary" style={{ width: "100%" }}>{isEdit ? "Save" : "Continue"}</button>
        </form>
      </div>
    </div>
  );
}
