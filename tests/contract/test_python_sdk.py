import json

import httpx
import pytest
from openclass_sdk import OpenClass


def test_sdk_uses_public_protocol() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/classifiers/support-intent/classify"
        assert json.loads(request.content) == {"observation": "hello", "metadata": {}}
        return httpx.Response(200, json={"selected_class": None})

    with OpenClass(transport=httpx.MockTransport(handle)) as client:
        assert (
            client.classify(classifier="support-intent", observation="hello")["selected_class"]
            is None
        )


def test_sdk_does_not_hide_http_errors() -> None:
    with OpenClass(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
        with pytest.raises(httpx.HTTPStatusError):
            client.health()


def test_sdk_requests_runs_and_reviews_over_public_routes() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path == "/api/v1/classifiers/support-intent/runs/run-1/reviews"
            assert json.loads(request.content) == {"trigger": "manual"}
            return httpx.Response(201, json={"id": "review", "result": {"finding": "no_issue"}})
        if request.url.path == "/api/v1/classifiers/support-intent/runs/run-1":
            return httpx.Response(200, json={"observation": {"content": "x"}, "result": {}})
        assert request.url.path in (
            "/api/v1/classifiers/support-intent/runs",
            "/api/v1/classifiers/support-intent/reviews",
        )
        return httpx.Response(200, json=[])

    with OpenClass(transport=httpx.MockTransport(handle)) as client:
        assert client.review_run(classifier="support-intent", run_id="run-1")["id"] == "review"
        assert client.reviews("support-intent") == []
        assert client.runs("support-intent") == []
        assert client.run("support-intent", "run-1")["observation"]["content"] == "x"
