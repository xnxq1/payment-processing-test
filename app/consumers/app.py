from faststream import FastStream
from faststream.rabbit import RabbitBroker

from app.consumers.payments import PaymentConsumer
from app.infra.broker import declare_topology
from app.infra.config import Settings
from app.infra.logging import get_logger

logger = get_logger(__name__)


class ConsumerApp:
    def __init__(
        self,
        broker: RabbitBroker,
        payment_consumer: PaymentConsumer,
        settings: Settings,
    ) -> None:
        self.broker = broker
        self.payment_consumer = payment_consumer
        self.settings = settings

    def create_app(self) -> FastStream:
        self.payment_consumer.register()
        app = FastStream(self.broker, logger=logger)
        app.after_startup(self._declare_topology)
        return app

    async def _declare_topology(self) -> None:
        await declare_topology(self.broker, self.settings)
