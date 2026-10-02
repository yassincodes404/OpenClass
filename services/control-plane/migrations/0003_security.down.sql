-- Dev-only down migration for 0003_security.sql.
DROP TABLE IF EXISTS control_idempotency_keys;
DROP TABLE IF EXISTS control_audit_events;
ALTER TABLE control_projects DROP COLUMN IF EXISTS retention_days;
ALTER TABLE control_projects DROP COLUMN IF EXISTS redaction_enabled;
