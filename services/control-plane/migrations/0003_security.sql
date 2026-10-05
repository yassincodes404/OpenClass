-- Phase 4: append-only audit trail, idempotency keys, per-project privacy settings.
CREATE TABLE IF NOT EXISTS control_audit_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES control_workspaces(id) ON DELETE CASCADE,
  project_id uuid,
  actor varchar(200) NOT NULL,
  action varchar(80) NOT NULL,
  target varchar(300) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS control_audit_workspace_time_idx ON control_audit_events (workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS control_idempotency_keys (
  key varchar(200) NOT NULL,
  workspace_id uuid NOT NULL,
  response_hash varchar(64) NOT NULL,
  response jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  PRIMARY KEY (key, workspace_id)
);

ALTER TABLE control_projects ADD COLUMN IF NOT EXISTS redaction_enabled boolean NOT NULL DEFAULT true;
ALTER TABLE control_projects ADD COLUMN IF NOT EXISTS retention_days integer NOT NULL DEFAULT 90;
