import os
from typing import Literal

from openclass_core.novelty import NoveltyPolicy
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Single source of truth for the Alembic revision readiness requires. Update this
# constant (and only it) whenever a new migration becomes the expected head.
EXPECTED_SCHEMA_REVISION = "0026_decision_run_checkpoints"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPENCLASS_", env_nested_delimiter="__", hide_input_in_errors=True
    )
    database_url: str = "postgresql+asyncpg://openclass:openclass@localhost:5432/openclass"
    database_connect_timeout: float = Field(default=5, gt=0, le=60)
    redaction_enabled: bool = True
    redaction_blocklist: str = ""
    auth_required: bool = False
    internal_token: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)
    rate_limits_enabled: bool = True
    rate_limit_ingest_per_minute: int = Field(default=60, ge=1)
    rate_limit_classify_per_minute: int = Field(default=300, ge=1)
    idempotency_ttl_hours: int = Field(default=24, ge=1, le=24 * 30)
    novelty: NoveltyPolicy = NoveltyPolicy()
    decision_provider: Literal["mock", "jev", "laya", "openai-compatible"] = "laya"
    supervisor_provider: Literal["mock", "glm", "openai-compatible"] = "mock"
    discovery_provider: Literal["mock", "glm", "openai-compatible", "none"] = "mock"
    embedding_provider: Literal["hash-lexical", "openai-compatible"] = "hash-lexical"
    embedding_model: Literal["openai/text-embedding-3-small", "cohere/embed-v4.0"] = (
        "openai/text-embedding-3-small"
    )
    laya_base_url: str = "http://127.0.0.1:8000"
    laya_model: str = "laya-router"
    laya_timeout_seconds: float = Field(default=20, gt=0, le=60, allow_inf_nan=False)
    laya_max_retries: int = Field(default=0, ge=0, le=2)
    laya_allow_fallback: bool = False
    jev_api_key: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)
    jev_base_url: str = "https://ai-gateway.vercel.sh/typesafe"
    jev_model: str = Field(
        default="typesafe-ai/jev", pattern=r"^(typesafe-ai/)?jev[-a-zA-Z0-9.]*$", max_length=100
    )
    glm_api_key: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)
    glm_base_url: str = ""
    glm_model: str = ""
    discovery_api_key: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)
    discovery_base_url: str = ""
    discovery_model: str = ""
    discovery_timeout_seconds: float = Field(default=30, gt=0, le=120)
    provider_timeout_seconds: float = Field(default=20, gt=0, le=60, allow_inf_nan=False)
    provider_max_retries: int = Field(default=0, ge=0, le=2)

    @model_validator(mode="after")
    def configured_provider(self) -> "Settings":
        if self.auth_required and not self.internal_token.get_secret_value().strip():
            raise ValueError("OPENCLASS_AUTH_REQUIRED requires OPENCLASS_INTERNAL_TOKEN")
        if self.jev_base_url not in {
            "https://api.typesafe.ai",
            "https://ai-gateway.vercel.sh/typesafe",
        }:
            raise ValueError("Unsupported Jev base URL")
        if self.decision_provider == "jev" and not self.jev_api_key.get_secret_value().strip():
            raise ValueError("Jev requires OPENCLASS_JEV_API_KEY")
        if (
            self.discovery_provider in {"glm", "openai-compatible"}
            or self.supervisor_provider in {"glm", "openai-compatible"}
            or self.decision_provider == "openai-compatible"
            or self.embedding_provider == "openai-compatible"
        ):
            key = (
                self.discovery_api_key.get_secret_value().strip()
                or self.glm_api_key.get_secret_value().strip()
                or (
                    os.getenv("AI_GATEWAY_API_KEY", "")
                    if "openai-compatible"
                    in {
                        self.discovery_provider,
                        self.supervisor_provider,
                        self.decision_provider,
                        self.embedding_provider,
                    }
                    else ""
                )
            )
            if not key:
                raise ValueError("Configured LLM provider requires an API key")
        return self
