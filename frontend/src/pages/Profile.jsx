import React, { useMemo, useState } from "react";
import Icon from "../components/Icon.jsx";
import { Field, PageHead, Pill, ColorPickerField, FileUploadField, AssetList } from "../components/ui.jsx";
import VersionHistory from "../components/VersionHistory.jsx";
import FactSheetAssistant from "../components/FactSheetAssistant.jsx";
import { useStore } from "../store.jsx";
import { findConflicts } from "../engine/checker.js";
import { timeAgo } from "../util.js";
import { assetUrl, uploadAsset, API_CONFIGURED } from "../api.js";

const clone = (o) => JSON.parse(JSON.stringify(o));
const list = (s) => (s || "").split(",").map((x) => x.trim()).filter(Boolean);
const lines = (s) => (s || "").split("\n").map((x) => x.trim()).filter(Boolean);

export default function Profile() {
  const { state, dispatch } = useStore();
  const { brands, activeBrandId, role, changelog } = state;
  const isOwner = role === "owner" || role === "manager";
  const isCreator = role === "creator";

  const activeBrand = brands.find((b) => b.id === activeBrandId) || brands[0];

  const [d, setD] = useState(() => clone(activeBrand));
  const [activeTab, setActiveTab] = useState("overview"); // "overview", "products", "rules", "visuals", "history"
  const [showAssistant, setShowAssistant] = useState(false);
  const [showNewBrandModal, setShowNewBrandModal] = useState(false);
  const [showProductModal, setShowProductModal] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [showSuggestModal, setShowSuggestModal] = useState(false);
  const [suggestionText, setSuggestionText] = useState("");
  const [savedMsg, setSavedMsg] = useState("");

  // Update working state when switching brands
  const handleSelectBrand = (brandId) => {
    dispatch({ type: "selectBrand", brandId });
    const b = brands.find((x) => x.id === brandId) || brands[0];
    setD(clone(b));
    setSavedMsg("");
  };

  const conflicts = useMemo(() => findConflicts(d), [d]);

  const handleSaveBrand = async () => {
    if (!isOwner) return;
    await dispatch({
      type: "saveBrand",
      brand: d,
      summary: `Updated ${d.name} brand fact sheet and specifications`,
    });
    setSavedMsg("Brand profile saved successfully! Version bumped.");
    setTimeout(() => setSavedMsg(""), 3500);
  };

  const handleAddProduct = (prodData) => {
    const brandId = d.id;
    const prodId = prodData.id || `p-${Date.now().toString(36)}`;
    const product = { ...prodData, id: prodId, brandId };
    dispatch({ type: "saveProduct", brandId, product });
    setD((prev) => {
      const existing = prev.products || [];
      const idx = existing.findIndex((p) => p.id === product.id);
      const nextProds = idx >= 0 ? existing.map((p, i) => (i === idx ? product : p)) : [...existing, product];
      return { ...prev, products: nextProds };
    });
    setShowProductModal(false);
    setEditingProduct(null);
  };

  const handleSuggest = (e) => {
    e.preventDefault();
    if (!suggestionText.trim()) return;
    dispatch({
      type: "suggestProfile",
      brandId: d.id,
      brandName: d.name,
      title: `Creator suggestion for ${d.name}`,
      proposed: suggestionText.trim(),
    });
    setShowSuggestModal(false);
    setSuggestionText("");
    alert("Suggestion submitted to Brand Owner! Reviewers and Owners can view and approve it in the Approvals tab.");
  };

  return (
    <div className="setup">
      <PageHead eyebrow="Multi-Brand Governance Studio" title="Brand Fact Sheets & Specifications">
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          {isCreator && (
            <button className="btn" onClick={() => setShowSuggestModal(true)}>
              <Icon name="edit" size={15} /> Suggest Profile Changes
            </button>
          )}
          <button className="btn" onClick={() => setShowAssistant(true)}>
            <Icon name="sparkles" size={15} /> AI Fact-Sheet Assistant
          </button>
          {isOwner && (
            <button className="btn btn-primary" onClick={handleSaveBrand}>
              <Icon name="check" size={16} /> Save Changes (v{(d.version || 1) + 1})
            </button>
          )}
        </div>
      </PageHead>

      {/* Brand Switcher Bar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 12, padding: "10px 16px", marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, overflowX: "auto" }}>
          <span style={{ fontSize: 12.5, fontWeight: 700, textTransform: "uppercase", color: "var(--muted)", marginRight: 6 }}>
            Saved Brands:
          </span>
          {brands.map((b) => (
            <button
              key={b.id}
              className={`btn ${b.id === d.id ? "btn-primary" : ""}`}
              style={{ height: 32, fontSize: 13, padding: "0 14px" }}
              onClick={() => handleSelectBrand(b.id)}
            >
              {b.name} <span style={{ opacity: 0.7, fontSize: 11 }}>v{b.version || 1}</span>
            </button>
          ))}
          {isOwner && (
            <button className="btn" style={{ height: 32, fontSize: 12.5 }} onClick={() => setShowNewBrandModal(true)}>
              <Icon name="plus" size={14} /> New Brand
            </button>
          )}
        </div>

        {savedMsg && <span className="ok-txt" style={{ fontSize: 13 }}><Icon name="check" size={14} /> {savedMsg}</span>}
      </div>

      {/* Permissions Notification for Creator/Reviewer */}
      {!isOwner && (
        <div style={{ background: "color-mix(in srgb, var(--accent) 8%, transparent)", border: "1px solid color-mix(in srgb, var(--accent) 25%, transparent)", borderRadius: 10, padding: "10px 16px", marginBottom: 18, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ fontSize: 13 }}>
            <Icon name="shield" size={15} style={{ color: "var(--accent)", marginRight: 8, verticalAlign: "middle" }} />
            <b>{role === "creator" ? "Creator Perspective" : "Reviewer Perspective"}:</b> Only Brand Owners can publish official edits. You can view all approved rules, specs, and claims.
          </div>
          {isCreator && (
            <button className="btn sm" onClick={() => setShowSuggestModal(true)}>
              Suggest Change
            </button>
          )}
        </div>
      )}

      {/* Main Studio Navigation Tabs */}
      <div className="tabs" style={{ marginBottom: 16 }}>
        <button className={`tab ${activeTab === "overview" ? "on" : ""}`} onClick={() => setActiveTab("overview")}>
          Brand Overview & Logo
        </button>
        <button className={`tab ${activeTab === "products" ? "on" : ""}`} onClick={() => setActiveTab("products")}>
          Product Fact Sheets ({d.products?.length || 0})
        </button>
        <button className={`tab ${activeTab === "visuals" ? "on" : ""}`} onClick={() => setActiveTab("visuals")}>
          Visual Identity & Palette
        </button>
        <button className={`tab ${activeTab === "history" ? "on" : ""}`} onClick={() => setActiveTab("history")}>
          Version Changelog
        </button>
      </div>

      {/* TAB 1: Brand Overview & Logo */}
      {activeTab === "overview" && (
        <section className="panel" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="panel-h">
            <h2>{d.name} Brand Fact Sheet</h2>
            <Pill tone="ok">Version {d.version || 1}</Pill>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr", gap: 16 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <Field label="Brand Name">
                <input
                  className="inp"
                  value={d.name || ""}
                  disabled={!isOwner}
                  onChange={(e) => setD({ ...d, name: e.target.value })}
                />
              </Field>

              <Field label="Brand Description & Purpose" hint="Overview of what the brand represents">
                <textarea
                  className="inp"
                  rows={3}
                  value={d.description || ""}
                  disabled={!isOwner}
                  onChange={(e) => setD({ ...d, description: e.target.value })}
                />
              </Field>

              <Field label="Tagline">
                <input className="inp" value={d.tagline || ""} disabled={!isOwner} onChange={(e) => setD({ ...d, tagline: e.target.value })} />
              </Field>
              <Field label="Industry">
                <input className="inp" value={d.industry || ""} disabled={!isOwner} onChange={(e) => setD({ ...d, industry: e.target.value })} />
              </Field>
              <Field label="Brand History" hint="Milestones and timeline">
                <textarea className="inp" rows={3} value={d.history || ""} disabled={!isOwner} onChange={(e) => setD({ ...d, history: e.target.value })} />
              </Field>
              <Field label="Brand Values" hint="Comma-separated">
                <input className="inp" value={d.valuesText || ""} disabled={!isOwner} onChange={(e) => setD({ ...d, valuesText: e.target.value })} />
              </Field>
              <Field label="Target Audience">
                <textarea className="inp" rows={2} value={d.targetAudience || ""} disabled={!isOwner} onChange={(e) => setD({ ...d, targetAudience: e.target.value })} />
              </Field>
              <Field label="Brand Voice" hint="How the brand speaks">
                <textarea className="inp" rows={2} value={d.voiceText || ""} disabled={!isOwner} onChange={(e) => setD({ ...d, voiceText: e.target.value })} />
              </Field>

              <Field label="Heritage & Origin" hint="Founding story, country of origin, and heritage">
                <textarea
                  className="inp"
                  rows={2}
                  value={d.heritage || ""}
                  disabled={!isOwner}
                  onChange={(e) => setD({ ...d, heritage: e.target.value })}
                />
              </Field>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <FileUploadField
                label="Primary Brand Logo"
                hint="Upload, replace or remove the official logo (PNG, SVG, JPEG; preview shown)"
                file={d.logoUrl || d.logo ? { name: `${d.name} logo`, url: d.logoUrl || (d.logo && d.logo.length > 1 ? d.logo : null) } : null}
                onFileSelect={async (f) => {
                  if (!isOwner) return;
                  if (!f) { setD({ ...d, logoAssetId: "", logoUrl: null }); return; }
                  if (!API_CONFIGURED) { setD({ ...d, logoUrl: f.url }); return; }
                  try {
                    const up = await uploadAsset(f, "logo");
                    setD((cur) => ({ ...cur, logoAssetId: up.assetId, logoUrl: assetUrl(up.assetId) }));
                  } catch (e) { setSavedMsg(e.message || "Upload failed"); }
                }}
              />

              <Field label="Tone & Personality" hint="Comma-separated personality traits">
                <input
                  className="inp"
                  value={(d.voice || []).join(", ")}
                  disabled={!isOwner}
                  onChange={(e) => setD({ ...d, voice: list(e.target.value) })}
                />
              </Field>

              <Field label="Tone Description">
                <textarea
                  className="inp"
                  rows={2}
                  value={d.tone || ""}
                  disabled={!isOwner}
                  onChange={(e) => setD({ ...d, tone: e.target.value })}
                />
              </Field>
            </div>
          </div>
        </section>
      )}

      {/* TAB 2: Product Fact Sheets */}
      {activeTab === "products" && (
        <section className="panel">
          <div className="panel-h" style={{ marginBottom: 16 }}>
            <div>
              <h2>Products Under {d.name}</h2>
              <span className="muted small">Each product maintains its own independent fact sheet and specifications</span>
            </div>
            {isOwner && (
              <button
                className="btn btn-primary sm"
                onClick={() => {
                  setEditingProduct({ name: "", previousName: "", specifications: "", approvedClaims: [], restrictedClaims: [], terminology: [] });
                  setShowProductModal(true);
                }}
              >
                <Icon name="plus" size={14} /> Add Product Fact Sheet
              </button>
            )}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 14 }}>
            {(d.products || []).map((prod) => (
              <div
                key={prod.id}
                style={{
                  background: "var(--panel2)",
                  border: "1px solid var(--line)",
                  borderRadius: 12,
                  padding: "16px 20px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 12,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div>
                    <h3 style={{ margin: 0, fontSize: 17, color: "var(--fg)" }}>{prod.name}</h3>
                    {prod.previousName && (
                      <span className="muted small" style={{ color: "var(--warn)" }}>
                        Formerly known as: <b>{prod.previousName}</b> (disallowed in live copy)
                      </span>
                    )}
                  </div>
                  {isOwner && (
                    <button
                      className="btn sm"
                      onClick={() => {
                        setEditingProduct(clone(prod));
                        setShowProductModal(true);
                      }}
                    >
                      <Icon name="edit" size={13} /> Edit Fact Sheet
                    </button>
                  )}
                </div>

                {prod.imageUrl && <img src={prod.imageUrl} alt={prod.name} style={{ maxHeight: 120, maxWidth: "100%", objectFit: "contain", alignSelf: "flex-start", borderRadius: 8 }} />}
                {prod.description && <div style={{ fontSize: 13.5 }}>{prod.description}</div>}
                {(prod.assetList || []).length > 0 && <div className="muted small">Documents: {(prod.assetList || []).map((a) => a.name).join(", ")}</div>}
                <div style={{ fontSize: 13.5, color: "var(--fg)", lineHeight: 1.5 }}>
                  <b>Specifications:</b> {prod.specifications || "No specifications listed."}
                </div>

                {prod.approvedClaims && prod.approvedClaims.length > 0 && (
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", color: "var(--ok)", marginBottom: 4 }}>
                      Verified Claims & Evidence ({prod.approvedClaims.length})
                    </div>
                    <ul style={{ margin: "0 0 0 16px", padding: 0, fontSize: 13, color: "var(--muted)" }}>
                      {prod.approvedClaims.map((c, i) => (
                        <li key={i}><b style={{ color: "var(--fg)" }}>{c.claim}</b> — <i>{c.source}</i></li>
                      ))}
                    </ul>
                  </div>
                )}

                {prod.restrictedClaims && prod.restrictedClaims.length > 0 && (
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", color: "var(--bad)", marginBottom: 4 }}>
                      Restricted Claims ({prod.restrictedClaims.length})
                    </div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {prod.restrictedClaims.map((r, i) => (
                        <span key={i} style={{ background: "color-mix(in srgb, var(--bad) 12%, transparent)", color: "var(--bad)", padding: "3px 8px", borderRadius: 6, fontSize: 12 }}>
                          {r}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* TAB 3: Claims & Terminology */}
      {activeTab === "claims" && (
        <section className="panel" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div className="panel-h">
            <h2>Approved Claims & Brand Terminology</h2>
            <span className="muted small">Content is audited against these verified facts</span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            {/* Approved Claims */}
            <div style={{ background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 10, padding: 14 }}>
              <div style={{ fontWeight: 700, fontSize: 14, color: "var(--ok)", marginBottom: 10 }}>
                Approved Claims (with Citations)
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, display: "flex", flexDirection: "column", gap: 8 }}>
                {(d.approvedClaims || []).map((c, i) => (
                  <li key={i}>
                    <div style={{ fontWeight: 600, color: "var(--fg)" }}>{typeof c === "string" ? c : c.claim}</div>
                    {typeof c === "object" && c.source && (
                      <div className="muted small" style={{ fontSize: 11.5 }}>Source: {c.source}</div>
                    )}
                  </li>
                ))}
              </ul>
            </div>

            {/* Restricted Claims */}
            <div style={{ background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 10, padding: 14 }}>
              <div style={{ fontWeight: 700, fontSize: 14, color: "var(--bad)", marginBottom: 10 }}>
                Restricted / Prohibited Claims
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, display: "flex", flexDirection: "column", gap: 8, color: "var(--bad)" }}>
                {(d.restrictedClaims || []).map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          </div>

          {/* Terminology Rules Table */}
          <div>
            <h3 style={{ fontSize: 15, marginBottom: 8 }}>Brand Terminology Rules</h3>
            <div className="table-wrap">
              <table className="tbl">
                <thead>
                  <tr><th>Avoid / Deprecated</th><th>Preferred Term</th><th>Severity</th><th>Guideline Reason</th></tr>
                </thead>
                <tbody>
                  {(d.terminology || []).map((t, i) => (
                    <tr key={i}>
                      <td><span style={{ color: "var(--bad)", fontWeight: 600 }}>{t.from}</span></td>
                      <td><span style={{ color: "var(--ok)", fontWeight: 600 }}>{t.to}</span></td>
                      <td>
                        <span style={{ textTransform: "uppercase", fontSize: 11, fontWeight: 700, color: t.strictness === "critical" ? "var(--bad)" : "var(--warn)" }}>
                          {t.strictness || "warning"}
                        </span>
                      </td>
                      <td className="small">{t.why}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {/* TAB 4: Visual Identity & Color Palette */}
      {activeTab === "visuals" && (
        <section className="panel">
          <div className="panel-h">
            <h2>Visual Identity & Colour Palette</h2>
            <span className="muted small">Interactive color pickers and approved typography</span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 20 }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                <span style={{ fontWeight: 600, fontSize: 13.5 }}>Brand Colour Palette</span>
                {isOwner && (
                  <button
                    className="btn sm"
                    onClick={() => {
                      const nextPal = [...(d.palette || []), { name: "New Accent", hex: "#1FAA8C", role: "Accent" }];
                      setD({ ...d, palette: nextPal });
                    }}
                  >
                    <Icon name="plus" size={13} /> Add Colour
                  </button>
                )}
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {(d.palette || []).map((c, i) => (
                  <ColorPickerField
                    key={i}
                    color={c}
                    onChange={(updated) => {
                      if (!isOwner) return;
                      const nextPal = d.palette.map((x, idx) => (idx === i ? updated : x));
                      setD({ ...d, palette: nextPal });
                    }}
                    onRemove={isOwner ? () => {
                      setD({ ...d, palette: d.palette.filter((_, idx) => idx !== i) });
                    } : null}
                  />
                ))}
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <Field label="Approved Fonts" hint="Official brand typefaces">
                <input
                  className="inp"
                  value={(d.fonts || []).join(", ")}
                  disabled={!isOwner}
                  onChange={(e) => setD({ ...d, fonts: list(e.target.value) })}
                />
              </Field>

              <AssetList
                label="Logo variations & other brand assets"
                items={d.assetList || []} canEdit={isOwner && API_CONFIGURED} upload={uploadAsset} urlFor={assetUrl}
                kinds={[["logo", "Logo variation"], ["image", "Image"], ["guideline", "Guideline document"], ["other", "Other"]]}
                onChange={(items) => setD({ ...d, assetList: items })}
              />

              <Field label="Deprecated / Retired Asset Names" hint="Files flagged if detected">
                <textarea
                  className="inp"
                  rows={2}
                  value={(d.deprecatedAssets || []).join("\n")}
                  disabled={!isOwner}
                  onChange={(e) => setD({ ...d, deprecatedAssets: lines(e.target.value) })}
                />
              </Field>
            </div>
          </div>
        </section>
      )}

      {/* TAB 5: History */}
      {activeTab === "history" && (
        <section className="panel">
          <div className="panel-h"><h2>Version history</h2></div>
          {API_CONFIGURED && activeBrand._srv ? (
            <VersionHistory base={`/api/brands/${activeBrand.id}`} canRestore={role === "owner"} currentVersion={activeBrand.version}
              onRestored={() => { setSavedMsg("Restored as a new version. Reloading…"); setTimeout(() => window.location.reload(), 700); }} />
          ) : (
            <ol className="timeline">
              {[...changelog].reverse().map((c) => (
                <li key={c.version}><span className="tl-dot" /><div><b>Version {c.version}</b> <span className="muted small">· {c.by} · {timeAgo(c.at)}</span><p>{c.summary}</p></div></li>
              ))}
            </ol>
          )}
        </section>
      )}

      {/* New Brand Modal */}
      {showNewBrandModal && (
        <div className="modal-bg" onClick={() => setShowNewBrandModal(false)}>
          <div className="modal" style={{ maxWidth: 480 }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h2 className="serif">Create Independent Brand Profile</h2>
              <button className="icon-btn" onClick={() => setShowNewBrandModal(false)}><Icon name="x" /></button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.target;
                const name = form.brandName.value.trim();
                const desc = form.brandDesc.value.trim();
                if (!name) return;
                const id = name.toLowerCase().replace(/[^a-z0-9]+/g, "-");
                const newB = {
                  id,
                  name,
                  description: desc,
                  voice: ["clear", "professional"],
                  palette: [{ name: "Brand Primary", hex: "var(--accent)", role: "Primary" }],
                  fonts: ["Inter"],
                  approvedClaims: [],
                  restrictedClaims: [],
                  terminology: [],
                  products: [],
                  version: 1,
                  updatedAt: new Date().toISOString(),
                };
                dispatch({ type: "createBrand", brand: newB });
                setD(newB);
                setShowNewBrandModal(false);
              }}
              style={{ display: "flex", flexDirection: "column", gap: 14 }}
            >
              <Field label="Brand Name">
                <input name="brandName" className="inp" placeholder="e.g. Acme, McLaren, Patagonia" required autoFocus />
              </Field>
              <Field label="Brand Description">
                <textarea name="brandDesc" className="inp" rows={3} placeholder="Brief summary of brand mission..." />
              </Field>
              <div className="modal-actions">
                <button type="submit" className="btn btn-primary" style={{ width: "100%", justifyContent: "center" }}>
                  Create Brand Profile
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Product Fact Sheet Modal */}
      {showProductModal && editingProduct && (
        <div className="modal-bg" onClick={() => setShowProductModal(false)}>
          <div className="modal" style={{ maxWidth: 560 }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h2 className="serif">{editingProduct.id ? "Edit Product Fact Sheet" : "Add Product Fact Sheet"}</h2>
              <button className="icon-btn" onClick={() => setShowProductModal(false)}><Icon name="x" /></button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleAddProduct(editingProduct);
              }}
              style={{ display: "flex", flexDirection: "column", gap: 12 }}
            >
              <Field label="Product Name">
                <input
                  className="inp"
                  value={editingProduct.name}
                  onChange={(e) => setEditingProduct({ ...editingProduct, name: e.target.value })}
                  required
                />
              </Field>
              <Field label="Previous Name (if rebranded)" hint="Flagged as outdated in review">
                <input
                  className="inp"
                  value={editingProduct.previousName || ""}
                  placeholder="e.g. Alpha Hydro, Dino"
                  onChange={(e) => setEditingProduct({ ...editingProduct, previousName: e.target.value })}
                />
              </Field>
              <Field label="Specifications & Specs">
                <textarea
                  className="inp"
                  rows={3}
                  value={editingProduct.specifications || ""}
                  placeholder="Dimensions, battery life, materials, engine output..."
                  onChange={(e) => setEditingProduct({ ...editingProduct, specifications: e.target.value })}
                />
              </Field>
              <Field label="Product Description">
                <textarea className="inp" rows={2} value={editingProduct.description || ""} onChange={(e) => setEditingProduct({ ...editingProduct, description: e.target.value })} />
              </Field>
              <Field label="Notes" hint="Internal context for reviewers">
                <textarea className="inp" rows={2} value={editingProduct.notes || ""} onChange={(e) => setEditingProduct({ ...editingProduct, notes: e.target.value })} />
              </Field>
              <FileUploadField
                label="Product Image"
                hint="Shown on the product fact sheet"
                file={editingProduct.imageUrl ? { name: `${editingProduct.name || "Product"} image`, url: editingProduct.imageUrl } : null}
                onFileSelect={async (f) => {
                  if (!f) { setEditingProduct({ ...editingProduct, imageAssetId: "", imageUrl: null }); return; }
                  if (!API_CONFIGURED) return;
                  try { const up = await uploadAsset(f, "image"); setEditingProduct((cur) => ({ ...cur, imageAssetId: up.assetId, imageUrl: assetUrl(up.assetId) })); }
                  catch (e) { setSavedMsg(e.message || "Upload failed"); }
                }}
              />
              <AssetList
                label="Supporting documents & images"
                items={editingProduct.assetList || []} canEdit={API_CONFIGURED} upload={uploadAsset} urlFor={assetUrl}
                kinds={[["guideline", "Supporting document"], ["image", "Image"], ["other", "Other"]]}
                onChange={(items) => setEditingProduct({ ...editingProduct, assetList: items })}
              />
              <div className="modal-actions">
                <button type="submit" className="btn btn-primary" style={{ width: "100%", justifyContent: "center" }}>
                  Save Product Fact Sheet
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Creator Suggestion Modal */}
      {showSuggestModal && (
        <div className="modal-bg" onClick={() => setShowSuggestModal(false)}>
          <div className="modal" style={{ maxWidth: 500 }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div>
                <div className="eyebrow-s">Creator Collaboration</div>
                <h2 className="serif">Suggest Brand Fact Sheet Changes</h2>
              </div>
              <button className="icon-btn" onClick={() => setShowSuggestModal(false)}><Icon name="x" /></button>
            </div>
            <form onSubmit={handleSuggest} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <p className="muted small" style={{ margin: 0 }}>
                Creators cannot alter official brand guidelines directly. Your proposed updates will be routed to the <b>Brand Owner</b> for review.
              </p>
              <Field label="Proposed Rule, Specification, or Claim Update">
                <textarea
                  className="inp"
                  rows={5}
                  placeholder="Describe the requested change, e.g. 'Add new 2026 certification evidence to the Smart Bottle claims'..."
                  value={suggestionText}
                  onChange={(e) => setSuggestionText(e.target.value)}
                  required
                />
              </Field>
              <div className="modal-actions">
                <button type="submit" className="btn btn-primary" style={{ width: "100%", justifyContent: "center" }}>
                  Submit Suggestion to Owner
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* AI Fact-Sheet Assistant Drawer/Modal */}
      {showAssistant && (
        <FactSheetAssistant
          brandName={d.name}
          onClose={() => setShowAssistant(false)}
          onApply={(draft) => {
            handleAddProduct(draft);
          }}
        />
      )}
    </div>
  );
}
