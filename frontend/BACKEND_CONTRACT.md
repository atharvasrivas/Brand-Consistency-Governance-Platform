# Backend contract

What the frontend sends and expects, so the Flask backend (`backend-api`), the AI checks (`ai-checks`) and the database (`database-workflow`) can be built without guessing. The built-in rules engine in `src/engine/checker.js` is a working reference implementation of every check below.

> **Implemented.** The Flask server is on branch `backend-api` (see `backend/README.md`). Differences from the plan below: `profile` in `/api/review` and `/api/rewrite` is ignored (the server uses its stored profile), actions are the REST endpoints listed in the backend README, and the store (`src/store.jsx`) loads from `GET /api/bootstrap` and sends `X-User-Role` / `X-User-Name` headers.

## How the frontend talks to the backend

- Set `VITE_API_URL` at build time (for example `https://your-service.onrender.com`).
- `src/api.js` calls the two endpoints below. If a call fails, it falls back to the built-in engine, so the app never blocks.
- Enable CORS for the Vercel domain and `http://localhost:5173`.
- Keep the Gemini API key on the backend only.

## POST `/api/review`

Request:

```json
{
  "content": "Alpha is the fastest service in the country. ...",
  "meta": { "type": "blog", "audience": "Small business owners", "purpose": "Drive sign-ups" },
  "image": {
    "name": "holiday-post-Logo-Primary-2023.png",
    "alt": "",
    "fonts": "Comic Sans, Inter",
    "textInImage": "HOLIDAY OFFER!",
    "analysis": {
      "offPalette": [{ "hex": "#c4a000", "share": 0.31, "nearest": { "name": "Coral", "hex": "#FF6B5E" } }],
      "lowContrast": { "ratio": 2.4 }
    }
  },
  "profile": { "...": "see Brand profile below" }
}
```

- `meta.type` is one of `blog`, `social`, `ad`, `email`, `document`.
- `image` is `null` when there is no image. `analysis` is computed in the browser and may be missing.

Response:

```json
{ "findings": [ /* Finding[] */ ] }
```

### Finding

| Field | Type | Notes |
|---|---|---|
| `id` | string | Unique within the response, for example `T-NAME:12` |
| `key` | string | Stable across re-runs (rule + quote + nearby text). The frontend remembers accept/reject decisions by `key` |
| `ruleId` | string | Rule that raised it, for example `T-NAME`, `C-FAST`, `IMG-ALT` |
| `label` | string | Short title, for example "Claim needs a source" |
| `category` | string | One of: `Facts & claims`, `Terminology`, `Language & tone`, `Brand aura`, `Content patterns`, `Visual identity`, `Access & channel fit` |
| `strictness` | `"mandatory"` or `"flexible"` | Mandatory findings block submission until fixed or overridden with a reason |
| `kind` | `"replace"`, `"advice"` or `"conflict"` | `replace` has an exact suggested wording, `advice` is guidance only, `conflict` means two approved sources disagree |
| `scope` | `"text"`, `"image"` or `"document"` | `text` findings need `start` and `end` |
| `start`, `end` | number | Character offsets into `content` (`text` scope only). Must match `quote` exactly |
| `quote` | string | The text the finding refers to |
| `suggestion` | string | For `replace`: the exact replacement. For `advice`: the guidance sentence |
| `why` | string | Plain-language reason |
| `source` | `{ doc, ref }` | The guideline, fact or asset behind the finding. Required |
| `confidence` | number 0 to 1 | |
| `needsHuman` | boolean | True for low confidence (below 0.7), visual guesses and conflicts. These are routed to a reviewer |
| `options` | `[{ label, text, source }]` | `conflict` only. `text: null` means "keep as written" |
| `fix` | `{ type: "append" or "prepend" or "alt", text? }` | Optional one-click fix for `document` and `image` scope |
| `orSource` | boolean | Optional. Shows "or attach an approved source" |

Rules the backend must keep (these are the product's promises):

1. Every finding must cite a `source`. If the AI cannot point to an approved source, do not return it as a verified fact. Return `needsHuman: true` with lower confidence.
2. Validate the Gemini JSON against this schema before returning it. Drop or downgrade anything malformed.
3. When two approved sources disagree, return `kind: "conflict"` with both options and do not pick one.
4. Never return `start`/`end` that do not match `quote`.
5. Send Gemini only the context needed for the check.

## POST `/api/rewrite`

Request:

```json
{
  "content": "...",
  "meta": { "type": "blog", "audience": "...", "purpose": "..." },
  "profile": { "...": "..." },
  "dismissed": ["T-CUST|users|..."]
}
```

`dismissed` is the list of finding `key`s the creator rejected. The rewrite must leave those alone.

Response:

```json
{
  "text": "The rewritten content",
  "applied": [
    { "key": "T-NAME|alpha|...", "ruleId": "T-NAME", "label": "Outdated product name", "quote": "Alpha", "suggestion": "Nova", "strictness": "mandatory" }
  ],
  "skipped": [ /* Finding[] left unchanged because sources conflict */ ]
}
```

The rewrite must keep the creator's point, audience and call to action, and use only approved facts. Every entry in `applied` explains a change, because the UI shows "what changed, and why".

## Brand profile

This is the object sent as `profile` and stored in the database. Sample data is in `src/engine/seed.js` (`SEED_PROFILE`).

```json
{
  "version": 2,
  "brandName": "Nova",
  "productName": { "current": "Nova", "former": ["Alpha"] },
  "voice": ["warm", "clear", "direct"],
  "approvedClaims": ["Built for local businesses", "2,000+ local businesses"],
  "palette": [{ "name": "Nova Violet", "hex": "#5B4CE0" }],
  "fonts": ["Inter", "Playfair Display"],
  "approvedAssets": ["Logo-Primary-2026.svg"],
  "deprecatedAssets": ["Logo-Primary-2023", "logo-old", "Alpha-Logo"],
  "imageRules": { "logo": "mandatory", "alt": "mandatory", "fonts": "mandatory", "palette": "flexible" },
  "rules": [
    {
      "id": "T-NAME", "kind": "term", "strictness": "mandatory", "since": 2,
      "label": "Outdated product name", "category": "Terminology",
      "pairs": [["Alpha", "Nova"]],
      "why": "The product was renamed from Alpha to Nova.",
      "source": { "doc": "Brand Guidelines", "ref": "§2.1 Product naming" }
    }
  ]
}
```

Rule `kind` values the engine understands: `term`, `claim` (regex `patterns` with a `replacement`), `stat`, `tone`, `exclaim`, `caps`, `long`, `link`, `structure`. `since` is the profile version in which the rule started to apply.

## Data to store (suggested Supabase tables)

The frontend keeps this in `localStorage` today (`src/store.jsx`). Replace the reducer actions with API calls.

| Table | Columns |
|---|---|
| `profiles` | `version` (pk), `data` (jsonb, the profile above), `created_by`, `created_at`, `summary` |
| `submissions` | `id`, `title`, `type`, `audience`, `purpose`, `author`, `status` (`in_review`, `changes_requested`, `approved`, `rejected`), `profile_version`, `image` (jsonb), `created_at`, `updated_at` |
| `versions` | `submission_id`, `n`, `content`, `by`, `note`, `at` |
| `findings` | `submission_id`, `key`, `rule_id`, `label`, `category`, `strictness`, `quote`, `suggestion`, `source` (jsonb), `status` (`open`, `accepted`, `rejected`), `note`, `needs_human` |
| `comments` | `id`, `submission_id`, `by`, `role`, `text`, `at` |
| `activity` | `submission_id`, `by`, `text`, `at` |

Roles: `creator`, `reviewer`, `manager`. Only `reviewer` and `manager` may approve, request changes or reject. Only `manager` edits the profile. A mandatory finding with status `rejected` is an override and must carry a `note` (the reason).

## Actions the frontend performs (map these to endpoints)

| Store action (`src/store.jsx`) | Meaning |
|---|---|
| `submit` | Create a submission with version 1, its findings and an optional comment |
| `resubmit` | Add a new version to a submission and set it back to `in_review` |
| `decide` | Set status to `approved`, `changes_requested` or `rejected`, with an optional comment (required for the last two) |
| `comment` | Add a comment |
| `recheck` | Replace a submission's findings after re-running checks against a newer profile |
| `profile` | Save a new profile version with a change summary |

## Reference

- Request and response wiring: `src/api.js`
- Reference engine and finding shape: `src/engine/checker.js`
- Sample profile and submissions: `src/engine/seed.js`
