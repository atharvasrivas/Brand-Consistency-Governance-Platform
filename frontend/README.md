# Frontend

React app for the Brand Consistency and Governance Platform.

## Run

```
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run build    # static site in dist/
```

Deploy on Vercel with the root directory set to `frontend`, build command `npm run build` and output directory `dist`.

## Screens

| Route | Purpose |
|---|---|
| `#/` | Landing page |
| `#/review` | Review studio: paste content or an image, run the check, accept, edit or reject each finding, rewrite in brand voice, submit |
| `#/approvals` | Queue, findings, comments, revision history and the reviewer decision |
| `#/profile` | Guided brand setup, auto-generated fact sheet, rules, visual identity, conflicts, profile history |
| `#/insights` | Brand Drift Radar, Change Finder and Impact Scanner |
| `#/responsible` | What runs where, and how AI is used |

Use the role switcher (top right) to act as Creator, Reviewer or Brand Manager.

## Connecting the Flask backend

Set `VITE_API_URL` at build time. The app then calls:

- `POST /api/review` with `{ content, meta, image, profile }` and expects `{ findings: Finding[] }`
- `POST /api/rewrite` with `{ content, meta, profile, dismissed }` and expects `{ text, applied, skipped }`

The full request and response contract, finding shape, brand profile and suggested database tables are in `BACKEND_CONTRACT.md`. If the API is unset or unreachable, the app uses the built-in rules engine so the workflow keeps working.

## Data

Submissions, comments and profile changes are stored in the browser (`localStorage`) until the Supabase layer is connected. Replace the reducer in `src/store.jsx` with API calls when the database is ready.

## Connecting to the backend

Build or run with `VITE_API_URL=https://<backend>` (for example `http://localhost:5000`). The app loads all data from `GET /api/bootstrap`, and every submit, decision, comment, profile save and re-check goes through the API. If the server cannot be reached at start-up, the app runs on its built-in engine and localStorage, and the header pill reads "Local rules engine".
