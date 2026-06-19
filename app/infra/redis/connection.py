import redis.asyncio as redis_async
from redis.asyncio import Redis

from app.infra.config import Settings
from app.infra.logging import get_logger

logger = get_logger(__name__)


async def create_redis_client(settings: Settings) -> Redis:
    logger.info("creating_redis_client", host=settings.redis_host)
    return await redis_async.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
    )
