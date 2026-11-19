import React, { useEffect, useState } from "react";
import Icon from "../components/Icon.jsx";
import { navigate } from "../util.js";

const SLIDES = [
  { type: "cited", icon: "link", title: "Findings that cite their source", stat: "Every flag", sub: "Names the guideline, fact or asset behind it", values: [30, 50, 45, 80, 60, 90], pill: "Example" },
  { type: "drift", icon: "chart", title: "Brand Drift Radar", stat: "Fix it once", sub: "Recurring issues grouped across every submission", values: [60, 40, 70, 85, 55] },
  { type: "human", icon: "users", title: "People approve", stat: "100% human", sub: "Nothing publishes without authorised approval", values: [20, 35, 90, 50, 70] },
];

function Bars({ values }) {
  const max = Math.max(...values);
  return (
    <div className="bars" aria-hidden="true">
      {values.map((v, i) => (
        <span key={i} className={i % 2 === 0 ? "bar bar-a" : "bar bar-b"} style={{ height: `${(v / max) * 100}%`, animationDelay: `${i * 70}ms` }} />
      ))}
    </div>
  );
}

function Carousel() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((x) => (x + 1) % SLIDES.length), 4000);
    return () => clearInterval(t);
  }, []);
  const s = SLIDES[i];
  return (
    <div className="carousel">
      <div key={i} className="glass-card slide-in">
        <div className="gc-left">
          <div className="gc-label"><Icon name={s.icon} size={20} className="accent" /> <span>{s.title}</span></div>
          <div className="gc-rule" />
          <h3 className="serif gc-stat">{s.stat}</h3>
          <p className="gc-sub">{s.sub}</p>
          <div className="gc-dots">
            {SLIDES.map((_, k) => <button key={k} aria-label={`Show slide ${k + 1}`} className={k === i ? "dot on" : "dot"} onClick={() => setI(k)} />)}
          </div>
        </div>
        <div className="gc-right">
          {s.pill && <span className="gc-pill">{s.pill}</span>}
          <Bars values={s.values} />
        </div>
      </div>
    </div>
  );
}

const LOOP = [
  ["1", "Create profile", "Guidelines, facts, terms, assets and examples", "Manager"],
  ["2", "Define style", "Voice traits shown through on-brand examples", "Manager"],
  ["3", "Set checks", "Mandatory rules vs flexible guidance", "Manager"],
  ["4", "Submit content", "Text, document, image or link, with purpose", "Creator"],
  ["5", "Review content", "Facts, tone, pattern, visuals, accessibility", "Platform"],
  ["6", "Show findings", "Issue, reason, source and suggested fix", "Platform"],
  ["7", "Suggest or rewrite", "A phrase fix or a full on-brand rewrite", "Platform"],
  ["8", "Revise", "Accept, edit or dismiss, then resubmit", "Creator"],
  ["9", "Approve", "Comment, request changes, approve or reject", "Reviewer"],
  ["10", "Track patterns", "Recurring issues and brand-change impact", "Platform"],
];

export default function Landing() {
  return (
    <section className="landing">
      <div className="hero-video" aria-hidden="true">
        <div className="hero-glow" />
        <video autoPlay loop muted playsInline src="https://cdn.jiro.build/Tanvir/bg/light-rays-1770271561336.mp4" />
      </div>

      <div className="hero-wrap">
        <div className="hero-col">
          <div className="eyebrow fade" style={{ animationDelay: "0s" }}>Source-backed · Explainable · Human-approved</div>
          <h1 className="serif hero-title fade" style={{ animationDelay: ".1s" }}>Brand consistency, checked before it goes live.</h1>
          <p className="hero-sub fade" style={{ animationDelay: ".2s" }}>
            Review any post, ad, email or document against your approved facts, guidelines and assets. Every finding names its source and comes with a fix. People make the final call.
          </p>
          <div className="cta-row fade" style={{ animationDelay: ".3s" }}>
            <button className="btn-hero primary" onClick={() => navigate("/review")}><Icon name="shield" size={18} /> Open the workspace</button>
            <button className="btn-hero secondary" onClick={() => document.getElementById("loop").scrollIntoView({ behavior: "smooth" })}>See how it works</button>
          </div>
        </div>

        <div className="carousel-wrap fade" style={{ animationDelay: ".4s" }}><Carousel /></div>

        <div className="trust fade" style={{ animationDelay: ".8s" }}>
          <div className="trust-item"><span className="ibox"><Icon name="star" size={14} /></span> Mandatory vs flexible rules</div>
          <div className="trust-item">
            <span className="ibox"><Icon name="shield" size={14} /></span>
            <span className="ibox"><Icon name="monitor" size={14} /></span>
            <span className="ibox"><Icon name="phone" size={14} /></span>
            Blogs, social, ads, email, documents
          </div>
          <div className="trust-item"><span className="ibox"><Icon name="lock" size={14} /></span> Prototype uses sample data</div>
        </div>
      </div>

      <div id="loop" className="loop-wrap">
        <div className="eyebrow">How it works</div>
        <h2 className="serif loop-title">Ten steps, one connected loop.</h2>
        <div className="loop-grid">
          {LOOP.map(([n, t, d, who]) => (
            <div key={n} className="loop-card">
              <div className="loop-top"><span className="loop-n">{n}</span><span className={`role-tag role-${who.toLowerCase()}`}>{who}</span></div>
              <h4>{t}</h4>
              <p>{d}</p>
            </div>
          ))}
        </div>
        <div className="loop-cta">
          <button className="btn-hero primary" onClick={() => navigate("/review")}>Try the review workflow <Icon name="arrow" size={16} /></button>
          <span className="muted small">CodeNova 2026 · Team CodeBlooded</span>
        </div>
      </div>
    </section>
  );
}
