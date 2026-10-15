-- Stable, lossless audit pagination, including events sharing transaction now().
CREATE INDEX control_audit_workspace_time_id_idx
  ON control_audit_events (workspace_id, created_at DESC, id DESC);
