# MedBill Lens

Understand a hospital bill before you pay it.

MedBill Lens reads an itemised hospital bill, shows you exactly what was charged, and compares
each charge against benchmark price ranges for your city, hospital type, treatment and room
category. It then gives you a prioritised list of neutral questions to ask the hospital billing
department.

It deliberately does **not** claim that any charge is wrong, that a hospital is overcharging, or
that anything is fraudulent. A charge outside a benchmark range is normal and often has an
explanation. The value is in showing you where the numbers differ so you know what to ask.

---

## What it does

| Step | What happens |
| --- | --- |
| Upload | PDF, JPG or PNG. Text PDFs are parsed directly; scanned documents go through OCR. |
| Review | Every extracted charge is shown for correction. Nothing is compared until you confirm. |
| Analyse | Each charge is matched to benchmark records and a min/median/max range is computed. |
| Report | A shareable report with per-charge comparisons, questions and sources. |
| Profile | Display, comparison and privacy preferences. Stored in your browser. |

Navigation order is Home, Check a bill, Benchmarks, Demo, About, Profile.

Two important design rules are enforced in code:

1. **The numbers are deterministic.** Benchmark selection, ranges, differences, percentages and
   flags are computed by the analysis engine. An AI provider may help read the document and write
   explanations, but never produces a number in the comparison.
2. **You confirm before analysis.** Automatic reading is a starting point, not the truth. A
   missing or misread charge corrupts everything downstream, so the comparison is gated on your
   confirmation.

---

## Quick start

### One command

Everything is already installed. Open a terminal in the project root and run:

```bash
npm run dev
```

That starts the backend and the frontend together, waits until both actually answer, then
opens <http://localhost:5173> in your browser.

```
  MedBill Lens development servers

  [api] starting FastAPI on port 8000
  [web] starting Vite on port 5173
  ...
  Ready.
  [api]  http://127.0.0.1:8000/api/health
  [web]  http://localhost:5173
  Both reload on save. Press Ctrl+C here to stop both.
```

Both sides update while you work:

| You edit | What happens |
| --- | --- |
| anything under `backend/app` | uvicorn restarts the API, the Vite proxy reconnects |
| any `frontend/src` file | Vite hot-reloads the open tab, no refresh needed |
| `frontend/index.html` or CSS | Vite full-reloads the page |

`Ctrl+C` in that terminal stops both, so one terminal is enough.

| Variant | Does |
| --- | --- |
| `npm run dev` | Both servers, browser opens |
| `npm run dev -- --no-open` | Both servers, leave the browser alone |
| `npm run dev:api` | Backend only |
| `npm run dev:web` | Frontend only |

`scripts/dev.mjs` needs nothing beyond Node, which is already required to build the frontend.
If a port is occupied it stops before launching anything and says how to free it:

```
Cannot start: port 5173 is already in use
     npx kill-port 5173
```

In VS Code you can also press **`Ctrl+Shift+B`**, or `F5` to start both and open Chrome.

### Two terminals: frontend here, backend there

If you prefer a separate terminal per server, run these two side by side.

**Terminal 1 — frontend**

```bash
cd frontend
npm run dev
```

Vite serves <http://localhost:5173> and hot-reloads on save.

**Terminal 2 — backend**

```bash
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

The API is at <http://127.0.0.1:8000>, interactive docs at `/docs`. Vite proxies `/api/*`
to it, so the frontend works as soon as this is up.

In VS Code, `Ctrl+Shift+P` > **Tasks: Run Task** gives you the same two things as separate
terminals:

| Task | Terminal runs |
| --- | --- |
| `Frontend: Vite only` | `npm run dev` in `frontend/` |
| `Backend: API only` | uvicorn in `backend/` |
| `Dev: both servers, two terminals` | both of the above, side by side |

#### Stop the backend with `Ctrl+C`

`--reload` makes uvicorn run the app in a child process that **inherits the listening
socket**. `Ctrl+C` signals the whole process group, so both go away. If you instead close
the terminal or force-kill the window, the child survives, keeps port 8000 bound to a PID
that no longer exists, and the next start fails with a confusing "address already in use"
where `netstat` shows a port owned by a dead process. If that happens:

```powershell
Get-CimInstance Win32_Process -Filter "Name like '%python%'" |
  Where-Object { $_.CommandLine -match 'spawn_main' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

`npm run dev` avoids this entirely: it stops the whole process tree for you.

### Running the two halves by hand

Prefer separate terminals, or want a different port? Each half runs on its own.

### Backend

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux

.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

Or in one line on Windows PowerShell:

```powershell
cd backend; .\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

The API is then at <http://127.0.0.1:8000>, with interactive docs at `/docs`.

No configuration is required. With no `.env` file the server runs in demo mode: the built-in
engine reads text PDFs, and the bundled benchmark datasets — synthetic demo rows plus the
published CGHS tariff — are seeded on first run.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to the backend, so there is no CORS setup and no
secrets in the browser.

### Production build, single origin

To check the real build instead of the dev server, serve `frontend/dist` from
the API itself:

```bash
cd frontend && npm run build
cd .. && backend\.venv\Scripts\python scripts\serve_dist.py
```

Or from the project root: `npm run build && npm run serve`.

That opens <http://127.0.0.1:8080> with the frontend and API on one origin, which is how you would
deploy it: any static host or CDN for `dist`, plus the API behind it.

---

## Environment variables

All variables are prefixed `MEDBILL_`. Copy `.env.example` to `.env` to change any of them; every
value below has a working default.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MEDBILL_ENVIRONMENT` | `development` | `development`, `staging` or `production`. |
| `MEDBILL_DATABASE_URL` | SQLite file | Any SQLAlchemy URL. PostgreSQL-compatible schema. |
| `MEDBILL_AI_PROVIDER` | `demo` | `demo`, `openai`, `openai_compatible`, or another gateway. |
| `MEDBILL_AI_API_KEY` | unset | Required only for a real provider. |
| `MEDBILL_AI_MODEL` | provider default | Overrides the model id. |
| `MEDBILL_AI_BASE_URL` | provider default | Override for OpenAI-compatible gateways. |
| `MEDBILL_AI_FALLBACK_TO_DEMO` | `true` | Fall back to the demo engine if the provider fails. |
| `MEDBILL_DEMO_MODE` | `true` | Enables synthetic demo scenarios and the sample documents. |
| `MEDBILL_MAX_UPLOAD_SIZE_MB` | `10` | Upload size limit. |
| `MEDBILL_RAW_FILE_RETENTION_MINUTES` | `30` | Raw documents are purged after this window. |
| `MEDBILL_STORAGE_DIR` | `./data/uploads` | Must never point at a publicly served path. |
| `MEDBILL_SERVE_RAW_FILES` | `false` | Do not enable. Raw documents are never served over HTTP. |
| `MEDBILL_CORS_ORIGINS` | localhost:5173 | Comma-separated allowed origins. |
| `MEDBILL_AUTH_ENABLED` | `false` | Require an API key on write endpoints. |
| `MEDBILL_RATE_LIMIT_ENABLED` | `true` | Per-client rate limiting. |
| `MEDBILL_RATE_LIMIT_REQUESTS` | `60` | Requests per window. |
| `MEDBILL_FLAG_*` | see below | Flagging thresholds. Deterministic; AI never decides these. |

Frontend variables (`frontend/.env`, all optional):

| Variable | Purpose |
| --- | --- |
| `VITE_API_BASE_URL` | Absolute API origin. Leave unset in development to use the Vite proxy. |
| `VITE_PROXY_TARGET` | Backend origin the dev server proxies to. Defaults to `http://127.0.0.1:8000`. |

### Enabling a real AI provider

The product is fully functional without a key: reading, every comparison, the report and the
questions all work on the demo engine. A key only upgrades the written explanations from templated
to generated.

```dotenv
MEDBILL_AI_PROVIDER=openai
MEDBILL_AI_API_KEY=sk-...
MEDBILL_AI_MODEL=gpt-4o-mini
```

The comparison engine is unaffected either way.

---

## Demo mode

Demo mode exists so the whole product can be explored without an AI key or a real bill. It seeds
2,328 synthetic benchmark records (alongside the published CGHS tariff) and three scenario bills:

| Scenario | Bill total | What it demonstrates |
| --- | --- | --- |
| A | ₹43,950 | Mostly within range; one charge with no benchmark. |
| B | ₹230,100 | A long stay with several charges above their range. |
| C | ₹96,400 | A community clinic with limited comparable data. |

All figures, hospital names and patients are fictional. Demo artefacts are labelled as demo data
in the API (`is_demo_data`), in the UI and in every generated report.

---

## Architecture

```
medbill-lens/
├── backend/
│   ├── app/
│   │   ├── core/         # settings, enums, domain errors
│   │   ├── db/           # engine, session, base model
│   │   ├── models/       # SQLAlchemy models
│   │   ├── providers/    # extraction: demo, deterministic parser, real AI
│   │   ├── repositories/ # data access
│   │   ├── routes/       # FastAPI routers
│   │   ├── schemas/      # Pydantic contracts
│   │   ├── services/     # bills, benchmarks, analysis, report, privacy
│   │   └── utils/        # money and date helpers
│   ├── data/             # seeded benchmarks and sample bills
│   ├── scripts/          # smoke, e2e and full-stack checks
│   └── tests/
├── docs/
│   └── api-contract.md   # frontend/backend contract and how it is verified
└── frontend/
    └── src/
        ├── api/          # typed client and response contracts
        ├── components/   # editor, charts, shared UI
        ├── hooks/        # async data helpers
        ├── lib/          # formatting and flag metadata
        ├── pages/        # home, upload, review, analysis, report, benchmarks, demo, about
        └── state/        # app metadata and bill session
```

### Why the numbers come from the engine

The engine (`app/services/benchmark_engine.py`) owns benchmark selection, range computation,
difference arithmetic, flag thresholds and coverage. It is pure and deterministic: the same bill
and context always produce the same output.

A language model is only used for reading documents and writing prose. This split is deliberate.
A model that writes fluent explanations cannot be trusted to add up a hospital bill, and a tool
that lets it try will produce confident, wrong numbers.

### Privacy

Uploaded documents are stored only long enough to extract the bill, then purged on a timer
(`MEDBILL_RAW_RETENTION_MINUTES`) and whenever a bill is deleted. There is no endpoint that
serves a raw document over HTTP. Reports redact patient name, patient ID and bill number by
default.

---

## Profile and preferences

`/profile` is a settings page covering identity, number formatting, comparison defaults, the
analysis table's starting filter, report redaction and stored data.

**There is no account system.** Auth is an off-by-default stub (`MEDBILL_AUTH_ENABLED`), so
preferences live in `localStorage` under `medbill-lens.preferences.v1` and never reach the API.
Every field on that page is wired to real behaviour:

| Preference | Effect |
| --- | --- |
| Display name | Label in the header. Never printed on a report or export. |
| Digit grouping | Lakh (`12,34,567`) or million (`1,234,567`). Formatting only. |
| Show paise | Rounds displayed amounts. Underlying values are unchanged. |
| Default currency | Used for manual entries and unspecified amounts. |
| Layout density | Comfortable or compact. |
| Comparison defaults | Pre-fill review context and benchmark filters, but only where the bill is silent. |
| Starting filter | Which charges the analysis table opens on. |
| Hide unmatched charges | Drops rows with no benchmark. Coverage still counts them. |
| Report redaction | The six `hide_*` and `include_*` parameters sent to `/api/bills/{id}/report`. |
| Remember recent bills | Off keeps the recent list for the visit only, and writes nothing to the browser. |

The redaction toggles are the only ones that change what leaves your machine, so changing them
alters the next report you generate. `redaction_applied` in the response reports only the four
`hide_*` fields; the two `include_*` switches add or drop report sections instead.

Stale or hand-edited stored values degrade to defaults field by field rather than breaking the
page. `Reset all settings` restores the defaults.

---

## API

All responses use JSON. Errors always use the same envelope, so the frontend can render them
without special-casing:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Some of the details provided were not valid.",
    "detail": "Field required",
    "hint": "items.0.category: Field required"
  }
}
```

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/health` | Provider, dataset and limits. |
| `GET` | `/api/disclaimer` | Notice text shown in the UI. |
| `GET` | `/api/options` | Enum values for the dropdowns. |
| `POST` | `/api/bills/upload` | Multipart upload. Returns `{bill, next_step, warnings}`. |
| `POST` | `/api/bills/{id}/extract` | Reads charges from the stored document. |
| `GET` | `/api/bills/{id}` | The bill with its items and totals. |
| `PUT` | `/api/bills/{id}/items` | Edit and/or confirm. Returns a bare bill. |
| `POST` | `/api/bills` | Manual entry. Confirmed on creation. |
| `POST` | `/api/bills/{id}/analyze` | Runs the comparison. |
| `GET` | `/api/bills/{id}/analysis` | The stored analysis. `409` if not confirmed. |
| `POST` | `/api/bills/{id}/questions` | Regenerates questions. |
| `GET` | `/api/bills/{id}/report` | Report as JSON, Markdown or HTML. |
| `DELETE` | `/api/bills/{id}` | Deletes the bill and purges its document. |
| `GET` | `/api/benchmarks` | Filterable benchmark records. |
| `GET` | `/api/benchmarks/stats` | Dataset coverage and provenance. |
| `GET` | `/api/demo/scenarios` | Scenario catalogue. |
| `POST` | `/api/demo/scenarios/{key}/run` | Loads and analyses a scenario in one call. |

Requests are strict: unknown fields are rejected with `422` rather than ignored, because a
silently dropped field such as `city` changes which benchmarks match and produces entirely
different numbers with a successful response.

---

## Tests

From the project root:

```bash
npm run check          # everything below, in order
```

Or individually:

```bash
npm test               # unit and API tests
npm run test:contract  # every endpoint the UI calls
npm run test:e2e       # real PDF over HTTP, upload -> report
npm run test:smoke     # all three demo scenarios
npm run verify         # typecheck + lint + production build
```

These wrap the backend scripts and run the virtualenv Python for you, so you do not
need `cd backend` or an activated shell:

```bash
cd backend
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m scripts.fullstack_check
```

`scripts/e2e_check.py` exists to catch integration bugs that unit tests miss: it
uploads a real generated PDF over HTTP and confirms the extracted charges match
the seeded scenario exactly.

`scripts/fullstack_check.py` goes further and asserts the *shape* of every
response the React app consumes, so a renamed field fails there instead of
rendering `undefined` in the browser. See [`docs/api-contract.md`](docs/api-contract.md).

The test suite runs against a temporary database and storage directory configured
before any application import, so it can never touch your development data.

Preferences live in the browser, so they are not covered by the API checks. What *is*
covered is the contract the Profile page depends on: `fullstack_check.py` asserts that
`/api/bills/{id}/report` echoes exactly the four `hide_*` fields, honours each one
independently, clears `anonymized` when nothing is hidden, drops the `questions` and
`sources` sections when the `include_*` toggles are off, and rejects an unsupported
`format`.

---

## Deployment notes

- Serve the API with `uvicorn` (single worker is fine; the engine is stateless per request).
- Set `MEDBILL_ENVIRONMENT=production`, `MEDBILL_CORS_ORIGINS` to your frontend origin, and turn
  on `MEDBILL_AUTH_REQUIRED` if the instance is public.
- Point `MEDBILL_DATABASE_URL` at PostgreSQL for anything beyond local use.
- Build the frontend with `npm run build` and serve `dist` from any static host or CDN.
- Seed the benchmark datasets once on a fresh database: every `*_benchmarks.json` in
  `backend/data/` is loaded together (synthetic demo rows plus the published CGHS tariff).
  Regenerate `cghs_benchmarks.json` with `python scripts/import_cghs.py --cache <rates.json>`.
- Raw-document retention is a privacy control, not a storage strategy. Keep it short.

---

## Troubleshooting

**`ImportError: DLL load failed while importing _util_cy: An Application Control policy has
blocked this file`**

Windows Smart App Control (or a WDAC policy) is blocking SQLAlchemy's compiled Cython
extension, so the backend cannot import at all. This is not a bug in this project and it
cannot be fixed by reinstalling the same wheel. `backend/requirements.txt` pins
`sqlalchemy>=2.0,<2.1` for exactly this reason: 2.1 made those extensions mandatory, while
2.0 guards the import and falls back to pure Python.

```bash
cd backend
.\.venv\Scripts\python.exe -m pip install "sqlalchemy>=2.0,<2.1"
```

If you hit this on a fresh machine, make sure pip resolves to the 2.0 line before debugging
anything else:

```bash
.\.venv\Scripts\python.exe -c "import sqlalchemy; print(sqlalchemy.__version__)"
```

**Port 8000 in use, but `netstat` shows a PID that no longer exists**

You force-killed uvicorn instead of stopping it with `Ctrl+C`. See
[Stop the backend with Ctrl+C](#stop-the-backend-with-ctrlc) above.

**VS Code shows "task error" / the task terminates immediately**

Check `Ctrl+Shift+P` > **Tasks: Run Task** and run `Backend: API only` on its own; its output
shows the real failure. Long-running servers use a background problem matcher keyed on the
readiness line (`Application startup complete.` / `Local: ...5173`), so a task that stops
early means the process exited, not that the matcher misfired.

---

## Limitations

- Handwritten notes, stamps and poor scans can produce extraction errors. Always use the review
  step.
- Benchmark packages are sometimes fixed-price plans rather than itemised prices, which makes a
  direct comparison misleading.
- Rare procedures may have too few records to compare. That is reported rather than extrapolated.
- Hospitals negotiate privately, so a published benchmark can sit well below an actual charge.
- Prices are not adjusted for inflation or currency.
- Only the hospital can confirm what was actually provided and billed.

---

## Disclaimer

MedBill Lens provides information for your own review. It is not medical, legal or financial
advice, it does not determine whether a charge is correct, and it never alleges wrongdoing by any
hospital or provider. Benchmark comparisons are indicative only. In a dispute, raise the bill with
the hospital billing department first.
