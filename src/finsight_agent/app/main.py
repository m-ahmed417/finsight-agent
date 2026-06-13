from fastapi import FastAPI

from finsight_agent.app.api.routes import router
from finsight_agent.app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Production-style AI equity research assistant.",
    )
    app.include_router(router)
    return app


app = create_app()
