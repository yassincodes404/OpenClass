"""Public HTTP client. This package has no core or server dependency."""

from typing import Any
from urllib.parse import quote

import httpx


class OpenClass:
    def __init__(
        self,
        base_url: str = "http://localhost:7331",
        *,
        timeout: float = 30,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout, transport=transport
        )

    def __enter__(self) -> "OpenClass":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        response = self._client.request(method, path, json=body, params=params, headers=headers)
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def health(self) -> dict[str, Any]:
        return dict(self._request("GET", "/health/ready"))

    def classifiers(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/api/v1/classifiers"))

    def create_classifier(
        self, *, slug: str, name: str, classes: list[dict[str, Any]], description: str = ""
    ) -> dict[str, Any]:
        return dict(
            self._request(
                "POST",
                "/api/v1/classifiers",
                {"slug": slug, "name": name, "description": description, "classes": classes},
            )
        )

    def classify(
        self, *, classifier: str, observation: str, metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return dict(
            self._request(
                "POST",
                f"/api/v1/classifiers/{quote(classifier, safe='')}/classify",
                {"observation": observation, "metadata": metadata or {}},
            )
        )

    def ontology(self, classifier: str) -> dict[str, Any]:
        return dict(
            self._request("GET", f"/api/v1/classifiers/{quote(classifier, safe='')}/ontology")
        )

    def unknowns(self, classifier: str) -> list[dict[str, Any]]:
        return list(
            self._request("GET", f"/api/v1/classifiers/{quote(classifier, safe='')}/unknowns")
        )

    def candidates(self, classifier: str) -> list[dict[str, Any]]:
        return list(
            self._request("GET", f"/api/v1/classifiers/{quote(classifier, safe='')}/candidates")
        )

    def reject_candidate(self, classifier: str, candidate_id: str, reason: str) -> dict[str, Any]:
        path = (
            f"/api/v1/classifiers/{quote(classifier, safe='')}/candidates/"
            f"{quote(candidate_id, safe='')}/reject"
        )
        return dict(self._request("POST", path, {"reason": reason}))

    def projects(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/api/v1/projects"))

    def create_project(self, *, name: str, description: str = "") -> dict[str, Any]:
        return dict(
            self._request("POST", "/api/v1/projects", {"name": name, "description": description})
        )

    def project(self, project: str) -> dict[str, Any]:
        return dict(self._request("GET", f"/api/v1/projects/{quote(project, safe='')}"))

    def update_project(
        self,
        project: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        body = {
            k: v
            for k, v in (("name", name), ("description", description), ("status", status))
            if v is not None
        }
        return dict(self._request("PATCH", f"/api/v1/projects/{quote(project, safe='')}", body))

    def project_summary(self, project: str) -> dict[str, Any]:
        return dict(self._request("GET", f"/api/v1/projects/{quote(project, safe='')}/summary"))

    def project_analytics(self, project: str) -> dict[str, Any]:
        return dict(self._request("GET", f"/api/v1/projects/{quote(project, safe='')}/analytics"))

    def project_audit(self, project: str) -> list[dict[str, Any]]:
        return list(self._request("GET", f"/api/v1/projects/{quote(project, safe='')}/audit"))

    def runs(self, classifier: str, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        return list(
            self._request(
                "GET",
                f"/api/v1/classifiers/{quote(classifier, safe='')}/runs",
                params={"limit": limit, "offset": offset},
            )
        )

    def run(self, classifier: str, run_id: str) -> dict[str, Any]:
        return dict(
            self._request(
                "GET", f"/api/v1/classifiers/{quote(classifier, safe='')}/runs/{quote(run_id)}"
            )
        )

    def review_run(self, classifier: str, run_id: str) -> dict[str, Any]:
        return dict(
            self._request(
                "POST",
                f"/api/v1/classifiers/{quote(classifier, safe='')}/runs/{quote(run_id)}/reviews",
                {"trigger": "manual"},
            )
        )

    def reviews(self, classifier: str, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        return list(
            self._request(
                "GET",
                f"/api/v1/classifiers/{quote(classifier, safe='')}/reviews",
                params={"limit": limit, "offset": offset},
            )
        )

    def create_event(
        self,
        project: str,
        *,
        content: str,
        source_type: str = "text",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return dict(
            self._request(
                "POST",
                f"/api/v1/projects/{quote(project, safe='')}/events",
                {
                    "content": content,
                    "source_type": source_type,
                    "metadata": metadata or {},
                },
            )
        )

    def create_events_batch(
        self,
        project: str,
        *,
        items: list[dict[str, Any]],
        source_type: str = "text",
    ) -> list[dict[str, Any]]:
        payload = self._request(
            "POST",
            f"/api/v1/projects/{quote(project, safe='')}/events/batch",
            {
                "items": items,
                "source_type": source_type,
            },
        )
        # 207 multi-status: {"items": [{index, status, event?|error?, deduped?}]}
        if isinstance(payload, dict) and "items" in payload:
            return list(payload["items"])
        return list(payload)

    def events(
        self,
        project: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return list(
            self._request(
                "GET",
                f"/api/v1/projects/{quote(project, safe='')}/events",
                params={"limit": limit, "offset": offset},
            )
        )

    def event(self, project: str, event_id: str) -> dict[str, Any]:
        return dict(
            self._request(
                "GET",
                f"/api/v1/projects/{quote(project, safe='')}/events/{quote(event_id, safe='')}",
            )
        )

    def create_decision_service(
        self,
        project: str,
        *,
        name: str,
        instructions: str,
        choices: list[dict[str, Any]],
        description: str = "",
        provider_override: str | None = None,
    ) -> dict[str, Any]:
        return dict(
            self._request(
                "POST",
                f"/api/v1/projects/{quote(project, safe='')}/decision-services",
                {
                    "name": name,
                    "instructions": instructions,
                    "choices": choices,
                    "description": description,
                    "provider_override": provider_override,
                },
            )
        )

    def decision_services(self, project: str) -> list[dict[str, Any]]:
        return list(
            self._request(
                "GET",
                f"/api/v1/projects/{quote(project, safe='')}/decision-services",
            )
        )

    def decision_service(self, project: str, service_id: str) -> dict[str, Any]:
        p = quote(project, safe="")
        sid = quote(service_id, safe="")
        return dict(
            self._request(
                "GET",
                f"/api/v1/projects/{p}/decision-services/{sid}",
            )
        )

    def update_decision_service(
        self,
        project: str,
        service_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        status: str | None = None,
        provider_override: str | None = None,
    ) -> dict[str, Any]:
        body = {
            k: v
            for k, v in (
                ("name", name),
                ("description", description),
                ("instructions", instructions),
                ("status", status),
                ("provider_override", provider_override),
            )
            if v is not None
        }
        p = quote(project, safe="")
        sid = quote(service_id, safe="")
        return dict(
            self._request(
                "PATCH",
                f"/api/v1/projects/{p}/decision-services/{sid}",
                body,
            )
        )

    def execute_decision_runs(
        self,
        project: str,
        service_id: str,
        *,
        raw_event_ids: list[str],
    ) -> list[dict[str, Any]]:
        p = quote(project, safe="")
        sid = quote(service_id, safe="")
        return list(
            self._request(
                "POST",
                f"/api/v1/projects/{p}/decision-services/{sid}/runs",
                {"raw_event_ids": raw_event_ids},
            )
        )

    def decision_runs(
        self,
        project: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return list(
            self._request(
                "GET",
                f"/api/v1/projects/{quote(project, safe='')}/runs",
                params={"limit": limit, "offset": offset},
            )
        )

    def decision_run(self, project: str, run_id: str) -> dict[str, Any]:
        return dict(
            self._request(
                "GET",
                f"/api/v1/projects/{quote(project, safe='')}/runs/{quote(run_id, safe='')}",
            )
        )

    def provider_status(self) -> dict[str, Any]:
        return dict(self._request("GET", "/api/v1/providers/status"))

    def evidence(
        self,
        project: str,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        return list(
            self._request(
                "GET",
                f"/api/v1/projects/{quote(project, safe='')}/evidence",
                params=params,
            )
        )

    def evidence_item(self, project: str, evidence_id: str) -> dict[str, Any]:
        p = quote(project, safe="")
        eid = quote(evidence_id, safe="")
        return dict(self._request("GET", f"/api/v1/projects/{p}/evidence/{eid}"))

    def triage_evidence(
        self,
        project: str,
        evidence_id: str,
        *,
        diagnosis: str,
        rationale: str | None = None,
    ) -> dict[str, Any]:
        p = quote(project, safe="")
        eid = quote(evidence_id, safe="")
        body: dict[str, Any] = {"diagnosis": diagnosis}
        if rationale is not None:
            body["rationale"] = rationale
        return dict(self._request("PATCH", f"/api/v1/projects/{p}/evidence/{eid}/triage", body))

    def transition_evidence(
        self,
        project: str,
        evidence_id: str,
        *,
        target_status: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        p = quote(project, safe="")
        eid = quote(evidence_id, safe="")
        body: dict[str, Any] = {"target_status": target_status}
        if note is not None:
            body["note"] = note
        return dict(self._request("POST", f"/api/v1/projects/{p}/evidence/{eid}/transition", body))

    def ai_diagnose_evidence(self, project: str, evidence_id: str) -> dict[str, Any]:
        p = quote(project, safe="")
        eid = quote(evidence_id, safe="")
        return dict(self._request("POST", f"/api/v1/projects/{p}/evidence/{eid}/ai-diagnose"))

    def submit_run_feedback(
        self,
        project: str,
        run_id: str,
        *,
        action: str,
        corrected_choice: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        p = quote(project, safe="")
        rid = quote(run_id, safe="")
        body: dict[str, Any] = {"action": action}
        if corrected_choice is not None:
            body["corrected_choice"] = corrected_choice
        if note is not None:
            body["note"] = note
        return dict(self._request("POST", f"/api/v1/projects/{p}/runs/{rid}/feedback", body))

    def run_feedback(self, project: str, run_id: str) -> list[dict[str, Any]]:
        p = quote(project, safe="")
        rid = quote(run_id, safe="")
        return list(self._request("GET", f"/api/v1/projects/{p}/runs/{rid}/feedback"))

    def create_evidence_case(
        self,
        project: str,
        *,
        title: str,
        description: str = "",
        decision_service_id: str | None = None,
        evidence_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        p = quote(project, safe="")
        body: dict[str, Any] = {"title": title, "description": description}
        if decision_service_id is not None:
            body["decision_service_id"] = decision_service_id
        if evidence_ids is not None:
            body["evidence_ids"] = evidence_ids
        return dict(self._request("POST", f"/api/v1/projects/{p}/evidence-cases", body))

    def evidence_cases(
        self,
        project: str,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        p = quote(project, safe="")
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        return list(self._request("GET", f"/api/v1/projects/{p}/evidence-cases", params=params))

    def evidence_case(self, project: str, case_id: str) -> dict[str, Any]:
        p = quote(project, safe="")
        cid = quote(case_id, safe="")
        return dict(self._request("GET", f"/api/v1/projects/{p}/evidence-cases/{cid}"))

    def case_evidence(self, project: str, case_id: str) -> list[dict[str, Any]]:
        p = quote(project, safe="")
        cid = quote(case_id, safe="")
        return list(self._request("GET", f"/api/v1/projects/{p}/evidence-cases/{cid}/evidence"))

    def add_evidence_to_case(
        self, project: str, case_id: str, *, evidence_id: str
    ) -> dict[str, Any]:
        p = quote(project, safe="")
        cid = quote(case_id, safe="")
        return dict(
            self._request(
                "POST",
                f"/api/v1/projects/{p}/evidence-cases/{cid}/evidence",
                {"evidence_id": evidence_id},
            )
        )

    def evolution_summary(self, project: str) -> dict[str, Any]:
        p = quote(project, safe="")
        return dict(self._request("GET", f"/api/v1/projects/{p}/evolution/summary"))

    def project_candidates(self, project: str) -> list[dict[str, Any]]:
        p = quote(project, safe="")
        return list(self._request("GET", f"/api/v1/projects/{p}/candidates"))

    def project_candidate(self, project: str, candidate_id: str) -> dict[str, Any]:
        p = quote(project, safe="")
        cid = quote(candidate_id, safe="")
        return dict(self._request("GET", f"/api/v1/projects/{p}/candidates/{cid}"))

    def propose_project_choice(
        self, project: str, service_id: str, *, run_ids: list[str]
    ) -> dict[str, Any]:
        p = quote(project, safe="")
        sid = quote(service_id, safe="")
        return dict(
            self._request(
                "POST",
                f"/api/v1/projects/{p}/decision-services/{sid}/candidates",
                {"run_ids": run_ids},
            )
        )

    def propose_from_evidence(
        self,
        project: str,
        *,
        service_id: str | None = None,
        evidence_ids: list[str] | None = None,
        evidence_case_id: str | None = None,
    ) -> dict[str, Any]:
        p = quote(project, safe="")
        body: dict[str, Any] = {}
        if service_id is not None:
            body["service_id"] = service_id
        if evidence_ids is not None:
            body["evidence_ids"] = evidence_ids
        if evidence_case_id is not None:
            body["evidence_case_id"] = evidence_case_id
        return dict(self._request("POST", f"/api/v1/projects/{p}/evolution/propose", body))

    def evaluate_project_candidate(self, project: str, candidate_id: str) -> dict[str, Any]:
        p = quote(project, safe="")
        cid = quote(candidate_id, safe="")
        return dict(self._request("POST", f"/api/v1/projects/{p}/candidates/{cid}/evaluate"))

    def promote_project_candidate(
        self, project: str, candidate_id: str, *, note: str | None = None
    ) -> dict[str, Any]:
        p = quote(project, safe="")
        cid = quote(candidate_id, safe="")
        body = {"note": note} if note is not None else None
        return dict(self._request("POST", f"/api/v1/projects/{p}/candidates/{cid}/promote", body))

    def reject_project_choice(
        self, project: str, candidate_id: str, *, reason: str
    ) -> dict[str, Any]:
        p = quote(project, safe="")
        cid = quote(candidate_id, safe="")
        return dict(
            self._request(
                "POST",
                f"/api/v1/projects/{p}/candidates/{cid}/reject",
                {"reason": reason},
            )
        )

    # ── Integrations ──────────────────────────────────────────

    def project_integrations(self, project: str) -> list[dict[str, Any]]:
        p = quote(project, safe="")
        return list(self._request("GET", f"/api/v1/projects/{p}/integrations"))

    def project_integration(self, project: str, integration_id: str) -> dict[str, Any]:
        p = quote(project, safe="")
        iid = quote(integration_id, safe="")
        return dict(self._request("GET", f"/api/v1/projects/{p}/integrations/{iid}"))

    def create_project_integration(
        self,
        project: str,
        *,
        name: str,
        type: str,
        endpoint: str | None = None,
        secret_ref: str | None = None,
        capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        p = quote(project, safe="")
        body: dict[str, Any] = {
            "name": name,
            "type": type,
            "endpoint": endpoint,
            "secret_ref": secret_ref,
            "capabilities": capabilities or [],
            "metadata": metadata or {},
        }
        return dict(self._request("POST", f"/api/v1/projects/{p}/integrations", body))

    def update_project_integration(
        self,
        project: str,
        integration_id: str,
        *,
        name: str | None = None,
        status: str | None = None,
        endpoint: str | None = None,
        secret_ref: str | None = None,
        capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        p = quote(project, safe="")
        iid = quote(integration_id, safe="")
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if status is not None:
            body["status"] = status
        if endpoint is not None:
            body["endpoint"] = endpoint
        if secret_ref is not None:
            body["secret_ref"] = secret_ref
        if capabilities is not None:
            body["capabilities"] = capabilities
        if metadata is not None:
            body["metadata"] = metadata
        return dict(self._request("PATCH", f"/api/v1/projects/{p}/integrations/{iid}", body))

    def delete_project_integration(self, project: str, integration_id: str) -> None:
        p = quote(project, safe="")
        iid = quote(integration_id, safe="")
        self._request("DELETE", f"/api/v1/projects/{p}/integrations/{iid}")

    def test_project_integration(self, project: str, integration_id: str) -> dict[str, Any]:
        p = quote(project, safe="")
        iid = quote(integration_id, safe="")
        return dict(self._request("POST", f"/api/v1/projects/{p}/integrations/{iid}/test"))

    def ingest_integration_webhook(
        self,
        project: str,
        integration_id: str,
        *,
        event_key: str,
        content: str,
        source: str = "webhook",
        metadata: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        p = quote(project, safe="")
        iid = quote(integration_id, safe="")
        headers = {"X-OpenClass-Token": token} if token else None
        body = {
            "event_key": event_key,
            "source": source,
            "content": content,
            "metadata": metadata or {},
        }
        return dict(
            self._request(
                "POST",
                f"/api/v1/projects/{p}/integrations/{iid}/webhook",
                body,
                headers=headers,
            )
        )

    def system_health(self) -> dict[str, Any]:
        return dict(self._request("GET", "/api/v1/system/health"))
