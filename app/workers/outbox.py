import asyncio
import signal
from datetime import UTC, datetime, timedelta

from faststream.rabbit import RabbitBroker, RabbitExchange

from app.domain.outbox import OutboxEvent
from app.infra.broker import declare_topology
from app.infra.config import Settings
from app.infra.db.repos.outbox import OutboxRepo
from app.infra.logging import get_logger
from app.logic.utils import exponential_backoff_seconds, normalize

logger = get_logger(__name__)

MAX_PUBLISH_RETRIES = 5


class OutboxPublisher:
    def __init__(
        self,
        broker: RabbitBroker,
        exchange: RabbitExchange,
        outbox_repo: OutboxRepo,
        settings: Settings,
    ) -> None:
        self.broker = broker
        self.exchange = exchange
        self.repo = outbox_repo
        self.settings = settings
        self._stop = asyncio.Event()

    async def run(self) -> None:
        await self.broker.connect()
        await declare_topology(self.broker, self.settings)
        logger.info(
            "outbox_publisher_started",
            poll_interval=self.settings.outbox_poll_interval_seconds,
            batch_size=self.settings.outbox_batch_size,
        )
        try:
            while not self._stop.is_set():
                processed = await self._process_batch()
                if processed == 0:
                    await self._sleep(self.settings.outbox_poll_interval_seconds)
        finally:
            await self.broker.stop()
            logger.info("outbox_publisher_stopped")

    def stop(self) -> None:
        self._stop.set()

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except TimeoutError:
            pass

    async def _process_batch(self) -> int:
        async with self.repo.transaction():
            events = await self.repo.lock_pending_batch(self.settings.outbox_batch_size)
            if not events:
                return 0
            for event in events:
                await self._publish_one(event)
        return len(events)

    async def _publish_one(self, event: OutboxEvent) -> None:
        try:
            await self.broker.publish(
                normalize(event.payload or {}),
                exchange=self.exchange,
                routing_key=event.topic,
                message_id=str(event.id),
                persist=True,
            )
            await self.repo.mark_published(event.id)
            logger.info(
                "outbox_event_published",
                event_id=str(event.id),
                routing_key=event.topic,
                event_type=event.event_type,
            )
        except Exception as e:  # noqa: BLE001 — RabbitMQ может упасть по разным причинам
            retry_count = int(event.retry_count) + 1
            terminal = retry_count >= MAX_PUBLISH_RETRIES
            available_at = datetime.now(tz=UTC) + timedelta(
                seconds=exponential_backoff_seconds(retry_count)
            )
            await self.repo.mark_failed(
                event_id=event.id,
                last_error=str(e)[:500],
                retry_count=retry_count,
                available_at=available_at,
                terminal=terminal,
            )
            logger.error(
                "outbox_event_publish_failed",
                event_id=str(event.id),
                routing_key=event.topic,
                error=str(e),
                retry_count=retry_count,
                terminal=terminal,
            )


def install_signal_handlers(publisher: OutboxPublisher) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, publisher.stop)
