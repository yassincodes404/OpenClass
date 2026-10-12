"""Operations dashboard: analytics summary, alert rules, resumable events."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from openclass_core.alerting import AlertRule, evaluate_rules
from openclass_core.projects import ProjectService as ProjectDomainService
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from openclass_server.persistence.unknown_triage import UnknownTriageStore
from openclass_server.settings import Settings

VALID_METRICS = ("unknown_rate", "recurring_unknowns", "latency", "cost")


class RuleCreate(BaseModel):
    metric: str
    threshold: float = Field(gt=0)
    window: str = Field(default="1h", max_length=20)


def operations_router(
    config: Settings,
    projects: ProjectDomainService,
    sessions: async_sessionmaker[AsyncSession],
    triage_store: UnknownTriageStore,
) -> APIRouter:
    router = APIRouter(tags=["operations"])

    async def _measurements(project_id: str, since: datetime) -> dict[str, float | None]:
        """Measured persisted values only — no samples, no invention."""
        async with sessions() as session:
            runs_rows = await session.execute(
                sa.text(
                    "SELECT payload FROM decision_runs WHERE project_id = :pid"
                    " AND created_at >= :since"
                ),
                {"pid": project_id, "since": since},
            )
            unknown = total = 0
            recurring: dict[str, int] = {}
            latencies: list[float] = []
            for row in runs_rows:
                payload = row.payload
                if isinstance(payload, str):
                    payload = json.loads(payload)
                payload = payload if isinstance(payload, dict) else {}
                total += 1
                run = payload
                if (
                    run.get("selected_choice") == "UNKNOWN"
                    or run.get("supervision_outcome") == "UNKNOWN"
                ):
                    unknown += 1
                    snapshot = run.get("input_snapshot", {})
                    hash_key = str(snapshot.get("content_hash", snapshot.get("content", "")))
                    recurring[hash_key] = recurring.get(hash_key, 0) + 1
                latency = run.get("latency_ms")
                if isinstance(latency, (int, float)):
                    latencies.append(float(latency))
            cost = await session.execute(
                sa.text(
                    "SELECT COALESCE(SUM(estimated_cost), 0) FROM provider_usage"
                    " WHERE project_id = :pid AND usage_date >= :since_date"
                ),
                {"pid": project_id, "since_date": since.date()},
            )
            cost_value = float(cost.scalar() or 0.0)
        return {
            "unknown_rate": (unknown / total) if total else None,
            "recurring_unknowns": float(max(recurring.values())) if recurring else 0.0,
            "latency": (sum(latencies) / len(latencies)) if latencies else None,
            "cost": cost_value,
        }

    @router.get("/api/v1/projects/{identifier}/analytics/summary")
    async def analytics_summary(
        identifier: str,
        days: int = 7,
    ) -> dict[str, Any]:
        project = await projects.get(identifier)
        now = datetime.now(UTC)
        week_ago = now - timedelta(days=days)
        two_weeks_ago = now - timedelta(days=days * 2)
        current = await _measurements(str(project.id), week_ago)
        previous = await _measurements(str(project.id), two_weeks_ago)
        async with sessions() as session:
            top = await session.execute(
                sa.text(
                    "SELECT selected_choice, count(*) AS n FROM decision_runs"
                    " WHERE project_id = :pid AND created_at >= :since"
                    " GROUP BY selected_choice ORDER BY n DESC LIMIT 5"
                ),
                {"pid": str(project.id), "since": week_ago},
            )
            daily = await session.execute(
                sa.text(
                    "SELECT date(created_at) AS day, count(*) AS total,"
                    " SUM(CASE WHEN selected_choice = 'UNKNOWN' THEN 1 ELSE 0 END) AS unknowns"
                    " FROM decision_runs WHERE project_id = :pid AND created_at >= :since"
                    " GROUP BY day ORDER BY day"
                ),
                {"pid": str(project.id), "since": week_ago},
            )
            pending = await session.execute(
                sa.text(
                    "SELECT count(*) FROM cluster_candidates"
                    " WHERE project_id = :pid AND status IN"
                    " ('candidate', 'collecting_evidence', 'validating')"
                ),
                {"pid": str(project.id)},
            )
            versions = await session.execute(
                sa.text(
                    "SELECT to_version, event_type, created_at FROM service_ontology_events"
                    " WHERE project_id = :pid ORDER BY created_at DESC LIMIT 5"
                ),
                {"pid": str(project.id)},
            )
            fired = await session.execute(
                sa.text(
                    "SELECT metric, measured, threshold, created_at FROM alert_events"
                    " WHERE project_id = :pid ORDER BY created_at DESC LIMIT 10"
                ),
                {"pid": str(project.id)},
            )
        prev_rate = previous.get("unknown_rate")
        curr_rate = current.get("unknown_rate")
        return {
            "window_days": days,
            "unknown_rate": curr_rate,
            "previous_unknown_rate": prev_rate,
            "unknown_rate_delta": None
            if curr_rate is None or prev_rate is None
            else round(curr_rate - prev_rate, 4),
            "latency_avg_ms": current.get("latency"),
            "provider_cost": current.get("cost"),
            "recurring_unknowns": current.get("recurring_unknowns"),
            "top_classes": [{"class": row.selected_choice, "count": row.n} for row in top],
            "daily": [
                {"date": str(row.day), "total": row.total, "unknowns": row.unknowns or 0}
                for row in daily
            ],
            "pending_reviews": int(pending.scalar() or 0),
            "recent_versions": [
                {
                    "to_version": row.to_version,
                    "event": row.event_type,
                    "created_at": row.created_at,
                }
                for row in versions
            ],
            "recent_alerts": [
                {
                    "metric": row.metric,
                    "measured": row.measured,
                    "threshold": row.threshold,
                    "created_at": row.created_at,
                }
                for row in fired
            ],
            "simulated": config.decision_provider == "mock",
        }

    @router.get("/api/v1/projects/{identifier}/alerts/rules")
    async def list_rules(identifier: str) -> list[dict[str, Any]]:
        project = await projects.get(identifier)
        async with sessions() as session:
            rows = await session.execute(
                sa.text(
                    'SELECT id, metric, threshold, "window", enabled FROM alert_rules'
                    " WHERE project_id = :pid ORDER BY created_at"
                ),
                {"pid": str(project.id)},
            )
            return [
                {
                    "id": row.id,
                    "metric": row.metric,
                    "threshold": row.threshold,
                    "window": row.window,
                    "enabled": row.enabled,
                }
                for row in rows
            ]

    @router.post("/api/v1/projects/{identifier}/alerts/rules", status_code=201)
    async def create_rule(identifier: str, body: RuleCreate) -> dict[str, Any]:
        if body.metric not in VALID_METRICS:
            raise HTTPException(status_code=400, detail=f"metric must be one of {VALID_METRICS}")
        project = await projects.get(identifier)
        rule_id = str(uuid4())
        async with sessions.begin() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO alert_rules"
                    ' (id, project_id, metric, threshold, "window", enabled, created_at)'
                    " VALUES (:id, :pid, :metric, :threshold, :window, TRUE, :created)"
                ),
                {
                    "id": rule_id,
                    "pid": str(project.id),
                    "metric": body.metric,
                    "threshold": body.threshold,
                    "window": body.window,
                    "created": datetime.now(UTC),
                },
            )
        return {
            "id": rule_id,
            "metric": body.metric,
            "threshold": body.threshold,
            "window": body.window,
            "enabled": True,
        }

    @router.post("/api/v1/projects/{identifier}/alerts/evaluate")
    async def evaluate_alerts(identifier: str) -> dict[str, Any]:
        """Evaluate all rules against current measurements; fire + audit breaches."""
        project = await projects.get(identifier)
        async with sessions() as session:
            rows = await session.execute(
                sa.text(
                    'SELECT id, metric, threshold, "window", enabled FROM alert_rules'
                    " WHERE project_id = :pid AND enabled = TRUE"
                ),
                {"pid": str(project.id)},
            )
            rules = [
                AlertRule(
                    id=row.id,
                    project_id=str(project.id),
                    metric=row.metric,
                    threshold=row.threshold,
                    window=row.window,
                    enabled=bool(row.enabled),
                )
                for row in rows
            ]
        since = datetime.now(UTC) - timedelta(hours=1)
        measurements = await _measurements(str(project.id), since)
        alerts = evaluate_rules(rules, measurements)
        for alert in alerts:
            async with sessions.begin() as session:
                await session.execute(
                    sa.text(
                        "INSERT INTO alert_events"
                        " (id, project_id, rule_id, metric, measured,"
                        "  threshold, created_at)"
                        " VALUES (:id, :pid, :rid, :metric, :measured, :threshold, :created)"
                    ),
                    {
                        "id": str(uuid4()),
                        "pid": str(project.id),
                        "rid": alert["rule_id"],
                        "metric": alert["metric"],
                        "measured": alert["measured"],
                        "threshold": alert["threshold"],
                        "created": datetime.now(UTC),
                    },
                )
            await triage_store.append_audit(
                project.id, "portal-user", "quality.alert", f"rule:{alert['metric']}", dict(alert)
            )
        return {"fired": len(alerts), "alerts": alerts, "measurements": measurements}

    @router.get("/api/v1/projects/{identifier}/ops/events")
    async def project_events(identifier: str, after: str = "") -> dict[str, Any]:
        """Ordered, resumable event log (JSON polling; SSE transport below).

        Namespaced under /ops because the Genesis raw-events route owns
        /projects/:id/events. The cursor is the last event's timestamp.
        """
        project = await projects.get(identifier)
        async with sessions() as session:
            rows = await session.execute(
                sa.text(
                    "SELECT event_type, actor, payload, created_at FROM audit_events"
                    " WHERE project_id = :pid AND CAST(created_at AS VARCHAR) > :after"
                    " ORDER BY created_at, id LIMIT 100"
                ),
                {"pid": str(project.id), "after": after},
            )
            events = []
            for row in rows:
                created = row.created_at
                stamp = created.isoformat() if hasattr(created, "isoformat") else str(created)
                payload = row.payload
                if isinstance(payload, str):
                    payload = json.loads(payload)
                events.append(
                    {
                        "event": row.event_type,
                        "actor": row.actor,
                        "payload": payload,
                        "created_at": stamp,
                    }
                )
        next_cursor = events[-1]["created_at"] if events else after
        return {"events": events, "next_cursor": next_cursor}

    @router.get("/api/v1/projects/{identifier}/ops/events/stream")
    async def project_events_stream(identifier: str, after: str = "") -> StreamingResponse:
        """SSE transport: resumable via the timestamp cursor (Last-Event-ID style)."""
        project = await projects.get(identifier)

        async def generate() -> AsyncGenerator[str, None]:
            cursor = after
            idle = 0
            while idle < 15:  # close after ~30s idle; clients reconnect with cursor
                async with sessions() as session:
                    rows = await session.execute(
                        sa.text(
                            "SELECT event_type, actor, payload, created_at FROM audit_events"
                            " WHERE project_id = :pid AND CAST(created_at AS VARCHAR) > :after"
                            " ORDER BY created_at, id LIMIT 50"
                        ),
                        {"pid": str(project.id), "after": cursor},
                    )
                    fresh = rows.fetchall()
                if fresh:
                    for row in fresh:
                        created = row.created_at
                        cursor = (
                            created.isoformat() if hasattr(created, "isoformat") else str(created)
                        )
                        payload = row.payload
                        if isinstance(payload, str):
                            payload = json.loads(payload)
                        data = json.dumps(
                            {
                                "event": row.event_type,
                                "actor": row.actor,
                                "payload": payload,
                                "created_at": cursor,
                            }
                        )
                        yield f"id: {cursor}\nevent: openclass\ndata: {data}\n\n"
                    idle = 0
                else:
                    yield ": keep-alive\n\n"
                    idle += 1
                await asyncio.sleep(2)

        return StreamingResponse(generate(), media_type="text/event-stream")

    return router
