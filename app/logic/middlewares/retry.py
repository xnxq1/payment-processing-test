from typing import ClassVar

from faststream import BaseMiddleware
from faststream.rabbit import RabbitBroker, RabbitExchange

from app.infra.config import Settings
from app.infra.http import HttpPermanentError, HttpRetryableError
from app.infra.logging import get_logger
from app.logic.utils import exponential_backoff_seconds

logger = get_logger(__name__)

RETRYABLE: tuple[type[BaseException], ...] = (
    HttpRetryableError,
    HttpPermanentError,
)


class RetryMiddleware(BaseMiddleware):
    """Перехват исключений subscriber'а.

    Поведение:
    - ретраябельная ошибка и попытки не исчерпаны → republish в retry queue с TTL,
      ack оригинала.
    - ретраябельная ошибка, попытки исчерпаны → пробрасываем дальше →
      FastStream делает reject(no requeue) → DLX → DLQ.
    - неретраябельная (любая неожиданная) → пробрасываем дальше → DLX → DLQ.

    Зависимости (`broker`, `exchange`, `settings`) выставляются через
    `RetryMiddleware.setup(...)` один раз при сборке DI-контейнера.
    """

    _broker: ClassVar[RabbitBroker | None] = None
    _exchange: ClassVar[RabbitExchange | None] = None
    _settings: ClassVar[Settings | None] = None

    @classmethod
    def setup(
        cls,
        broker: RabbitBroker,
        exchange: RabbitExchange,
        settings: Settings,
    ) -> None:
        cls._broker = broker
        cls._exchange = exchange
        cls._settings = settings

    async def after_processed(self, exc_type, exc_val, exc_tb):  # noqa: ARG002
        if exc_val is None:
            return False

        if not isinstance(exc_val, RETRYABLE):
            return False

        settings = self._settings
        if settings is None:
            return False

        headers = dict(self.msg.headers or {}) if self.msg else {}
        retry_count = int(headers.get("x-retry-count", 0))
        next_count = retry_count + 1
        max_retries = settings.payment_max_retries

        if next_count >= max_retries:
            logger.error("retry_exhausted", retry_count=retry_count, error=str(exc_val))
            return False

        delay_sec = exponential_backoff_seconds(next_count)
        new_headers = {k: v for k, v in headers.items() if not str(k).startswith("x-death")}
        new_headers["x-retry-count"] = str(next_count)
        new_headers["x-last-error"] = str(exc_val)[:200]

        await self._broker.publish(
            self.msg.body,
            exchange=self._exchange,
            routing_key=settings.topic_payments_retry,
            headers=new_headers,
            expiration=delay_sec,
            persist=True,
        )
        logger.warning(
            "retry_scheduled",
            retry_count=next_count,
            delay_seconds=delay_sec,
            error=str(exc_val),
        )
        return True
