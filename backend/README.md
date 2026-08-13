# QEMS Backend — Architecture, Database & AI Integration

This is the backend for the **Quality Error Management System (QEMS)**, covering the three
modules owned by K. Somanadh in the project report (Section 16.3): **Architecture & Database
Design**, **AI Integration**, and the core **backend CRUD APIs** (built here as well, since the
teammates on this project — G. Hasini and A. Prashanth — are focused on UI/UX only). This
document explains, in detail, everything that exists in this folder, why it's built the way it
is, and how it deviates from the original project report.

## The one deliberate deviation from the report: OpenAI instead of Gemini

The original report (Section 6.2, Section 13) specifies the **Google Gemini API** for every
AI-assisted feature. **This implementation uses OpenAI instead.** Nothing about the feature set
changes — every capability from Section 13 is implemented, just against a different provider:

| Report (Gemini)                          | This implementation (OpenAI)                        |
|-------------------------------------------|-------------------------------------------------------|
| Gemini `generateContent`                  | OpenAI Chat Completions (`chat.completions.create`)   |
| Gemini embeddings endpoint                | OpenAI Embeddings (`embeddings.create`, `text-embedding-3-small`, 1536 dims) |
| `GOOGLE_API_KEY` / Gemini SDK              | `OPENAI_API_KEY` / `openai` Python SDK                |

All the Gemini-specific code lives in `app/services/ai_service.py` and `app/api/v1/routers/ai.py`
— that's the only place the swap matters. Everything else (data model, workflow, RBAC, auth) is
provider-agnostic.

---

## What's actually implemented

Given the QEMS folder was empty, this build covers the **full backend**, not just the AI slice:

1. **Architecture & Database Design** (Section 7, 8) — the layered FastAPI architecture and the
   complete normalized PostgreSQL schema from the report's DDL (Section 8.4), plus one addition
   (an embedding column) needed for AI similarity search.
2. **Core backend CRUD APIs** (Section 11) — auth, error lifecycle, evidence upload, rebuttals,
   QA decisions, and reports — normally A. Prashanth's module, built here too since UI is the
   only other module in progress.
3. **AI Integration** (Section 13) — root-cause analysis, similarity search, severity prediction,
   report summarization, smart recommendations, and natural-language search, all via OpenAI.

**Not built here** (per project decision, out of scope for this pass): Dockerization and final
frontend integration — that's still K. Somanadh's Section 16.3 item to do later, once the React
frontend (G. Hasini) and this API have both matured enough to wire together.

---

## Folder structure

```
backend/
  app/
    main.py                    # FastAPI app: middleware, routers, exception handlers
    core/
      config.py                # Settings loaded from .env (pydantic-settings)
      db.py                    # Async SQLAlchemy engine/session, declarative Base
      security.py              # Password hashing (bcrypt), JWT create/decode
      middleware.py            # Request logging + sliding-window rate limiter
      exceptions.py            # QEMSError hierarchy -> structured JSON error responses
    models/                    # SQLAlchemy ORM models, one file per table
    schemas/                   # Pydantic request/response models, one file per resource
    api/v1/
      deps.py                  # get_current_user, require_role() RBAC guard
      routers/                 # auth, errors, evidence, rebuttals, decisions, reports, ai
    services/                  # Business logic: state machine, error/auth/notification/AI services
    repositories/               # Data-access layer (repository pattern) — one per entity
    tasks/
      seed.py                  # Dev seed: roles, SLA policies, departments, categories
      seed_users.py            # Dev seed: one test user per role
  alembic/                     # DB migrations (versions/ has the initial schema)
  tests/                       # pytest suite (state machine, security, RBAC, full lifecycle)
  storage/evidence/            # Local disk evidence storage (dev only — see below)
  requirements.txt
  .env.example
```

---

## Architecture (Section 7)

Three-tier layered architecture exactly as specified in the report:

```
Client Request
     |
     v
API Layer (routers/)       <- request validation via Pydantic schemas
     |
     v
Middleware                  <- JWT auth, CORS, request logging, rate limiting
     |
     v
Service Layer (services/)   <- business rules, the error workflow state machine, SLA calc
     |
     v
Repository Layer (repositories/) <- all SQLAlchemy queries, transactions
     |
     v
PostgreSQL
```

Routers never touch SQLAlchemy directly — they call a service, which calls one or more
repositories. This is what lets the error workflow (state transitions, audit logging,
notifications) live in one place (`app/services/error_service.py`) instead of being duplicated
across every router that touches an error.

### The error state machine (Section 7.6)

Implemented literally as a transition table in `app/services/error_state_machine.py`:

```
Open -> In Review -> Rebuttal Raised -> QA Decision Pending -> Resolved -> Closed
                  \-------------------------^                          \
                                                                     Rejected -> Closed
```

Every transition is validated against this table (`assert_valid_transition`); an invalid
transition raises a `409 Conflict`. An `Admin` can force any transition via
`admin_override: true` on `PATCH /errors/{id}/status` — this bypasses the table but is always
recorded in the audit log as `ERROR_STATUS_ADMIN_OVERRIDE` (matches Section 7.6's "Admin
override, logged" arrow).

A QA decision of `"Escalated"` is a special case not in the report's state diagram: it's
recorded but does **not** close the error — it stays in `QA Decision Pending` for a senior
reviewer, since escalation logically can't auto-close a workflow.

---

## Database (Section 8)

The schema in `app/models/` is a direct implementation of the report's DDL (Section 8.4) — same
12 tables, same normalization (3NF, with audit/notification tables intentionally denormalized for
read performance, per Section 8.1), same indexes (`idx_errors_status`, `idx_errors_department`,
`idx_errors_due_at`, `idx_evidence_error`, `idx_audit_error`).

**One addition beyond the report's DDL**: `errors.description_embedding`, a
`vector(1536)` column (via the `pgvector` extension), storing the OpenAI embedding of each
error's description for similarity search (Section 13.2). The report mentions pgvector as the
implementation mechanism for this feature but didn't add the column to its DDL — this fills that
gap.

All timestamp columns are `TIMESTAMPTZ` (timezone-aware), configured once via SQLAlchemy's
`type_annotation_map` on the declarative `Base` (`app/core/db.py`) rather than repeated on every
column.

### Migrations

Managed with Alembic (`alembic/`), configured to read `DATABASE_URL` from `.env` (see
`alembic/env.py`) rather than hardcoding credentials in `alembic.ini`. The initial migration
(`alembic/versions/f0a5d490f0d4_initial_schema.py`) creates the `vector` extension and all 12
tables.

**This was tested against a real, running PostgreSQL instance** (Postgres 17 + pgvector 0.8.6,
installed locally for this build) — not just autogenerated and left unverified. The migration
was applied, seeded, and exercised through the full API before being considered done.

---

## Backend CRUD (Section 9, 11)

Implements every endpoint listed in the report's Section 11 REST API doc:

| Method | Path                              | Auth                              | Section |
|--------|-----------------------------------|-------------------------------------|---------|
| POST   | `/api/v1/auth/login`              | none                                 | 11.2 |
| POST   | `/api/v1/auth/refresh`            | refresh token                       | 11.2 |
| POST   | `/api/v1/errors`                  | any authenticated user              | 11.3 |
| GET    | `/api/v1/errors`                  | any authenticated user              | 11.3 |
| GET    | `/api/v1/errors/{id}`             | any authenticated user              | 11.3 |
| PATCH  | `/api/v1/errors/{id}/status`      | QA Reviewer, Admin                  | 11.3 |
| POST   | `/api/v1/errors/{id}/evidence`    | any authenticated user              | 11.4 |
| POST   | `/api/v1/errors/{id}/rebuttals`   | Department Owner, Admin             | 11.5 |
| POST   | `/api/v1/errors/{id}/decision`    | QA Reviewer, Admin                  | 11.6 |
| GET    | `/api/v1/reports/summary`         | QA Reviewer, Admin, Viewer          | 11.7 |
| POST   | `/api/v1/ai/root-cause`           | QA Reviewer, Admin                  | 11.8 |
| GET    | `/api/v1/ai/similar/{id}`         | QA Reviewer, Admin                  | 11.8 |
| POST   | `/api/v1/ai/severity-prediction`  | any authenticated user              | 13.3 |
| POST   | `/api/v1/ai/report-summary`       | QA Reviewer, Admin, Viewer          | 13.4 |
| POST   | `/api/v1/ai/smart-recommendation` | QA Reviewer, Admin                  | 13.5 |
| POST   | `/api/v1/ai/nl-search`            | any authenticated user              | 13.6 |
| GET    | `/api/v1/departments`             | any authenticated user              | — (added for frontend integration, see below) |
| GET    | `/api/v1/categories`              | any authenticated user              | — (added for frontend integration, see below) |
| GET    | `/api/v1/users`                   | any authenticated user              | — (added for frontend integration, see below) |
| GET    | `/health`                          | none                                 | — (orchestration health-check) |

The three lookup endpoints (`app/api/v1/routers/lookups.py`) aren't in the report's Section 11 —
they exist because the frontend needs somewhere to source real `department_id`/`category_id`
values for dropdowns and to resolve `raised_by`/`assigned_to`/decision-author IDs to display
names, since the core resource endpoints only ever return foreign keys (matching the report's
normalized DDL). `RebuttalSummary`/`DecisionSummary` also gained `raised_by`/`decided_by` fields,
and `auth.UserSummary` gained `email`/`department_id`, for the same reason — see
`../frontend/README.md` for the full account of what the frontend needed and why.

Auth is JWT (HS256), matching Section 9.3/14.1/14.6 exactly: 30-minute access tokens, 7-day
refresh tokens, role claims embedded in the access token, validated on every protected request via
`get_current_user`. RBAC is enforced with `require_role(*roles)` (`app/api/v1/deps.py`) —
server-side only, independent of any UI restriction (Section 14.2).

### Evidence storage

The report specifies Supabase Storage or Azure Blob Storage (Section 6.2). This build talks to
a **local MinIO instance** — a real S3-compatible object store, not local disk — via
`app/services/storage_service.py`. Every upload goes through `PUT /qems-evidence/evidence/<uuid>_<filename>`
using boto3, and the returned `file_url` is a real, fetchable URL, not a stub. Because MinIO
speaks the S3 API, swapping to real AWS S3, Supabase Storage, or Azure Blob's S3-compatible
endpoint in production is a config change (`S3_ENDPOINT_URL`, credentials) — the code doesn't
change. Files are validated for MIME type and size before upload (Section 4.6/14.5).

One deliberate simplification: the MinIO bucket is set to public-read (`mc anonymous set
download`) rather than generating presigned URLs per upload. Section 14.5 calls for signed,
time-limited URLs in production — implementing that fully means every place `EvidenceSummary`
gets serialized would need to call back into the storage service to mint a fresh URL instead of
reading a static DB column, which is a real (if contained) piece of surgery. Flagging it here
rather than doing it silently or claiming it's done.

Run `docker run` isn't used — MinIO and Mailpit (below) run as plain local processes, matching
how Postgres is run in this project (see Setup). Start them with:
```bash
MINIO_ROOT_USER=qems_minio MINIO_ROOT_PASSWORD=qems_minio_secret \
  minio server --address ":9000" --console-address ":9001" /opt/homebrew/var/minio-data &
mailpit --smtp 127.0.0.1:1025 --listen 127.0.0.1:8025 &
```
MinIO console: `http://localhost:9001` (login with the root user/password above).

### Email notifications (Section 4.7)

`NotificationService` (`app/services/notification_service.py`) sends real SMTP email — recipient
address is resolved from the `user_id` via `UserRepository`, subject/body are built by the
caller, and the send itself goes through Python's `smtplib` off the event loop
(`asyncio.get_running_loop().run_in_executor`) so it never blocks other requests. Every send is
also recorded in the `notifications` table with a `Pending` → `Sent`/`Failed` status, satisfying
the append-only visibility the report expects.

In dev this points at a local **Mailpit** instance — a real SMTP server with nothing behind it
but a web inbox at `http://localhost:8025`, so you can watch the actual emails QEMS sends
(assignment notices, rebuttal-raised alerts, QA decision notices) without needing a real mail
account. Swapping to a real provider (SendGrid, Resend, or your organization's SMTP) in
production is a `.env` change (`SMTP_HOST`/`PORT`/credentials) — `NotificationService` doesn't
change.

### Error handling

Every error response is structured JSON: `{"error": {"code": ..., "message": ...}}` (Section 9.5).
This is enforced by two exception handlers in `app/main.py` — one for the app's own `QEMSError`
hierarchy (`NotFoundError`, `PermissionDeniedError`, `ValidationError`, `ConflictError`,
`UnauthorizedError`, `AIServiceError`), and a catch-all for anything unhandled, so a bug never
leaks a raw Python traceback to the client.

### Known limitation

`GET /reports/summary?format=pdf` is **not implemented** — it returns a clear `400` explaining
that only `json` and `csv` are supported. Adding real PDF generation would mean pulling in a
rendering library (e.g. `reportlab` or a headless-browser approach) that wasn't asked for in this
pass; CSV export is fully implemented and covers the same underlying data.

---

## AI Integration (Section 13) — via OpenAI

All AI logic lives in `app/services/ai_service.py`; the router (`app/api/v1/routers/ai.py`) is a
thin layer that fetches the relevant DB context and calls it. Every response includes
`"label": "AI Suggestion"` — the report is explicit (13.7) that AI output must always be
presented as a suggestion, a human reviewer stays in the loop, and nothing AI-generated is ever
persisted as an authoritative field without confirmation. This build honors that: **no AI
endpoint writes anything back to the `errors` table** (except the description embedding, which is
plumbing for search, not a judgment call).

1. **Root-cause analysis** (13.1) — `POST /ai/root-cause`. Builds a prompt from the error's
   title/description/category plus a list of historically similar *closed* errors (from #2
   below), asks OpenAI for a structured JSON root-cause + confidence. Cached in-process per
   `error_id` for 1 hour (13.7's caching requirement) — a simple dict cache, documented as
   not-distributed (fine for a single-instance dev/demo deployment; swap for Redis if you scale
   out).
2. **Similarity search** (13.2) — `GET /ai/similar/{id}`. Every error's description is embedded
   with OpenAI's `text-embedding-3-small` at creation time and stored in
   `errors.description_embedding`. Similarity search uses pgvector's cosine-distance operator
   directly in SQL (`Error.description_embedding.cosine_distance(...)`, see
   `app/repositories/error_repository.py::find_similar_closed`) — no embeddings are pulled into
   Python for comparison, so this scales with the database, not with app memory.
3. **Severity prediction** (13.3) — `POST /ai/severity-prediction`. Suggests Low/Medium/High/
   Critical from a title+description; the inspector can accept or override it (this endpoint
   itself doesn't touch the DB — the frontend decides what to do with the suggestion).
4. **Report summarization** (13.4) — `POST /ai/report-summary`. Pulls matching errors for a date
   range/department and asks OpenAI for a narrative summary to append to an exported report.
5. **Smart recommendations** (13.5) — `POST /ai/smart-recommendation`. Given a category +
   department, looks at recent history in that department and asks OpenAI to suggest a likely
   owner and estimate SLA risk.
6. **Natural-language search** (13.6) — `POST /ai/nl-search`. Translates a plain-English query
   (e.g. "high severity packaging errors from last month still open") into structured filter
   fields matching `GET /errors`'s query parameters.

**Implementation notes (13.7), confirmed in this build:**
- All AI calls are server-side only — the `OPENAI_API_KEY` never reaches the frontend.
- Every OpenAI SDK failure (bad key, rate limit, timeout) is caught and turned into a clean
  `503 {"error": {"code": "ai_service_unavailable", ...}}` — verified against a real 401 from an
  invalid key during testing (see Testing section below).
- Error **creation never fails because of AI** — if embedding generation throws, it's logged and
  the error is created without an embedding (verified in testing).

---

## Setup

### Prerequisites

- Python 3.11+ (built and tested on 3.13)
- PostgreSQL 15+ with the `pgvector` extension available
- MinIO (object storage) and Mailpit (SMTP + web inbox) — `brew install minio minio-mc mailpit`.
  Only needed for evidence upload and email notifications; everything else works without them.
- An OpenAI API key (only needed for the `/ai/*` endpoints — everything else works without it)

### Install

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# edit .env: set DATABASE_URL, JWT_SECRET, OPENAI_API_KEY
```

### Database

```bash
# create the database/role (adjust to your local Postgres setup), then:
alembic upgrade head
python -m app.tasks.seed          # roles, SLA policies, departments, categories
python -m app.tasks.seed_users    # one test user per role, password: Password123!
```

### Object storage & email

```bash
# MinIO — object storage for evidence uploads
MINIO_ROOT_USER=qems_minio MINIO_ROOT_PASSWORD=qems_minio_secret \
  minio server --address ":9000" --console-address ":9001" /opt/homebrew/var/minio-data &
mc alias set local http://localhost:9000 qems_minio qems_minio_secret
mc mb local/qems-evidence
mc anonymous set download local/qems-evidence   # public-read; see "Known limitation" above

# Mailpit — catches every email QEMS sends, viewable at http://localhost:8025
mailpit --smtp 127.0.0.1:1025 --listen 127.0.0.1:8025 &
```

### Run

```bash
uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` for interactive Swagger UI (auto-generated by FastAPI from
the Pydantic schemas — useful for the frontend team to see exact request/response shapes).

### Test

```bash
pytest -v
```

16 tests covering: the state machine's allowed/rejected transitions and admin override, JWT
create/decode and password hashing round-trips, RBAC guard allow/reject behavior, and — the most
important one — a full integration test that runs an error through
**Open → In Review → Rebuttal Raised → QA Decision Pending → Resolved → Closed** against a real
Postgres transaction (rolled back after, so it leaves no data behind), asserting the audit log,
SLA due-date computation, and QA code generation all work together correctly.

---

## What was actually verified (not just written)

Everything in this README was checked against a live environment during the build, not assumed:

- Installed PostgreSQL 17 + pgvector 0.8.6 locally, created the `qems` database, ran the Alembic
  migration, and confirmed all 12 tables + the `vector(1536)` column exist with the right
  constraints and indexes.
- Seeded roles/departments/categories/SLA policies and one test user per role.
- Booted the FastAPI app and hit every route via `curl`, driving a **complete error lifecycle
  through the real API**: login → create error (QA code `QEMS-2026-00001` generated correctly,
  SLA due-date computed correctly from the category's policy) → transition to In Review → submit
  a rebuttal as Department Owner → record a QA decision as QA Reviewer → confirmed the error
  auto-closed and the audit log has all 6 entries in order.
- Confirmed RBAC actually blocks a Viewer from recording a decision (`403`) and the state machine
  actually rejects an invalid `Open -> Closed` jump (`409`).
- Hit an AI endpoint with an invalid OpenAI key and confirmed it returns a clean `503` with a
  structured error body instead of a raw traceback (this uncovered and fixed a real gap — OpenAI
  SDK errors weren't being translated to the app's JSON error format until this was found here).
- Ran the full pytest suite against the same live database: 16/16 passing.
- Installed and ran MinIO + Mailpit locally, created an error assigned to another user, and
  confirmed a real email landed in Mailpit's inbox with the correct recipient, subject, and body.
  Uploaded a PDF as evidence, confirmed the object actually exists in the MinIO bucket
  (`mc ls`), and confirmed the returned URL serves the real file content back — checked all the
  way through the frontend too, where the evidence link now points straight at the MinIO URL.

Two environment issues were hit and fixed along the way, in case they resurface on another
machine: `asyncpg==0.29.0` fails to build on Python 3.13 (fixed by pinning `0.30.0`), and
`passlib==1.7.4`'s bcrypt backend self-test is incompatible with `bcrypt>=4.1` (fixed by pinning
`bcrypt==4.0.1` — both pins are already in `requirements.txt`).
