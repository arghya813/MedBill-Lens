# API contract

The frontend and backend are separate deployables that agree on JSON. This
document records the parts of that agreement which are easy to break, and the
convention that keeps them in sync.

## Verification

`backend/scripts/fullstack_check.py` starts a real server on a free port and
asserts the response shape of every endpoint the frontend calls, against a
throwaway database. Run it after any backend response change:

```bash
cd backend
python -m scripts.fullstack_check
```

It is deliberately stricter than the UI. Each check names the field it expects,
so a renamed attribute fails here rather than rendering `undefined` in the
browser.

## Source of truth

| Side | File | Role |
| --- | --- | --- |
| Backend | `app/schemas/*.py` | Pydantic models that generate the OpenAPI document |
| Frontend | `src/api/types.ts` | Hand-maintained mirror of those models |

The frontend types are **not** generated. They are written by hand and kept
honest by `fullstack_check.py`. If you change a backend schema, change
`types.ts` in the same commit.

## Benchmark datasets

`GET /api/benchmarks`, `GET /api/benchmarks/stats`, the analysis endpoints and
`GET /api/health/disclaimer` all describe the records that are actually in the
database, never a hard-coded constant:

| Field | Values | Derived from |
| --- | --- | --- |
| `dataset_label` | `Demo Dataset — …`, `Official Government Tariff Dataset`, `Mixed Demo and Official Benchmark Datasets` | how many rows are verified vs total |
| `is_demo_data` | `true` only when nothing is verified | `count_verified() == 0` |
| `notice` | matching notice text | `DATASET_NOTICES` in `app/core/enums.py` |

Every `*_benchmarks.json` under `backend/data/` is loaded together at seed time:

- `demo_benchmarks.json` — synthetic placeholders (`verification_status: demo`)
  for the scenarios and the multispecialty demo bills.
- `cghs_benchmarks.json` — 19,680 rows built by `backend/scripts/import_cghs.py`
  from the official CGHS rate API (`cghs.mohfw.gov.in`, cached in
  `backend/data/cghs_rates.json`; 2,594 published codes ×
  8 cities after dropping unlisted codes), published under O.M.
  `F.No.5-16/CGHS(HQ)/HEC/2024(PartI)` dated 03.10.2025. For each city, `min` /
  `median` / `max` are the minimum, the base rate (NABH, semi-private) and the
  maximum of that city's nine ward × facility cells; `median` therefore equals
  the O.M. "A" column. Cities map to tiers the way the O.M. maps X/Y/Z:
  `tier1` = Tier I (Delhi, Mumbai, Bengaluru, Hyderabad, Chennai, Kolkata, Pune,
  Ahmedabad), `tier2` = Tier II (Jaipur and the rest).

Government rows always carry `verification_status: government_rate`, a
`source_name`, a `source_url` on `cghs.mohfw.gov.in` and a `source_date`.

Comparisons are filtered by `currency_code` as well as city and hospital
category, so a bill denominated in anything other than the dataset's currency
reports insufficient data instead of a misleading cross-currency number.

When nothing from the bill's own hospital type resembles a charge, the engine
retries with the same city's other hospital types before giving up. Such a
row carries `match_scope: hospital_category_relaxed` and keeps its own source
and verification status (typically the published CGHS tariff), and the
analysis notes explain the substitution. Matches found without the fallback
never change: the fallback only runs for charges that would otherwise report
no data.

## Inconsistent envelopes on purpose

The API is not uniformly wrapped, and the frontend mirrors what it actually
returns rather than what would be tidier:

| Endpoint | Shape |
| --- | --- |
| `POST /api/bills/upload` | `{ bill, next_step, warnings }` |
| `POST /api/bills` (manual) | `{ bill, next_step, warnings }` |
| `POST /api/bills/{id}/extract` | `{ bill, warnings, requires_confirmation }` |
| `POST /api/bills/{id}/analyze` | `{ analysis, messages }` |
| `POST /api/demo/scenarios/{key}/run` | `{ analysis, messages }` |
| `PUT /api/bills/{id}/items` | bare `BillOut` |
| `GET /api/bills/{id}/analysis` | bare `AnalysisOut` |
| `POST /api/bills/{id}/questions` | `{ bill_id, questions }` |
| `GET /api/bills/{id}/report` | bare `ReportResponse` |

`api.updateBillItems` therefore returns `BillOut`, while `api.createManualBill`
returns `UploadResponse`. `ReviewPage` normalises the two before using them.

## Errors

Every 4xx and 5xx response uses one envelope, so the UI can render any failure
without special-casing:

```json
{ "error": { "code": "...", "message": "...", "detail": "...", "hint": "..." } }
```

`message` is safe to show to a user. `detail` is for logs. For `422`
validation failures `hint` contains `field: message` pairs, which the frontend
renders as a list under the message.

`ApiError` in `src/api/client.ts` preserves all four fields. The analysis page
treats `409` specially: it means the bill is not confirmed (or has not been
analysed yet), and is rendered as a prompt to review rather than as an error.

## Two shapes for dropdown options

`GET /api/options` mixes conventions, and the UI normalises them:

```json
{
  "categories":          [{ "value": "room", "label": "Room" }],
  "hospital_categories": [{ "value": "multispecialty", "label": "Multispecialty" }],
  "room_categories":     [{ "value": "private", "label": "Private" }],
  "cities":              ["Kolkata"],
  "treatments":          ["Internal Medicine"]
}
```

Categories are objects; cities and treatments are bare strings. `toOptions()` in
`src/lib/format.ts` converts a mixed array into `{value, label}` pairs, so
components always receive `SelectOption[]`.

## Money and numbers

- Money is always a plain **number in major units**. Never a formatted string,
  so the UI can do arithmetic and delegate display to `formatMoney`.
- The server owns display formatting where the value is comparative:
  `benchmark_display` and `difference_display` arrive ready to render, and the
  UI shows them verbatim instead of recomputing. Recomputing in two places is
  how a ₹ and a $ drift apart.
- `formatMoney` uses `en-IN` grouping (`1,23,450.50`); `formatMoneyCompact`
  abbreviates to lakh and crore for chart axes.
- `benchmark_min`, `benchmark_median` and `benchmark_max` are nullable, and
  the UI renders `—` rather than `₹0`. A missing benchmark is not zero.

## Money arithmetic in the UI

Two places add numbers the client side, both for display only and both
intentional:

- `BillEditor.itemTotal` computes `quantity × unit_price` for the live row total
  while typing.
- `itemTotal` treats the `discount` category as an absolute value so a negative
  discount reduces the subtotal rather than negating twice.

The authoritative totals always come from the server in `bill.totals`. The
client figure exists so the editor feels responsive before saving.

## Requests are strict

Unknown fields are rejected with `422`. This is not pedantry: posting `city`
inside `metadata` instead of `context` used to be silently dropped, which
changed which benchmarks matched and returned completely different numbers with
a `200`. `fullstack_check.py` asserts the `422`.

## Live preview before confirmation

`POST /api/bills/preview` compares charges that have not been confirmed yet.
The review screen is where the user corrects what extraction read, so gating the
comparison behind confirmation would hide the flags exactly when they are needed.

| Property | Why it is this way |
| --- | --- |
| Writes nothing | No bill update, no `has_analysis`, no confirmation. The preview must never be the reason an analysis is stored. |
| No AI | Deterministic benchmark comparison only, so it is safe to call while the user types. |
| `bill_id` optional | The manual-entry screen previews before a bill exists. |
| Rows keyed by the client | `items[].key` is echoed back as `comparisons[].id`, and `sort_index` is the row's index in the submitted payload. |
| Blank `description` allowed | `""` means "an empty row the user has not filled in yet", and those rows are skipped rather than rejected — unlike `PUT /{id}/items`, where `description` has `min_length=1`. |

Matching on the key rather than the position matters: a blank row dropped by the
server, or a row the user just inserted, must not shift every status one place
down the table. `ReviewPage` builds the cells with a `Map` keyed on that value.

Unknown fields are still a `422`, like every other endpoint. It shares the
standard rate limit (60/min), so the review screen debounces it at 1500 ms,
aborts superseded requests, and keeps the last good comparison on a `429`
instead of flashing an error.

## Preferences are not part of the contract

`/profile` stores everything in `localStorage` under
`medbill-lens.preferences.v1`. Nothing on that page is a request, so none of it
appears in `api/client.ts` and none of it is covered by `fullstack_check.py`.

The one exception is report redaction. The Profile page passes the user's six
choices straight through to `GET /api/bills/{id}/report`, and that split matters:

| Group | Parameters | Effect |
| --- | --- | --- |
| Redaction | `hide_patient_name`, `hide_patient_id`, `hide_bill_number`, `hide_hospital_name` | Replaces values with a placeholder. Echoed back in `redaction_applied`. |
| Content | `include_questions`, `include_sources` | Adds or drops a whole report section. |

`redaction_applied` contains **only** the four `hide_*` keys. Do not expect the
`include_*` toggles there, and do not treat a missing key as `False` — the report
page derives its "hidden in this report" list from that dict.

Setting all four `hide_*` flags to `false` returns `"anonymized": false`. The
report still records which fields were hidden either way.

Because changing these preferences changes what leaves the machine, the report is
the one place where a preference change is externally visible. Everything else is
presentation only.

## Adding an endpoint

1. Add the Pydantic response model in `app/schemas/`.
2. Add the route and register it in `app/routers` (see `app/main.py`).
3. Add the method to `api` in `src/api/client.ts`.
4. Add the response type to `src/api/types.ts`.
5. Add a shape check to `fullstack_check.py`.
6. Add a test in `backend/tests/test_api.py`.
