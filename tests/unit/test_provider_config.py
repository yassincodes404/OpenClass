import pytest
from fastapi.testclient import TestClient
from openclass_provider_jev import JevDecisionProvider
from openclass_provider_laya import LayaDecisionProvider
from openclass_provider_mock import MockDecisionProvider
from openclass_server.main import create_app
from openclass_server.provider_config import decision_provider
from openclass_server.settings import Settings
from pydantic import SecretStr, ValidationError


def test_mock_default_and_explicit_jev_selection() -> None:
    assert isinstance(decision_provider(Settings()), LayaDecisionProvider)
    assert isinstance(decision_provider(Settings(decision_provider="mock")), MockDecisionProvider)
    config = Settings(decision_provider="jev", jev_api_key=SecretStr("synthetic-key"))
    assert isinstance(decision_provider(config), JevDecisionProvider)
    assert "synthetic-key" not in repr(config) + config.model_dump_json()
    assert "jev_api_key" not in config.model_dump()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"decision_provider": "invalid"},
        {"supervisor_provider": "glm"},
        {"decision_provider": "jev"},
        {"provider_max_retries": 3},
        {"provider_timeout_seconds": float("nan")},
        {"jev_base_url": "https://secret@evil.test"},
    ],
)
def test_invalid_configuration_fails_closed(kwargs) -> None:
    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_environment_configuration(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLASS_DECISION_PROVIDER", "jev")
    monkeypatch.setenv("OPENCLASS_JEV_API_KEY", "synthetic-key")
    assert isinstance(decision_provider(Settings()), JevDecisionProvider)


def test_configured_secrets_never_persist_or_echo(database_url, classifier_body) -> None:
    with TestClient(
        create_app(Settings(database_url=database_url, jev_api_key=SecretStr("synthetic-key")))
    ) as client:
        client.post("/api/v1/classifiers", json=classifier_body).raise_for_status()
        base = "/api/v1/classifiers/support-intent"
        for body in (
            {"observation": "synthetic-key"},
            {"observation": "ok", "metadata": {"key": "synthetic-key"}},
            {"observation": {"key": "synthetic-key"}},
        ):
            response = client.post(f"{base}/classify", json=body)
            assert response.status_code == 422
            assert "synthetic-key" not in response.text
        assert client.get(f"{base}/runs").json() == []
        assert "synthetic-key" not in client.get("/api/v1/providers").text
