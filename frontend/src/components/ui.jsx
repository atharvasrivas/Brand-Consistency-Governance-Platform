import React, { useRef, useState } from "react";
import Icon from "./Icon.jsx";
import { STATUS, initials } from "../util.js";

export function Pill({ tone = "muted", children, title }) {
  return <span className={`pill pill-${tone}`} title={title}>{children}</span>;
}

export function StatusPill({ status }) {
  const s = STATUS[status] || { label: status, cls: "" };
  return <span className={`status ${s.cls}`}>{s.label}</span>;
}

export function Avatar({ name, tone }) {
  return <span className={`avatar ${tone ? `av-${tone}` : ""}`} title={name}>{initials(name)}</span>;
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} className={value === t.id ? "tab on" : "tab"} onClick={() => onChange(t.id)}>
          {t.icon && <Icon name={t.icon} size={15} />} {t.label}{t.count != null && <span className="tab-count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Meter({ value }) {
  const pct = Math.round(value * 100);
  return (
    <span className="meter" title={`${pct}% confidence`}>
      <span className="meter-track"><span className="meter-fill" style={{ width: `${pct}%` }} /></span>
      <span className="meter-num">{pct}%</span>
    </span>
  );
}

export function SourceTag({ source }) {
  if (!source) return null;
  return <span className="src"><Icon name="link" size={13} /> {source.doc}{source.ref ? ` · ${source.ref}` : ""}</span>;
}

export function Empty({ icon = "file", title, children }) {
  return (
    <div className="empty">
      <span className="empty-ic"><Icon name={icon} size={22} /></span>
      <b>{title}</b>
      {children && <p>{children}</p>}
    </div>
  );
}

export function Field({ label, hint, children, className = "" }) {
  return (
    <label className={`field ${className}`}>
      <span className="field-l">{label}</span>
      {children}
      {hint && <span className="field-h">{hint}</span>}
    </label>
  );
}

export function PageHead({ eyebrow, title, children }) {
  return (
    <div className="page-head">
      <div>
        <div className="eyebrow-s">{eyebrow}</div>
        <h1 className="serif page-title">{title}</h1>
      </div>
      {children && <div className="page-head-r">{children}</div>}
    </div>
  );
}

// Interactive Color Picker & Palette Editor
export function ColorPickerField({ color, onChange, onRemove, label = "Brand Color" }) {
  const [hex, setHex] = useState(color.hex || "var(--accent)");
  const [name, setName] = useState(color.name || "");

  const handleHexChange = (newHex) => {
    setHex(newHex);
    onChange({ ...color, hex: newHex, name });
  };

  const handleNameChange = (newName) => {
    setName(newName);
    onChange({ ...color, hex, name: newName });
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 10, padding: "8px 12px" }}>
      <input
        type="color"
        value={hex.startsWith("#") && hex.length === 7 ? hex : "var(--accent)"}
        onChange={(e) => handleHexChange(e.target.value)}
        style={{ width: 36, height: 36, borderRadius: 8, border: "none", cursor: "pointer", background: "none" }}
        title="Choose color"
      />
      <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1 }}>
        <input
          type="text"
          className="inp"
          placeholder="Color Name (e.g. Signal Coral)"
          value={name}
          onChange={(e) => handleNameChange(e.target.value)}
          style={{ height: 28, fontSize: 13 }}
        />
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 11, color: "var(--muted)" }}>HEX:</span>
          <input
            type="text"
            className="inp"
            placeholder="#HEX"
            value={hex}
            onChange={(e) => handleHexChange(e.target.value)}
            style={{ height: 24, fontSize: 12, width: 90, fontFamily: "var(--mono)" }}
          />
          {color.role && <span style={{ fontSize: 11, background: "var(--line)", padding: "2px 6px", borderRadius: 4, color: "var(--muted)" }}>{color.role}</span>}
        </div>
      </div>
      {onRemove && (
        <button type="button" className="icon-btn" onClick={onRemove} title="Remove color" style={{ color: "var(--muted)" }}>
          <Icon name="x" size={14} />
        </button>
      )}
    </div>
  );
}

// Usable Asset Upload Control replacing confusing filename text inputs
export function FileUploadField({ onFileSelect, file, accept = "image/*,.pdf,.svg", label = "Upload Asset", hint = "Upload logo, product render, or guideline PDF" }) {
  const fileInputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);

  const handleFiles = (files) => {
    if (!files || !files[0]) return;
    const selected = files[0];
    const isImage = selected.type.startsWith("image/");
    const reader = new FileReader();
    reader.onload = (e) => {
      onFileSelect({
        name: selected.name,
        size: selected.size,
        type: selected.type,
        url: isImage ? e.target.result : null,
      });
    };
    reader.readAsDataURL(selected);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {label && <span className="field-l">{label}</span>}
      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
        style={{ display: "none" }}
        onChange={(e) => handleFiles(e.target.files)}
      />
      {file ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 14px", border: "1px solid var(--line)", background: "var(--panel2)", borderRadius: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {file.url ? (
              <img src={file.url} alt={file.name} style={{ width: 44, height: 44, objectFit: "contain", borderRadius: 6, background: "rgba(255,255,255,0.05)", border: "1px solid var(--line)" }} />
            ) : (
              <div style={{ width: 44, height: 44, display: "grid", placeItems: "center", background: "var(--line)", borderRadius: 6 }}>
                <Icon name="file" size={20} />
              </div>
            )}
            <div>
              <div style={{ fontWeight: 600, fontSize: 13.5, color: "var(--fg)" }}>{file.name}</div>
              <div style={{ fontSize: 11.5, color: "var(--muted)" }}>
                {file.size ? `${Math.round(file.size / 1024)} KB` : "Attached file"}
              </div>
            </div>
          </div>
          <span style={{ display: "flex", gap: 6 }}>
            <button type="button" className="btn" style={{ height: 32, fontSize: 12.5 }} onClick={() => fileInputRef.current && fileInputRef.current.click()}>
              Replace
            </button>
            <button type="button" className="btn" style={{ height: 32, fontSize: 12.5 }} onClick={() => onFileSelect(null)}>
              Remove
            </button>
          </span>
        </div>
      ) : (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files); }}
          onClick={() => fileInputRef.current?.click()}
          style={{
            border: dragOver ? "2px dashed var(--accent)" : "1px dashed var(--line)",
            background: dragOver ? "color-mix(in srgb, var(--accent) 5%, transparent)" : "var(--panel2)",
            borderRadius: 10,
            padding: "20px 16px",
            textAlign: "center",
            cursor: "pointer",
            transition: "all 0.15s ease",
          }}
        >
          <Icon name="upload" size={24} style={{ color: "var(--accent)", marginBottom: 8 }} />
          <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--fg)" }}>Click to browse or drop file here</div>
          <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>{hint}</div>
        </div>
      )}
    </div>
  );
}
