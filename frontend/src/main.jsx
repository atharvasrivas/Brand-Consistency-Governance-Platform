import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { StoreProvider } from "./store.jsx";
import "./styles.css";

class Boundary extends React.Component {
  constructor(p) { super(p); this.state = { err: null }; }
  static getDerivedStateFromError(err) { return { err }; }
  render() {
    if (!this.state.err) return this.props.children;
    return (
      <div style={{ padding: 40, maxWidth: 560, margin: "10vh auto", fontFamily: "system-ui" }}>
        <h2>Something went wrong on this page</h2>
        <p>Your saved work is safe and any draft text was autosaved in this browser. Reload to continue.</p>
        <button className="btn btn-primary" onClick={() => location.reload()}>Reload</button>
      </div>
    );
  }
}

try { document.documentElement.dataset.theme = localStorage.getItem("bgp.theme") || "lime"; } catch { document.documentElement.dataset.theme = "lime"; }

createRoot(document.getElementById("root")).render(
  <Boundary>
    <StoreProvider>
      <App />
    </StoreProvider>
  </Boundary>
);
