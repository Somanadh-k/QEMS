BEGIN;

-- Running upgrade a7b8c9d0e1f2 -> e1f2a3b4c5d6

CREATE TABLE messages (
    message_id SERIAL NOT NULL, 
    error_id INTEGER NOT NULL, 
    sender_id INTEGER NOT NULL, 
    parent_message_id INTEGER, 
    message TEXT NOT NULL, 
    message_type VARCHAR(30) DEFAULT 'TEXT' NOT NULL, 
    is_read BOOLEAN DEFAULT false NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (message_id), 
    CONSTRAINT ck_messages_type CHECK (message_type IN ('TEXT','EVIDENCE_REQUEST','EVIDENCE_UPLOAD','STATUS_NOTE')), 
    FOREIGN KEY(error_id) REFERENCES errors (error_id) ON DELETE CASCADE, 
    FOREIGN KEY(sender_id) REFERENCES users (user_id), 
    FOREIGN KEY(parent_message_id) REFERENCES messages (message_id) ON DELETE SET NULL
);

CREATE INDEX idx_messages_error ON messages (error_id, created_at);

CREATE INDEX idx_messages_parent ON messages (parent_message_id);

CREATE TABLE message_attachments (
    attachment_id SERIAL NOT NULL, 
    message_id INTEGER NOT NULL, 
    file_name VARCHAR(255) NOT NULL, 
    file_type VARCHAR(50) NOT NULL, 
    file_size_kb INTEGER NOT NULL, 
    storage_key VARCHAR(300) NOT NULL, 
    uploaded_by INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (attachment_id), 
    FOREIGN KEY(message_id) REFERENCES messages (message_id) ON DELETE CASCADE, 
    FOREIGN KEY(uploaded_by) REFERENCES users (user_id)
);

CREATE INDEX idx_message_attachments_message ON message_attachments (message_id);

ALTER TABLE notifications ADD COLUMN event_type VARCHAR(40);

ALTER TABLE notifications ADD COLUMN content TEXT;

ALTER TABLE notifications ADD COLUMN retry_count SMALLINT DEFAULT '0' NOT NULL;

ALTER TABLE notifications ADD COLUMN next_retry_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE notifications ADD COLUMN read_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE notifications ADD COLUMN created_at TIMESTAMP WITH TIME ZONE;

UPDATE notifications SET created_at = COALESCE(sent_at, now()) WHERE created_at IS NULL;

ALTER TABLE notifications ALTER COLUMN created_at SET NOT NULL;

ALTER TABLE notifications ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE notification_templates (
    id SERIAL NOT NULL, 
    event_type VARCHAR(40) NOT NULL, 
    subject_template VARCHAR(300) NOT NULL, 
    body_template TEXT NOT NULL, 
    enabled BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (event_type)
);

INSERT INTO notification_templates (event_type, subject_template, body_template) VALUES ('ERROR_CREATED', 'New QA Error Logged: {{error_id}}', 'A new QA error has been logged.

Error ID: {{error_id}}
Severity: {{severity}}
Category: {{category}}

View it here: {{qems_url}}');

INSERT INTO notification_templates (event_type, subject_template, body_template) VALUES ('ERROR_ASSIGNED', 'Action Required: {{error_id}}', 'A new QA error has been assigned to you.

Error ID: {{error_id}}
Severity: {{severity}}
Category: {{category}}
Assigned By: {{sender}}
Due Date: {{due_date}}

Please review the error and submit your response.
{{qems_url}}');

INSERT INTO notification_templates (event_type, subject_template, body_template) VALUES ('MESSAGE_RECEIVED', 'New message on {{error_id}}', '{{sender}} sent a new message on {{error_id}}:

"{{message}}"

Reply here: {{qems_url}}');

INSERT INTO notification_templates (event_type, subject_template, body_template) VALUES ('REBUTTAL_SUBMITTED', 'Response Received: Rebuttal on {{error_id}}', 'A stakeholder has submitted a rebuttal for {{error_id}}. Please review the response and supporting evidence.

{{message}}

{{qems_url}}');

INSERT INTO notification_templates (event_type, subject_template, body_template) VALUES ('EVIDENCE_REQUESTED', 'Evidence Required: {{error_id}}', 'Additional evidence has been requested for {{error_id}}.

Request: {{message}}

Please upload supporting evidence: {{qems_url}}');

INSERT INTO notification_templates (event_type, subject_template, body_template) VALUES ('DECISION_UPDATED', 'QA decision recorded: {{error_id}}', 'A QA decision has been recorded on {{error_id}}.

Decision: {{decision}}
Notes: {{message}}

{{qems_url}}');

INSERT INTO notification_templates (event_type, subject_template, body_template) VALUES ('DEADLINE_APPROACHING', 'Reminder: {{error_id}} is due soon', '{{error_id}} is due {{due_date}} and is still awaiting a response. Please act before the deadline.

{{qems_url}}');

INSERT INTO notification_templates (event_type, subject_template, body_template) VALUES ('ERROR_OVERDUE', 'Overdue: {{error_id}}', '{{error_id}} has exceeded its response deadline ({{due_date}}). Immediate attention is required.

{{qems_url}}');

INSERT INTO notification_templates (event_type, subject_template, body_template) VALUES ('ERROR_RESOLVED', 'Resolved: {{error_id}}', '{{error_id}} ({{category}}) has been marked Resolved.

Decision: {{decision}}

{{qems_url}}');

CREATE TABLE notification_logs (
    id SERIAL NOT NULL, 
    notification_id INTEGER NOT NULL, 
    provider VARCHAR(30) NOT NULL, 
    provider_message_id VARCHAR(255), 
    status VARCHAR(20) NOT NULL, 
    error_message TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(notification_id) REFERENCES notifications (notification_id) ON DELETE CASCADE
);

CREATE INDEX idx_notification_logs_notification ON notification_logs (notification_id);

UPDATE alembic_version SET version_num='e1f2a3b4c5d6' WHERE alembic_version.version_num = 'a7b8c9d0e1f2';

COMMIT;

