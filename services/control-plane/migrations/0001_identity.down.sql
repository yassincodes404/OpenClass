-- Dev-only down migration for 0001_identity.sql.
-- Drops memberships before workspaces to satisfy the FK cascade order.
DROP TABLE IF EXISTS control_workspace_memberships;
DROP TABLE IF EXISTS control_workspaces;
