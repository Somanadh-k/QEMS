-- QEMS full schema, generated from the project's own Alembic migrations
-- (alembic/versions/*.py) via `alembic upgrade head --sql`, for pasting directly into
-- Supabase's SQL Editor without giving anyone your DB connection string.
--
-- This is DERIVED, not hand-maintained: if the migrations change, regenerate it rather
-- than editing this file directly (see backend/README.md's "Database & Storage
-- (Supabase)" section for the exact two-command regeneration steps -- one migration's
-- upgrade() runs a live conditional query that offline mode can't execute, so it's
-- spliced in by hand from that migration's own literal values instead of skipped).
--
-- Verified byte-for-byte against a real `alembic upgrade head` run: identical table
-- set, identical final alembic_version (f1a2b3c4d5e6), identical seeded row counts.
--
-- After running this, the schema exists but is empty of data -- still run
-- `python -m app.tasks.seed` and `python -m app.tasks.seed_users` against your Supabase
-- DATABASE_URL to get roles/departments/categories/demo users (they hash passwords in
-- Python via bcrypt, which isn't something to hand-roll in SQL).

BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> f0a5d490f0d4

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE departments (
    department_id SERIAL NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    PRIMARY KEY (department_id), 
    UNIQUE (name)
);

CREATE TABLE roles (
    role_id SERIAL NOT NULL, 
    role_name VARCHAR(50) NOT NULL, 
    PRIMARY KEY (role_id), 
    UNIQUE (role_name)
);

CREATE TABLE sla_policies (
    sla_policy_id SERIAL NOT NULL, 
    severity VARCHAR(20) NOT NULL, 
    sla_hours INTEGER NOT NULL, 
    PRIMARY KEY (sla_policy_id), 
    CONSTRAINT ck_sla_hours_positive CHECK (sla_hours > 0)
);

CREATE TABLE categories (
    category_id SERIAL NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    sla_policy_id INTEGER, 
    PRIMARY KEY (category_id), 
    FOREIGN KEY(sla_policy_id) REFERENCES sla_policies (sla_policy_id), 
    UNIQUE (name)
);

CREATE TABLE users (
    user_id SERIAL NOT NULL, 
    full_name VARCHAR(120) NOT NULL, 
    email VARCHAR(150) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    department_id INTEGER, 
    is_active BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (user_id), 
    FOREIGN KEY(department_id) REFERENCES departments (department_id), 
    UNIQUE (email)
);

CREATE TABLE errors (
    error_id SERIAL NOT NULL, 
    qa_error_code VARCHAR(20) NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    description TEXT NOT NULL, 
    category_id INTEGER NOT NULL, 
    severity VARCHAR(20) NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    department_id INTEGER NOT NULL, 
    raised_by INTEGER NOT NULL, 
    assigned_to INTEGER, 
    date_discovered DATE NOT NULL, 
    due_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    closed_at TIMESTAMP WITH TIME ZONE, 
    description_embedding VECTOR(1536), 
    PRIMARY KEY (error_id), 
    CONSTRAINT ck_errors_severity CHECK (severity IN ('Low','Medium','High','Critical')), 
    FOREIGN KEY(assigned_to) REFERENCES users (user_id), 
    FOREIGN KEY(category_id) REFERENCES categories (category_id), 
    FOREIGN KEY(department_id) REFERENCES departments (department_id), 
    FOREIGN KEY(raised_by) REFERENCES users (user_id), 
    UNIQUE (qa_error_code)
);

CREATE INDEX idx_errors_department ON errors (department_id);

CREATE INDEX idx_errors_due_at ON errors (due_at);

CREATE INDEX idx_errors_status ON errors (status);

CREATE TABLE user_roles (
    user_id INTEGER NOT NULL, 
    role_id INTEGER NOT NULL, 
    PRIMARY KEY (user_id, role_id), 
    FOREIGN KEY(role_id) REFERENCES roles (role_id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (user_id) ON DELETE CASCADE
);

CREATE TABLE audit_logs (
    audit_id BIGSERIAL NOT NULL, 
    error_id INTEGER, 
    actor_id INTEGER NOT NULL, 
    action VARCHAR(50) NOT NULL, 
    before_value JSONB, 
    after_value JSONB, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (audit_id), 
    FOREIGN KEY(actor_id) REFERENCES users (user_id), 
    FOREIGN KEY(error_id) REFERENCES errors (error_id)
);

CREATE INDEX idx_audit_error ON audit_logs (error_id);

CREATE TABLE evidence (
    evidence_id SERIAL NOT NULL, 
    error_id INTEGER NOT NULL, 
    file_name VARCHAR(255) NOT NULL, 
    file_url VARCHAR NOT NULL, 
    file_type VARCHAR(50) NOT NULL, 
    file_size_kb INTEGER NOT NULL, 
    uploaded_by INTEGER NOT NULL, 
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (evidence_id), 
    FOREIGN KEY(error_id) REFERENCES errors (error_id) ON DELETE CASCADE, 
    FOREIGN KEY(uploaded_by) REFERENCES users (user_id)
);

CREATE INDEX idx_evidence_error ON evidence (error_id);

CREATE TABLE notifications (
    notification_id SERIAL NOT NULL, 
    error_id INTEGER, 
    recipient_id INTEGER NOT NULL, 
    channel VARCHAR(20) NOT NULL, 
    subject VARCHAR(200) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    sent_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (notification_id), 
    FOREIGN KEY(error_id) REFERENCES errors (error_id), 
    FOREIGN KEY(recipient_id) REFERENCES users (user_id)
);

CREATE TABLE qa_decisions (
    decision_id SERIAL NOT NULL, 
    error_id INTEGER NOT NULL, 
    decided_by INTEGER NOT NULL, 
    decision VARCHAR(20) NOT NULL, 
    notes TEXT NOT NULL, 
    decided_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (decision_id), 
    CONSTRAINT ck_qa_decision_value CHECK (decision IN ('Resolved','Rejected','Escalated')), 
    FOREIGN KEY(decided_by) REFERENCES users (user_id), 
    FOREIGN KEY(error_id) REFERENCES errors (error_id) ON DELETE CASCADE
);

CREATE TABLE rebuttals (
    rebuttal_id SERIAL NOT NULL, 
    error_id INTEGER NOT NULL, 
    raised_by INTEGER NOT NULL, 
    justification TEXT NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (rebuttal_id), 
    FOREIGN KEY(error_id) REFERENCES errors (error_id) ON DELETE CASCADE, 
    FOREIGN KEY(raised_by) REFERENCES users (user_id)
);

INSERT INTO alembic_version (version_num) VALUES ('f0a5d490f0d4') RETURNING alembic_version.version_num;

-- Running upgrade f0a5d490f0d4 -> d650696750e8

ALTER TABLE users ADD COLUMN phone VARCHAR(30);

ALTER TABLE users ADD COLUMN address VARCHAR(255);

ALTER TABLE users ADD COLUMN employee_id VARCHAR(30);

UPDATE alembic_version SET version_num='d650696750e8' WHERE alembic_version.version_num = 'f0a5d490f0d4';

-- Running upgrade d650696750e8 -> a1b2c3d4e5f6

CREATE TABLE ai_prompt_versions (
    version VARCHAR(60) NOT NULL, 
    insight_type VARCHAR(30) NOT NULL, 
    prompt_text TEXT NOT NULL, 
    output_schema JSONB, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    retired_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (version)
);

CREATE TABLE ai_insights (
    insight_id BIGSERIAL NOT NULL, 
    error_id INTEGER, 
    insight_type VARCHAR(30) NOT NULL, 
    model_name VARCHAR(80) NOT NULL, 
    prompt_version VARCHAR(60), 
    input_fingerprint VARCHAR(64) NOT NULL, 
    retrieved_error_ids INTEGER[], 
    metrics JSONB, 
    score_breakdown JSONB, 
    risk_score NUMERIC(5, 2), 
    risk_band VARCHAR(10), 
    ai_output JSONB, 
    prompt_tokens INTEGER, 
    completion_tokens INTEGER, 
    cost_usd NUMERIC(10, 5), 
    latency_ms INTEGER, 
    status VARCHAR(20) DEFAULT 'FRESH' NOT NULL, 
    error_message TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    reviewed_by INTEGER, 
    reviewed_at TIMESTAMP WITH TIME ZONE, 
    reviewer_action VARCHAR(30), 
    reviewer_notes TEXT, 
    PRIMARY KEY (insight_id), 
    CONSTRAINT ck_insight_risk_band CHECK (risk_band IS NULL OR risk_band IN ('LOW','MEDIUM','HIGH')), 
    CONSTRAINT ck_insight_reviewer_action CHECK (reviewer_action IS NULL OR reviewer_action IN ('ACCEPTED','PARTIALLY_ACCEPTED','REJECTED','NO_ACTION')), 
    FOREIGN KEY(error_id) REFERENCES errors (error_id) ON DELETE CASCADE, 
    FOREIGN KEY(prompt_version) REFERENCES ai_prompt_versions (version), 
    FOREIGN KEY(reviewed_by) REFERENCES users (user_id)
);

CREATE INDEX idx_insight_error_type ON ai_insights (error_id, insight_type);

CREATE INDEX idx_insight_fingerprint ON ai_insights (input_fingerprint);

CREATE UNIQUE INDEX ux_insight_fresh ON ai_insights (error_id, insight_type) WHERE status = 'FRESH';

CREATE TABLE ai_cost_ledger (
    ledger_id BIGSERIAL NOT NULL, 
    feature VARCHAR(40) NOT NULL, 
    model_name VARCHAR(80) NOT NULL, 
    call_type VARCHAR(20) NOT NULL, 
    prompt_tokens INTEGER DEFAULT '0' NOT NULL, 
    completion_tokens INTEGER DEFAULT '0' NOT NULL, 
    cost_usd NUMERIC(10, 5) DEFAULT '0' NOT NULL, 
    cache_hit BOOLEAN DEFAULT false NOT NULL, 
    occurred_on TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (ledger_id)
);

CREATE INDEX idx_cost_day_feature ON ai_cost_ledger (occurred_on, feature);

ALTER TABLE audit_logs ADD COLUMN actor_type VARCHAR(20) DEFAULT 'USER' NOT NULL;

ALTER TABLE audit_logs ADD COLUMN reason VARCHAR(500);

ALTER TABLE audit_logs ADD COLUMN request_id VARCHAR(36);

ALTER TABLE audit_logs ADD COLUMN insight_id BIGINT;

ALTER TABLE audit_logs ADD COLUMN prev_hash VARCHAR(64);

ALTER TABLE audit_logs ADD COLUMN row_hash VARCHAR(64);

ALTER TABLE audit_logs ADD CONSTRAINT fk_audit_insight FOREIGN KEY(insight_id) REFERENCES ai_insights (insight_id);

ALTER TABLE audit_logs ALTER COLUMN actor_id DROP NOT NULL;

ALTER TABLE audit_logs ADD CONSTRAINT ck_audit_actor_type CHECK (actor_type IN ('USER','SYSTEM','SYSTEM_AI'));

ALTER TABLE audit_logs ADD CONSTRAINT ck_audit_user_has_actor CHECK ((actor_type = 'USER' AND actor_id IS NOT NULL) OR actor_type <> 'USER');

CREATE INDEX idx_audit_created ON audit_logs (created_at);

CREATE INDEX IF NOT EXISTS idx_errors_embedding ON errors USING hnsw (description_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

UPDATE alembic_version SET version_num='a1b2c3d4e5f6' WHERE alembic_version.version_num = 'd650696750e8';

-- Running upgrade a1b2c3d4e5f6 -> b2c3d4e5f6a7

CREATE TABLE processes (
    process_id SERIAL NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    department_id INTEGER, 
    owner_user_id INTEGER, 
    active BOOLEAN DEFAULT true NOT NULL, 
    PRIMARY KEY (process_id), 
    UNIQUE (name), 
    FOREIGN KEY(department_id) REFERENCES departments (department_id), 
    FOREIGN KEY(owner_user_id) REFERENCES users (user_id)
);

CREATE TABLE business_calendars (
    calendar_id SERIAL NOT NULL, 
    name VARCHAR(80) NOT NULL, 
    timezone VARCHAR(60) DEFAULT 'UTC' NOT NULL, 
    workday_start TIME WITHOUT TIME ZONE NOT NULL, 
    workday_end TIME WITHOUT TIME ZONE NOT NULL, 
    workdays INTEGER[] NOT NULL, 
    PRIMARY KEY (calendar_id), 
    UNIQUE (name)
);

CREATE TABLE calendar_holidays (
    calendar_id INTEGER NOT NULL, 
    holiday_date DATE NOT NULL, 
    name VARCHAR(120), 
    PRIMARY KEY (calendar_id, holiday_date), 
    FOREIGN KEY(calendar_id) REFERENCES business_calendars (calendar_id) ON DELETE CASCADE
);

CREATE TABLE sla_matrix (
    sla_id SERIAL NOT NULL, 
    category_id INTEGER, 
    department_id INTEGER, 
    severity VARCHAR(20), 
    stage VARCHAR(20) NOT NULL, 
    budget_hours NUMERIC(6, 2) NOT NULL, 
    business_hours_only BOOLEAN DEFAULT true NOT NULL, 
    calendar_id INTEGER, 
    effective_from TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    effective_to TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (sla_id), 
    CONSTRAINT ck_sla_matrix_budget_positive CHECK (budget_hours > 0), 
    CONSTRAINT ck_sla_matrix_stage CHECK (stage IN ('RESPOND','REBUT','DECIDE','CLOSE')), 
    FOREIGN KEY(category_id) REFERENCES categories (category_id), 
    FOREIGN KEY(department_id) REFERENCES departments (department_id), 
    FOREIGN KEY(calendar_id) REFERENCES business_calendars (calendar_id)
);

CREATE INDEX idx_sla_matrix_lookup ON sla_matrix (severity, stage, effective_from);

CREATE TABLE sla_events (
    event_id SERIAL NOT NULL, 
    error_id INTEGER NOT NULL, 
    stage VARCHAR(20) NOT NULL, 
    event_type VARCHAR(20) NOT NULL, 
    occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    owner_role VARCHAR(50), 
    due_at TIMESTAMP WITH TIME ZONE, 
    reason TEXT, 
    actor_id INTEGER, 
    sla_id INTEGER, 
    PRIMARY KEY (event_id), 
    FOREIGN KEY(error_id) REFERENCES errors (error_id) ON DELETE CASCADE, 
    FOREIGN KEY(actor_id) REFERENCES users (user_id), 
    FOREIGN KEY(sla_id) REFERENCES sla_matrix (sla_id)
);

CREATE INDEX idx_sla_events_error ON sla_events (error_id, occurred_at);

CREATE TABLE escalation_rules (
    rule_id SERIAL NOT NULL, 
    trigger VARCHAR(20) NOT NULL, 
    level SMALLINT NOT NULL, 
    severity_min VARCHAR(20), 
    target_role VARCHAR(50), 
    target_user_id INTEGER, 
    channel VARCHAR(20) DEFAULT 'email' NOT NULL, 
    cooldown_minutes INTEGER DEFAULT '720' NOT NULL, 
    active BOOLEAN DEFAULT true NOT NULL, 
    PRIMARY KEY (rule_id), 
    CONSTRAINT ck_escalation_trigger CHECK (trigger IN ('AT_RISK','BREACH','LEVEL_TIMEOUT')), 
    FOREIGN KEY(target_user_id) REFERENCES users (user_id)
);

CREATE TABLE escalations (
    escalation_id SERIAL NOT NULL, 
    error_id INTEGER NOT NULL, 
    level SMALLINT NOT NULL, 
    rule_id INTEGER NOT NULL, 
    escalated_to INTEGER NOT NULL, 
    trigger VARCHAR(20) NOT NULL, 
    triggered_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    acknowledged_at TIMESTAMP WITH TIME ZONE, 
    acknowledged_by INTEGER, 
    next_action TEXT, 
    eta TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (escalation_id), 
    CONSTRAINT ux_escalation_once UNIQUE (error_id, level, rule_id), 
    FOREIGN KEY(error_id) REFERENCES errors (error_id) ON DELETE CASCADE, 
    FOREIGN KEY(rule_id) REFERENCES escalation_rules (rule_id), 
    FOREIGN KEY(escalated_to) REFERENCES users (user_id), 
    FOREIGN KEY(acknowledged_by) REFERENCES users (user_id)
);

CREATE INDEX idx_escalation_open ON escalations (acknowledged_at);

CREATE TABLE error_transitions (
    transition_id BIGSERIAL NOT NULL, 
    error_id INTEGER NOT NULL, 
    from_status VARCHAR(30), 
    to_status VARCHAR(30) NOT NULL, 
    actor_id INTEGER, 
    actor_type VARCHAR(20) DEFAULT 'USER' NOT NULL, 
    reason TEXT, 
    rule_applied VARCHAR(60), 
    round_no INTEGER DEFAULT '1' NOT NULL, 
    occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (transition_id), 
    FOREIGN KEY(error_id) REFERENCES errors (error_id) ON DELETE CASCADE, 
    FOREIGN KEY(actor_id) REFERENCES users (user_id)
);

CREATE INDEX idx_transition_error ON error_transitions (error_id, occurred_at);

ALTER TABLE errors ADD COLUMN embedding_model VARCHAR(60);

ALTER TABLE errors ADD COLUMN embedded_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE errors ADD COLUMN embedding_source_hash VARCHAR(64);

ALTER TABLE errors ADD COLUMN process_id INTEGER;

ALTER TABLE errors ADD FOREIGN KEY(process_id) REFERENCES processes (process_id);

ALTER TABLE errors ADD COLUMN sla_state VARCHAR(20) DEFAULT 'ON_TRACK' NOT NULL;

ALTER TABLE errors ADD COLUMN sla_stage VARCHAR(20);

ALTER TABLE errors ADD COLUMN sla_due_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE errors ADD COLUMN sla_clock_owner_role VARCHAR(50);

ALTER TABLE errors ADD COLUMN sla_paused_ms BIGINT DEFAULT '0' NOT NULL;

ALTER TABLE errors ADD COLUMN escalation_level SMALLINT DEFAULT '0' NOT NULL;

ALTER TABLE errors ADD COLUMN risk_score NUMERIC(5, 2);

ALTER TABLE errors ADD COLUMN risk_score_breakdown JSONB;

ALTER TABLE errors ADD COLUMN risk_computed_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE errors ADD COLUMN round_no SMALLINT DEFAULT '1' NOT NULL;

CREATE INDEX idx_errors_governance ON errors (sla_state, risk_score);

CREATE INDEX idx_errors_recurrence ON errors (category_id, process_id, created_at);

INSERT INTO business_calendars (name, timezone, workday_start, workday_end, workdays) VALUES ('Default 9-5 Mon-Fri', 'UTC', '09:00', '17:00', '{1,2,3,4,5}');

INSERT INTO sla_matrix (severity, stage, budget_hours, business_hours_only,
                                calendar_id, effective_from)
        SELECT p.severity, s.stage,
               ROUND(p.sla_hours * s.share, 2), true,
               (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'),
               -- Backdated deliberately. These budgets were already in force via
               -- sla_policies; stamping them as effective from the migration date would
               -- leave every pre-existing error with no governing policy, which the
               -- evaluator would then read as permanently ON_TRACK.
               TIMESTAMPTZ '2000-01-01 00:00:00+00'
        FROM sla_policies p
        CROSS JOIN (VALUES ('RESPOND', 0.3), ('REBUT', 0.3), ('DECIDE', 0.3), ('CLOSE', 0.1))
                   AS s(stage, share);

INSERT INTO escalation_rules (trigger, level, severity_min, target_role, channel, cooldown_minutes)
        VALUES ('BREACH', 1, NULL, 'QA Reviewer', 'email', 720),
               ('LEVEL_TIMEOUT', 2, 'High', 'Admin', 'email', 1440);

UPDATE errors SET sla_due_at = due_at, sla_stage = 'RESPOND', sla_state = 'ON_TRACK';

UPDATE alembic_version SET version_num='b2c3d4e5f6a7' WHERE alembic_version.version_num = 'a1b2c3d4e5f6';

-- Running upgrade b2c3d4e5f6a7 -> c3d4e5f6a7b8

ALTER TABLE evidence ADD COLUMN storage_key VARCHAR(300);

ALTER TABLE evidence ADD COLUMN sha256 VARCHAR(64);

ALTER TABLE evidence ADD COLUMN evidence_class VARCHAR(40);

ALTER TABLE evidence ADD COLUMN retention_until TIMESTAMP WITH TIME ZONE;

UPDATE evidence SET storage_key = COALESCE(NULLIF(substring(file_url from 'evidence/.*'), ''), file_url) WHERE storage_key IS NULL;

CREATE TABLE evidence_access_log (
    access_id BIGSERIAL NOT NULL, 
    evidence_id INTEGER NOT NULL, 
    accessed_by INTEGER NOT NULL, 
    action VARCHAR(40) NOT NULL, 
    accessed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (access_id), 
    FOREIGN KEY(evidence_id) REFERENCES evidence (evidence_id) ON DELETE CASCADE, 
    FOREIGN KEY(accessed_by) REFERENCES users (user_id)
);

CREATE INDEX idx_evidence_access ON evidence_access_log (evidence_id, accessed_at);

UPDATE alembic_version SET version_num='c3d4e5f6a7b8' WHERE alembic_version.version_num = 'b2c3d4e5f6a7';

-- Running upgrade c3d4e5f6a7b8 -> d4e5f6a7b8c9

REVOKE UPDATE, DELETE ON audit_logs FROM CURRENT_USER;

UPDATE alembic_version SET version_num='d4e5f6a7b8c9' WHERE alembic_version.version_num = 'c3d4e5f6a7b8';

-- Running upgrade d4e5f6a7b8c9 -> e5f6a7b8c9d0

INSERT INTO sla_matrix (severity, stage, budget_hours, business_hours_only, calendar_id, effective_from) SELECT * FROM (VALUES ('Critical', 'RESPOND', 1.2, true, (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'), TIMESTAMPTZ '2000-01-01 00:00:00+00'), ('Critical', 'REBUT', 1.2, true, (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'), TIMESTAMPTZ '2000-01-01 00:00:00+00'), ('Critical', 'DECIDE', 1.2, true, (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'), TIMESTAMPTZ '2000-01-01 00:00:00+00'), ('Critical', 'CLOSE', 0.4, true, (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'), TIMESTAMPTZ '2000-01-01 00:00:00+00'), ('High', 'RESPOND', 7.2, true, (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'), TIMESTAMPTZ '2000-01-01 00:00:00+00'), ('High', 'REBUT', 7.2, true, (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'), TIMESTAMPTZ '2000-01-01 00:00:00+00'), ('High', 'DECIDE', 7.2, true, (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'), TIMESTAMPTZ '2000-01-01 00:00:00+00'), ('High', 'CLOSE', 2.4, true, (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'), TIMESTAMPTZ '2000-01-01 00:00:00+00'), ('Medium', 'RESPOND', 21.6, true, (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'), TIMESTAMPTZ '2000-01-01 00:00:00+00'), ('Medium', 'REBUT', 21.6, true, (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'), TIMESTAMPTZ '2000-01-01 00:00:00+00'), ('Medium', 'DECIDE', 21.6, true, (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'), TIMESTAMPTZ '2000-01-01 00:00:00+00'), ('Medium', 'CLOSE', 7.2, true, (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'), TIMESTAMPTZ '2000-01-01 00:00:00+00'), ('Low', 'RESPOND', 50.4, true, (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'), TIMESTAMPTZ '2000-01-01 00:00:00+00'), ('Low', 'REBUT', 50.4, true, (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'), TIMESTAMPTZ '2000-01-01 00:00:00+00'), ('Low', 'DECIDE', 50.4, true, (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'), TIMESTAMPTZ '2000-01-01 00:00:00+00'), ('Low', 'CLOSE', 16.8, true, (SELECT calendar_id FROM business_calendars WHERE name = 'Default 9-5 Mon-Fri'), TIMESTAMPTZ '2000-01-01 00:00:00+00')) AS v (severity, stage, budget_hours, business_hours_only, calendar_id, effective_from) WHERE NOT EXISTS (SELECT 1 FROM sla_matrix);

UPDATE alembic_version SET version_num='e5f6a7b8c9d0' WHERE alembic_version.version_num = 'd4e5f6a7b8c9';

-- Running upgrade e5f6a7b8c9d0 -> f1a2b3c4d5e6

ALTER TABLE escalations DROP CONSTRAINT ux_escalation_once;

ALTER TABLE escalations ADD CONSTRAINT ux_escalation_once UNIQUE (error_id, level, rule_id, escalated_to);

UPDATE alembic_version SET version_num='f1a2b3c4d5e6' WHERE alembic_version.version_num = 'e5f6a7b8c9d0';

COMMIT;
