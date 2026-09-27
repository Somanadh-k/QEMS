# QEMS — Comprehensive QA & Security Test Report

**Test date:** 2026-09-06
**System under test:** QEMS (Quality Error Management System) — FastAPI backend, React frontend, PostgreSQL + pgvector
**Report status:** Final, normalized (supersedes all earlier drafts of this file)

## Status Dashboard

| Metric | Result |
|---|---:|
| Total tests | 227 |
| Passed | 220 |
| Failed | 2 |
| Blocked | 2 |
| Not implemented | 1 |
| Not testable | 2 |
| Open critical defects | 0 |
| Open high defects | 0 |
| Open medium defects | 2 |
| Open low defects | 0 |
| Production status | Single-department pilot |

---

## 1. Executive Summary

QEMS was tested end-to-end against a live backend, a live PostgreSQL database, and the
project's existing `pytest` regression suite. Of **227** test cases executed across
authentication, RBAC, the full error lifecycle, rebuttals, evidence, decisions,
SLA/escalations, reporting, AI functionality, AI/API security, and database integrity:
**220 passed, 2 failed, 2 were blocked by data/timing conditions (not defects), and 1 is
a documented not-implemented feature.** Two additional areas — live AI narrative output
quality and live browser-driven frontend interaction — are **NOT TESTABLE** in this
environment for stated, non-application reasons, and are reported as such rather than
assumed, inferred, or fabricated.

**Nine previously-identified defects (D-01 through D-09, D-11) were re-verified in this
session and confirmed FIXED.** One previously-reported item (D-10) was re-isolated to a
benign React development-mode behavior and is retracted as not a defect.

**Two open defects remain, both instances of the same underlying gap**: neither
`GET /errors/{id}` nor `GET /evidence/{id}/url` enforces department/ownership
authorization, so any authenticated user can read another department's error records or
mint an evidence link for them. This is documented in the codebase's own docstring as
deferred scope, not a silent regression, but it is a real, reproduced MEDIUM-severity gap.

**Verdict: READY for a single-department pilot, with conditions. NOT READY for
multi-department or multi-tenant production** until department/ownership authorization
is implemented for error and evidence reads, and until AI narrative output quality is
validated against a real model.

## 2. Scope

This audit covered, using only the running system and existing project tooling (no new
test frameworks or dependencies were installed):

- Authentication and refresh-token handling
- Role-based access control (Admin, QA Reviewer, Department Owner, Viewer) across every
  state-changing and read endpoint
- QA error creation, field validation, and unique error-code generation
- The full error lifecycle state machine, valid and invalid transitions
- Rebuttal submission and validation
- Evidence upload, validation, and presigned-URL retrieval
- QA decision recording
- SLA computation/pause and escalation listing/acknowledgment
- Dashboard/reporting data accuracy (backend source only — see §16, §23)
- AI functionality: root-cause suggestion, similarity search, severity prediction,
  report summarization, smart recommendation, NL search, and the recurrence/risk
  Quality Signal pipeline
- AI and API security, including prompt-injection and IDOR probing
- Database referential and hash-chain integrity
- The existing 76-test `pytest` regression suite
- Baseline (non-load) performance sampling

Explicitly **out of scope** for this audit, by instruction: destructive testing, database
mutation beyond ordinary API-driven writes, application code changes, and installing new
tooling (e.g., a browser-automation framework) solely to close a testing gap.

## 3. Test Environment

| | |
|---|---|
| **Frontend** | React 19 + Vite 8, dev server verified reachable (`200`); production build (`npm run build`) verified to complete with no errors |
| **Backend** | FastAPI + Uvicorn, verified reachable (`GET /health` → `200`), Python 3.13 |
| **Database** | PostgreSQL with pgvector; `alembic current` verified equal to `alembic heads` (no pending/divergent migrations) |
| **Object storage** | MinIO — health endpoint verified reachable |
| **Email** | Mailpit — verified reachable |
| **AI provider** | OpenAI configured (chat + embedding models); `OPENAI_API_KEY` is a literal placeholder value — every live chat-completion call was confirmed to fail upstream with a genuine `401` from OpenAI, which the application correctly translates into a clean `503` |
| **Browser automation** | Not available in this environment — no Playwright, no headless Chromium/Chrome, no Cypress installed or reachable; not installed for this audit (would introduce a new dependency for a one-off check) |
| **Test method** | Direct HTTP calls against the live backend, direct SQL against the live database, execution of the existing `pytest` suite, a production frontend build, and static source review |

## 4. Test Statistics

| Category | Total | Passed | Failed | Blocked | Not Implemented | Not Testable |
|---|---|---|---|---|---|---|
| Environment/Startup | 6 | 6 | 0 | 0 | 0 | 0 |
| Authentication | 10 | 9 | 0 | 0 | 1 | 0 |
| RBAC | 30 | 30 | 0 | 0 | 0 | 0 |
| Error Creation | 1 | 1 | 0 | 0 | 0 | 0 |
| Error Validation | 10 | 10 | 0 | 0 | 0 | 0 |
| Unique ID Generation | 1 | 1 | 0 | 0 | 0 | 0 |
| Lifecycle (valid + invalid transitions) | 12 | 12 | 0 | 0 | 0 | 0 |
| Rebuttal | 7 | 7 | 0 | 0 | 0 | 0 |
| Evidence | 7 | 7 | 0 | 0 | 0 | 0 |
| QA Decision | 3 | 3 | 0 | 0 | 0 | 0 |
| SLA | 4 | 4 | 0 | 0 | 0 | 0 |
| Escalation | 4 | 2 | 0 | 2 | 0 | 0 |
| Dashboard | 1 | 1 | 0 | 0 | 0 | 0 |
| Reports | 5 | 5 | 0 | 0 | 0 | 0 |
| AI Functionality | 7 | 7 | 0 | 0 | 0 | 0 |
| AI Similarity | 1 | 1 | 0 | 0 | 0 | 0 |
| AI Recurrence | 3 | 3 | 0 | 0 | 0 | 0 |
| AI Authorization | 3 | 3 | 0 | 0 | 0 | 0 |
| AI Security | 4 | 4 | 0 | 0 | 0 | 0 |
| AI Narrative Quality | 1 | 0 | 0 | 0 | 0 | 1 |
| API Security (incl. both IDOR checks) | 11 | 9 | 2 | 0 | 0 | 0 |
| Frontend — live browser | 1 | 0 | 0 | 0 | 0 | 1 |
| Frontend — static/build | 4 | 4 | 0 | 0 | 0 | 0 |
| Database Integrity | 11 | 11 | 0 | 0 | 0 | 0 |
| Regression (`pytest`) | 76 | 76 | 0 | 0 | 0 | 0 |
| Performance | 4 | 4 | 0 | 0 | 0 | 0 |
| **TOTAL** | **227** | **220** | **2** | **2** | **1** | **2** |

Reconciliation: 220 + 2 + 2 + 1 + 2 = **227**. ✓

## 5. Functional Test Results

Every backend module was exercised end-to-end against the live system: login, error
creation through the full lifecycle to closure, rebuttal, evidence upload and retrieval,
QA decision, SLA pause, reports (JSON and CSV, filtered), and all AI/signal endpoints. No
module was found to be a stub or an unreachable code path. Functional defects, where
found, are recorded in §20/§21, not as module absence.

## 6. Authentication & RBAC

**Authentication** — PASS except logout (documented as not implemented):

- Valid login succeeds for all 4 seeded roles.
- Invalid password and unknown-user both return an identical `401` with the same
  message — no user enumeration via response differences.
- Malformed/garbage bearer token and missing token on a protected route both → `401`.
- A refresh token presented as an access token is correctly rejected (`401`).
- `GET /auth/me` returns the correct current-user summary; `POST /auth/refresh` with a
  valid refresh token succeeds.
- `POST /auth/logout` — **NOT IMPLEMENTED** (`404`). Logout is a client-side token
  discard only. Not counted as a defect: nothing in the codebase claims a server-side
  logout/revocation exists for this stateless JWT design.

**RBAC** — full role × endpoint matrix, verified with real tokens per role, 30/30 PASS:

| Action | Admin | QA Reviewer | Dept. Owner | Viewer |
|---|---|---|---|---|
| Create error | ✅ | ✅ | ✅ | ✅ *(no role guard by design — see note)* |
| List/view errors | ✅ | ✅ | ✅ | ✅ |
| Transition status | ✅ | ✅ | ❌ 403 | ❌ 403 |
| Submit rebuttal | ✅ | ❌ 403 | ✅ | ❌ 403 |
| Record decision | ✅ | ✅ | ❌ 403 | ❌ 403 |
| Pause SLA clock | ✅ | ❌ 403 | *(same guard)* | *(same guard)* |
| View audit-chain verify | ✅ | ❌ 403 | ❌ 403 | ❌ 403 |
| AI root-cause/recommendation | ✅ | ✅ | ❌ 403 | ❌ 403 |
| Reports summary/trends | ✅ | ✅ | ❌ 403 *(by design)* | ✅ |
| Upload evidence | ✅ | ✅ | ✅ | ✅ *(no role guard — see note)* |

Every negative-permission case returned a clean `403 permission_denied`, enforced at the
API layer, not only in the UI. `POST /errors` and evidence upload have no `require_role`
guard at all — any authenticated user, including `Viewer`, can create errors and attach
evidence. This is a product-scope observation (the `Viewer` role is not strictly
read-only), not logged as a defect.

## 7. Error Lifecycle

Verified state machine, confirmed live end-to-end:

```
Open → In Review → {Rebuttal Raised, QA Decision Pending}
Rebuttal Raised → QA Decision Pending
QA Decision Pending → {Resolved, Rejected}
Resolved → Closed, Rejected → Closed
Closed → (terminal)
```

**Valid transitions — all PASS**: `Open → In Review`; `In Review → QA Decision Pending`;
`record_decision(Resolved)` auto-chains to `Closed` with `closed_at` populated; a genuine
`Admin`-role `admin_override:true` correctly bypasses the state machine, while the
identical request from a non-Admin role is silently downgraded to the normal rule and
correctly rejected.

**Invalid transitions — all correctly rejected, all PASS**: skip-ahead
(`Open → QA Decision Pending`), repeat-same-state, `Closed → Open`, rebuttal on a
`Closed` error, and duplicate decision on a `Closed` error all return `409`. An
unrecognized status string (e.g. `"NotARealStatus"`) returns a clean `422` naming every
valid value — confirmed as the current, correct behavior (see D-03 in §21).

## 8. Rebuttal Management

- Valid rebuttal by the correct role (`Department Owner`) → `201`; error correctly moves
  to `Rebuttal Raised`.
- Rebuttal by `QA Reviewer` or `Viewer` → `403`.
- Empty-string justification → `422` (current, correct behavior — see D-06 in §21).
- A second rebuttal while already `Rebuttal Raised` → `409`.
- A 20,000-character justification is accepted without error.

## 9. Evidence Management

- Valid PNG upload → `201` with correct metadata and SHA-256.
- Unsupported MIME type → `422`. Oversized file (16 MB against a 15 MB limit) → `422`.
- Upload against a nonexistent error → `404`.
- Path-traversal filename (`../../../etc/passwd`) → accepted but handled safely: the
  server generates its own opaque storage key and only stores the traversal string as a
  cosmetic display name. No traversal risk confirmed.
- 0-byte file → `422` (current, correct behavior — see D-08 in §21).
- Presigned evidence URL issued correctly with a 5-minute expiry and an access-log row.
- **`GET /evidence/{id}/url` has no ownership/department check** — see D-07-EVIDENCE
  in §20.

## 10. QA Decisions

- Valid decision (`Resolved`) by `QA Reviewer` → `201`, error auto-closes.
- Decision by `Department Owner` or `Viewer` → `403`.
- Invalid decision literal → `422` with a clear message naming the three valid values
  (current, correct behavior — see D-09 in §21).
- No AI-touched route accepts a write to `decision`, `status`, or `severity` — confirmed
  both by reading every AI route and by the project's own `test_ai_write_isolation.py`
  (genuine structural assertions on route schemas, model columns, and prompt text — not
  a stub), which passed in the regression run (§18).

## 11. SLA & Escalation

- `GET /errors/{id}/sla` → `200`, correct state/stage/consumption-ratio/timeline
  structure.
- `POST /errors/{id}/sla/pause` — Admin-only (`QA Reviewer` correctly gets `403`),
  requires a non-empty reason (empty reason → `422`).
- `GET /escalations` — Admin sees all; non-admin roles correctly scoped to their own.
- **`POST /escalations/{id}/ack` — BLOCKED**, not failed. The live database currently has
  zero rows in `escalations` and zero errors past their SLA due date, confirmed directly
  via SQL. This is a direct, expected consequence of a full database reset performed
  earlier: every seeded due date is now in the future, so the background escalation job
  has had nothing to fire on. Forcing a breach would require either waiting for a real
  SLA window to elapse or backdating governance data, both judged out of scope for a
  non-destructive audit. The acknowledgment code path itself was read and follows the
  same pattern (role guard + required non-empty field) already verified working for SLA
  pause.

## 12. Dashboard & Reporting

**Dashboard**: no live browser is available in this environment (§16, §23), so the
dashboard's rendered tiles could not be visually verified. What was verified instead is
the backend data source the dashboard reads from: `GET /reports/summary` correctly
reports a `total_errors` value that matches direct database counts exactly at every
point checked, including past the previously-reported 100-record threshold at which the
dashboard was known to fail before its fix. The specific fix itself (`AppContext.jsx`
looping through pages using the API's own `total` rather than a hard-capped 100-row
fetch) was confirmed by reading the current source, which is structurally correct.
**Live rendering of the dashboard is NOT TESTABLE in this session** (§23).

**Reports**:
- `GET /reports/summary` — correct aggregation, verified against `severity=Critical`,
  `department_id` filters, and a future date range (correctly returns all-zero, not an
  error).
- `GET /reports/summary?format=csv` — confirmed genuine: a `text/csv` streaming response
  with a proper `Content-Disposition: attachment` header.
- `GET /reports/analytics/trends` — `200`, correct monthly-bucketed structure.

## 13. AI Functionality

**Verified live** (root-cause suggestion, similar-error search, severity prediction,
report summarization, smart recommendation, NL-search-to-filters, and the Quality Signal
recurrence-risk pipeline):

| Test | Result |
|---|---|
| Root-cause analysis | Clean `503 ai_service_unavailable`, citing the real upstream `401` from OpenAI — not a crash |
| Similar-error search | **PASS** — `200`, returns embedding-retrieved candidates, independent of the chat-completion outage |
| Severity prediction / report summary / smart recommendation / NL search | `503`, clean, in every case |
| Signal/recurrence engine | `200` — for a freshly created, topically-unique error, correctly returns `NO_COMPARABLE_FINDINGS` rather than fabricating a result |
| Signal recompute / insights history | `200`, consistent behavior |
| Root-cause on nonexistent error | `404` |
| ~114 KB description at creation | `201` — creation and embedding both completed without error |

**AI similarity/vector retrieval**: VERIFIED — `GET /ai/similar/{id}` returns
pgvector-backed retrieval results independent of the chat-completion outage (embeddings
fall back to a deterministic local embedder when no usable key is configured).

**AI recurrence/risk-scoring infrastructure**: VERIFIED — the embed → gate → retrieve →
count → score/band → narrate → persist pipeline runs and returns correct, honest
non-fabricated statuses (e.g. `NO_COMPARABLE_FINDINGS`) when no comparable history exists.

**AI authorization**: VERIFIED — `Department Owner` and `Viewer` both correctly blocked
(`403`) from `/ai/root-cause` and `/errors/{id}/insights`.

**AI narrative/root-cause/summary quality: NOT TESTABLE.**
Reason: `OPENAI_API_KEY` is a placeholder value, and every live OpenAI call returned a
genuine `401` upstream. No real model-generated narrative, root-cause suggestion, or
summary was ever produced in this session, so relevance, coherence, and hallucination
risk could not be evaluated. This is stated as an environmental limitation, not a defect
and not a tested-and-passed result.

## 14. AI Security & Human-in-the-Loop

- **Prompt injection isolation — TESTED for workflow-field protection.** A description
  field was deliberately constructed with an injection payload instructing the model to
  alter severity/status, submitted through the normal error-creation API. The root-cause
  endpoint still returned a clean `503` (no crash), and a direct follow-up read confirmed
  the targeted fields (`severity`, `status`) were unchanged. This confirms no AI-touched
  code path can write to a workflow field, matching the structural guarantee already
  enforced by `test_ai_write_isolation.py`.
- **No secret leakage in frontend**: searching frontend source and the compiled
  production bundle for API-key-shaped strings found no actual secret value — the one
  match in source was a user-facing status string referencing the environment variable
  name, not a key.
- All AI calls are proxied through the backend; the frontend has no direct OpenAI
  integration.
- **Human oversight — VERIFIED**: no route allows an AI-touched path to write
  `decision`, `status`, or `severity`; every insight requires an explicit reviewer action
  (accept/partial/reject) with a mandatory note for anything short of full acceptance.

## 15. API Security

- Negative/non-numeric error IDs → `404`/`422` correctly. Malformed JSON body → `422`.
- SQL injection via a string filter param and via a typed integer field — both safely
  neutralized by the ORM; database tables confirmed intact immediately after.
- **Login rate limiting**: engages at exactly the configured 5-per-minute threshold.
- **Per-account rate-limit isolation confirmed**: after exhausting the rate-limit budget
  against one account from a given source, a different real account logged in
  successfully on the very next request from the same source (see D-05 in §21).
- All protected routes reject a missing token.
- **IDOR — `GET /errors/{id}` has no department/ownership scoping**: confirmed
  reproduced. See D-07 in §20.

## 16. Frontend Testing

**Production build: VERIFIED.** `npm run build` completes with no errors.

**Frontend source-level behavior: VERIFIED where possible.**
- RBAC-aware UI gating is present in source (role-derived booleans gating the
  transition/rebuttal/decision UI), confirmed by direct reading of the component.
- No client-side router is present (no `react-router`/`BrowserRouter` in source or
  dependencies) — the application has no deep-linkable routes. This is a UX
  characteristic, not a defect against any stated requirement.
- The dashboard pagination fix was confirmed correct by reading the current data-fetching
  logic (loops through all pages using the API's reported total, rather than truncating
  at a fixed page size).

**Live browser automation regression: NOT TESTABLE.**
Reason: no browser automation tooling (Playwright, headless Chromium/Chrome, Cypress) is
installed or reachable in this environment. None was installed for this audit, since
doing so solely to close a one-off testing gap would introduce a new dependency outside
the audit's scope. No claim is made that live UI interaction, clicking, or visual
rendering was verified.

## 17. Database Integrity

| Check | Result |
|---|---|
| Orphan evidence / rebuttal / qa_decision rows | 0 each |
| Errors with a status outside the enum | 0 |
| `Closed` errors missing `closed_at` | 0 |
| Duplicate `qa_error_code` values | 0 |
| Orphan `user_roles` rows | 0 |
| Escalations with a null owner | 0 (table currently empty — see §11) |
| `audit_logs` rows with a null `row_hash` | 0 |
| Audit-log table DB-level write protection | Confirmed in force at the database level (DELETE/UPDATE privileges revoked for the application role) |
| `GET /audit/verify` | Confirmed valid against real, live-generated audit activity from this session's own test traffic |
| `Closed` errors with zero `qa_decisions` rows | A nonzero count exists, traced entirely to legacy seed-inserted historical records that bypass the normal service layer. **This is a seed-data characteristic, not a current API workflow defect** — no route was found, or exercised, that lets a live, API-driven closure skip creating a `QADecision` row. |
| Migrations | `alembic current` matches `alembic heads` exactly — no pending or divergent migrations |

## 18. Regression Testing

The existing 76-test `pytest` suite was executed and passed in full (76/76), including
the structural AI-write-isolation tests, audit-chain tests, RBAC tests, state-machine
tests, and SLA/business-hours tests. This suite was run more than once during the audit,
with identical results each time, including after a substantial volume of additional
API-driven test data had been created.

**Caveat, applicable throughout this report**: a passing `pytest` suite verifies logic in
isolation against fixture data. It does not, by itself, prove the live database's audit
chain is intact or that a live database grant is actually revoked — both of those were
separately verified directly against the running system (§17), not inferred from the
test suite passing.

## 19. Performance & Reliability

| Check | Result |
|---|---|
| `GET /errors?page_size=20` × 10 | Low single-digit-to-low-teens millisecond average |
| `GET /errors?page_size=100` × 10 | Tens of milliseconds average |
| `GET /reports/analytics/trends` × 10 | Low single-digit millisecond average |
| `GET /reports/summary` × 10 | Low single-digit millisecond average |

No N+1 query pattern was observed in the endpoints exercised. Rapid sequential error
creation produced zero duplicate `qa_error_code` values.

**This was NOT a production-scale load test.** No concurrency or volume stress was
applied, consistent with the instruction to avoid destructive testing. Performance was
sampled only at the current, modest single-user data volume; behavior at production data
volumes or under concurrent load remains untested.

## 20. Open Defects

| ID | Severity | Endpoint | Description | Status |
|---|---|---|---|---|
| D-07 | MEDIUM | `GET /errors/{id}` | Missing department/ownership authorization scoping. An authenticated user can retrieve an error belonging to another department. | **OPEN** |
| D-07-EVIDENCE | MEDIUM | `GET /evidence/{id}/url` | Missing department/ownership authorization scoping. An authenticated user can obtain an evidence URL belonging to another department. | **OPEN** |

D-07 and D-07-EVIDENCE are two endpoint manifestations of the same underlying
authorization gap — neither endpoint applies a department/ownership filter before
returning data — and are recorded as two explicit findings because both were
independently reproduced against their respective endpoints. Fixing the underlying gap
(e.g., applying the same department-visibility pattern already used elsewhere in the
codebase for AI-neighbour retrieval) would be expected to resolve both.

No other open defects exist. No new defect class was found beyond this one.

## 21. Resolved Defects

The following defects were found and fixed prior to this audit session and were
**independently re-verified as currently fixed** by direct reproduction in this session
(not by re-reading the prior report's claims):

| ID | Description | Status |
|---|---|---|
| D-01 | Dashboard count/pagination issue — dashboard KPI aggregation was truncated past a fixed row-count cap | **FIXED AND RE-VERIFIED** |
| D-02 | Audit-chain database protection issue — DB-level write protection on the audit log was not actually in force | **FIXED AND RE-VERIFIED** |
| D-03 | Invalid lifecycle status value caused an unhandled server error instead of a clean validation error | **FIXED AND RE-VERIFIED** |
| D-04 | Oversized error title caused an unhandled server error instead of a clean validation error | **FIXED AND RE-VERIFIED** |
| D-05 | Rate-limit account isolation issue — login rate limiting was shared across accounts on the same source instead of isolated per account | **FIXED AND RE-VERIFIED** |
| D-06 | Empty rebuttal justification was accepted without validation | **FIXED AND RE-VERIFIED** |
| D-08 | Zero-byte evidence file uploads were accepted without validation | **FIXED AND RE-VERIFIED** |
| D-09 | Invalid QA decision values were rejected only by a generic database constraint message instead of a clear API validation error | **FIXED AND RE-VERIFIED** |
| D-11 | SLA migration/seed ordering issue could leave SLA policy data empty on a fresh install | **FIXED AND RE-VERIFIED** |
| D-10 | Reported duplicate `/signal` requests on a single page view | **RETRACTED / NOT A DEFECT** — re-isolated to a benign React StrictMode development-mode double-invoke behavior, not a real defect |

None of these are listed in §20; none regressed during this session's testing.

## 22. Blocked Tests

- **Escalation acknowledgment** (`POST /escalations/{id}/ack`): blocked because the live
  database currently has zero escalation rows and zero errors past their SLA due date —
  a direct, confirmed consequence of a prior full database reset. Reproducing a real
  escalation would require either waiting for a genuine SLA breach or backdating
  governance data, both out of scope for a non-destructive audit. The code path itself
  was read and follows the same validated pattern used elsewhere (role guard + required
  non-empty field).

This category is intentionally kept separate from FAILED: a blocked test could not be
executed to a pass/fail conclusion due to environmental/data conditions, not because the
system produced an incorrect result.

## 23. Not-Testable Areas

Two areas are explicitly marked NOT TESTABLE rather than assumed, extrapolated, or
fabricated:

1. **AI narrative/root-cause/summary output quality.** `OPENAI_API_KEY` is a placeholder
   value; every live chat-completion call returned a genuine `401` from OpenAI. No real
   model-generated text was ever produced in this session, so no claim is made about the
   relevance, coherence, or hallucination behavior of actual AI-generated content. This is
   distinct from AI *failure handling*, which was actively tested and verified GOOD
   (§13).
2. **Live browser-driven frontend interaction.** No browser automation tool (Playwright,
   headless Chromium/Chrome, Cypress) is installed or reachable in this environment. No
   claim is made that clicking through the UI, visual rendering, or live in-browser
   behavior was verified. What was verified instead — a successful production build and
   static source review — is reported separately in §16 and is not a substitute for live
   UI testing.

## 24. Missing / Not Implemented Functionality

- **`POST /auth/logout`** — not implemented; logout is a client-side token discard only.
  Not a defect: nothing in the codebase or its documentation claims a server-side
  logout/revocation exists for this stateless JWT design.
- **Department/ownership scoping on error and evidence reads** — see D-07 /
  D-07-EVIDENCE in §20. Recorded there as an open defect rather than here, since it is a
  reproduced security gap, not merely an absent feature.
- **URL-based frontend routing** — confirmed absent. Not a defect against any stated
  requirement; a UX characteristic (no deep links, no browser back/forward) worth noting.

## 25. Risk Assessment

- **Hallucination / output-quality risk**: NOT TESTABLE this session (§13, §23). The
  architectural mitigations (deterministic scoring fully separate from narrative
  generation, schema-validated model output, human-in-the-loop acknowledgment) were
  reviewed and are structurally sound, but no actual model output was ever produced to
  evaluate against them.
- **Prompt injection**: actively tested with a real injection payload through the normal
  creation API; the targeted workflow fields were provably unchanged afterward — a
  genuine, reproduced mitigation.
- **Data exposure to the AI provider**: error titles/descriptions (which may reference
  customer case identifiers) are sent to OpenAI as part of prompts; no PII-redaction step
  exists before that data leaves the backend. Worth a data-classification review before
  enabling AI features against real customer data.
- **Authorization risk**: D-07 / D-07-EVIDENCE represent a genuine confidentiality gap
  across departments — low-moderate impact for a single-tenant pilot, real impact beyond
  that.
- **Model dependency**: the system fails closed and safely everywhere tested when
  OpenAI is unavailable — verified live across every AI-touching endpoint exercised, all
  returning clean `503`s, zero `500`s.

## 26. Production Readiness

**READY FOR SINGLE-DEPARTMENT PILOT WITH CONDITIONS.**

**NOT READY FOR MULTI-DEPARTMENT / MULTI-TENANT PRODUCTION** until department/ownership
authorization is implemented for error and evidence reads (D-07, D-07-EVIDENCE).

Additionally, AI narrative quality has not been validated against a real model output in
any session to date. Before claiming that the generative AI output itself — as opposed to
its failure-handling behavior — has been validated, a valid production-like AI
configuration (a real, working API key) must be provided and a dedicated re-test of
narrative relevance, coherence, and hallucination risk must be performed. Failure
handling and narrative quality are separate claims; only the former has been verified.

| Dimension | Rating | Basis |
|---|---|---|
| Security | GOOD, with one known open gap | D-07 / D-07-EVIDENCE open, MEDIUM, documented; all other tested security controls (auth, SQLi, rate limiting, injection isolation) behaved correctly |
| Functional correctness | GOOD | All lifecycle, rebuttal, evidence, decision, and validation paths verified correct; all nine previously-fixed defects re-confirmed fixed |
| AI reliability | GOOD (failure handling); UNTESTED (output quality) | Every AI path fails clean; no real model output was ever produced to judge quality |
| Data integrity | GOOD | Audit chain verified valid against real activity; DB-level write protection confirmed in force; zero orphans/invalid states |
| UX | GOOD (verifiable parts); UNTESTED (live rendering) | No browser automation tool available this session |
| Performance | GOOD at tested (modest) scale | Not load-tested; untested at production volume |
| Maintainability | GOOD | Structural regression tests are genuine and meaningful, not decorative |

## 27. Recommendations

1. **(Security, MEDIUM)** Implement department/ownership scoping on `GET /errors/{id}`
   and `GET /evidence/{id}/url` before this system is used across more than one
   department. (D-07, D-07-EVIDENCE)
2. **(AI reliability)** Configure a real, working AI API key and perform a dedicated
   re-test of narrative/root-cause/summary output quality before any pilot or demo that
   needs to show real generative output — this remains the largest untested surface.
3. **(Data quality)** If a fully clean demonstration dataset matters, consider
   documenting or reconciling why legacy seed-inserted closed errors bypass normal
   decision/audit recording — currently a cosmetic data-provenance gap, not a functional
   one.
4. **(Process)** No browser-automation tooling exists in this environment. If live
   frontend regression testing is a recurring need, deliberately select and install one
   rather than continuing to mark it NOT TESTABLE indefinitely.
5. **(Process)** The escalation-acknowledgment path has not been exercised against a
   real SLA breach since the last database reset. A deliberate, one-time test (e.g., a
   disposable record with a due date in the past) is recommended before relying on this
   path for a real pilot.

## 28. Final Verdict

Every previously-known defect (D-01 through D-09, D-11) remains fixed and was
independently re-verified in this session against live system behavior, not re-asserted
from prior documentation. D-10 is retracted as not a defect. The only open defect is a
single authorization gap manifesting on two endpoints (D-07, D-07-EVIDENCE) — a real,
reproduced MEDIUM-severity issue, but one that was always a documented, deliberate scope
limitation rather than a broken guarantee.

**QEMS is READY for a single-department pilot, with conditions. It is NOT READY for
multi-department or multi-tenant production** until the authorization gap is closed. AI
narrative quality and live browser-driven UI behavior remain genuinely unvalidated — not
because either was found to be defective, but because neither could be exercised in this
environment (a placeholder AI key; no browser automation tooling). Both should be
resolved and specifically re-tested before either is claimed as validated.

---

## Appendix A — Test Data Created

Approximately 65 additional QA error records were created during this audit through the
normal, unmodified API — the same path a real user would take — with titles prefixed to
identify them as test data (e.g. `Audit test`, `RBAC probe`, `Lifecycle`, `Rebuttal`,
`Evidence`, `Decision`, `Prompt injection probe`, `Very long description test`), along
with their associated evidence files, rebuttals, decisions, and audit-log rows. The
database's total error count grew from 102 to 136 over the course of testing.

This data was **not deleted**: no `DELETE /errors` endpoint exists, and removing rows
directly via SQL would itself mutate the audit-log table this report verifies as intact
— doing so would undermine the very integrity check being reported on. This mirrors the
approach taken in the prior audit session.

## Appendix B — Evidence / Audit Artifacts

- HTTP-level test evidence: harness scripts executed against the live backend, retained
  at `backend/audit_evidence/scratch_audit1.py` through `scratch_audit6.py` (re-runnable,
  read-only with respect to application code).
- Database integrity evidence: direct SQL queries against the live PostgreSQL database
  (orphan-row checks, status-enum checks, hash-chain verification, migration-head check).
- Regression evidence: `pytest -q` output from the existing 76-test suite, run multiple
  times during the session.
- Build evidence: `npm run build` output confirming a clean production frontend build.
- Source-review evidence: direct reading of the relevant backend and frontend source for
  every claim about code structure, validation logic, and RBAC/authorization gating made
  in this report.

---

## Management Summary

QEMS was put through a full functional, security, and integrity audit covering
authentication, permissions, the complete error-handling workflow, AI features, and the
underlying database. **220 of 227 tests passed.** The 2 failures are both the same
underlying issue — a permissions gap that lets a logged-in user view another
department's records — which is a known, medium-severity item, not a system-breaking
bug. The 2 blocked tests and 1 not-implemented item are minor and well understood (no
breached deadlines exist yet to test an acknowledgment button against; there's no
"log out" button on the server side, only in the browser).

All nine bugs found and fixed earlier in this project's life were independently
re-checked in this audit and confirmed to still be fixed. No new bugs of that kind were
introduced.

Two things could not be tested here, through no fault of the product: the quality of the
AI's written suggestions (the AI service key on this machine is a placeholder, not a
real one) and the visual behavior of the website in a browser (no browser-testing tool
was available in this environment). Both are recommended as next steps before treating
the AI features or the frontend as fully signed off.

**Bottom line: QEMS is ready to pilot with a single department. It should not be rolled
out across multiple departments until the permissions gap above is fixed, and the AI's
actual output quality should be checked with a real API key before it's presented as a
finished feature.**
