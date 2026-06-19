from typing import Any

from faststream.middlewares import AckPolicy
from faststream.rabbit import RabbitBroker, RabbitExchange, RabbitQueue

from app.infra.config import Settings
from app.infra.logging import get_logger
from app.logic.handlers.processing import ProcessPaymentHandler

logger = get_logger(__name__)


class PaymentConsumer:
    def __init__(
        self,
        broker: RabbitBroker,
        exchange: RabbitExchange,
        queue: RabbitQueue,
        handler: ProcessPaymentHandler,
        settings: Settings,
    ) -> None:
        self.broker = broker
        self.exchange = exchange
        self.queue = queue
        self.handler = handler
        self.settings = settings

    def register(self) -> None:
        @self.broker.subscriber(
            self.queue,
            self.exchange,
            ack_policy=AckPolicy.REJECT_ON_ERROR,
        )
        async def _on_message(payload: dict[str, Any]) -> None:
            await self.handler.execute(payload)
