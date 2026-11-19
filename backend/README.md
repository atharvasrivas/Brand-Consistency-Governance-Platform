# Backend (Flask)

API for the Brand Consistency and Governance Platform. A deterministic rule engine always runs; Gemini is an optional layer on top. The server ships with **no brands, products, people or submissions**: an Owner creates everything (or loads the clearly labelled sample brand).

## Run
```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # optional
python3 wsgi.py               # http://localhost:5000
python3 -m pytest -q          # tests
```

## Model
- **Brands** (independent, versioned) → **Products** (fact sheet per product, versioned). Every save writes a new version; saving with a stale `version` returns 409.
- Profile items (claims, restricted claims, terminology, specs, colours) have `status: approved|draft`. Only approved items are used as facts. Assistant output is always `draft`.
- A review/submission is bound to `brandId` + `productId` (or `productId: null` for brand-level content). The server builds the context from that one brand/product only; a product of another brand returns 404. Submissions record the brand/product versions used.

## Roles (enforced on the server)
| Capability | Creator | Reviewer | Owner |
|---|---|---|---|
| Review a draft, submit own content | yes | review only (cannot submit) | yes |
| View brand profiles | yes | yes | yes |
| Suggest a profile change | yes | yes | – |
| Create/edit brands and products, uploads, assistant, resolve suggestions | – | – | yes |
| Approve/reject submissions | – | yes | yes (not own) |
| Insights | – | yes | yes |

Identity in `AUTH_MODE=demo` is a **prototype identity** sent in `X-User-Id/Role/Name/Designation` headers by the onboarding screen. Anyone can set these headers, so it is not security. `AUTH_MODE=jwt` verifies a Supabase Auth token and reads the role from `app_metadata.brand_role`.

## Endpoints (all `/api`)
`GET /health` · `GET /bootstrap` · `GET|POST /brands` · `GET|PUT /brands/<id>` · `GET /brands/<id>/versions` · `POST /brands/<id>/products` · `PUT /brands/<id>/products/<pid>` · `GET /brands/<id>/products/<pid>/versions` · `POST /assets` · `GET /assets/<id>` · `GET /assistant/questions` · `POST /assistant/factsheet` · `GET|POST /suggestions` · `POST /suggestions/<id>/resolve` · `POST /review` · `POST /rewrite` · `GET|POST /submissions` · `GET /submissions/<id>` · `POST /submissions/<id>/versions|decision|comments|recheck` · `GET /insights` · `POST /demo/load`

Review body: `{brandId, productId|null, content, meta:{type,audience,purpose}, image?}`. `productId` must be present (null = “Brand-level content / no product”). Findings carry `quote, label, category, severity (critical|warning|suggestion), strictness, suggestion, why, source, occurrences, ranges, needsHuman`. Repeated issues are merged; punctuation-only findings are never produced. Claims or figures the profile cannot verify are flagged for a person, with no invented source.

## Gemini (optional)
Set `GEMINI_API_KEY`. The key is read only on the server. The model gets just the selected approved context and the draft, must return schema-validated JSON, can only add non-mandatory findings, must quote the draft verbatim and cite a real approved item to count as verified; rewrites are rejected if they add numbers or new violations. On any failure the rule engine result stands. **Request handling is tested with mocked HTTP only; it has not been run against the live Gemini API.**

## Storage
`STORE=sqlite` (default) or `STORE=supabase`. Supabase uses one table, `bg_docs` (`schema/supabase.sql`), through PostgREST with the service key, which must stay on the server. RLS is enabled with no policies, so the public keys cannot read it.

## Known limits
Uploaded PDFs/documents are stored but their text is not extracted (paste text into the assistant instead). `GET /assets/<id>` is unauthenticated and relies on unguessable ids. Findings that need pixel analysis (palette/contrast) are computed in the browser and kept on submit.
