-- Phase 3: control-plane project/classifier mappings and scoped API keys.
CREATE TABLE IF NOT EXISTS control_projects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES control_workspaces(id) ON DELETE CASCADE,
  engine_project_id uuid NOT NULL UNIQUE,
  slug varchar(80) NOT NULL UNIQUE,
  name varchar(200) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS control_classifiers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES control_projects(id) ON DELETE CASCADE,
  engine_classifier_id uuid NOT NULL UNIQUE,
  slug varchar(80) NOT NULL,
  name varchar(200) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, slug)
);

CREATE TABLE IF NOT EXISTS control_api_keys (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES control_workspaces(id) ON DELETE CASCADE,
  project_id uuid NOT NULL REFERENCES control_projects(id) ON DELETE CASCADE,
  key_hash text NOT NULL UNIQUE,
  prefix varchar(24) NOT NULL,
  scopes text[] NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz
);

CREATE INDEX IF NOT EXISTS control_projects_workspace_idx ON control_projects (workspace_id);
CREATE INDEX IF NOT EXISTS control_classifiers_project_idx ON control_classifiers (project_id);
CREATE INDEX IF NOT EXISTS control_api_keys_project_idx ON control_api_keys (project_id);
