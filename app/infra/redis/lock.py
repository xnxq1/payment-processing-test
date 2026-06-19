from contextlib import asynccontextmanager

from redis.asyncio import Redis

from app.infra.logging import get_logger

logger = get_logger(__name__)


class RedisLocks:
    def __init__(self, client: Redis) -> None:
        self.client = client

    @asynccontextmanager
    async def acquire(self, key: str, timeout: int = 60):
        async with self.client.lock(key, timeout=timeout, blocking_timeout=timeout):
            yield
