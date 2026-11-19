import React, { useEffect, useState } from "react";
import Landing from "./pages/Landing.jsx";
import Review from "./pages/Review.jsx";
import Approvals from "./pages/Approvals.jsx";
import Profile from "./pages/Profile.jsx";
import Insights from "./pages/Insights.jsx";
import Responsible from "./pages/Responsible.jsx";
import Governance from "./pages/Governance.jsx";
import Rules from "./pages/Rules.jsx";
import Icon from "./components/Icon.jsx";
import OnboardingModal from "./components/OnboardingModal.jsx";
import { useStore } from "./store.jsx";
import { ROLES } from "./engine/seed.js";
import { navigate } from "./util.js";

const ALL_NAV = [
  { path: "/review", label: "Brand Review", icon: "search", roles: ["creator", "reviewer", "owner"] },
  { path: "/approvals", label: "Approvals", icon: "check", roles: ["reviewer", "owner"] },
  { path: "/insights", label: "Insights", icon: "chart", roles: ["reviewer", "owner"] },
  { path: "/governance", label: "Governance", icon: "shield", roles: ["reviewer", "owner"] },
  { path: "/profile", label: "Brand Profile", icon: "book", roles: ["reviewer", "owner"] },
  { path: "/rules", label: "Rules & Knowledge", icon: "book", roles: ["reviewer", "owner"] },
];

function ThemeSwitch() {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || "lime");
  const pick = (t) => {
    setTheme(t);
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem("bgp.theme", t); } catch { /* preference simply is not remembered */ }
  };
  return (
    <div className="theme-switch" role="group" aria-label="Colour theme">
      <button className={theme === "lime" ? "on" : ""} onClick={() => pick("lime")} aria-pressed={theme === "lime"} title="Midnight Lime">
        <span className="theme-dot" style={{ background: "var(--swatch-lime)" }} /> Lime
      </button>
      <button className={theme === "coral" ? "on" : ""} onClick={() => pick("coral")} aria-pressed={theme === "coral"} title="Navy & Coral">
        <span className="theme-dot" style={{ background: "var(--swatch-coral)" }} /> Coral
      </button>
    </div>
  );
}

function useRoute() {
  const get = () => (window.location.hash.replace(/^#/, "") || "/").split("?")[0];
  const [route, setRoute] = useState(get());
  useEffect(() => {
    const on = () => { setRoute(get()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

function Shell({ route, children, onEditUser }) {
  const { state, dispatch } = useStore();
  const currentRole = state.role || state.user?.role || "creator";
  const pending = state.submissions.filter((s) => s.status === "in_review").length;
  const pendingSuggestions = (state.suggestions || []).filter((s) => s.status === "pending").length;

  const visibleNav = ALL_NAV.filter((n) => n.roles.includes(currentRole));

  return (
    <div className="app">
      <header className="topbar">
        <button className="brand" onClick={() => navigate("/")} aria-label="Home">
          <span className="logo"><Icon name="shield" size={18} /></span>
          <span><b>Brand Governance</b><small>Platform</small></span>
        </button>

        <nav className="nav" aria-label="Main">
          {visibleNav.map((n) => (
            <a key={n.path} href={`#${n.path}`} className={route === n.path ? "nav-a on" : "nav-a"}>
              <Icon name={n.icon} size={16} /> {n.label}
              {n.path === "/approvals" && (pending + pendingSuggestions) > 0 && (
                <span className="badge" title={`${pending} submissions, ${pendingSuggestions} suggestions`}>
                  {pending + pendingSuggestions}
                </span>
              )}
            </a>
          ))}
        </nav>

        <div className="top-right">
          <span
            className={state.remote ? "pill pill-ok" : "pill pill-muted"}
            title={state.remote ? "Connected to the Flask API: data is shared and checks run on the server" : "Running on the built-in multi-brand engine in this browser"}
          >
            {state.remote ? "API connected" : "Local engine"}
          </span>

          <ThemeSwitch />
          {/* Active Brand Badge */}
          <button
            className="btn"
            style={{ height: 32, fontSize: 12, padding: "0 10px", background: "var(--panel2)", border: "1px solid var(--line)", display: "flex", alignItems: "center", gap: 6 }}
            onClick={() => navigate("/profile")}
            title="Active Brand context (click to configure in Brand Profile)"
          >
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--accent)" }} />
            <span>Brand: <b>{state.profile?.name || "None"}</b></span>
          </button>

          {/* Active User Identity & Role Switcher */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <button
              className="btn"
              style={{ height: 32, fontSize: 12.5, padding: "0 12px", background: "color-mix(in srgb, var(--accent) 12%, transparent)", border: "1px solid color-mix(in srgb, var(--accent) 30%, transparent)", color: "var(--fg)" }}
              onClick={onEditUser}
              title="Click to update identity or switch role"
            >
              <span style={{ textTransform: "capitalize", fontWeight: 700, color: "var(--accent)", marginRight: 4 }}>
                {currentRole === "owner" ? "Brand Owner" : currentRole}
              </span>
              · {state.user?.name || "Set Identity"}
            </button>

          </div>
        </div>
      </header>

      {state.apiError && (
        <div className="api-error" role="alert">
          <span>{state.apiError}</span>
          <button className="link-btn" onClick={() => dispatch({ type: "error", message: null })}>Dismiss</button>
        </div>
      )}

      <main className="main">{children}</main>

      <footer className="foot">
        <span>
          CodeNova 2026 · Team CodeBlooded · Multi-Brand Governance Platform ·{" "}
          <a href="#/responsible">Responsible AI</a>
        </span>
        {!state.remote && (
          <button
            className="link-btn"
            onClick={() => {
              if (window.confirm("Reset demo data back to default multi-brand seed profiles?")) dispatch({ type: "reset" });
            }}
          >
            Reset demo data
          </button>
        )}
      </footer>
    </div>
  );
}

function EmptyWorkspace({ role, dispatch }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const isOwner = role === "owner";
  return (
    <div style={{ maxWidth: 560, margin: "60px auto", textAlign: "center", background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 16, padding: 32 }}>
      <h2 className="serif" style={{ marginBottom: 8 }}>No brand profiles yet</h2>
      {isOwner ? (
        <>
          <p className="muted" style={{ fontSize: 14, lineHeight: 1.6 }}>Create your first brand, then add its approved facts under Brand Profile. Nothing is checked against facts nobody has approved.</p>
          <form style={{ display: "flex", gap: 8, justifyContent: "center", margin: "16px 0" }} onSubmit={async (e) => {
            e.preventDefault();
            if (!name.trim()) return;
            setBusy(true);
            await dispatch({ type: "createBrand", brand: { name: name.trim(), description: "", palette: [], fonts: [], approvedClaims: [], restrictedClaims: [], terminology: [], deprecatedAssets: [] } });
            setBusy(false);
          }}>
            <input className="inp" value={name} onChange={(e) => setName(e.target.value)} placeholder="Brand name" aria-label="Brand name" />
            <button className="btn btn-primary" disabled={busy}>Create brand</button>
          </form>
          <button className="link-btn" disabled={busy} onClick={async () => { setBusy(true); await dispatch({ type: "loadDemo" }); setBusy(false); }}>
            Or load a clearly labelled sample brand to explore
          </button>
        </>
      ) : (
        <p className="muted" style={{ fontSize: 14, lineHeight: 1.6 }}>A Brand Owner needs to create a brand profile and approve its facts before content can be reviewed.</p>
      )}
    </div>
  );
}

const roleLabel = (r) => (r === "owner" ? "Brand Owner" : r.charAt(0).toUpperCase() + r.slice(1));

function AccessDenied({ role, needed = "Reviewer or Owner" }) {
  return (
    <div style={{ maxWidth: 600, margin: "60px auto", textAlign: "center", background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 16, padding: "40px 24px" }}>
      <Icon name="shield" size={40} style={{ color: "var(--warn)", marginBottom: 14 }} />
      <h2 className="serif" style={{ marginBottom: 8 }}>Access Restricted for {role} Role</h2>
      <p style={{ color: "var(--muted)", fontSize: 14, lineHeight: 1.6, marginBottom: 20 }}>
        This section is reserved for <b>{needed}</b> roles according to the governance access matrix. Your role can use Brand Review.
      </p>
      <div style={{ display: "flex", justifyContent: "center", gap: 12 }}>
        <button className="btn btn-primary" onClick={() => navigate("/review")}>
          Go to Brand Review
        </button>
      </div>
    </div>
  );
}

export default function App() {
  const route = useRoute();
  const { state, dispatch } = useStore();
  const [showOnboarding, setShowOnboarding] = useState(false);

  const user = state.user || {};
  const currentRole = state.role || user.role || "creator";

  // Force onboarding modal on first visit if user hasn't set their name
  const needsOnboarding = !user.onboarded || !user.name;

  const modal = (needsOnboarding || showOnboarding) && (
    <OnboardingModal
      initialUser={user}
      isEdit={user.onboarded && showOnboarding}
      onClose={() => setShowOnboarding(false)}
      onSave={(u) => {
        dispatch({ type: "setUserIdentity", user: u });
        setShowOnboarding(false);
      }}
    />
  );

  if (!state.ready) return <div className="boot" role="status">Connecting to brand governance engine…</div>;

  if (state.brands.length === 0 && route !== "/" && route !== "/responsible") {
    return <><Shell route={route} onEditUser={() => setShowOnboarding(true)}><EmptyWorkspace role={currentRole} dispatch={dispatch} /></Shell>{modal}</>;
  }

  const renderRoute = () => {
    if (route === "/" || route === "") return <Landing />;
    if (route === "/responsible") return <Responsible />;
    const entry = ALL_NAV.find((n) => n.path === route);
    if (!entry) return <Review />;
    if (!entry.roles.includes(currentRole)) return <AccessDenied role={roleLabel(currentRole)} needed={entry.roles.map(roleLabel).join(" or ")} />;
    const pages = { "/review": Review, "/approvals": Approvals, "/insights": Insights, "/profile": Profile, "/governance": Governance, "/rules": Rules };
    const Page = pages[route];
    return <Page />;
  };

  return (
    <>
      <Shell route={route} onEditUser={() => setShowOnboarding(true)}>
        {renderRoute()}
      </Shell>

      {modal}
    </>
  );
}
