"""Terminal Inspector over the public Python HTTP SDK (no core or server imports)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from typing import Any

import httpx
from openclass_sdk import OpenClass


def _format_probability(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "-"
    if round(numeric, 2) == round(numeric, 6):
        return f"{numeric:.2f}"
    return f"{numeric:.4f}".rstrip("0").rstrip(".")


def _truncate(text: str, width: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= width:
        return clean
    if width <= 1:
        return clean[:width]
    return f"{clean[: width - 1]}…"


def _extract_server_url(client: OpenClass) -> str:
    inner = getattr(client, "_client", None)
    base_url = getattr(inner, "base_url", None)
    if base_url is not None:
        return str(base_url).rstrip("/")
    return "http://localhost:7331"


def _render_box(title: str, lines: Sequence[str], *, min_width: int = 76) -> list[str]:
    content_width = max(
        min_width,
        len(title) + 4,
        *(len(line) for line in lines),
    )
    top_title = f"─ {title} "
    top_bar = "┌" + top_title + "─" * max(0, content_width + 2 - len(top_title)) + "┐"
    body = [f"│ {line.ljust(content_width)} │" for line in lines]
    bottom_bar = "└" + "─" * (content_width + 2) + "┘"
    return [top_bar, *body, bottom_bar]


def _render_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            if idx < len(widths):
                widths[idx] = max(widths[idx], len(cell))

    top = "┌─" + "─┬─".join("─" * width for width in widths) + "─┐"
    header_line = (
        "│ " + " │ ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers)) + " │"
    )
    separator = "├─" + "─┼─".join("─" * width for width in widths) + "─┤"
    bottom = "└─" + "─┴─".join("─" * width for width in widths) + "─┘"

    if not rows:
        inner_width = len(header_line) - 4
        empty_line = f"│ {'(no decision runs recorded)'.ljust(inner_width)} │"
        empty_bottom = "└" + "─" * (len(header_line) - 2) + "┘"
        return [top, header_line, separator, empty_line, empty_bottom]

    body_lines = [
        "│ " + " │ ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row)) + " │"
        for row in rows
    ]
    return [top, header_line, separator, *body_lines, bottom]


class OpenClassInspector:
    """HTTP-only terminal inspector backed by `openclass_sdk.OpenClass`."""

    def __init__(
        self,
        client: OpenClass,
        *,
        run_limit: int = 10,
        unknown_limit: int = 20,
    ) -> None:
        self._client = client
        self._run_limit = run_limit
        self._unknown_limit = unknown_limit

    def fetch_project_snapshot(self, project: str) -> dict[str, Any]:
        health = self._client.health()
        summary = self._client.project_summary(project)
        try:
            project_meta = self._client.project(project)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            project_meta = {"slug": project, "name": project, "status": "active"}

        runs = self._client.decision_runs(project, limit=self._run_limit, offset=0)
        unknowns_payload = self._client.project_unknowns(
            project, limit=self._unknown_limit, offset=0
        )
        unknown_items = list(unknowns_payload.get("items", []))
        clusters = self._client.clusters(project)
        candidates = self._client.discovery_candidates(project)

        total_unknowns = int(summary.get("unknowns", len(unknown_items)))
        return {
            "kind": "project",
            "server_url": _extract_server_url(self._client),
            "health": health,
            "project": {
                "id": project_meta.get("id", project),
                "slug": project_meta.get("slug", project),
                "name": project_meta.get("name", project),
                "status": project_meta.get("status", "active"),
            },
            "summary": {
                "events": int(summary.get("events", 0)),
                "decision_runs": int(summary.get("decision_runs", len(runs))),
                "unknowns": total_unknowns,
                "pending_evidence": int(summary.get("pending_evidence", 0)),
                "pending_candidates": int(summary.get("pending_candidates", len(candidates))),
                "audit_events": int(summary.get("audit_events", 0)),
                "active_policy": summary.get("active_policy"),
            },
            "decision_runs": [
                {
                    "id": str(run.get("id", "-")),
                    "selected_choice": str(run.get("selected_choice") or "UNKNOWN"),
                    "supervision_outcome": str(run.get("supervision_outcome", "-")),
                    "unknown_probability": float(run.get("unknown_probability", 0.0)),
                    "provider": str(run.get("provider", "-")),
                    "simulated": bool(
                        run.get("execution_mode") == "mock"
                        or run.get("provider") == "mock"
                        or run.get("real_inference") is False
                    ),
                }
                for run in runs
            ],
            "unknown_pool": {
                "total_unknowns": total_unknowns,
                "items": unknown_items,
                "clusters": clusters,
                "discovery_candidates": candidates,
            },
        }

    def fetch_classifier_snapshot(self, classifier: str) -> dict[str, Any]:
        health = self._client.health()
        ontology = self._client.ontology(classifier)
        raw_runs = self._client.runs(classifier, limit=self._run_limit, offset=0)
        unknowns = self._client.unknowns(classifier)
        candidates = self._client.candidates(classifier)

        normalized_runs: list[dict[str, Any]] = []
        for record in raw_runs:
            result = record.get("result", record) if isinstance(record, dict) else {}
            decision = result.get("decision", {}) if isinstance(result, dict) else {}
            novelty = result.get("novelty", {}) if isinstance(result, dict) else {}
            provider = str(decision.get("provider", result.get("provider", "-")))
            normalized_runs.append(
                {
                    "id": str(result.get("id", "-")),
                    "selected_choice": str(result.get("selected_class") or "UNKNOWN"),
                    "supervision_outcome": str(
                        novelty.get("state", result.get("supervision_outcome", "-"))
                    ),
                    "unknown_probability": float(
                        decision.get(
                            "unknown_probability",
                            result.get("unknown_probability", 0.0),
                        )
                    ),
                    "provider": provider,
                    "simulated": provider == "mock",
                }
            )

        normalized_candidates = [
            {
                "id": str(item.get("id", "-")),
                "canonical_name": item.get("canonical_name"),
                "display_name": item.get("display_name"),
                "type": item.get("proposal_type", item.get("type", "new_class")),
                "status": item.get("status", "candidate"),
                "confidence": float(item.get("confidence", 0.0)),
                "provider": str(item.get("discovery_provider", item.get("provider", "mock"))),
                "simulated": str(item.get("discovery_provider", item.get("provider", "")))
                == "mock",
            }
            for item in candidates
        ]

        return {
            "kind": "classifier",
            "server_url": _extract_server_url(self._client),
            "health": health,
            "project": {
                "id": str(ontology.get("classifier_id", classifier)),
                "slug": classifier,
                "name": classifier,
                "status": f"ontology v{ontology.get('version_number', 1)}",
            },
            "summary": {
                "events": len(raw_runs),
                "decision_runs": len(raw_runs),
                "unknowns": len(unknowns),
                "pending_evidence": len(unknowns),
                "pending_candidates": len(normalized_candidates),
                "audit_events": 0,
                "active_policy": f"v{ontology.get('version_number', 1)}",
            },
            "decision_runs": normalized_runs,
            "unknown_pool": {
                "total_unknowns": len(unknowns),
                "items": unknowns,
                "clusters": [],
                "discovery_candidates": normalized_candidates,
            },
        }

    def render_snapshot(self, snapshot: dict[str, Any]) -> str:
        server_url = str(snapshot.get("server_url", "http://localhost:7331"))
        health = snapshot.get("health", {})
        health_status = str(health.get("status", "unknown"))
        schema_rev = health.get("schema")
        health_display = f"{health_status} (schema {schema_rev})" if schema_rev else health_status

        project = snapshot.get("project", {})
        project_name = str(project.get("name", "-"))
        project_slug = str(project.get("slug", "-"))
        project_label = (
            f"{project_name} ({project_slug})" if project_name != project_slug else project_slug
        )

        summary = snapshot.get("summary", {})
        header_lines = [
            f"Server URL   : {server_url}",
            f"Health Status: {health_display}",
            f"Project      : {project_label}",
            "─" * 74,
            (
                f"events: {summary.get('events', 0)}  │  "
                f"decision_runs: {summary.get('decision_runs', 0)}  │  "
                f"unknowns: {summary.get('unknowns', 0)}"
            ),
            (
                f"pending_evidence: {summary.get('pending_evidence', 0)}  │  "
                f"pending_candidates: {summary.get('pending_candidates', 0)}  │  "
                f"audit_events: {summary.get('audit_events', 0)}"
            ),
        ]
        if summary.get("active_policy"):
            header_lines.append(f"active_policy: {summary['active_policy']}")

        sections: list[str] = []
        sections.extend(_render_box("OpenClass Terminal Inspector", header_lines))

        runs = list(snapshot.get("decision_runs", []))
        run_headers = (
            "id",
            "selected_choice",
            "supervision_outcome",
            "unknown_probability",
            "provider",
        )
        run_rows: list[tuple[str, str, str, str, str]] = []
        for run in runs:
            provider_str = str(run.get("provider", "-"))
            if run.get("simulated") and "simulated" not in provider_str:
                provider_str = f"{provider_str} [simulated]"
            run_rows.append(
                (
                    str(run.get("id", "-")),
                    str(run.get("selected_choice") or "UNKNOWN"),
                    str(run.get("supervision_outcome", "-")),
                    _format_probability(run.get("unknown_probability", 0.0)),
                    provider_str,
                )
            )
        sections.append("")
        sections.append("Recent Decision Runs")
        sections.extend(_render_table(run_headers, run_rows))

        pool = snapshot.get("unknown_pool", {})
        unknown_items = list(pool.get("items", []))
        clusters = list(pool.get("clusters", []))
        candidates = list(pool.get("discovery_candidates", []))
        total_unknowns = int(pool.get("total_unknowns", len(unknown_items)))

        pool_lines: list[str] = [
            (
                f"total unknowns: {total_unknowns}  │  "
                f"clusters: {len(clusters)}  │  "
                f"discovery candidates: {len(candidates)}"
            ),
            "─" * 74,
            "Unknown Observations (permanent UNKNOWN state; not proof of a new class):",
        ]
        if not unknown_items:
            pool_lines.append("  (none)")
        else:
            for item in unknown_items[:5]:
                run_id = str(item.get("run_id", item.get("id", "-")))
                triage = item.get("triage") if isinstance(item.get("triage"), dict) else {}
                status = str(triage.get("status", item.get("review_state", "new")))
                prob = _format_probability(item.get("unknown_probability", 0.0))
                content_raw = item.get("content", "")
                if not content_raw and isinstance(item.get("observation"), dict):
                    content_raw = item["observation"].get("content", "")
                preview = _truncate(str(content_raw), 42)
                pool_lines.append(
                    f"  • {run_id} [status={status}, unknown_probability={prob}] {preview}"
                )

        pool_lines.append("Clusters:")
        if not clusters:
            pool_lines.append("  (no clusters formed)")
        else:
            for cluster in clusters:
                cid = str(cluster.get("id", "-"))
                size = int(
                    cluster.get(
                        "size",
                        len(cluster.get("members", []))
                        if isinstance(cluster.get("members"), list)
                        else 0,
                    )
                )
                algo = str(cluster.get("algorithm", "cosine"))
                model = str(cluster.get("model", "-"))
                threshold = _format_probability(cluster.get("threshold", 0.0))
                sim_tag = " [simulated]" if cluster.get("simulated") else ""
                pool_lines.append(
                    f"  • {cid} (size={size}, threshold={threshold}, "
                    f"algorithm={algo}, model={model}){sim_tag}"
                )

        pool_lines.append("Discovery Candidates (inactive until evaluated & human-promoted):")
        if not candidates:
            pool_lines.append("  (no discovery candidates)")
        else:
            for cand in candidates:
                cand_id = str(cand.get("id", "-"))
                name = str(
                    cand.get("canonical_name")
                    or cand.get("display_name")
                    or cand.get("type", "candidate")
                )
                ctype = str(cand.get("type", cand.get("proposal_type", "new_class")))
                status = str(cand.get("status", "candidate"))
                conf = _format_probability(cand.get("confidence", 0.0))
                provider = str(cand.get("provider", "-"))
                sim_tag = " [simulated]" if cand.get("simulated") or provider == "mock" else ""
                pool_lines.append(
                    f"  • {cand_id} {name} [type={ctype}, status={status}, "
                    f"confidence={conf}, provider={provider}]{sim_tag}"
                )

        sections.append("")
        sections.extend(_render_box("Unknown Pool & Clusters", pool_lines))
        return "\n".join(sections)

    def render_project(self, project: str) -> str:
        snapshot = self.fetch_project_snapshot(project)
        return self.render_snapshot(snapshot)

    def render_classifier(self, classifier: str) -> str:
        snapshot = self.fetch_classifier_snapshot(classifier)
        return self.render_snapshot(snapshot)


def render_project_dashboard(client: OpenClass, project: str) -> str:
    """Fetch and render a deterministic terminal dashboard for an OpenClass project."""
    return OpenClassInspector(client).render_project(project)


def render_classifier_dashboard(client: OpenClass, classifier: str) -> str:
    """Fetch and render a deterministic terminal dashboard for a legacy classifier."""
    return OpenClassInspector(client).render_classifier(classifier)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openclass-tui",
        description="OpenClass Terminal Inspector over the public HTTP SDK",
    )
    parser.add_argument(
        "--server",
        default=os.getenv("OPENCLASS_SERVER_URL", "http://localhost:7331"),
        help="OpenClass server base URL (default: OPENCLASS_SERVER_URL or http://localhost:7331)",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Project slug or ID to inspect",
    )
    parser.add_argument(
        "--classifier",
        default=None,
        help="Optional legacy classifier slug to inspect",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="emit_json",
        help="Emit structured JSON snapshot instead of the box-drawing dashboard",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        with OpenClass(args.server) as client:
            inspector = OpenClassInspector(client)
            target_project: str | None = args.project
            target_classifier: str | None = args.classifier

            if not target_project and not target_classifier:
                projects = client.projects()
                if projects:
                    first = projects[0]
                    target_project = str(first.get("slug") or first.get("id"))
                else:
                    classifiers = client.classifiers()
                    if classifiers:
                        target_classifier = str(classifiers[0].get("slug"))

            if target_project:
                snapshot = inspector.fetch_project_snapshot(target_project)
            elif target_classifier:
                snapshot = inspector.fetch_classifier_snapshot(target_classifier)
            else:
                print(
                    "OpenClass TUI: no projects or classifiers found; "
                    "pass --project <slug> or --classifier <slug>",
                    file=sys.stderr,
                )
                sys.exit(1)

            if args.emit_json:
                print(json.dumps(snapshot, indent=2))
            else:
                print(inspector.render_snapshot(snapshot))
    except httpx.HTTPStatusError as exc:
        print(
            f"OpenClass TUI: server returned HTTP {exc.response.status_code}: {exc.response.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    except httpx.RequestError:
        print(
            "OpenClass TUI: could not reach server; run openclass serve or check --server",
            file=sys.stderr,
        )
        sys.exit(1)
    except (OSError, ValueError, TypeError) as exc:
        print(f"OpenClass TUI: invalid configuration: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
