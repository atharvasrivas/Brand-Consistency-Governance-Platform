// API layer with multi-brand and product context support.
// If VITE_API_URL is set, calls the Flask backend; if the call fails or is unset,
// falls back to the deterministic local rules engine so the platform never blocks.
import { reviewAll, rewriteContent } from "./engine/checker.js";
import { lightFinding } from "./util.js";

const BASE = ((typeof import.meta !== "undefined" && import.meta.env && import.meta.env.VITE_API_URL) || "").replace(/\/$/, "");

export const API_CONFIGURED = !!BASE;

let actor = { role: "creator", name: "", id: "" };
export function setActor(a) { actor = a; }

export class ApiError extends Error {
  constructor(status, message, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

export async function apiFetch(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-User-Role": actor.role,
      "X-User-Name": encodeURIComponent(actor.name || ""),
      "X-User-Id": actor.id || "",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* empty body */
  }
  if (!res.ok) throw new ApiError(res.status, (data && data.error) || `HTTP ${res.status}`, data);
  return data;
}

export const assetUrl = (id) => (id ? `${BASE}/api/assets/${encodeURIComponent(id)}` : null);

// Upload an image/document picked in the browser (data URL) to the server; returns { assetId, name, mime }.
export async function uploadAsset(file, kind = "other") {
  const m = /^data:([^;]+);base64,(.*)$/s.exec(file.url || "");
  if (!m) throw new ApiError(422, "Only image files can be uploaded here");
  return apiFetch("POST", "/api/assets", { name: file.name, mime: m[1], data: m[2], kind });
}

const post = (path, body) => apiFetch("POST", path, body);

// POST /api/review { content, meta, image, brandId, productId, profile, product }
export async function review(payload) {
  if (BASE) {
    try {
      const data = await post("/api/review", {
        content: payload.content,
        meta: payload.meta,
        image: payload.image,
        brandId: payload.brandId,
        productId: payload.productId,
      });
      return { findings: data.findings, engine: "api", notice: data.notice, profileVersion: data.profileVersion };
    } catch (e) {
      if (e instanceof ApiError) return { findings: [], engine: "api", notice: e.message };
      console.warn("Review API unavailable, falling back to local multi-brand rules:", e.message);
    }
  }
  return { findings: reviewAll(payload), engine: "local" };
}

// POST /api/rewrite { content, meta, profile, product, dismissed, brandId, productId }
export async function rewrite(payload) {
  if (BASE) {
    try {
      return {
        ...(await post("/api/rewrite", {
          content: payload.content,
          meta: payload.meta,
          dismissed: payload.dismissed,
          brandId: payload.brandId,
          productId: payload.productId,
        })),
        engine: "api",
      };
    } catch (e) {
      if (e instanceof ApiError) return { text: payload.content, applied: [], skipped: [], engine: "api", notice: e.message };
      console.warn("Rewrite API unavailable, falling back to local rewrite:", e.message);
    }
  }
  return {
    ...rewriteContent(
      payload.content,
      payload.meta,
      payload.profile,
      new Set(payload.dismissed || []),
      payload.product
    ),
    engine: "local",
  };
}

// Re-run checks on a submission's latest version
export async function recheck(submission, profile, product = null) {
  const latest = submission.versions[submission.versions.length - 1];
  const res = await review({
    content: latest.content,
    meta: { type: submission.type, audience: submission.audience, purpose: submission.purpose },
    image: submission.image,
    brandId: submission.brandId,
    productId: submission.productId,
    profile,
    product,
  });
  const prior = new Map((submission.findings || []).map((f) => [f.key, f]));
  const findings = res.findings.map((f) => {
    const p = prior.get(f.key);
    return lightFinding({ ...f, status: p && p.status !== "open" ? p.status : "open", note: p && p.note });
  });
  return { findings, added: findings.filter((f) => !prior.has(f.key)).length };
}

// ---------------------------------------------------------------------------
// Adapter between the UI's brand shape and the API's versioned brand/product records.
// The server record is kept in `_srv` so nothing the UI does not edit (assets, ids, drafts) is lost on save.
// ---------------------------------------------------------------------------
const lines = (t) => String(t || "").split("\n").map((x) => x.trim()).filter(Boolean);
const srcRef = (x) => (typeof x === "string" ? x : (x && x.ref) || "");

function fromSrvTerm(t) {
  return { id: t.id, from: t.avoid, to: t.prefer, strictness: t.strict ? "critical" : "warning", why: "", source: t.source, status: t.status };
}
function toSrvTerm(t) {
  return { id: t.id, avoid: t.from, prefer: t.to, strict: t.strictness === "critical", source: srcRef(t.source), status: t.status === "draft" ? "draft" : "approved" };
}

export function fromSrvProduct(p) {
  return {
    id: p.id, brandId: p.brandId, name: p.name, previousName: (p.previousNames || [])[0] || "", description: p.description || "",
    specifications: (p.specs || []).map((x) => `${x.name}: ${x.value}`).join("\n"),
    approvedClaims: (p.approvedClaims || []).map((c) => ({ id: c.id, claim: c.text, source: c.source, verified: c.status !== "draft" })),
    restrictedClaims: (p.restrictedClaims || []).map((r) => r.text),
    terminology: (p.terminology || []).map(fromSrvTerm), assets: [], version: p.version, demo: !!p.demo, _srv: p,
  };
}

export function toSrvProduct(p) {
  const base = p._srv || {};
  const reason = (t) => ((base.restrictedClaims || []).find((r) => r.text === t) || {}).reason || "";
  return {
    ...base, name: p.name, description: p.description, previousNames: p.previousName ? [p.previousName] : [],
    specs: lines(p.specifications).map((l) => { const i = l.indexOf(":"); return i > 0 ? { name: l.slice(0, i).trim(), value: l.slice(i + 1).trim() } : { name: "Specification", value: l }; }).filter((x) => x.value),
    approvedClaims: (p.approvedClaims || []).map((c) => ({ id: c.id, text: c.claim, source: c.source || "", status: c.verified === false ? "draft" : "approved" })),
    restrictedClaims: (p.restrictedClaims || []).map((t) => ({ text: t, reason: reason(t) })),
    terminology: (p.terminology || []).map(toSrvTerm), version: p.version,
  };
}

export function fromSrvBrand(b) {
  return {
    id: b.id, name: b.name, logo: (b.name || "?").slice(0, 1).toUpperCase(), description: b.description || "", heritage: b.heritage || "",
    personality: (b.personality || []).join(", "), tone: b.toneGuidance || "", voice: b.personality || [],
    approvedClaims: (b.approvedClaims || []).map((c) => ({ id: c.id, claim: c.text, source: c.source, status: c.status, category: "General" })),
    restrictedClaims: (b.restrictedClaims || []).map((r) => r.text),
    terminology: (b.terminology || []).map(fromSrvTerm),
    palette: (b.colours || []).map((c) => ({ name: c.name, hex: c.hex, role: "" })),
    fonts: b.fonts || [], approvedAssets: (b.assets || []).map((a) => a.name), deprecatedAssets: b.deprecatedAssets || [],
    tagline: b.tagline || "", industry: b.industry || "", history: b.history || "", valuesText: (b.values || []).join(", "),
    voiceText: b.voice || "", targetAudience: b.targetAudience || "", logoAssetId: b.logoAssetId || "", logoUrl: assetUrl(b.logoAssetId),
    version: b.version, updatedAt: b.updatedAt, demo: !!b.demo, products: (b.products || []).map(fromSrvProduct), _srv: b,
  };
}

export function toSrvBrand(b, changeNote) {
  const base = b._srv || {};
  const reason = (t) => ((base.restrictedClaims || []).find((r) => r.text === t) || {}).reason || "";
  const personality = Array.isArray(b.voice) && b.voice.length ? b.voice : String(b.personality || "").split(",").map((x) => x.trim()).filter(Boolean);
  return {
    ...base, name: b.name, description: b.description, heritage: b.heritage, personality,
    tagline: b.tagline || "", industry: b.industry || "", history: b.history || "", values: String(b.valuesText || "").split(",").map((x) => x.trim()).filter(Boolean),
    voice: b.voiceText || "", targetAudience: b.targetAudience || "", logoAssetId: b.logoAssetId || "", toneGuidance: b.tone || "",
    approvedClaims: (b.approvedClaims || []).map((c) => ({ id: c.id, text: c.claim, source: c.source || "", status: c.status === "draft" ? "draft" : "approved" })),
    restrictedClaims: (b.restrictedClaims || []).map((t) => ({ text: t, reason: reason(t) })),
    terminology: (b.terminology || []).map(toSrvTerm),
    colours: (b.palette || []).map((c) => ({ name: c.name, hex: c.hex, status: "approved" })),
    fonts: b.fonts || [], deprecatedAssets: b.deprecatedAssets || [], version: b.version, changeNote: changeNote || "",
  };
}

export function fromSrvSuggestion(s) {
  const status = s.status === "dismissed" ? "rejected" : s.status === "accepted" ? "approved" : s.status;
  return { ...s, status, proposed: s.proposal, at: s.createdAt };
}

export function fromSrvSubmission(s) {
  return { ...s, profileVersion: s.brandVersion || s.profileVersion };
}
