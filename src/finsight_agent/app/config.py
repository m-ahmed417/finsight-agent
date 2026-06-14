from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FinSight"
    app_env: str = Field(default="local", validation_alias="APP_ENV")
    database_url: str = Field(
        default="sqlite:///./finsight.db",
        validation_alias="DATABASE_URL",
    )
    sec_user_agent: str = Field(
        default="FinSight/0.1 configured-via-env",
        validation_alias="SEC_USER_AGENT",
    )
    llm_provider: str = Field(default="mock", validation_alias="LLM_PROVIDER")
    llm_model: str = Field(default="mock", validation_alias="LLM_MODEL")
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )
    deepseek_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="DEEPSEEK_API_KEY",
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
