"""Shared snapshot-to-row mapping; no transactions or domain policy."""

from openclass_core.projects import ProjectAuditEvent, RawEvent

from .tables import AuditEventRow, RawEventRow


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
        metadata_=event.metadata,
        created_at=event.created_at,
        payload=event.model_dump(mode="json"),
    )
