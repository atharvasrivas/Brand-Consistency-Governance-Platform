import React, { useState } from "react";
import Icon from "./Icon.jsx";

export default function FactSheetAssistant({ onClose, onApply, brandName = "Nova" }) {
  const [tab, setTab] = useState("qa"); // "qa" or "doc"
  const [name, setName] = useState("");
  const [specs, setSpecs] = useState("");
  const [former, setFormer] = useState("");
  const [claims, setClaims] = useState("");
  const [restricted, setRestricted] = useState("");
  const [docText, setDocText] = useState("");
  const [generated, setGenerated] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleGenerate = (e) => {
    e.preventDefault();
    setLoading(true);
    setTimeout(() => {
      // Deterministic drafting based on inputs
      const prodName = name.trim() || `${brandName} NextGen Product`;
      const draft = {
        name: prodName,
        previousName: former.trim(),
        description: specs.trim() ? `Official product specifications and features for ${prodName}. ${specs.trim()}` : `Next-generation flagship offering under ${brandName}.`,
        specifications: specs.trim() || "Standard enterprise specifications.",
        approvedClaims: claims.split("\n").map(c => c.trim()).filter(Boolean).map(c => ({
          claim: c,
          source: `${prodName} Engineering Fact Sheet`,
          verified: false,
        })),
        restrictedClaims: restricted.split("\n").map(r => r.trim()).filter(Boolean),
        terminology: former.trim() ? [
          { from: former.trim(), to: prodName, strictness: "critical", why: `Rebrand from previous model name ${former.trim()} to ${prodName}.` }
        ] : [],
      };

      if (draft.approvedClaims.length === 0) {
        draft.approvedClaims.push({ claim: "Engineered with certified materials", source: "Lab Spec Test", verified: false });
      }

      setGenerated(draft);
      setLoading(false);
    }, 600);
  };

  return (
    <div className="modal-bg" role="dialog" aria-modal="true" aria-label="AI Fact-Sheet Assistant" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 640 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <div className="eyebrow-s">Fact-Sheet Assistant</div>
            <h2 className="serif" style={{ margin: "4px 0" }}>Draft Product Fact Sheet</h2>
            <p className="muted small" style={{ margin: 0 }}>
              Turns your answers into a structured draft (template-based, no AI model involved). <b>Every item stays a draft until an Owner verifies it.</b>
            </p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <Icon name="x" size={18} />
          </button>
        </div>

        {!generated ? (
          <form onSubmit={handleGenerate} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", gap: 8, borderBottom: "1px solid var(--line)", paddingBottom: 8 }}>
              <button
                type="button"
                className={`tab ${tab === "qa" ? "on" : ""}`}
                onClick={() => setTab("qa")}
                style={{ fontSize: 13 }}
              >
                Guided Questions
              </button>
              <button
                type="button"
                className={`tab ${tab === "doc" ? "on" : ""}`}
                onClick={() => setTab("doc")}
                style={{ fontSize: 13 }}
              >
                Paste Document Notes
              </button>
            </div>

            {tab === "qa" ? (
              <>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <label style={{ fontSize: 13, fontWeight: 600 }}>Product Name</label>
                  <input
                    type="text"
                    className="inp"
                    placeholder="e.g. Nova Smart Bottle, Ferrari 296 GTB"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                  />
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <label style={{ fontSize: 13, fontWeight: 600 }}>Previous / Deprecated Name (if applicable)</label>
                  <input
                    type="text"
                    className="inp"
                    placeholder="e.g. Alpha Hydro, Dino"
                    value={former}
                    onChange={(e) => setFormer(e.target.value)}
                  />
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <label style={{ fontSize: 13, fontWeight: 600 }}>Key Specifications & Engineering Details</label>
                  <textarea
                    className="inp"
                    rows={3}
                    placeholder="e.g. 600ml volume, UV-C LED self-cleaning, 24h cold thermal insulation..."
                    value={specs}
                    onChange={(e) => setSpecs(e.target.value)}
                  />
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <label style={{ fontSize: 13, fontWeight: 600 }}>Verified Marketing Claims (one per line)</label>
                  <textarea
                    className="inp"
                    rows={2}
                    placeholder="e.g. Keeps drinks cold for 24 hours (ISO thermal test)&#10;830 cv total power output"
                    value={claims}
                    onChange={(e) => setClaims(e.target.value)}
                  />
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <label style={{ fontSize: 13, fontWeight: 600 }}>Restricted Claims to Avoid (one per line)</label>
                  <textarea
                    className="inp"
                    rows={2}
                    placeholder="e.g. Cures dehydration&#10;Autonomous self-driving vehicle"
                    value={restricted}
                    onChange={(e) => setRestricted(e.target.value)}
                  />
                </div>
              </>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label style={{ fontSize: 13, fontWeight: 600 }}>Paste Raw Product Notes or Press Release</label>
                <textarea
                  className="inp"
                  rows={8}
                  placeholder="Paste press releases, engineering specs, or internal launch briefs here..."
                  value={docText}
                  onChange={(e) => {
                    setDocText(e.target.value);
                    if (!name) setName(docText.slice(0, 30));
                  }}
                />
              </div>
            )}

            <div className="modal-actions">
              <button type="submit" className="btn btn-primary" disabled={loading} style={{ width: "100%", justifyContent: "center" }}>
                {loading ? "Generating Draft Fact Sheet..." : "Generate Draft Fact Sheet"}
              </button>
            </div>
          </form>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ background: "color-mix(in srgb, var(--warn) 14%, transparent)", border: "1px solid var(--warn)", borderRadius: 8, padding: "10px 14px", color: "var(--fg)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700, color: "var(--warn)", fontSize: 13 }}>
                <Icon name="alert" size={16} /> Draft — Verify Before Approval
              </div>
              <div style={{ fontSize: 12.5, marginTop: 4, color: "var(--muted)" }}>
                AI generated this draft fact sheet. You must review the specifications and verify claim evidence before publishing to the official brand profile.
              </div>
            </div>

            <div style={{ background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 10, padding: 14, display: "flex", flexDirection: "column", gap: 10, maxHeight: 320, overflowY: "auto" }}>
              <div>
                <span className="muted small">Product Name</span>
                <div style={{ fontWeight: 600, fontSize: 15 }}>{generated.name}</div>
              </div>
              {generated.previousName && (
                <div>
                  <span className="muted small">Previous Name (Disallowed)</span>
                  <div style={{ color: "var(--warn)", fontSize: 13 }}>{generated.previousName}</div>
                </div>
              )}
              <div>
                <span className="muted small">Specifications</span>
                <div style={{ fontSize: 13, color: "var(--fg)" }}>{generated.specifications}</div>
              </div>
              <div>
                <span className="muted small">Draft Approved Claims</span>
                <ul style={{ margin: "4px 0 0 16px", padding: 0, fontSize: 13 }}>
                  {generated.approvedClaims.map((c, i) => (
                    <li key={i}>{c.claim} <span className="muted small">({c.source})</span></li>
                  ))}
                </ul>
              </div>
              {generated.restrictedClaims.length > 0 && (
                <div>
                  <span className="muted small">Restricted Claims</span>
                  <ul style={{ margin: "4px 0 0 16px", padding: 0, fontSize: 13, color: "var(--bad)" }}>
                    {generated.restrictedClaims.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </div>
              )}
            </div>

            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => {
                  onApply(generated);
                  onClose();
                }}
              >
                <Icon name="check" size={16} /> Apply Draft to Fact Sheet
              </button>
              <button type="button" className="btn" onClick={() => setGenerated(null)}>
                Revise Answers
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
