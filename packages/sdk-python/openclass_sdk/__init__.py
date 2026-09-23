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

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        response = self._client.request(method, path, json=body)
        response.raise_for_status()
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
