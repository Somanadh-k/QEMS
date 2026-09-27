# QEMS — Evaluator Q&A / Technical Defense
### 30 likely questions, honest answers, and difficult follow-ups

Every answer here is grounded in `TEST_REPORT.md` (final, 2026-09-06) and the current source code. Where a claim is uncertain or unverified, the answer says so explicitly rather than rounding up.

---

### 1. Why did you build QEMS?

Quality error management at most organizations — including the one this project models — runs on email threads, spreadsheets, and manual follow-ups. That process works at small scale and quietly fails at real scale: ownership becomes ambiguous, evidence gets scattered, SLA breaches go unnoticed until someone escalates by phone, and recurring defects are invisible because nothing connects this month's incident to last quarter's. QEMS digitizes the entire quality-governance lifecycle end to end — capture, ownership, evidence, rebuttal, decision, audit, SLA, and now recurrence intelligence — as a single system of record.

**Difficult follow-up — "Isn't this just reinventing a generic ticketing system?"**
A generic ticketing tool (Jira, ServiceNow) solves ownership and status tracking, but has no purpose-built concept of evidentiary chain-of-custody (hashed files, access logs), regulatory-grade audit immutability (a hash-chained log with database-level write revocation), or a domain-specific state machine matching a quality-governance workflow (rebuttal, QA decision, SLA stage ownership). Those require a data model built for this domain, not a generic issue tracker configured to approximate it.

---

### 2. What problem does it solve, specifically?

Four measurable failure modes in manual QA error handling: (1) unclear ownership — who is responsible for this error right now; (2) evidentiary weakness — evidence isn't hashed, isn't access-logged, and can be silently swapped; (3) SLA blindness — nobody notices a breach until it's escalated manually; (4) invisible recurrence — the same defect recurring across time or process is undetectable without deliberately cross-referencing history, which nobody has time to do by hand.

---

### 3. Why isn't this just a CRUD application?

Three things a CRUD app doesn't have by default, all present and independently verified here: a server-enforced state machine that makes invalid lifecycle transitions structurally impossible (verified: `Open → QA Decision Pending` skip-ahead, repeat-state, and `Closed → Open` all correctly rejected with 409); a tamper-evident audit log (SHA-256 hash chain, with UPDATE/DELETE privileges revoked at the database grant level for the application's own role — confirmed in force, not just documented); and a deterministic recurrence-scoring engine over vector-embedded history, computed in SQL and a pure Python function, with AI touching only the narrative layer on top.

**Difficult follow-up — "A CRUD app could enforce a state machine in application code too."**
True — the distinguishing claim isn't "state machine exists," it's that it's enforced at the service layer independent of the UI, tested by directly calling the API (not clicking through the frontend), and combined with an audit trail that a normal CRUD app's soft-delete/update history doesn't structurally prevent tampering with the way a hash chain plus revoked database grants does.

---

### 4. Where exactly is AI used?

Six explicit endpoints (all backed by OpenAI, all confirmed live in the audit): root-cause suggestion (`POST /ai/root-cause`), similarity search (`GET /ai/similar/{id}`), severity prediction (`POST /ai/severity-prediction`), report summarization (`POST /ai/report-summary`), smart recommendation for likely owner and SLA risk (`POST /ai/smart-recommendation`), and natural-language search translated into filter parameters (`POST /ai/nl-search`). Beyond those six, there's a separate, more sophisticated Quality Signal engine (`GET /errors/{id}/signal`) that computes a recurrence-risk band from historical similarity, with AI touching only the final narrative-generation step.

---

### 5. Why use vector embeddings at all?

Because "does this look like a defect we've seen before" is fundamentally a semantic-similarity question, not a keyword-match question — two findings can describe the same root failure ("agent failed to verify identity" vs. "representative did not complete verification") in completely different wording. A keyword or category filter would miss that; an embedding of the description text, compared by cosine distance, catches it. Every error's title+description is embedded once at creation (or re-embedded if the source text changes) using OpenAI's `text-embedding-3-small` (1536 dimensions), stored directly on the `errors` row.

---

### 6. Why pgvector specifically, instead of a dedicated vector database?

Because similarity search here always needs to be joined against relational metadata that already lives in Postgres — department, category, process, status, severity, discovery date — in the same query. pgvector lets a single SQL statement filter by department (for authorization scoping), exclude the current error, cap the distance, and order by nearest neighbour, all inside Postgres's own query planner and transaction guarantees. A separate vector store would mean either duplicating that metadata externally or doing two round-trips and joining in application code, which is slower and loses transactional consistency.

---

### 7. How does similarity search actually work, mechanically?

`Error.description_embedding.cosine_distance(embedding)` — a native pgvector SQL operator — computed against every error's stored embedding, filtered to exclude the source error, optionally scoped by department and by embedding model (so an OpenAI-model vector is never compared against the offline fallback model's vector, which would be numerically meaningless), and capped at a distance ceiling (0.25 for the OpenAI embedding space, calibrated separately at 0.62 for the offline lexical fallback). Results are ordered by distance and returned with the raw distance value, not just a boolean "similar/not similar."

---

### 8. What happens if the AI service fails or is unreachable?

Every AI-touching endpoint fails closed and cleanly. In the actual audit, `OPENAI_API_KEY` was a placeholder, so every live chat-completion call received a genuine `401` from OpenAI — and the application correctly translated every one of those into a clean `503 {"error": {"code": "ai_service_unavailable", ...}}`, with zero `500`s observed anywhere in the AI surface. Error creation itself never fails because of AI: if embedding generation throws, it's logged and the error is created without an embedding rather than blocking the write. The Quality Signal engine goes further — it has an offline deterministic lexical embedder as a fallback, so the retrieval machinery (thresholds, gating, scoring) can be exercised even with zero API key configured.

---

### 9. Can AI modify a QA decision, status, or severity?

No — and this is enforced structurally, not just by convention. No AI-touched route accepts a write to `decision`, `status`, or `severity` on the `errors` table. This is asserted by a dedicated test (`test_ai_write_isolation.py`) that reads every AI route's schema and the model columns it's permitted to touch, and it was independently re-verified behaviorally: a live prompt-injection payload was submitted through the normal error-creation API, instructing the model to alter severity and status, and a follow-up read confirmed both fields were unchanged.

---

### 10. How do you prevent hallucinations in the AI output?

Architecturally, by never letting the model produce a number that matters. Every figure a reviewer sees — similar-finding count, process concentration, quarter-on-quarter trend, the 0-100 risk score, the LOW/MEDIUM/HIGH band — is computed in SQL and a pure Python scoring function (`recurrence.py`), before the model is ever called. The model receives those already-final numbers and produces only the explanatory sentence around them; it cannot alter the score or band, because it's never given a field to write one into.

**Honest limit:** the *quality* of that narrative sentence — whether it's coherent, relevant, and non-hallucinatory as prose — was not testable in the audit, because the test environment's OpenAI key was a placeholder and every real call failed upstream before generating text. What's verified is the failure-handling behavior (clean degradation), not narrative content quality. That's explicitly named as the largest untested surface in the test report's own recommendations.

---

### 11. How is prompt injection handled?

Tested directly, not just designed around. A QA error description was deliberately constructed with an injection payload instructing the model to change the error's severity and status. It was submitted through the ordinary, unmodified error-creation API — not a special test harness — and the root-cause endpoint still returned a clean `503` (the real failure mode in this environment), with a follow-up read confirming the targeted fields were unchanged. This is a genuine, reproduced mitigation, not merely a theoretical one, and it's structurally guaranteed by the write-isolation design in question 9 regardless of what the model outputs.

---

### 12. How are API keys / secrets protected?

The OpenAI API key is read server-side only, from environment configuration, and never reaches the frontend — the frontend has no direct OpenAI integration; every AI call is proxied through the backend. This was independently checked, not assumed: the audit searched both the frontend source and the compiled production JavaScript bundle for API-key-shaped strings and found no actual secret value — the one match was a user-facing status string that referenced the environment variable's *name*, not a key.

---

### 13. How does RBAC work?

A single FastAPI dependency, `require_role(*allowed_roles)`, checked server-side on every protected route — independent of anything the UI shows or hides. Four roles exist: Admin, QA Reviewer, Department Owner, Viewer. All thirty role-by-endpoint combinations tested in the audit passed, using real JWTs per role called directly against the API (not through the frontend). One honest, deliberate exception: `POST /errors` and evidence upload have no role guard at all — any authenticated user, including Viewer, can create an error or attach evidence. That's a product-scope decision (anyone can be the person who spots a defect), not an oversight, and it's documented as such rather than silently discovered.

---

### 14. How is department-level authorization enforced?

Via a shared helper, `visible_departments(user)`: Admin and QA Reviewer are treated as globally scoped (they have cross-department duties everywhere else — decisions, transitions, audit verification), and every other role is restricted to their own `department_id`. This is correctly applied today in the AI/Quality-Signal neighbour-retrieval path. **It is not yet applied** to two read endpoints — `GET /errors/{id}` and `GET /evidence/{id}/url` — which is the audit's one open finding (D-07 / D-07-EVIDENCE, both MEDIUM severity, same underlying gap). This is documented in the codebase's own docstring as deferred scope and confirmed reproduced in the audit, not a silent regression.

**Difficult follow-up — "Doesn't that undermine everything else you've claimed about authorization?"**
No — it narrows the claim precisely rather than invalidating it. RBAC (role-based — *what actions* a role may perform) is fully enforced and tested at 30/30. Department scoping (data-based — *which records* a user may see) is correctly implemented in one path and missing in two others. Those are different dimensions of authorization, and being explicit about which one has a gap is what makes the "single-department pilot ready, not multi-tenant ready" verdict credible rather than a blanket claim that would be false.

---

### 15. How is auditability achieved?

Every state-changing action writes a row to `audit_logs`, which is structured as a SHA-256 hash chain: each row's hash covers its own content plus the previous row's hash, computed via a transaction-scoped advisory lock so concurrent writers can't fork the chain. `GET /audit/verify` walks the chain and reports the first break, if any — independently confirmed valid against real, live-generated audit activity in the audit session, not just re-read from a prior claim. Tampering isn't merely against policy: UPDATE and DELETE privileges on `audit_logs` are revoked at the PostgreSQL grant level for the application's own database role, confirmed in force directly against the live database.

---

### 16. How does the state machine prevent invalid transitions?

`assert_valid_transition()` checks the target status against a fixed transition table (`Open → In Review`; `In Review → {Rebuttal Raised, QA Decision Pending}`; `Rebuttal Raised → QA Decision Pending`; `QA Decision Pending → {Resolved, Rejected}`; `Resolved/Rejected → Closed`; `Closed` is terminal) before any state change is committed. An unrecognized target string is validated against the enum first and raises a clean `422` naming every valid value — a fix for a previously-found defect (D-03) where an invalid string used to fall through to an unhandled `500`. All valid and invalid transitions were independently re-tested and passed, including skip-ahead, repeat-state, reopening a closed error, a rebuttal on a closed error, and a duplicate decision on a closed error — all correctly return `409`.

---

### 17. How does SLA escalation work?

SLA is stage-scoped, not a single deadline for the whole error: separate budgeted clocks for RESPOND, REBUT, DECIDE, and CLOSE, each with a recorded clock-owner role, so lateness is attributable to whichever side actually held the ball. Budgets come from an effective-dated `SLAMatrix` (category/department/severity-specific, with a specificity tie-break for overlapping rules), and elapsed time is computed with business-hours-aware arithmetic — a timezone-aware calendar that excludes weekends and holidays and correctly handles a deadline landing over a long weekend or a DST transition. A background APScheduler worker ticks SLA state and evaluates escalation rules; an `EscalationRule` fires at a trigger (AT_RISK, BREACH, LEVEL_TIMEOUT) with a cooldown to prevent re-firing storms, and a unique constraint (`error, level, rule`) guarantees a worker restart can't duplicate an escalation. Acknowledging an escalation requires a committed `next_action`, not a bare "seen" click.

**Honest limit:** escalation *acknowledgment* itself was blocked, not failed, in the audit — the live database had zero rows past their SLA due date at test time (a direct consequence of a full database reset), so there was nothing to acknowledge. The code path was read and follows the same validated pattern (role guard, required non-empty field) already confirmed working for SLA pause.

---

### 18. Why PostgreSQL?

It was the original report's database choice, and it's the one relational database with a mature vector-similarity extension (pgvector) that lets similarity search run as a first-class SQL operator joined against the same relational metadata (department, category, severity) everything else in the schema needs. It also gives QEMS transactional guarantees the audit log and the SLA event history both depend on, plus fine-grained grant revocation (used to make the audit log's immutability a database-level control, not just an application convention).

---

### 19. Why FastAPI?

Async I/O throughout, Pydantic-validated request/response schemas that double as the auto-generated interactive Swagger documentation (`/docs`) the frontend team worked against directly, and a clean dependency-injection model that made `require_role()` and `get_current_user()` reusable, testable guards rather than repeated boilerplate in every route.

---

### 20. Why React (with Vite)?

That was the frontend team's (G. Hasini's) existing build, originally developed against mock data. The integration work respected that existing structure — most page components needed field-name updates to match the real API's response shape, not a rewrite — rather than replacing a working frontend with a different framework for its own sake.

**Difficult follow-up — "The frontend has no client-side router — why not?"**
Confirmed absent by source review — no `react-router` or `BrowserRouter` in source or dependencies. It's reported honestly as a UX characteristic (no deep-linkable URLs, no browser back/forward) rather than a defect against any stated requirement, since nothing in the original scope required deep linking. It's listed as a known gap, not concealed.

---

### 21. How did you test the system?

A 227-test independent audit executed directly against a live backend, a live PostgreSQL database, and the project's own existing `pytest` suite — using direct HTTP calls, direct SQL queries, a production frontend build, and static source review, with no new test frameworks or dependencies installed for the audit. It covered authentication, RBAC (30 role × endpoint checks), the full lifecycle state machine, rebuttals, evidence, QA decisions, SLA/escalation, dashboard/report data accuracy, all AI/signal endpoints, AI and API security (including prompt injection and IDOR probing), database referential and hash-chain integrity, the existing 76-test regression suite, and baseline (non-load) performance sampling.

---

### 22. What were the biggest bugs discovered (historically)?

Nine defects were found and fixed earlier in the project's life and independently re-verified as still fixed in the most recent audit (by direct reproduction, not by re-reading the prior report): a dashboard KPI pagination cap that silently truncated counts past 100 records (D-01); the audit-log's database-level write protection not actually being in force (D-02); an invalid lifecycle status value crashing with an unhandled `500` instead of a clean `422` (D-03); an oversized error title causing the same kind of crash (D-04); login rate limiting being shared across accounts on the same IP instead of isolated per account (D-05); an empty rebuttal justification being accepted without validation (D-06); a zero-byte evidence upload being accepted without validation (D-08); invalid QA decision values surfacing only a generic database-constraint error instead of a clear API validation message (D-09); and an SLA migration/seed ordering issue that could leave SLA policy data empty on a fresh install (D-11). A tenth reported item (D-10, duplicate `/signal` requests) was re-investigated and retracted — it turned out to be a benign React development-mode double-invoke, not a real defect.

---

### 23. What remains incomplete or open right now?

Two open MEDIUM-severity findings, both the same underlying gap on two endpoints: `GET /errors/{id}` and `GET /evidence/{id}/url` don't yet enforce department/ownership scoping (D-07 / D-07-EVIDENCE). One not-implemented feature: `POST /auth/logout` doesn't exist server-side — logout is a client-side token discard, consistent with the stateless JWT design and not claimed otherwise anywhere in the codebase. Two genuinely untested areas: AI narrative output quality (placeholder API key in the test environment) and live browser-driven frontend interaction (no browser-automation tooling installed). And two process gaps worth naming honestly: escalation acknowledgment hasn't been exercised against a real SLA breach since the last database reset, and the system has not been load-tested at production data volumes or under concurrent load.

---

### 24. Is the system production-ready?

**Ready for a single-department pilot, with conditions. Not ready for multi-department or multi-tenant production** until the department/ownership authorization gap (D-07/D-07-EVIDENCE) is closed and AI narrative output quality is validated against a real, working model. That's the audit's explicit verdict, not a softened restatement of it — the report rates security "GOOD, with one known open gap," functional correctness "GOOD," AI reliability "GOOD (failure handling); UNTESTED (output quality)," data integrity "GOOD," and performance "GOOD at tested (modest) scale," each with the basis for that rating stated alongside it.

---

### 25. What would you build next?

In order of priority: first, close D-07/D-07-EVIDENCE by applying the existing `visible_departments()` pattern to the two under-scoped read endpoints — the smallest, highest-value fix available. Second, configure a real OpenAI key in a controlled environment and re-run a dedicated narrative-quality evaluation, since that's the largest genuinely untested surface. Third, deliberately select and install a browser-automation tool (Playwright is the natural fit given the existing FastAPI/async stack) so live UI regression stops being a permanent "not testable" line item. Beyond that: the seven-phase roadmap on the limitations slide — deeper recurrence forecasting, a root-cause knowledge graph across processes, proactive pre-breach alerts, and enterprise SSO/BI integrations.

---

### 26. What's the actual database schema size, and did it grow beyond the original design?

Yes, substantially. The original project report specified a 12-table DDL. The current schema has 24 tables across 7 Alembic migrations — the additional 12 tables are exactly the governance capability this system adds beyond the original academic scope: AI provenance (`ai_insights`, `ai_prompt_versions`, `ai_cost_ledger`), SLA/escalation governance (`sla_matrix`, `sla_events`, `escalations`, `escalation_rules`, `business_calendars`, `calendar_holidays`), typed transition history (`error_transitions`), business-process dimension (`processes`), and evidence-access logging (`evidence_access_log`). `alembic current` matches `alembic heads` exactly, with no pending or divergent migrations, confirmed against a real running Postgres 17 + pgvector 0.8.6 instance.

---

### 27. The project report specified Google Gemini for AI — why does the build use OpenAI?

A single, explicitly documented deliberate deviation, not an unplanned substitution. Every capability the report specifies for the AI component (Section 13) is implemented — root-cause analysis, similarity search, severity prediction, report summarization, smart recommendations, and NL search — just against OpenAI's Chat Completions and Embeddings APIs instead of Gemini's `generateContent` and embeddings endpoint. The swap is isolated to two files (`ai_service.py` and the `ai` router); the data model, workflow, RBAC, and every other module are provider-agnostic and unaffected.

---

### 28. Who built what on this team?

Per the project report's ownership split (Section 16): G. Hasini and A. Prashanth focused on frontend UI/UX; K. Somanadh (this presenter) owned architecture, database design, backend CRUD, AI integration, and final system integration. Since the frontend and this integration work were the only pieces in active progress when backend development began, the backend CRUD build (auth, error workflows, evidence, rebuttals, decisions) was completed as part of this scope as well, alongside the architecture, database, and AI work originally assigned.

---

### 29. How confident are you in the 227/220 test numbers — could they be inflated or cherry-picked?

The report is explicit about its own limits, which is itself evidence against cherry-picking: it distinguishes FAILED from BLOCKED from NOT TESTABLE rather than folding awkward results into a passing category, it names the two open defects by ID with severity and reproduction steps rather than summarizing them away, and it retracts a previously-reported defect (D-10) when re-investigation showed it wasn't real, rather than leaving an inflated defect count standing. The reconciliation line — 220+2+2+1+2 = 227 — is stated and checked in the report itself, and every category subtotal in the statistics table (Section 4) sums to the same total.

---

### 30. What's the single most impressive technical decision in this system, and why?

The seven-step split in the Quality Signal engine — deterministic embed/gate/retrieve/count/score steps completely separated from the one inferred narration step, with the model given no field in which to express a decision. Most "AI-powered" systems blur that line, so a model outage degrades the whole feature and a governance-sensitive number (a risk score, in this case) ends up implicitly trusted to a language model's arithmetic. Here, an OpenAI outage costs exactly the prose and none of the arithmetic — verified in the audit by the fact that every AI-touching endpoint returned a clean `503` while the deterministic Quality Signal metrics kept computing and rendering correctly throughout.

---

## Further difficult follow-ups (rapid-fire)

**"What if two reviewers try to transition the same error at the same time?"**
Not explicitly load-tested for that race in the audit (performance testing was baseline, non-concurrent sampling only), but the state machine's guard runs inside the same database transaction as the write, so a losing concurrent request would encounter the already-updated state and correctly receive a 409 rather than corrupt the record. This is an architecture guarantee, not something the audit specifically stress-tested — an honest gap to name if pressed further.

**"Could someone forge a JWT?"**
Only if they had the `JWT_SECRET` — tokens are HS256-signed and verified server-side on every request via `decode_token()`; a malformed or garbage bearer token, and a missing token on a protected route, both correctly return 401, and a refresh token presented as an access token is correctly rejected.

**"What happens to evidence files if MinIO/S3 is down?**"
Not explicitly covered as a named test case in the audit; the upload path would fail at the storage-service call, and by the same fail-closed pattern used for AI, the expectation is a clean error rather than a crash — but this specific failure mode isn't independently confirmed in the test report, so it should be stated as an architectural expectation, not a verified result, if asked precisely.

**"Why does Viewer get almost the same create/upload permissions as everyone else?"**
Deliberate product-scope decision, documented as such rather than found as a gap: anyone in the workflow can be the person who first spots a defect, so error creation and evidence upload are intentionally open to any authenticated user. Everything with governance weight — transitions, rebuttals, decisions, SLA control, audit access — is tightly role-gated.
