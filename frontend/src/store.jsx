import React, { createContext, useContext, useEffect, useReducer, useRef } from "react";
import { SEED_BRANDS, SEED_PROFILE, buildSeedSubmissions, seedChangelog } from "./engine/seed.js";
import { API_CONFIGURED, ApiError, apiFetch, setActor, fromSrvBrand, toSrvBrand, toSrvProduct, fromSrvProduct, fromSrvSuggestion, fromSrvSubmission } from "./api.js";

const KEY = "codeblooded.brandgov.v3";
const USER_KEY = "codeblooded.user.identity";
const Ctx = createContext(null);

const defaultUser = {
  name: "",
  role: "creator",
  onboarded: false,
};

function loadUser() {
  try {
    const raw = localStorage.getItem(USER_KEY);
    if (raw) {
      const u = JSON.parse(raw);
      if (u && u.name) return { ...u, onboarded: true };
    }
  } catch {
    /* ignore */
  }
  return defaultUser;
}

function fresh() {
  const user = loadUser();
  // With a server configured, real data only: never seed sample brands or submissions.
  const brands = API_CONFIGURED ? [] : SEED_BRANDS;
  const activeBrand = brands[0] || null;
  const activeProduct = activeBrand && activeBrand.products && activeBrand.products[0] ? activeBrand.products[0].id : null;

  return {
    user,
    role: user.role || "creator",
    brands,
    activeBrandId: activeBrand ? activeBrand.id : null,
    activeProductId: activeProduct,
    profile: activeBrand,
    changelog: API_CONFIGURED ? [] : seedChangelog(),
    submissions: API_CONFIGURED ? [] : buildSeedSubmissions(),
    suggestions: [],
    editId: null,
    nextId: 1008,
    remote: false,
    ready: !API_CONFIGURED,
    apiError: null,
  };
}

function load() {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      const user = loadUser();
      if (API_CONFIGURED) return fresh();
      const brands = parsed.brands && parsed.brands.length ? parsed.brands : SEED_BRANDS;
      const activeBrandId = parsed.activeBrandId || brands[0].id;
      const profile = brands.find((b) => b.id === activeBrandId) || brands[0];
      return {
        ...parsed,
        user,
        role: user.role || parsed.role || "creator",
        brands,
        activeBrandId,
        profile,
        remote: false,
        ready: !API_CONFIGURED,
        apiError: null,
      };
    }
  } catch {
    /* fallback to fresh */
  }
  return fresh();
}

const now = () => new Date().toISOString();

function reducer(state, a) {
  switch (a.type) {
    case "setUserIdentity": {
      const updatedUser = { ...a.user, id: a.user.id || state.user?.id || (globalThis.crypto?.randomUUID ? crypto.randomUUID() : `u-${Date.now()}-${Math.random().toString(36).slice(2)}`), onboarded: true };
      try {
        localStorage.setItem(USER_KEY, JSON.stringify(updatedUser));
      } catch { /* ignore */ }
      return { ...state, user: updatedUser, role: updatedUser.role };
    }
    case "role": {
      const updatedUser = { ...state.user, role: a.role };
      try {
        localStorage.setItem(USER_KEY, JSON.stringify(updatedUser));
      } catch { /* ignore */ }
      return { ...state, role: a.role, user: updatedUser };
    }
    case "selectBrand": {
      const brand = state.brands.find((b) => b.id === a.brandId) || state.brands[0];
      const prod = brand.products && brand.products.length ? brand.products[0].id : null;
      return {
        ...state,
        activeBrandId: brand.id,
        activeProductId: prod,
        profile: brand,
      };
    }
    case "selectProduct":
      return { ...state, activeProductId: a.productId };
    case "createBrand": {
      const newBrands = [...state.brands, a.brand];
      return {
        ...state,
        brands: newBrands,
        activeBrandId: a.brand.id,
        profile: a.brand,
        activeProductId: a.brand.products && a.brand.products[0] ? a.brand.products[0].id : null,
      };
    }
    case "saveBrand": {
      const updatedBrands = state.brands.map((b) => (b.id === a.brand.id ? a.brand : b));
      const version = (a.brand.version || 1) + 1;
      const savedBrand = { ...a.brand, version, updatedAt: now() };
      return {
        ...state,
        brands: updatedBrands.map((b) => (b.id === savedBrand.id ? savedBrand : b)),
        profile: savedBrand,
        changelog: [
          ...state.changelog,
          { version, at: now(), by: a.by || state.user?.name || "Brand Owner", summary: a.summary || `Updated ${savedBrand.name} fact sheet` },
        ],
      };
    }
    case "saveProduct": {
      const brand = state.brands.find((b) => b.id === a.brandId);
      if (!brand) return state;
      const prods = brand.products || [];
      const exists = prods.some((p) => p.id === a.product.id);
      const nextProds = exists ? prods.map((p) => (p.id === a.product.id ? a.product : p)) : [...prods, a.product];
      const updatedBrand = { ...brand, products: nextProds, updatedAt: now() };
      return {
        ...state,
        brands: state.brands.map((b) => (b.id === brand.id ? updatedBrand : b)),
        profile: state.activeBrandId === brand.id ? updatedBrand : state.profile,
      };
    }
    case "suggestProfile": {
      const sug = {
        id: `SUG-${Date.now().toString(36)}`,
        brandId: a.brandId,
        brandName: a.brandName,
        productId: a.productId || null,
        productName: a.productName || null,
        author: state.user?.name || "Creator",
        role: "creator",
        title: a.title,
        proposed: a.proposed,
        status: "pending",
        at: now(),
      };
      return { ...state, suggestions: [sug, ...state.suggestions] };
    }
    case "decideSuggestion": {
      return {
        ...state,
        suggestions: state.suggestions.map((s) => (s.id === a.id ? { ...s, status: a.status, decidedAt: now(), decidedBy: state.user?.name || "Owner" } : s)),
      };
    }
    case "edit":
      return { ...state, editId: a.id };
    case "reset":
      return { ...fresh(), user: state.user, role: state.role, remote: state.remote, ready: true };
    case "hydrate":
      return { ...state, ...a.data, remote: true, ready: true, apiError: null };
    case "offline":
      return { ...state, remote: false, ready: true };
    case "error":
      return { ...state, apiError: a.message };
    case "replaceSubmission": {
      const exists = state.submissions.some((s) => s.id === a.submission.id);
      return {
        ...state,
        submissions: exists ? state.submissions.map((s) => (s.id === a.submission.id ? a.submission : s)) : [a.submission, ...state.submissions],
        apiError: null,
      };
    }
    case "setProfile":
      return { ...state, profile: a.profile, changelog: a.changelog, apiError: null };
    case "submit": {
      const id = `S-${state.nextId}`;
      const s = {
        ...a.submission,
        id,
        brandId: a.submission.brandId || state.activeBrandId,
        brandName: a.submission.brandName || state.profile.name,
        productId: a.submission.productId || state.activeProductId,
        productName: a.submission.productName || "Brand-level",
        profileVersion: state.profile.version || 1,
      };
      return { ...state, nextId: state.nextId + 1, submissions: [s, ...state.submissions] };
    }
    case "resubmit": {
      const submissions = state.submissions.map((s) => {
        if (s.id !== a.id) return s;
        const n = s.versions.length + 1;
        return {
          ...s,
          ...a.fields,
          status: "in_review",
          updatedAt: now(),
          profileVersion: state.profile.version,
          versions: [...s.versions, { n, content: a.content, at: now(), by: a.by || state.user?.name || "Creator", note: a.note || "Revised" }],
          findings: a.findings,
          activity: [...s.activity, { at: now(), by: a.by || state.user?.name || "Creator", text: `Resubmitted as version ${n}` }],
        };
      });
      return { ...state, submissions };
    }
    case "decide": {
      const label = { approved: "Approved the content", changes_requested: "Requested changes", rejected: "Rejected the content" }[a.status];
      const author = a.by || state.user?.name || (state.role === "owner" ? "Brand Owner" : "Reviewer");
      const submissions = state.submissions.map((s) =>
        s.id !== a.id ? s : {
          ...s,
          status: a.status,
          updatedAt: now(),
          comments: a.comment ? [...s.comments, { id: `${s.id}-c${s.comments.length}`, by: author, role: a.role || state.role, text: a.comment, at: now() }] : s.comments,
          activity: [...s.activity, { at: now(), by: author, text: label }],
        }
      );
      return { ...state, submissions };
    }
    case "comment": {
      const author = a.by || state.user?.name || "User";
      const submissions = state.submissions.map((s) =>
        s.id !== a.id ? s : { ...s, comments: [...s.comments, { id: `${s.id}-c${s.comments.length}`, by: author, role: a.role || state.role, text: a.text, at: now() }] }
      );
      return { ...state, submissions };
    }
    case "recheck": {
      const submissions = state.submissions.map((s) =>
        s.id !== a.id ? s : {
          ...s,
          profileVersion: state.profile.version,
          findings: a.findings,
          activity: [...s.activity, { at: now(), by: a.by || state.user?.name || "Reviewer", text: a.text || "Re-checked against updated brand rules" }],
        }
      );
      return { ...state, submissions };
    }
    default:
      return state;
  }
}

async function remoteAction(a, state) {
  switch (a.type) {
    case "submit": {
      const s = a.submission;
      const body = {
        title: s.title,
        type: s.type,
        audience: s.audience,
        purpose: s.purpose,
        image: s.image,
        content: s.versions[0].content,
        findings: s.findings,
        note: s.comments[0] && s.comments[0].text,
        brandId: s.brandId || state.activeBrandId,
        productId: s.productId || state.activeProductId,
        draft: !!a.draft,
      };
      const { submission } = await apiFetch("POST", "/api/submissions", body);
      return { actions: [{ type: "replaceSubmission", submission: fromSrvSubmission(submission) }], result: { id: submission.id } };
    }
    case "resubmit": {
      const body = { ...a.fields, content: a.content, findings: a.findings, note: a.note };
      const { submission } = await apiFetch("POST", `/api/submissions/${a.id}/versions`, body);
      return { actions: [{ type: "replaceSubmission", submission: fromSrvSubmission(submission) }], result: { id: submission.id } };
    }
    case "startReview": {
      const { submission } = await apiFetch("POST", `/api/submissions/${a.id}/start-review`);
      return { actions: [{ type: "replaceSubmission", submission: fromSrvSubmission(submission) }], result: { id: submission.id } };
    }
    case "submitDraft": {
      const { submission } = await apiFetch("POST", `/api/submissions/${a.id}/submit`, { content: a.content, findings: a.findings });
      return { actions: [{ type: "replaceSubmission", submission: fromSrvSubmission(submission) }], result: { id: submission.id } };
    }
    case "decide": {
      const { submission } = await apiFetch("POST", `/api/submissions/${a.id}/decision`, { status: a.status, comment: a.comment, acknowledged: !!a.acknowledged });
      return { actions: [{ type: "replaceSubmission", submission: fromSrvSubmission(submission) }], result: { id: submission.id } };
    }
    case "comment": {
      const { submission } = await apiFetch("POST", `/api/submissions/${a.id}/comments`, { text: a.text });
      return { actions: [{ type: "replaceSubmission", submission: fromSrvSubmission(submission) }], result: { id: submission.id } };
    }
    case "recheck": {
      const { submission } = await apiFetch("POST", `/api/submissions/${a.id}/recheck`, { text: a.text });
      return { actions: [{ type: "replaceSubmission", submission: fromSrvSubmission(submission) }], result: { id: submission.id } };
    }
    case "saveBrand":
    case "createBrand":
    case "profile": {
      const b = a.brand || a.profile;
      const isNew = a.type === "createBrand" || !state.brands.some((x) => x.id === b.id && x._srv);
      const payload = toSrvBrand(isNew ? { ...b, _srv: undefined, version: undefined } : b, a.summary);
      const { brand } = isNew ? await apiFetch("POST", "/api/brands", payload) : await apiFetch("PUT", `/api/brands/${encodeURIComponent(b.id)}`, payload);
      const cur = state.brands.find((x) => x.id === b.id);
      const saved = { ...fromSrvBrand({ ...brand, products: [] }), products: cur && !isNew ? cur.products : [] };
      const brands = state.brands.some((x) => x.id === b.id) ? state.brands.map((x) => (x.id === b.id ? saved : x)) : [...state.brands, saved];
      const data = { brands, profile: saved, activeBrandId: saved.id };
      return { actions: [{ type: "hydrate", data }], result: { version: saved.version, id: saved.id } };
    }
    case "saveProduct": {
      const cur = state.brands.find((x) => x.id === a.brandId);
      if (!cur) return null;
      const isNew = !(a.product._srv && a.product.version);
      const payload = toSrvProduct(a.product);
      const { product } = isNew ? await apiFetch("POST", `/api/brands/${encodeURIComponent(a.brandId)}/products`, payload)
        : await apiFetch("PUT", `/api/brands/${encodeURIComponent(a.brandId)}/products/${encodeURIComponent(a.product.id)}`, payload);
      const saved = fromSrvProduct(product);
      const products = isNew ? [...cur.products, saved] : cur.products.map((p) => (p.id === saved.id ? saved : p));
      const updated = { ...cur, products };
      const brands = state.brands.map((x) => (x.id === cur.id ? updated : x));
      return { actions: [{ type: "hydrate", data: { brands, profile: state.activeBrandId === cur.id ? updated : state.profile, activeProductId: saved.id } }], result: { id: saved.id } };
    }
    case "suggestProfile": {
      const { suggestion } = await apiFetch("POST", "/api/suggestions", { brandId: a.brandId, productId: a.productId || null, title: a.title, proposal: a.proposed });
      return { actions: [{ type: "hydrate", data: { suggestions: [fromSrvSuggestion(suggestion), ...state.suggestions] } }], result: { id: suggestion.id } };
    }
    case "decideSuggestion": {
      const { suggestion } = await apiFetch("POST", `/api/suggestions/${encodeURIComponent(a.id)}/resolve`, { status: a.status === "approved" ? "accepted" : "dismissed" });
      return { actions: [{ type: "hydrate", data: { suggestions: state.suggestions.map((x) => (x.id === a.id ? fromSrvSuggestion(suggestion) : x)) } }], result: {} };
    }
    case "loadDemo": {
      await apiFetch("POST", "/api/demo/load");
      const data = await apiFetch("GET", "/api/bootstrap");
      return { actions: [{ type: "hydrate", data: bootData(data, state) }], result: {} };
    }
    default:
      return null;
  }
}

function bootData(d, state) {
  const brands = (d.brands || []).map(fromSrvBrand);
  const active = brands.find((b) => b.id === state.activeBrandId) || brands[0] || null;
  const product = active && active.products.find((p) => p.id === state.activeProductId);
  return {
    brands, profile: active, activeBrandId: active ? active.id : null, activeProductId: product ? product.id : null, changelog: [],
    suggestions: (d.suggestions || []).map(fromSrvSuggestion), submissions: (d.submissions || []).map(fromSrvSubmission),
  };
}

export function StoreProvider({ children }) {
  const [state, rawDispatch] = useReducer(reducer, undefined, load);
  const ref = useRef(state);
  ref.current = state;

  useEffect(() => {
    setActor({
      role: state.role || state.user?.role || "creator",
      name: state.user?.name || "",
      id: state.user?.id || "",
    });
  }, [state.role, state.user]);

  useEffect(() => {
    if (!API_CONFIGURED) return;
    if (!state.user?.name) { rawDispatch({ type: "offline" }); return; }
    let alive = true;
    apiFetch("GET", "/api/bootstrap")
      .then((d) => alive && rawDispatch({ type: "hydrate", data: bootData(d, ref.current) }))
      .catch(() => alive && rawDispatch({ type: "offline" }));
    return () => { alive = false; };
  }, [state.user?.name, state.role]);

  useEffect(() => {
    if (state.remote) return;
    try {
      localStorage.setItem(KEY, JSON.stringify({ ...state, apiError: null }));
    } catch {
      /* ignore */
    }
  }, [state]);

  async function dispatch(a) {
    const s = ref.current;
    if (!s.remote || !["submit", "resubmit", "startReview", "submitDraft", "decide", "comment", "recheck", "profile", "saveBrand", "createBrand", "saveProduct", "suggestProfile", "decideSuggestion", "loadDemo"].includes(a.type)) {
      const result = a.type === "submit" ? { id: `S-${s.nextId}` } : {};
      rawDispatch(a);
      return result;
    }
    try {
      const out = await remoteAction(a, s);
      if (out && out.actions) {
        out.actions.forEach((x) => rawDispatch(x));
        return out.result;
      }
      rawDispatch(a);
      return {};
    } catch (e) {
      if (e instanceof ApiError) {
        const detail = e.data && e.data.blockers ? ` (${e.data.blockers.map((b) => b.label).join(", ")})` : "";
        rawDispatch({ type: "error", message: e.message + detail });
        return null;
      }
      rawDispatch({ type: "error", message: "Could not reach the server. Check your connection and try again." });
      return null;
    }
  }

  return <Ctx.Provider value={{ state, dispatch }}>{children}</Ctx.Provider>;
}

export const useStore = () => useContext(Ctx);
