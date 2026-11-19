// Multi-brand seed profiles, product fact sheets, and sample data.
// Note: Hardcoded fictional personas (Priya Shah, Rohan Mehta, Anika Rao) are retained only in
// labelled seed submissions for demonstration history. Live users set their own identity via Onboarding.

export const ROLES = [
  { id: "creator", label: "Creator", description: "Submit content for brand review, resolve findings, and propose profile suggestions." },
  { id: "reviewer", label: "Reviewer", description: "Review submissions, add comments, request changes, and approve or reject content." },
  { id: "owner", label: "Brand Owner", description: "Create and edit official brand profiles, fact sheets, guidelines, and manage approvals." },
];

export const CONTENT_TYPES = [
  { id: "blog", label: "Blog post" },
  { id: "social", label: "Social post" },
  { id: "ad", label: "Advertisement" },
  { id: "email", label: "Email" },
  { id: "document", label: "Document / Fact Sheet" },
];

// Pre-seeded Brands with independent fact sheets and products
export const SEED_BRANDS = [
  {
    id: "nova",
    name: "Nova",
    logo: "https://api.iconify.design/lucide:sparkles.svg?color=%235B4CE0",
    description: "Next-generation smart consumer products and connected workspace platforms.",
    heritage: "Founded in 2021 to bring intuitive design and smart sensor technology into everyday lifestyle products.",
    personality: "Innovative, approachable, human-centric, and dependable.",
    tone: "Clear, warm, and confident without corporate jargon or hyperbolic claims.",
    voice: ["warm", "clear", "direct", "approachable"],
    approvedClaims: [
      { claim: "Built for local businesses", source: "Brand Manifesto §1.2", category: "Positioning" },
      { claim: "Over 2,000+ local businesses trust Nova", source: "Q3 2026 Verified Customer Audit", category: "Traction" },
      { claim: "Medical-grade 18/8 stainless steel", source: "Materials Lab Certification #ML-904", category: "Hardware" },
    ],
    restrictedClaims: [
      "Fastest service in the world",
      "Guaranteed 100% sales growth",
      "Completely unhackable / 100% secure",
      "Cures dehydration or health conditions",
    ],
    terminology: [
      { from: "Alpha", to: "Nova", strictness: "critical", why: "Alpha was the deprecated legacy product name; Nova is the official brand.", source: "Rebrand Directive 2026 §1" },
      { from: "users", to: "customers", strictness: "warning", why: "Brand guidelines prefer “customers” or “community members” over technical jargon.", source: "Brand Voice Guide §3" },
      { from: "utilize", to: "use", strictness: "suggestion", why: "Keep language direct and avoid unnecessarily complex verbs.", source: "Voice Guide: Simplicity" },
      { from: "in order to", to: "to", strictness: "suggestion", why: "Be concise.", source: "Voice Guide: Directness" },
      { from: "numerous", to: "many", strictness: "suggestion", why: "Conversational tone preferred.", source: "Voice Guide" },
    ],
    palette: [
      { name: "Nova Violet", hex: "#5B4CE0", role: "Primary" },
      { name: "Ink Navy", hex: "#12163A", role: "Dark" },
      { name: "Signal Teal", hex: "#1FAA8C", role: "Accent" },
      { name: "Coral Glow", hex: "#FF6B5E", role: "Highlight" },
      { name: "Cloud White", hex: "#F3F1FD", role: "Light" },
    ],
    fonts: ["Inter", "Playfair Display"],
    approvedAssets: ["Logo-Primary-2026.svg", "Nova-Bottle-Hero.png", "Guidelines-v2.pdf"],
    deprecatedAssets: ["Logo-Primary-2023.png", "Alpha-Logo.svg", "logo-old.png"],
    version: 3,
    updatedAt: "2026-11-14T10:00:00.000Z",
    products: [
      {
        id: "nova-bottle",
        name: "Nova Smart Bottle",
        previousName: "Alpha Hydro",
        description: "Intelligent thermal water bottle with UV-C self-cleaning cap, temperature sensing, and hydration tracking.",
        specifications: "Capacity: 600ml. Keeps cold for 24 hours, hot for 12 hours. UV-C LED 280nm sanitization. Bluetooth 5.3. 18/8 stainless steel.",
        approvedClaims: [
          { claim: "Keeps drinks cold for 24 hours", source: "Thermal Lab ISO-8302 Test", verified: true },
          { claim: "Keeps drinks hot for 12 hours", source: "Thermal Lab ISO-8302 Test", verified: true },
          { claim: "UV-C LED sanitizes cap and water in 60 seconds", source: "Microbiology Lab Report #MB-2026-4", verified: true },
        ],
        restrictedClaims: [
          "Eliminates 100% of all bacteria permanently",
          "Never requires recharging",
          "Water tastes 10x better",
        ],
        terminology: [
          { from: "Alpha Hydro", to: "Nova Smart Bottle", strictness: "critical", why: "Original crowdfunding model name replaced before launch." },
          { from: "flask", to: "Smart Bottle", strictness: "warning", why: "Standardize naming to Smart Bottle across marketing." },
        ],
        assets: ["Nova-Smart-Bottle-Render.png", "Spec-Sheet-Bottle-v3.pdf"],
      },
      {
        id: "nova-hub",
        name: "Nova Workspace Hub",
        previousName: "Alpha Station",
        description: "Compact desk console that tracks environmental metrics, scheduling, and smart hydration sync.",
        specifications: "7-inch E-Ink ambient display. USB-C Power Delivery 100W. Matter & Thread protocol support.",
        approvedClaims: [
          { claim: "Instant pairing with Nova Smart Bottle", source: "Product Manual §2", verified: true },
          { claim: "Ultra-low power E-Ink display lasting 30 days on backup", source: "Hardware Engineering Spec v1.4", verified: true },
        ],
        restrictedClaims: [
          "Replaces your entire computer",
          "Zero power consumption",
        ],
        terminology: [
          { from: "Alpha Station", to: "Nova Workspace Hub", strictness: "critical", why: "Deprecated hardware prototype name." },
        ],
        assets: ["Hub-Product-Photo.png"],
      },
    ],
  },
  {
    id: "ferrari",
    name: "Ferrari",
    logo: "https://api.iconify.design/simple-icons:ferrari.svg?color=%23D40000",
    description: "World-renowned Italian luxury sports car manufacturer founded in 1939 in Maranello.",
    heritage: "Synonymous with Formula 1 excellence, the Cavallino Rampante (Prancing Horse) represents timeless performance, passion, and design.",
    personality: "Prestigious, exhilarating, engineering-obsessed, uncompromising, and legendary.",
    tone: "Passionate yet impeccably refined. Technical precision balanced with evocative Italian automotive heritage.",
    voice: ["prestigious", "exhilarating", "refined", "precise"],
    approvedClaims: [
      { claim: "Born in Maranello, Italy", source: "Ferrari Corporate Archives", category: "Heritage" },
      { claim: "Iconic Italian design and racing pedigree since 1947", source: "Brand History §1", category: "Heritage" },
      { claim: "Pioneering mid-rear engine architecture", source: "Engineering Technical Brief 2025", category: "Engineering" },
    ],
    restrictedClaims: [
      "Budget-friendly sports car",
      "Autonomous self-driving vehicle",
      "Mass-market commuter car",
      "Electric car that doesn't need engine passion",
    ],
    terminology: [
      { from: "race car for the road", to: "road-legal berlinetta with racing DNA", strictness: "warning", why: "Use approved Maranello nomenclature; avoid colloquial cliches.", source: "Editorial Style Guide §4" },
      { from: "fast coupe", to: "berlinetta", strictness: "warning", why: "Ferrari refers to two-door closed models as berlinettas.", source: "Glossary of Terms" },
      { from: "Ferrari Motors", to: "Ferrari", strictness: "critical", why: "Official corporate and brand name is Ferrari, never Ferrari Motors.", source: "Legal Branding Guidelines" },
    ],
    palette: [
      { name: "Rosso Corsa", hex: "#D40000", role: "Primary" },
      { name: "Giallo Modena", hex: "#FFDD00", role: "Heritage Accent" },
      { name: "Nero", hex: "#111111", role: "Dark" },
      { name: "Argento Nürburgring", hex: "#C0C0C0", role: "Metallic" },
      { name: "Bianco Avus", hex: "#FFFFFF", role: "Light" },
    ],
    fonts: ["Inter", "Cinzel"],
    approvedAssets: ["Prancing-Horse-Official.svg", "Ferrari-Wordmark-2026.svg"],
    deprecatedAssets: ["Old-Ferrari-Motors-Logo.png"],
    version: 1,
    updatedAt: "2026-11-15T08:00:00.000Z",
    products: [
      {
        id: "ferrari-296",
        name: "Ferrari 296 GTB",
        previousName: "",
        description: "Mid-rear-engined two-seater berlinetta powered by a 120° V6 turbo hybrid powertrain.",
        specifications: "Total power: 830 cv (610 kW). Engine: 2992 cc 120° V6 turbo + rear electric motor. 0-100 km/h: 2.9 s. 0-200 km/h: 7.3 s. Max speed: >330 km/h. Electric range: 25 km.",
        approvedClaims: [
          { claim: "0 to 100 km/h in 2.9 seconds", source: "Official Homologation Certificate 2025", verified: true },
          { claim: "Total combined power output of 830 cv", source: "Technical Data Sheet 296 GTB §Powertrain", verified: true },
          { claim: "First 6-cylinder engine installed on an official road car sporting the Prancing Horse", source: "Ferrari Press Kit 296 GTB", verified: true },
        ],
        restrictedClaims: [
          "Zero to 100 km/h in under 2 seconds",
          "Full autopilot autonomous cruising",
          "Affordable family sports vehicle",
        ],
        terminology: [
          { from: "Dino V6", to: "120° turbo V6 hybrid", strictness: "warning", why: "The 296 GTB engine is an all-new architecture, not a Dino reboot." },
          { from: "Dino", to: "296 GTB", strictness: "critical", why: "Speculative press name. The car is officially 296 GTB." },
        ],
        assets: ["296-GTB-Launch-Asset.jpg", "296-GTB-Technical-Drawings.pdf"],
      },
      {
        id: "ferrari-sf90",
        name: "Ferrari SF90 Stradale",
        previousName: "",
        description: "The extreme PHEV supercar delivering 1,000 cv via a twin-turbo V8 and three electric motors.",
        specifications: "Total power: 1000 cv. Engine: 3990 cc 90° V8 turbo + 3 electric motors. 0-100 km/h: 2.5 s. All-wheel drive.",
        approvedClaims: [
          { claim: "1,000 cv total power output", source: "SF90 Technical Specification §1", verified: true },
          { claim: "0 to 100 km/h in 2.5 seconds", source: "Fiorano Track Performance Validation", verified: true },
        ],
        restrictedClaims: [
          "Zero maintenance required",
          "Can drive self-guided on race tracks",
        ],
        terminology: [
          { from: "electric Ferrari", to: "PHEV hybrid supercar", strictness: "warning", why: "Highlight the hybrid synergy between V8 combustion and electric motors." },
        ],
        assets: ["SF90-Stradale-Profile.jpg"],
      },
    ],
  },
];

// Compatibility: default single profile pointing to Nova
export const SEED_PROFILE = {
  ...SEED_BRANDS[0],
  brandName: SEED_BRANDS[0].name,
  productName: { current: "Nova Smart Bottle", former: ["Alpha Hydro"] },
  rules: [
    {
      id: "T-NAME", kind: "term", strictness: "mandatory", since: 2, label: "Outdated product name",
      category: "Terminology", caseSensitive: true, pairs: [["Alpha", "Nova"], ["Alpha Hydro", "Nova Smart Bottle"]],
      why: "The product was renamed from Alpha to Nova. The old name must not appear in public content.",
      source: { doc: "Brand Guidelines", ref: "§2.1 Product naming" },
    },
    {
      id: "T-CUST", kind: "term", strictness: "flexible", since: 1, label: "Preferred term",
      category: "Terminology", pairs: [["users", "customers"], ["user", "customer"]],
      why: "Brand Guidelines call the people we serve “customers”.",
      source: { doc: "Brand Guidelines", ref: "§3.2 Preferred terms" },
    },
    {
      id: "C-FAST", kind: "claim", strictness: "mandatory", since: 1, label: "Claim needs a source",
      category: "Facts & claims",
      patterns: [{ src: "\\b(?:the\\s+)?fastest\\s+(?:service|platform|tool|bottle)(?:\\s+in\\s+the\\s+(?:country|world|industry|market))?", flags: "i", replacement: "a fast product designed for local customers" }],
      why: "The approved fact sheet and linked study do not support this superlative comparison.",
      source: { doc: "Approved Fact Sheet", ref: "Approved claims" },
    },
    {
      id: "C-GUAR", kind: "claim", strictness: "mandatory", since: 1, label: "Claim needs a source",
      category: "Facts & claims",
      patterns: [{ src: "\\bguaranteed\\s+(?:results?|success|growth|cure)\\b", flags: "i", replacement: "verified results" }],
      why: "Absolute guarantees are prohibited unless certified by legal counsel.",
      source: { doc: "Approved Fact Sheet", ref: "Legal guidelines" },
    },
  ],
};

// Sample drafts organized by brand for testing
export const SAMPLE_DRAFTS_BY_BRAND = {
  nova: {
    blog: {
      title: "How Nova Smart Bottle revolutionizes daily hydration",
      audience: "Health-conscious consumers and local professionals",
      purpose: "Explain self-cleaning tech and drive pre-orders",
      content:
        "Alpha Hydro is the fastest bottle in the country. Our users utilize it in order to manage hydration, and numerous customers tell us they save hours of cleaning. Already 2,000+ local businesses use Nova, and it is 100% secure. It cures dehydration and keeps drinks cold for 24 hours.",
    },
    social: {
      title: "Nova Bottle Spring Announcement",
      audience: "Active lifestyle community",
      purpose: "Highlight 24h cold insulation",
      content: "Stay refreshed with Nova Smart Bottle! Medical-grade stainless steel keeps your water cold for 24 hours. Built for local businesses and everyday champions.",
    },
  },
  ferrari: {
    blog: {
      title: "The Sound and Science of the Ferrari 296 GTB",
      audience: "Automotive enthusiasts and prospective owners",
      purpose: "Showcase the Maranello hybrid V6 architecture",
      content:
        "Ferrari Motors has launched its new fast coupe called Dino. This street legal racecar produces 830 cv and accelerates from 0 to 100 km/h in 2.9 seconds. With autonomous self-driving vehicle features, it is the most budget-friendly sports car in Italy.",
    },
    social: {
      title: "Ferrari 296 GTB Fiorano Lap",
      audience: "Motorsport and luxury followers",
      purpose: "Celebrate Maranello engineering",
      content: "Born in Maranello, Italy. The Ferrari 296 GTB delivers an exhilarating 830 cv with 0 to 100 km/h in 2.9 seconds. Pure Italian passion.",
    },
  },
};

// Preserved historical seed submissions for testing review queue
const day = 86400000;
const ago = (d, h = 0) => new Date(Date.now() - d * day - h * 3600000).toISOString();

export const SEED_SUBMISSIONS = [
  {
    id: "S-1001",
    title: "Nova Spring Launch Blog",
    brandId: "nova",
    brandName: "Nova",
    productId: "nova-bottle",
    productName: "Nova Smart Bottle",
    type: "blog",
    author: "Sample Creator",
    status: "in_review",
    audience: "Active professionals",
    purpose: "Spring launch promotion",
    created: ago(1, 3),
    updatedAt: ago(1, 3),
    profileVersion: 3,
    versions: [
      {
        n: 1,
        content: "Alpha Hydro is the fastest bottle in the country. Our users utilize it in order to stay hydrated. Customers love it!",
        at: ago(1, 3),
        by: "Sample Creator",
        note: "Initial draft",
      },
    ],
    findings: [
      { key: "T-NAME|alpha hydro|...", ruleId: "T-NAME", label: "Outdated product name", category: "Terminology", strictness: "critical", quote: "Alpha Hydro", status: "open", suggestion: "Nova Smart Bottle", source: { doc: "Rebrand Directive 2026", ref: "§1" } },
      { key: "C-FAST|fastest bottle|...", ruleId: "C-FAST", label: "Claim needs a source", category: "Facts & claims", strictness: "critical", quote: "fastest bottle", status: "open", suggestion: "a fast product", source: { doc: "Approved Fact Sheet", ref: "Approved claims" } },
    ],
    comments: [{ id: "S-1001-c0", by: "Sample Creator", role: "creator", text: "Please review the spring copy.", at: ago(1, 3) }],
    activity: [{ at: ago(1, 3), by: "Sample Creator", text: "Submitted for review" }],
  },
  {
    id: "S-1002",
    title: "Ferrari 296 GTB Track Showcase",
    brandId: "ferrari",
    brandName: "Ferrari",
    productId: "ferrari-296",
    productName: "Ferrari 296 GTB",
    type: "social",
    author: "Sample Creator",
    status: "changes_requested",
    audience: "Supercar collectors",
    purpose: "Highlight technical specs",
    created: ago(2, 5),
    updatedAt: ago(1, 20),
    profileVersion: 1,
    versions: [
      {
        n: 1,
        content: "Ferrari Motors introduces the Dino fast coupe. A street legal racecar reaching 0-100 in 2.9s.",
        at: ago(2, 5),
        by: "Sample Creator",
        note: "First track teaser draft",
      },
    ],
    findings: [
      { key: "T-CORP|ferrari motors|...", ruleId: "T-CORP", label: "Incorrect corporate name", category: "Terminology", strictness: "critical", quote: "Ferrari Motors", status: "open", suggestion: "Ferrari", source: { doc: "Legal Branding", ref: "§1" } },
      { key: "T-TERM|fast coupe|...", ruleId: "T-TERM", label: "Off-brand terminology", category: "Terminology", strictness: "warning", quote: "fast coupe", status: "open", suggestion: "berlinetta", source: { doc: "Style Guide", ref: "§4" } },
    ],
    comments: [
      { id: "S-1002-c0", by: "Sample Reviewer", role: "reviewer", text: "Please replace 'Ferrari Motors' with 'Ferrari' and use 'berlinetta'.", at: ago(1, 20) },
    ],
    activity: [
      { at: ago(2, 5), by: "Sample Creator", text: "Submitted for review" },
      { at: ago(1, 20), by: "Sample Reviewer", text: "Requested changes" },
    ],
  },
];

export function seedChangelog() {
  return [
    { version: 1, at: ago(7), by: "System", summary: "Initial brand setup" },
    { version: 2, at: ago(3), by: "Brand Owner", summary: "Added product fact sheets and approved claims" },
    { version: 3, at: ago(1), by: "Brand Owner", summary: "Updated product terminology and restricted claims" },
  ];
}

export function buildSeedSubmissions() {
  return SEED_SUBMISSIONS;
}
