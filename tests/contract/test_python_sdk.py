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
