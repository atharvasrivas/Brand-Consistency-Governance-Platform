import React from "react";
import Icon from "../components/Icon.jsx";
import { PageHead } from "../components/ui.jsx";
import { API_CONFIGURED } from "../api.js";

const PRINCIPLES = [
  ["1", "Source-grounded", "AI gets only approved material and must cite it. A finding without an approved source is never treated as a verified fact."],
  ["2", "Validated", "The backend checks the structure and sources of every AI response before anyone sees it."],
  ["3", "Uncertainty routed", "Low confidence, visual guesses and conflicting guidelines go to a person instead of being decided automatically."],
  ["4", "People approve", "Nothing is published without authorised approval. Suggestions never apply themselves."],
];

const DISCLOSURE = [
  ["Built-in rules engine", "Runs entirely in your browser. Deterministic checks against the brand profile: terminology, claims, tone, structure and image details. No content leaves your device.", true],
  ["Flask API and Gemini", API_CONFIGURED ? "Connected. Only the context needed for each check is sent to the backend, which holds the API key and calls Gemini." : "Not connected in this build. When connected, the backend holds the Gemini key and sends only the context needed for each check.", API_CONFIGURED],
  ["Image analysis", "Colour and contrast estimates are computed in your browser on a small copy of the image. Visual results can be uncertain, so they are routed to a person.", true],
  ["Local storage", "Submissions, comments and profile changes are stored in this browser for the demo. Use “Reset demo data” in the footer to clear them.", true],
];

export default function Responsible() {
  return (
    <div className="page narrow">
      <PageHead eyebrow="Responsible AI" title="AI suggests. People decide." />
      <div className="resp-grid">
        {PRINCIPLES.map(([n, t, d]) => (
          <div key={n} className="panel resp"><span className="loop-n">{n}</span><div><b>{t}</b><p>{d}</p></div></div>
        ))}
      </div>
      <div className="banner banner-dark"><Icon name="shield" size={18} /><b>An AI finding is never a verified fact unless it points to an approved source.</b></div>
      <section className="panel">
        <div className="panel-h"><h2>What runs where</h2></div>
        {DISCLOSURE.map(([t, d, on]) => (
          <div key={t} className="disc"><span className={on ? "disc-dot on" : "disc-dot"} /><div><b>{t}</b><p className="muted">{d}</p></div></div>
        ))}
        <p className="muted small">The prototype uses sample, non-confidential brand content. Confidential material should only be sent to a service configuration that the organisation has reviewed.</p>
      </section>
    </div>
  );
}
