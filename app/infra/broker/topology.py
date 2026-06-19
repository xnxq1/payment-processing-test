from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from app.infra.config import Settings
from app.infra.logging import get_logger

logger = get_logger(__name__)


def get_exchange(settings: Settings) -> RabbitExchange:
    return RabbitExchange(
        settings.rabbitmq_exchange,
        type=ExchangeType.TOPIC,
        durable=True,
    )


def get_payments_queue(settings: Settings) -> RabbitQueue:
    return RabbitQueue(
        settings.topic_payments_new,
        durable=True,
        routing_key=settings.topic_payments_new,
        arguments={
            "x-dead-letter-exchange": settings.rabbitmq_exchange,
            "x-dead-letter-routing-key": settings.topic_payments_dlq,
        },
    )


def get_payments_retry_queue(settings: Settings) -> RabbitQueue:
    return RabbitQueue(
        settings.topic_payments_retry,
        durable=True,
        routing_key=settings.topic_payments_retry,
        arguments={
            "x-dead-letter-exchange": settings.rabbitmq_exchange,
            "x-dead-letter-routing-key": settings.topic_payments_new,
        },
    )


def get_payments_dlq(settings: Settings) -> RabbitQueue:
    return RabbitQueue(
        settings.topic_payments_dlq,
        durable=True,
        routing_key=settings.topic_payments_dlq,
    )


async def declare_topology(broker: RabbitBroker, settings: Settings) -> None:
    """Декларирует exchange и все queue (main + retry + dlq) с DLX-связками.

    Должно быть вызвано после `broker.connect()` или из startup hook FastStream.
    Идемпотентно — RabbitMQ молча игнорирует повторное declare с теми же параметрами.
    """
    exchange = await broker.declare_exchange(get_exchange(settings))
    payments_queue = await broker.declare_queue(get_payments_queue(settings))
    retry_queue = await broker.declare_queue(get_payments_retry_queue(settings))
    dlq_queue = await broker.declare_queue(get_payments_dlq(settings))

    await payments_queue.bind(exchange, routing_key=settings.topic_payments_new)
    await retry_queue.bind(exchange, routing_key=settings.topic_payments_retry)
    await dlq_queue.bind(exchange, routing_key=settings.topic_payments_dlq)
    logger.info("rabbit_topology_declared")
