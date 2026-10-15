-- Preserve existing responses; legacy keys without request identity fail closed
-- until expiry. Never silently delete, relabel, or reconstruct historical rows.
ALTER TABLE control_idempotency_keys ADD COLUMN scope text;
UPDATE control_idempotency_keys SET scope = 'workspace:' || workspace_id::text;
ALTER TABLE control_idempotency_keys ALTER COLUMN scope SET NOT NULL;
ALTER TABLE control_idempotency_keys DROP CONSTRAINT control_idempotency_keys_pkey;
ALTER TABLE control_idempotency_keys ALTER COLUMN workspace_id DROP NOT NULL;
ALTER TABLE control_idempotency_keys ADD PRIMARY KEY (scope, key);
ALTER TABLE control_idempotency_keys ADD COLUMN request_hash varchar(64);
ALTER TABLE control_idempotency_keys ADD COLUMN response_status integer NOT NULL DEFAULT 200
  CHECK (response_status BETWEEN 100 AND 599);

-- Older installations may have the original globally unique project slug.
DO $$
DECLARE constraint_name text;
BEGIN
  FOR constraint_name IN
    SELECT c.conname FROM pg_constraint c
    WHERE c.conrelid = 'control_projects'::regclass AND c.contype = 'u'
      AND c.conkey = ARRAY[(SELECT attnum FROM pg_attribute
        WHERE attrelid = 'control_projects'::regclass AND attname = 'slug')]::smallint[]
  LOOP
    EXECUTE format('ALTER TABLE control_projects DROP CONSTRAINT %I', constraint_name);
  END LOOP;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conrelid = 'control_projects'::regclass
      AND contype = 'u' AND conkey = ARRAY[
        (SELECT attnum FROM pg_attribute WHERE attrelid = 'control_projects'::regclass AND attname = 'workspace_id'),
        (SELECT attnum FROM pg_attribute WHERE attrelid = 'control_projects'::regclass AND attname = 'slug')
      ]::smallint[]
  ) THEN
    ALTER TABLE control_projects ADD CONSTRAINT control_projects_workspace_slug_key UNIQUE (workspace_id, slug);
  END IF;
END $$;

ALTER TABLE control_audit_events DROP CONSTRAINT control_audit_events_workspace_id_fkey;
ALTER TABLE control_audit_events ADD CONSTRAINT control_audit_events_workspace_id_fkey
  FOREIGN KEY (workspace_id) REFERENCES control_workspaces(id) ON DELETE RESTRICT;
ALTER TABLE control_audit_events ADD COLUMN correlation_id varchar(128);

CREATE FUNCTION control_reject_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'control history is append-only' USING ERRCODE = '55000';
END $$;
CREATE TRIGGER control_audit_append_only
  BEFORE UPDATE OR DELETE OR TRUNCATE ON control_audit_events
  FOR EACH STATEMENT EXECUTE FUNCTION control_reject_history_mutation();
CREATE TRIGGER control_migration_history_append_only
  BEFORE UPDATE OR DELETE OR TRUNCATE ON control_schema_migrations
  FOR EACH STATEMENT EXECUTE FUNCTION control_reject_history_mutation();
