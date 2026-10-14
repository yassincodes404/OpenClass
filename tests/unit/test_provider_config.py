import pytest
from fastapi.testclient import TestClient
from openclass_provider_jev import JevDecisionProvider
from openclass_provider_laya import LayaDecisionProvider
from openclass_provider_mock import MockDecisionProvider
from openclass_server.main import create_app
from openclass_server.provider_config import decision_provider, resolve_decision_provider
from openclass_server.settings import Settings
from pydantic import SecretStr, ValidationError


def test_mock_default_and_explicit_jev_selection() -> None:
    assert isinstance(decision_provider(Settings(decision_provider="laya")), LayaDecisionProvider)
    assert isinstance(decision_provider(Settings(decision_provider="mock")), MockDecisionProvider)
    config = Settings(decision_provider="jev", jev_api_key=SecretStr("synthetic-key"))
    assert isinstance(decision_provider(config), JevDecisionProvider)
    assert "synthetic-key" not in repr(config) + config.model_dump_json()
    assert "jev_api_key" not in config.model_dump()


def test_unknown_override_fails_closed() -> None:
    with pytest.raises(ValueError):
        resolve_decision_provider(Settings(decision_provider="mock"), "quantum")


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


def test_openai_compatible_discovery_and_teacher_defaults(monkeypatch) -> None:
    from openclass_provider_glm import (
        GLMDiscoveryProvider,
        OpenAICompatibleChoiceTeacher,
        OpenAICompatibleDiagnosisProvider,
    )
    from openclass_server.provider_config import (
        discovery_provider,
        project_diagnosis_provider,
        project_teacher_provider,
    )

    monkeypatch.setenv("AI_GATEWAY_API_KEY", "synthetic-gateway-key")
    settings = Settings(discovery_provider="openai-compatible")
    disc = discovery_provider(settings)
    teacher = project_teacher_provider(settings)
    diag = project_diagnosis_provider(settings)
    assert isinstance(disc, GLMDiscoveryProvider)
    assert isinstance(teacher, OpenAICompatibleChoiceTeacher)
    assert isinstance(diag, OpenAICompatibleDiagnosisProvider)
    assert teacher.url.startswith("https://ai-gateway.vercel.sh/v1")


def test_auth_required_and_internal_token_verification() -> None:
    from openclass_server.security import is_public_engine_path, verify_internal_token

    with pytest.raises(ValidationError):
        Settings(auth_required=True)

    config = Settings(auth_required=True, internal_token=SecretStr("internal-secret-token"))
    assert "internal-secret-token" not in repr(config) + config.model_dump_json()
    assert verify_internal_token("internal-secret-token", "internal-secret-token") is True
    assert verify_internal_token("Bearer internal-secret-token", "internal-secret-token") is True
    assert verify_internal_token("wrong-token", "internal-secret-token") is False
    assert verify_internal_token(None, "internal-secret-token") is False
    assert verify_internal_token("internal-secret-token", "") is False
    assert is_public_engine_path("/health", "GET") is True
    assert is_public_engine_path("/health/ready", "GET") is True
    assert is_public_engine_path("/api/v1/projects/demo/integrations/int-1/webhook", "POST") is True
    assert is_public_engine_path("/api/v1/projects/demo/webhooks/github", "POST") is True
    assert is_public_engine_path("/api/v1/projects", "GET") is False
