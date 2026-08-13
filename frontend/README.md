# QEMS Frontend

React (Vite) frontend for the Quality Error Management System, built by G. Hasini per the
project report's UI/UX ownership (Section 16.1). This document covers what changed to connect
it to the real backend at [`../backend`](../backend) — the frontend itself (components, styling,
page layout) is Hasini's work and is described only where it needed to change to talk to a real
API instead of mock data.

## What this frontend looked like before integration

The version received (via a zip export) was built entirely against mock data: a hardcoded array
of 6 example errors in `AppContext.jsx`, persisted to `localStorage`, with a login flow that
accepted any email/password and derived a fake role from the email string. No file in the
original code called `fetch` or any HTTP client — every "backend" interaction was a local state
mutation.

## What changed to connect it to the real backend

### 1. A real API client (`src/api/client.js`)

Talks to the FastAPI backend at `VITE_API_URL` (`.env`, defaults to `http://localhost:8000/api/v1`).
Handles:
- Attaching the JWT (`Authorization: Bearer <token>`) to every authenticated request.
- Parsing the backend's structured `{"error": {"code", "message"}}` shape into a typed `ApiError`.
- Transparently refreshing an expired access token once and retrying the original request; if the
  refresh token is also invalid, throws `SessionExpiredError` so the caller can force a logout.

### 2. ID/name resolution (`src/api/mappers.js`)

The backend's error records only carry foreign keys (`department_id`, `category_id`, `raised_by`,
`assigned_to`, rebuttal/decision author IDs) — matching the report's normalized schema (Section 8),
not denormalized display names. This module resolves those IDs to names using the
`/departments`, `/categories`, and `/users` lookups (added to the backend specifically for this —
see the backend README's "What changed" note) before anything reaches a page component.

### 3. `AppContext.jsx` rewritten to call the backend

Same public interface (`useApp()`) so most page components needed only field-name updates, not a
rewrite of their structure:
- `loginUser(email, password)` now calls `POST /auth/login` for real — wrong credentials actually
  fail, unlike the mock's always-succeed login.
- `errors` is fetched from `GET /errors` after login and after every mutating action.
- `loadErrorDetail(id)` fetches the full record with evidence/rebuttals/decisions from
  `GET /errors/{id}` — the list endpoint doesn't include those (matches the backend's
  `ErrorListItem` vs `ErrorDetailResponse` split), so the detail page fetches on demand rather
  than assuming everything is already in the flat `errors` array.
- `addError`, `transitionErrorStatus`, `addRebuttal`, `recordDecision` call the matching real
  endpoints instead of mutating local state.
- The mock's `updateError` (freeform edit of any field including status) and `deleteError` are
  **gone** — the backend enforces a state machine for status changes (Section 7.6) and never
  hard-deletes error records (Section 5, Auditability), so there was no honest way to keep those
  operations. See below for what replaced them.

### 4. Pages updated for the real data shape and workflow

- **Login** — async, shows real error messages on failed auth; demo-account buttons now match
  the backend's seeded users (`admin@qemscorp.dev` etc., see `backend/app/tasks/seed_users.py`)
  instead of fictitious `@qems.com` addresses.
- **CreateError** — Department and Category are now `<select>`s populated from the backend
  (`GET /departments`, `GET /categories`) instead of a hardcoded 5-item list; a required Category
  field was added (the backend requires `category_id` — the original mock didn't have the concept
  of a category at all). Fields with no backend equivalent (`employeeName`, `reportedBy`,
  freeform `rootCause`/`correctiveAction` at creation time) were removed rather than silently
  dropped on submit — see the in-form note explaining root cause and corrective action are
  captured later, during review and decision, not at creation.
- **QAErrors** — filters and the status/severity badges now cover the backend's real 7-state
  workflow (`Open → In Review → Rebuttal Raised → QA Decision Pending → Resolved/Rejected →
  Closed`) instead of the mock's 3-state `Open/Review/Closed`. The Edit and Delete row actions
  were removed (not real operations — see point 3); View still works, now navigating to a page
  that fetches live detail.
- **ErrorDetails** — the biggest change. Status is no longer a freeform dropdown; instead the
  page shows role-aware, state-aware action buttons that mirror exactly what the backend's RBAC
  and state machine allow (e.g. "Start Review" only appears for QA Reviewer/Admin while status is
  `Open`; the rebuttal form only appears for Department Owner/Admin while status is `In Review`;
  the QA decision form appears for QA Reviewer/Admin while status is `QA Decision Pending`).
  Getting this wrong in the UI would just produce a `403`/`409` from the backend, so the UI
  mirrors the real constraints instead of pretending everything is always editable. Root cause
  is no longer a static text field — there's a **"Get AI Suggestion"** button that calls the real
  `POST /ai/root-cause` endpoint (OpenAI-backed, see the backend README) and a **"Find Similar"**
  button for `GET /ai/similar/{id}`, both labeled "AI Suggestion" per the backend's human-in-the-loop
  design. Evidence is now a real, clickable list of uploaded files instead of one hardcoded fake
  PDF entry.
- **Dashboard / Reports** — KPI counts now bucket the real 7 statuses into Open / Under Review /
  Closed correctly (`Resolved`/`Rejected`/`Closed` all count as closed) instead of only matching
  the old literal `"Closed"` string; severity counts include `Critical`, which the mock never had.
- **Profile** — sourced from the real logged-in user (name/email/role/department all real); the
  Department dropdown now lists the backend's actual departments instead of a hardcoded mock
  list. Saving still only updates local state — the backend has no profile-update endpoint yet,
  and the save button's toast says so explicitly rather than implying the change was persisted.

### 5. CSS additions

The mock only styled 3 status badges (`open`/`review`/`closed`) and 3 severities
(`high`/`medium`/`low`). Added badge classes for the real workflow states
(`in-review`, `rebuttal-raised`, `qa-decision-pending`, `resolved`, `rejected`) and for
`critical` severity, in `src/index.css`.

## Running it

```bash
cd frontend
npm install
cp .env.example .env   # edit VITE_API_URL if the backend isn't on localhost:8000
npm run dev            # http://localhost:3000
```

Requires the backend running (see `../backend/README.md`) and its `CORS_ORIGINS` to include
`http://localhost:3000` (already the default in `../backend/.env.example`).

## Known gaps (documented honestly, not silently missing)

- **Profile edits are local-only.** No `PATCH /users/me` exists on the backend yet.
- **PDF report export isn't available** — the backend's `/reports/summary?format=pdf` returns a
  clear 400; only `json`/`csv` work. Reports page computes its charts client-side from the
  already-fetched `errors` list rather than calling `/reports/summary` a second time.
- **The monthly trend chart's historical months (Mar–Jul) are illustrative**, not real
  time-series data — only the current month reflects actual counts. A real trend would need a
  backend endpoint that aggregates by month, which wasn't part of this pass.
