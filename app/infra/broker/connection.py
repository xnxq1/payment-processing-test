from faststream.rabbit import RabbitBroker

from app.infra.config import Settings
from app.infra.logging import get_logger
from app.logic.middlewares import RetryMiddleware

logger = get_logger(__name__)


def create_rabbit_broker(settings: Settings) -> RabbitBroker:
    logger.info("creating_rabbit_broker")
    return RabbitBroker(
        settings.rabbitmq_url,
        app_id=settings.app_name,
        middlewares=(RetryMiddleware,),
    )
