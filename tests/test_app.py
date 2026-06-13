from fastapi import FastAPI

from finsight_agent.app.config import get_settings
from finsight_agent.app.main import create_app


def test_create_app_returns_fastapi_application() -> None:
    get_settings.cache_clear()

    app = create_app()

    assert isinstance(app, FastAPI)
    assert app.title == "FinSight"


def test_create_app_registers_health_route() -> None:
    get_settings.cache_clear()

    app = create_app()
    route_paths = {route.path for route in app.routes}

    assert "/health" in route_paths
