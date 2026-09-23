from openclass_core.novelty import NoveltyPolicy
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Single source of truth for the Alembic revision readiness requires. Update this
# constant (and only it) whenever a new migration becomes the expected head.
EXPECTED_SCHEMA_REVISION = "0002_supervisor_reviews"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENCLASS_", env_nested_delimiter="__")
    database_url: str = "postgresql+asyncpg://openclass:openclass@localhost:5432/openclass"
    database_connect_timeout: float = Field(default=5, gt=0, le=60)
    novelty: NoveltyPolicy = NoveltyPolicy()
