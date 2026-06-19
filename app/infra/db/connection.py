from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.infra.config import Settings
from app.infra.logging import get_logger

logger = get_logger(__name__)


def create_engine(settings: Settings) -> AsyncEngine:
    logger.info("creating_async_engine", host=settings.postgres_host)
    return create_async_engine(
        settings.db_url_async,
        echo=settings.debug,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
