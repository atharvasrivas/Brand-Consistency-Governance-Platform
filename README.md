# Brand Consistency and Governance Platform

CodeNova 2026 project by Team CodeBlooded.

A platform that reviews content against a brand's approved facts, guidelines and assets, explains each finding with its source, suggests exact corrections, and keeps people in control of approval.

## Branches

| Branch | Scope |
|---|---|
| `frontend-ui` | Page layout, brand profile, submission and results screens |
| `backend-api` | Flask endpoints and frontend connection |
| `ai-checks` | Gemini checks, explanations and rewrite suggestions |
| `database-workflow` | Supabase setup, review status and history |

Changes reach `main` through pull requests only.

## Gemini, images and version history

- `GEMINI_API_KEY` is read on the API server only. `GET /api/ai/status` reports the real state (off / unverified / text / full / failing); owners can run `POST /api/ai/diagnose` (or "Run diagnostics" in the header) to test the key, service, model, text and image analysis with real requests.
- Uploaded images are sent to the vision model with the brand's approved logo and visual assets. If an image cannot be analysed, an `IMG-UNANALYSED` finding routes it to a human reviewer. AI visual findings are advice, never mandatory.
- Uploaded images are stored as assets and served by id; treat asset ids as unguessable links, not as access control.
- Version history: `GET /api/brands/<id>/versions`, `/versions/<n>`, `/versions/compare?from=&to=`, `POST /versions/<n>/restore` (owner; creates a new version, history is never rewritten). Same under `/brands/<id>/products/<pid>/`.
- Change impact: `GET /api/governance/impact`, `/impact/history`, `POST /impact/decision` (recheck, dismiss, withdraw, resolved, reopen). Re-checking a submission clears its alerts.
- Drift Radar and Insights share one definition: a pattern is the same finding in two or more non-draft submissions.
