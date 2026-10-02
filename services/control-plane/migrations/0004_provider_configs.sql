-- Phase 7: provider config references (env var names only, never raw secrets).
CREATE TABLE IF NOT EXISTS control_provider_configs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES control_workspaces(id) ON DELETE CASCADE,
  project_id uuid NOT NULL REFERENCES control_projects(id) ON DELETE CASCADE,
  type varchar(50) NOT NULL CHECK (type IN ('mock','jev','laya','ollama','openai-compatible')),
  endpoint_ref varchar(200),
  model varchar(200),
  timeout_seconds integer NOT NULL DEFAULT 20 CHECK (timeout_seconds BETWEEN 1 AND 60),
  is_default boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS control_provider_configs_project_idx ON control_provider_configs (project_id);
