from openclass_core.novelty import NoveltyPolicy
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENCLASS_", env_nested_delimiter="__")
    database_url: str = "postgresql+asyncpg://openclass:openclass@localhost:5432/openclass"
    database_connect_timeout: float = Field(default=5, gt=0, le=60)
    novelty: NoveltyPolicy = NoveltyPolicy()
