from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.responses import ORJSONResponse

from app.api.exceptions import register_exception_handlers
from app.infra.config import Settings
from app.infra.logging import get_logger

logger = get_logger(__name__)


class AppBuilder:
    def __init__(self, routers: list[APIRouter], settings: Settings) -> None:
        self.routers = routers
        self.settings = settings

    @asynccontextmanager
    async def lifespan(self, _app: FastAPI):
        logger.info("api_started", version=self.settings.app_version)
        yield
        logger.info("api_stopped")

    def create_app(self) -> FastAPI:
        app = FastAPI(
            title=self.settings.app_name,
            description="Async payment processing service",
            version=self.settings.app_version,
            debug=self.settings.debug,
            default_response_class=ORJSONResponse,
            lifespan=self.lifespan,
        )
        register_exception_handlers(app)
        for router in self.routers:
            app.include_router(router)
        return app
