"""Shared snapshot-to-row mapping; no transactions or domain policy."""

from openclass_core.projects import Project, ProjectAuditEvent, RawEvent

from .tables import AuditEventRow, ProjectRow, RawEventRow


def _project_from_row(row: ProjectRow) -> Project:
    payload = dict(row.payload) if isinstance(row.payload, dict) else {}
    workspace_id = row.workspace_id if row.workspace_id is not None else payload.get("workspace_id")
    payload["workspace_id"] = workspace_id
    return Project.model_validate(payload)


project_from_row = _project_from_row


def audit_event_row(event: ProjectAuditEvent) -> AuditEventRow:
    return AuditEventRow(
        id=str(event.id),
        project_id=str(event.project_id),
        event_type=event.event_type,
        actor=event.actor,
        payload=event.model_dump(mode="json"),
        created_at=event.created_at,
    )


def raw_event_row(event: RawEvent) -> RawEventRow:
    return RawEventRow(
        id=str(event.id),
        project_id=str(event.project_id),
        source_type=event.source_type,
        content=event.content,
        content_hash=event.content_hash,
        metadata_=event.metadata,
        created_at=event.created_at,
        payload=event.model_dump(mode="json"),
    )
