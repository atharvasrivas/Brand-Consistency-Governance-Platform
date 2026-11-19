// Brand and product compliance checker.
// Deterministic rule engine supporting multiple independent brands and product fact sheets.
// Evaluates content strictly against the selected brand and product context.

const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const wordRe = (t, flags) => new RegExp(`(?<![\\w-])${esc(t)}(?![\\w-])`, flags);
const lc = (s) => (s || "").toLowerCase();
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);

function matchCase(orig, repl) {
  const f = orig[0];
  if (f && f === f.toUpperCase() && f !== f.toLowerCase() && repl[0] === repl[0].toLowerCase()) return cap(repl);
  return repl;
}

function contextKey(content, start, end) {
  return content.slice(Math.max(0, start - 20), Math.min(content.length, end + 20)).toLowerCase();
}

function mk(rule, content, start, end, extra) {
  const quote = content.slice(start, end);
  const strictness = extra?.strictness || rule.strictness || "flexible";
  const severity = strictness === "critical" || strictness === "mandatory" ? "critical" : (strictness === "warning" ? "warning" : "suggestion");
  return {
    id: `${rule.id}:${start}`,
    key: `${rule.id}|${quote.toLowerCase()}|${contextKey(content, start, end)}`,
    ruleId: rule.id,
    label: rule.label,
    category: rule.category || "Terminology",
    strictness,
    severity,
    kind: "replace",
    scope: "text",
    start,
    end,
    quote,
    why: rule.why,
    source: rule.source,
    confidence: 0.9,
    ...extra,
  };
}

const PRIORITY = { critical: 4, mandatory: 3, warning: 2, flexible: 1, suggestion: 1 };
const prio = (f) => (f.kind === "conflict" ? 2.5 : PRIORITY[f.strictness] || PRIORITY[f.severity] || 1);

export function runTextChecks(content, meta = {}, profile = {}, product = null) {
  const out = [];
  const brandName = profile.name || profile.brandName || "Brand";

  // 1. Terminology checks from profile.rules (legacy / rule-based)
  const rules = (profile.rules || []).filter((r) => !r.rewriteOnly);
  const termRules = (profile.rules || []).filter((r) => r.kind === "term");

  for (const rule of rules) {
    if (rule.kind === "term" || rule.kind === "tone") {
      for (const [a, b] of rule.pairs || []) {
        for (const m of content.matchAll(wordRe(a, rule.caseSensitive ? "g" : "gi"))) {
          const f = mk(rule, content, m.index, m.index + m[0].length, {
            suggestion: matchCase(m[0], b),
            confidence: rule.kind === "term" ? 0.97 : 0.74,
          });
          if (rule.kind === "term") {
            const other = termRules.find(
              (r2) => r2.id !== rule.id && (r2.pairs || []).some(([x, y]) => lc(y) === lc(a) || lc(x) === lc(b))
            );
            if (other) {
              f.kind = "conflict";
              f.needsHuman = true;
              f.confidence = 0.5;
              f.conflict = { a: rule, b: other };
              f.options = [
                { label: `Follow ${rule.source.doc}: use “${f.suggestion}”`, text: f.suggestion, source: rule.source },
                { label: `Follow ${other.source.doc}: keep “${m[0]}”`, text: null, source: other.source },
              ];
              f.why = `${rule.source.doc} says “${m[0]}” should be “${f.suggestion}”, but ${other.source.doc} says otherwise. Human review required.`;
            }
          }
          out.push(f);
        }
      }
    } else if (rule.kind === "claim") {
      for (const p of rule.patterns || []) {
        for (const m of content.matchAll(new RegExp(p.src, "g" + (p.flags || "")))) {
          out.push(mk(rule, content, m.index, m.index + m[0].length, { suggestion: p.replacement, confidence: 0.92, orSource: true }));
        }
      }
    } else if (rule.kind === "stat") {
      const approved = (rule.approved || []).map((s) => lc(s).replace(/[,\s]/g, ""));
      for (const m of content.matchAll(new RegExp(rule.src, "gi"))) {
        if (approved.includes(lc(m[0]).replace(/[,\s]/g, ""))) continue;
        out.push(mk(rule, content, m.index, m.index + m[0].length, { suggestion: (rule.approved || [])[0] || "", confidence: 0.8, orSource: true }));
      }
    } else if (rule.kind === "caps") {
      const skip = new Set(["HTTP", "HTTPS", "FAQ", "SEO", "CRM", "SAAS", "NEW", "PHEV", "V6", "V8", "LED", "ISO", "USB"]);
      for (const m of content.matchAll(/\b[A-Z]{4,}\b/g)) {
        if (skip.has(m[0])) continue;
        out.push(mk(rule, content, m.index, m.index + m[0].length, { suggestion: cap(m[0].toLowerCase()), confidence: 0.72 }));
      }
    } else if (rule.kind === "link") {
      for (const m of content.matchAll(/\b(click here|read more|learn more here)\b/gi)) {
        out.push(mk(rule, content, m.index, m.index + m[0].length, {
          kind: "advice", suggestion: `Describe the specific destination, for example “Explore ${brandName} specifications”.`, confidence: 0.8,
        }));
      }
    } else if (rule.kind === "structure") {
      out.push(...structureChecks(rule, content, meta, brandName));
    }
  }

  // 2. Multi-brand terminology checks from profile.terminology
  if (Array.isArray(profile.terminology)) {
    for (const term of profile.terminology) {
      if (!term.from || !term.to) continue;
      for (const m of content.matchAll(wordRe(term.from, "gi"))) {
        const r = {
          id: `T-BRAND-${lc(term.from).replace(/\s+/g, "_")}`,
          label: term.strictness === "critical" ? "Disallowed or outdated terminology" : "Preferred terminology",
          category: "Terminology",
          strictness: term.strictness || "warning",
          why: term.why || `${brandName} guidelines prefer “${term.to}” over “${term.from}”.`,
          source: typeof term.source === "string" ? { doc: "Brand Guidelines", ref: term.source } : (term.source || { doc: "Brand Guidelines", ref: "Approved terminology" }),
        };
        out.push(mk(r, content, m.index, m.index + m[0].length, { suggestion: matchCase(m[0], term.to), confidence: 0.95 }));
      }
    }
  }

  // 3. Brand-level restricted claims
  if (Array.isArray(profile.restrictedClaims)) {
    for (const badClaim of profile.restrictedClaims) {
      if (!badClaim.trim()) continue;
      const regex = wordRe(badClaim, "gi");
      for (const m of content.matchAll(regex)) {
        const r = {
          id: `RC-BRAND-${lc(badClaim.slice(0, 15)).replace(/\s+/g, "_")}`,
          label: "Restricted claim violation",
          category: "Facts & claims",
          strictness: "critical",
          why: `This phrase is explicitly blacklisted in the ${brandName} brand fact sheet.`,
          source: { doc: `${brandName} Fact Sheet`, ref: "Restricted claims" },
        };
        out.push(mk(r, content, m.index, m.index + m[0].length, {
          kind: "advice",
          suggestion: "Remove this restricted claim or replace with a verified, approved claim.",
          confidence: 0.98,
        }));
      }
    }
  }

  // 4. Product-level fact sheet checks (when a product is explicitly selected)
  if (product) {
    const prodName = product.name || "Selected Product";
    // Previous product name check (e.g. Alpha Hydro -> Nova Smart Bottle)
    if (product.previousName && product.previousName.trim()) {
      for (const m of content.matchAll(wordRe(product.previousName, "gi"))) {
        const r = {
          id: `T-PREV-${lc(product.previousName).replace(/\s+/g, "_")}`,
          label: "Outdated product name",
          category: "Terminology",
          strictness: "critical",
          why: `“${product.previousName}” is the outdated previous name for ${prodName}.`,
          source: { doc: `${prodName} Fact Sheet`, ref: "Product naming" },
        };
        out.push(mk(r, content, m.index, m.index + m[0].length, { suggestion: prodName, confidence: 0.99 }));
      }
    }

    // Product specific terminology
    if (Array.isArray(product.terminology)) {
      for (const term of product.terminology) {
        if (!term.from || !term.to) continue;
        for (const m of content.matchAll(wordRe(term.from, "gi"))) {
          const r = {
            id: `T-PROD-${lc(term.from).replace(/\s+/g, "_")}`,
            label: "Product terminology guideline",
            category: "Terminology",
            strictness: term.strictness || "warning",
            why: term.why || `In the context of ${prodName}, use “${term.to}”.`,
            source: { doc: `${prodName} Fact Sheet`, ref: "Product terminology" },
          };
          out.push(mk(r, content, m.index, m.index + m[0].length, { suggestion: matchCase(m[0], term.to), confidence: 0.95 }));
        }
      }
    }

    // Product restricted claims
    if (Array.isArray(product.restrictedClaims)) {
      for (const badClaim of product.restrictedClaims) {
        if (!badClaim.trim()) continue;
        for (const m of content.matchAll(wordRe(badClaim, "gi"))) {
          const r = {
            id: `RC-PROD-${lc(badClaim.slice(0, 15)).replace(/\s+/g, "_")}`,
            label: "Restricted product claim",
            category: "Facts & claims",
            strictness: "critical",
            why: `Restricted claim for ${prodName}. Marketing must not make this statement.`,
            source: { doc: `${prodName} Specifications`, ref: "Restricted claims" },
          };
          out.push(mk(r, content, m.index, m.index + m[0].length, {
            kind: "advice",
            suggestion: "Remove this restricted claim.",
            confidence: 0.98,
          }));
        }
      }
    }
  }

  // Resolve overlaps: keep highest priority, then earlier span
  const spans = out.filter((f) => f.scope === "text").sort((a, b) => a.start - b.start || prio(b) - prio(a));
  const kept = [];
  for (const f of spans) {
    const last = kept[kept.length - 1];
    if (last && f.start < last.end) {
      if (prio(f) > prio(last)) kept[kept.length - 1] = f;
      continue;
    }
    kept.push(f);
  }

  const docs = out.filter((f) => f.scope !== "text");
  const all = [...kept, ...docs];
  for (const f of all) {
    if (f.needsHuman === undefined) f.needsHuman = f.confidence < 0.7 || f.strictness === "critical";
  }
  return all;
}

function structureChecks(rule, content, meta, brandName) {
  const res = [];
  const type = meta.type;
  const doc = (label, suggestion, fix, ref, confidence = 0.68) => ({
    id: `${rule.id}:${label}`,
    key: `${rule.id}|${label.toLowerCase()}`,
    ruleId: rule.id,
    label,
    category: rule.category || "Content patterns",
    strictness: rule.strictness || "flexible",
    severity: "suggestion",
    kind: "advice",
    scope: "document",
    quote: "(whole draft)",
    suggestion,
    why: `Approved ${brandName} ${type} standards recommend this structure.`,
    source: { doc: "Brand Guidelines", ref },
    confidence,
    fix,
  });

  if ((type === "blog" || type === "ad") && content.trim()) {
    const brandLower = lc(brandName);
    const ctaPattern = new RegExp(`\\b(try ${brandLower}|start with ${brandLower}|explore ${brandLower}|get started|sign up|book a demo|contact us|start today|talk to us)\\b`, "i");
    if (!ctaPattern.test(content)) {
      res.push(doc("Missing call to action", `Conclude with a clear next step, for example “Discover ${brandName} today.”`, { type: "append", text: `\n\nDiscover ${brandName} today.` }, `${type} pattern`));
    }
  }

  if (type === "email" && content.trim()) {
    if (!/^subject:/im.test(content.trim())) {
      res.push(doc("Missing subject line", "Emails should open with a clear subject line.", { type: "prepend", text: "Subject: [Add subject]\n\n" }, "Email standard"));
    }
    if (!/\b(hi|hello|dear|welcome)\b/i.test(content.slice(0, 160))) {
      res.push(doc("Missing greeting", "Open with a friendly, professional greeting.", null, "Email standard"));
    }
  }

  if (type === "social" && content.length > 280) {
    res.push(doc("Length exceeds standard", "Keep social posts to 280 characters or fewer for optimal engagement.", null, "Social standard"));
  }

  return res;
}

// Image Findings
export function imageFindings(img, profile = {}) {
  if (!img) return [];
  const rules = profile.imageRules || {};
  const out = [];
  const brandName = profile.name || profile.brandName || "Brand";

  const base = (ruleId, label, category, key, quote, suggestion, why, source, confidence, extra) => ({
    id: `${ruleId}:${key}`,
    key: `${ruleId}|${key}`,
    ruleId, label, category,
    strictness: rules[extra?.rule] || "flexible",
    severity: "warning",
    kind: "advice", scope: "image", quote, suggestion, why, source, confidence, needsHuman: true,
    ...extra,
  });

  const name = (img.name || "").toLowerCase();
  const bad = (profile.deprecatedAssets || []).find((a) => name.includes(lc(a)));
  if (bad) {
    out.push(base("IMG-LOGO", "Outdated or unapproved logo asset", "Visual identity", img.name, img.name,
      `Replace it with an approved ${brandName} asset, such as “${(profile.approvedAssets || [])[0] || "the approved brand logo"}”.`,
      `The file name matches a retired or deprecated asset for ${brandName}.`,
      { doc: `${brandName} Assets`, ref: "Approved logo assets" }, 0.85, { rule: "logo" }));
  }

  if (!(img.alt || "").trim()) {
    out.push(base("IMG-ALT", "Missing alt text", "Access & channel fit", "alt", "(image has no alt text)",
      "Describe what the image displays in a concise sentence for accessibility.",
      "All published brand visual assets require informative alt text for accessibility.",
      { doc: "Accessibility Standards", ref: "Alt text guidelines" }, 0.95, { rule: "alt", fix: { type: "alt" }, needsHuman: false }));
  }

  const approvedFonts = (profile.fonts || []).map(lc);
  const used = (img.fonts || "").split(",").map((s) => s.trim()).filter(Boolean);
  for (const f of used) {
    if (approvedFonts.length > 0 && !approvedFonts.includes(lc(f))) {
      out.push(base("IMG-FONT", "Unapproved typography", "Visual identity", f, f,
        `Use an approved brand typeface: ${profile.fonts.join(", ")}.`,
        `“${f}” is not an approved typeface for ${brandName}.`,
        { doc: `${brandName} Guidelines`, ref: "Typography" }, 0.9, { rule: "fonts" }));
    }
  }

  return out;
}

// Master Review function combining text and image checks
export function reviewAll({ content, meta, image, profile = {}, product = null }) {
  const brandContext = profile || {};
  return [...runTextChecks(content, meta, brandContext, product), ...imageFindings(image, brandContext)];
}

// Content Rewriting
export function rewriteContent(content, meta = {}, profile = {}, dismissed = new Set(), product = null) {
  let text = content;
  const applied = [];
  const skipped = [];
  const findings = runTextChecks(content, meta, profile, product);

  for (const f of findings.filter((x) => x.scope === "text" && x.kind === "replace")) {
    if (dismissed.has(f.key)) continue;
    if (f.kind === "conflict") {
      skipped.push(f);
      continue;
    }
    const idx = text.indexOf(f.quote);
    if (idx !== -1) {
      text = text.slice(0, idx) + f.suggestion + text.slice(idx + f.quote.length);
      applied.push({ id: f.id, label: f.label, quote: f.quote, suggestion: f.suggestion, ruleId: f.ruleId, strictness: f.strictness });
    }
  }

  return { text, applied, skipped };
}

// Conflict detector between terminology rules
export function findConflicts(profile) {
  const rules = (profile.rules || []).filter((r) => r.kind === "term");
  const out = [];
  for (let i = 0; i < rules.length; i++) {
    for (let j = i + 1; j < rules.length; j++) {
      const pairsA = [];
      const pairsB = [];
      let term = null;
      for (const pa of rules[i].pairs || []) {
        for (const pb of rules[j].pairs || []) {
          if (lc(pa[1]) === lc(pb[0]) || lc(pb[1]) === lc(pa[0])) {
            if (!pairsA.includes(pa)) pairsA.push(pa);
            if (!pairsB.includes(pb)) pairsB.push(pb);
            term = term || (lc(pa[1]) === lc(pb[0]) ? pa[1] : pb[1]);
          }
        }
      }
      if (pairsA.length) out.push({ a: rules[i], b: rules[j], term, pairA: pairsA[0], pairB: pairsB[0], pairsA, pairsB });
    }
  }
  return out;
}

// Color helpers
export const hexToRgb = (h) => {
  const clean = (h || "#000000").replace("#", "");
  const n = parseInt(clean.length === 3 ? clean.split("").map((c) => c + c).join("") : clean, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

export const rgbToHex = ([r, g, b]) => "#" + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");

export function analysePixels(data, palette = []) {
  if (!palette.length) return { offPalette: [], lowContrast: null };
  const pal = palette.map((p) => ({ ...p, rgb: hexToRgb(p.hex) }));
  return { offPalette: [], lowContrast: null };
}
