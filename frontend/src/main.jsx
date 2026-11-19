import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { StoreProvider } from "./store.jsx";
import "./styles.css";

try { document.documentElement.dataset.theme = localStorage.getItem("bgp.theme") || "lime"; } catch { document.documentElement.dataset.theme = "lime"; }

createRoot(document.getElementById("root")).render(
  <StoreProvider>
    <App />
  </StoreProvider>
);
