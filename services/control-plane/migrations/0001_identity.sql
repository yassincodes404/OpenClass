CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE IF NOT EXISTS control_workspaces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), slug varchar(80) NOT NULL UNIQUE,
  name varchar(200) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS control_workspace_memberships (
  workspace_id uuid NOT NULL REFERENCES control_workspaces(id) ON DELETE CASCADE,
  subject varchar(200) NOT NULL, role varchar(16) NOT NULL CHECK (role IN ('owner','admin','reviewer','analyst','developer','viewer')),
  created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (workspace_id, subject)
);
