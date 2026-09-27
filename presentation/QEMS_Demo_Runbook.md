# QEMS — Live Demo Runbook
### Following one error through its entire lifecycle (target: 3-5 minutes)

This runbook follows one QA error from creation to closure, using the real seeded accounts and the real API — nothing here is mocked. Rehearse it once end-to-end before presenting; the Quality Signal step (Step 9) depends on the database already holding at least 50 embedded historical errors, so seed history data ahead of time (see Pre-Demo Setup).

---

## Pre-Demo Setup (do this before the evaluator arrives)

1. **Start the dependencies**, in order: PostgreSQL (with pgvector), then MinIO (evidence storage) and Mailpit (email — inbox at `http://localhost:8025`), then the backend, then the frontend.
   ```bash
   # Terminal 1 — backend
   cd backend && source .venv/bin/activate
   uvicorn app.main:app --reload --port 8000

   # Terminal 2 — frontend
   cd frontend && npm run dev
   ```
2. **Confirm migrations are current:** `alembic current` should match `alembic heads`.
3. **Seed base data if not already seeded:** `python -m app.tasks.seed` (roles, SLA policies, departments, categories) then `python -m app.tasks.seed_users` (one account per role).
4. **Seed history so the Quality Signal engine has a corpus to compare against.** The engine requires at least 50 embedded errors before it will render a recurrence verdict at all (`MIN_CORPUS_FOR_SIGNAL = 50`) — run the project's `app/tasks/seed_history.py` (or equivalent historical-data seed) ahead of time so Step 9 shows a real READY signal rather than "not enough history yet." If you want to demonstrate the honest "insufficient history" path *deliberately*, skip this step and say so explicitly — it's a legitimate thing to show, framed as intentional.
5. **Open four things before you start talking:** the frontend at `http://localhost:3000`, the API docs at `http://localhost:8000/docs` (useful if an evaluator asks to see a raw endpoint), the Mailpit inbox at `http://localhost:8025` (to show the real notification email land), and a terminal ready for `GET /audit/verify` or a quick `curl` if someone asks to see the raw JSON.
6. **Know your four demo accounts** (password for all: `Password123!`):

   | Role | Email |
   |---|---|
   | Admin | `admin@qemscorp.dev` |
   | QA Reviewer | `qa@qemscorp.dev` |
   | Department Owner | `owner@qemscorp.dev` |
   | Viewer | `viewer@qemscorp.dev` |

---

## The 12-Step Demo Sequence

### Step 1 — Login
**Click:** Open `http://localhost:3000`, log in as `owner@qemscorp.dev` (Department Owner) — this account will raise the error, since operations/department staff are the typical first reporter of a defect.
**Say:** "This is a real login against the backend — wrong credentials actually fail here, unlike a mock."
**Evaluator should notice:** The demo-account buttons on the login screen match real seeded users, not placeholder emails.
**Proves:** Real JWT authentication, not a client-side stub.

### Step 2 — Dashboard
**Click:** Land on the Dashboard after login.
**Say:** "These KPI counts are computed from the live database on every load — not a fixed six-record mock. If we create an error in a minute, this number moves."
**Evaluator should notice:** Severity breakdown includes Critical (the mock version never had this bucket), and status buckets correctly group Resolved/Rejected/Closed all as "closed."
**Proves:** Dashboard reads real aggregated data from `GET /reports/summary`, including past the 100-record pagination threshold that was previously a bug (D-01, fixed and re-verified).

### Step 3 — Create QA Error
**Click:** Navigate to "Create Error." Fill in a real title (e.g., "Agent skipped identity verification on account update call"), pick a Department and Category from the live dropdowns, set Severity to High, fill in a description with enough detail to be realistic, submit.
**Say:** "Department and Category here are real lookups from the backend, not a hardcoded list — and Category is required, because the backend needs it to resolve the SLA policy for this error."
**Evaluator should notice:** No fields exist here for root cause or corrective action — call this out proactively: "Those are captured later, during review and decision, not invented at creation time, because we don't know them yet."
**Proves:** Server-side validation (try submitting with an empty title first, if time allows, to show the clean 422) and category-driven SLA policy resolution.

### Step 4 — Unique QA Error ID Generated
**Click:** Point at the generated QA error code on the confirmation/detail view (format `QEMS-YYYY-NNNNN`).
**Say:** "This code is generated server-side and is globally unique — it's the identity this error carries through its entire life, into every audit row, every evidence file, every report."
**Evaluator should notice:** The code format and that it incremented correctly from whatever the last one was.
**Proves:** Unique ID generation confirmed race-safe under rapid sequential creation in the audit (zero duplicate `qa_error_code` values observed).

### Step 5 — Open Error Details
**Click:** Navigate into the error's detail page.
**Say:** "This page is role- and state-aware — the buttons you see here are exactly what the backend's RBAC and state machine currently allow for this account and this error's status. Nothing here is a dead end that returns a 403 if clicked."
**Evaluator should notice:** As Department Owner on a freshly-created `Open` error, there's no "Start Review" button yet — that only appears for QA Reviewer/Admin.
**Proves:** Frontend mirrors real backend constraints rather than exposing controls that would just fail server-side.

### Step 6 — Attach Evidence
**Click:** Upload a real file (a screenshot or PDF) as evidence on the error.
**Say:** "This file is hashed with SHA-256 the moment it lands, and it's stored under a server-generated key — even if I renamed this file to something malicious, the server never uses the client-supplied name as a path."
**Evaluator should notice:** The evidence list shows the file with real metadata (size, type, uploader) — not a static placeholder PDF the mock version used to show.
**Proves:** Real S3-compatible object storage (MinIO), MIME/size validation (try a file over 15MB or an unsupported type if you want to show the 422), and an access-log row written the moment the file is later viewed.

### Step 7 — Rebuttal
**Click:** Log out, log back in as `owner@qemscorp.dev` if not already, and — once a QA Reviewer has moved the error to `In Review` (Step 8 can happen first if easier to sequence) — submit a rebuttal justification.
**Say:** "A rebuttal is the department's chance to respond before a decision is made — and it's role-gated to the department owner, not open to everyone."
**Evaluator should notice:** Submitting an empty justification is rejected client- and server-side; a 20,000-character justification would still be accepted (tested in the audit) if you want to demonstrate there's no arbitrary truncation.
**Proves:** Correct status transition to `Rebuttal Raised`, and that a second rebuttal while already in that state is blocked with a 409.

### Step 8 — QA Review
**Click:** Log in as `qa@qemscorp.dev` (QA Reviewer). Open the same error and click "Start Review" (transitions `Open → In Review`), then advance it toward a decision.
**Say:** "Only Admin and QA Reviewer can move this status forward — a Department Owner or Viewer account would get a clean 403 attempting this same click via the API, not just a hidden button."
**Evaluator should notice:** The status badge updates immediately and matches exactly what's allowed next per the state diagram.
**Proves:** Server-enforced RBAC + state machine acting together, not just one or the other.

### Step 9 — AI Quality Signal
**Click:** On the error detail page, open the Quality Signal panel (or click "Find Similar" / trigger a signal computation).
**Say:** "Watch what's above the divider versus below it. Everything above — similar-finding count, same-process count, the quarter-on-quarter trend, the risk band — is computed in SQL and a deterministic scoring function. Only the paragraph below the divider comes from a language model, and if that model is unavailable, this panel still renders the facts — it just says the narrative is unavailable instead of disappearing."
**Evaluator should notice:** If no real OpenAI key is configured, the panel will honestly show `DEGRADED` (facts only, no narrative) rather than fake prose — treat this as a feature to point out, not something to apologize for: "This is the fail-safe behavior working exactly as designed." If the corpus doesn't yet have 50 embedded errors, it will show "not enough history yet" — also worth calling out as evidence the gate is real.
**Proves:** The seven-step deterministic/inferred split (Slide 8), pgvector-backed retrieval, and honest non-fabrication when evidence is insufficient (`NO_COMPARABLE_FINDINGS` / `INSUFFICIENT_HISTORY` are real, distinct, tested states — not error conditions).

### Step 10 — QA Decision
**Click:** As QA Reviewer, record a decision (Resolved, Rejected, or Escalated) with required notes.
**Say:** "Recording 'Resolved' here doesn't just update a field — it auto-chains the error straight to Closed, with the closed timestamp populated automatically, in the same operation."
**Evaluator should notice:** The status jumps from `QA Decision Pending` directly to `Closed` on a Resolved/Rejected decision — Escalated is the one decision that deliberately does *not* auto-close, because escalating logically can't end the workflow.
**Proves:** Decision-to-closure chaining, decision role-gating (Department Owner/Viewer would get 403 here), and validation on the decision literal (invalid values return a clear 422 naming the three valid options).

### Step 11 — Audit Trail
**Click:** Open the audit trail for this error (Admin or QA Reviewer account).
**Say:** "Everything we just did — creation, evidence upload, the rebuttal, the review transition, the AI signal computation, the decision, the auto-close — is in this list, in order, and it cannot be edited or deleted. Not by policy — the database itself has revoked update and delete privileges on this table for the application's own role."
**Evaluator should notice:** Each row shows `actor_type` — USER for the human actions we just took, and `SYSTEM_AI` for the recurrence-signal computation in Step 9, which is what lets you tell at a glance which entries were a person versus the AI's own bookkeeping.
**Proves:** The tamper-evident hash chain (offer to run `GET /audit/verify` live if there's time and appetite) and complete provenance from a single error back through every action taken on it.

### Step 12 — Dashboard / Report Update
**Click:** Navigate back to the Dashboard, then to Reports; optionally export the CSV.
**Say:** "No refresh trick here — this error, now Closed, is reflected in these numbers because the dashboard queries live data on every load, the same way it did in Step 2."
**Evaluator should notice:** The error we just walked through appears correctly bucketed as closed, and if you filter the report by today's date or the department used, it shows up in the filtered results too.
**Proves:** `GET /reports/summary` accuracy (verified in the audit to match direct database counts exactly) and real CSV export (`Content-Disposition: attachment`, genuine `text/csv`, not a client-side-generated file).

---

## If something goes wrong mid-demo

- **AI panel shows DEGRADED or an error instead of a narrative:** this is expected without a real OpenAI key — say so, and pivot immediately to explaining *why* that's the correct, designed behavior (Slide 8/9), rather than treating it as a malfunction.
- **Quality Signal shows "not enough history yet":** the corpus doesn't have 50 embedded errors yet — either pre-seed history before the next demo, or use it as a live demonstration of the engine's honesty about its own limits.
- **An action returns a 403 you didn't expect:** you're very likely logged in as the wrong role for that action — check which account is active. This is usually a teaching moment, not a bug: pause and explain which role the click actually requires.
- **Evidence upload fails:** confirm MinIO is running (`http://localhost:9001` console) — if it's down, skip to Step 7 and mention evidence storage is backed by a real S3-compatible object store that isn't running in this exact moment, rather than pretending the click worked.
