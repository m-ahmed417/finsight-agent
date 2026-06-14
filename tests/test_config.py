from finsight_agent.app.config import Settings, get_settings


def test_settings_load_default_values(monkeypatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.app_name == "FinSight"
    assert settings.app_env == "local"
    assert settings.database_url == "sqlite:///./finsight.db"
    assert settings.sec_user_agent == "FinSight/0.1 configured-via-env"
    assert settings.llm_provider == "mock"
    assert settings.llm_model == "mock"


def test_settings_load_environment_overrides(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("SEC_USER_AGENT", "FinSightTest/0.1 test@example.com")
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("LLM_MODEL", "fake-model")

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.database_url == "sqlite:///./test.db"
    assert settings.sec_user_agent == "FinSightTest/0.1 test@example.com"
    assert settings.llm_provider == "fake"
    assert settings.llm_model == "fake-model"


def test_get_settings_returns_cached_settings(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "cached-test")

    first_settings = get_settings()
    second_settings = get_settings()

    assert first_settings is second_settings
    assert first_settings.app_env == "cached-test"

    get_settings.cache_clear()
