from collections.abc import AsyncIterable

from dishka import Provider, Scope, make_async_container, provide
from faststream.rabbit import RabbitBroker, RabbitExchange, RabbitQueue
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api import PaymentsRouter
from app.consumers.app import ConsumerApp
from app.consumers.payments import PaymentConsumer
from app.infra.broker import create_rabbit_broker, get_exchange, get_payments_queue
from app.infra.config import Settings
from app.infra.db.connection import create_engine
from app.infra.db.repos.outbox import OutboxRepo
from app.infra.db.repos.payments import PaymentsRepo
from app.infra.http import HttpClient
from app.infra.logging import setup_logging
from app.infra.redis.connection import create_redis_client
from app.infra.redis.lock import RedisLocks
from app.logic.handlers.payments import (
    CreatePaymentHandler,
    GetPaymentHandler,
    ListPaymentsHandler,
)
from app.logic.handlers.processing import (
    PaymentGatewayEmulator,
    ProcessPaymentHandler,
)
from app.logic.middlewares import RetryMiddleware
from app.logic.payments.service import PaymentsService
from app.logic.webhooks.service import WebhookService
from app.main import AppBuilder
from app.workers.outbox import OutboxPublisher


class SettingsProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> Settings:
        s = Settings()
        setup_logging(log_level=s.log_level, json_logs=s.json_logs)
        return s


class DBProvider(Provider):
    @provide(scope=Scope.APP)
    def engine(self, settings: Settings) -> AsyncEngine:
        return create_engine(settings)

    @provide(scope=Scope.APP)
    def payments_repo(self, engine: AsyncEngine) -> PaymentsRepo:
        return PaymentsRepo(engine=engine)

    @provide(scope=Scope.APP)
    def outbox_repo(self, engine: AsyncEngine) -> OutboxRepo:
        return OutboxRepo(engine=engine)


class HttpProvider(Provider):
    @provide(scope=Scope.APP)
    async def http_client(self, settings: Settings) -> AsyncIterable[HttpClient]:
        client = HttpClient(timeout=settings.webhook_timeout_seconds)
        try:
            yield client
        finally:
            await client.close()


class RedisProvider(Provider):
    @provide(scope=Scope.APP)
    async def redis_client(self, settings: Settings) -> Redis:
        return await create_redis_client(settings)

    @provide(scope=Scope.APP)
    def redis_locks(self, redis_client: Redis) -> RedisLocks:
        return RedisLocks(client=redis_client)


class BrokerProvider(Provider):
    @provide(scope=Scope.APP)
    def broker(self, settings: Settings) -> RabbitBroker:
        return create_rabbit_broker(settings)

    @provide(scope=Scope.APP)
    def exchange(self, settings: Settings) -> RabbitExchange:
        return get_exchange(settings)

    @provide(scope=Scope.APP)
    def payments_queue(self, settings: Settings) -> RabbitQueue:
        return get_payments_queue(settings)


class LogicProvider(Provider):
    @provide(scope=Scope.APP)
    def payments_service(
        self,
        payments_repo: PaymentsRepo,
        outbox_repo: OutboxRepo,
        locks: RedisLocks,
    ) -> PaymentsService:
        return PaymentsService(
            payments_repo=payments_repo,
            outbox_repo=outbox_repo,
            locks=locks,
        )

    @provide(scope=Scope.APP)
    def webhook_service(self, http_client: HttpClient, settings: Settings) -> WebhookService:
        return WebhookService(http_client=http_client, secret=settings.webhook_secret)

    @provide(scope=Scope.APP)
    def payment_gateway(self, settings: Settings) -> PaymentGatewayEmulator:
        return PaymentGatewayEmulator(settings=settings)

    @provide(scope=Scope.APP)
    def create_payment_handler(self, service: PaymentsService) -> CreatePaymentHandler:
        return CreatePaymentHandler(payments_service=service)

    @provide(scope=Scope.APP)
    def get_payment_handler(self, service: PaymentsService) -> GetPaymentHandler:
        return GetPaymentHandler(payments_service=service)

    @provide(scope=Scope.APP)
    def list_payments_handler(self, service: PaymentsService) -> ListPaymentsHandler:
        return ListPaymentsHandler(payments_service=service)

    @provide(scope=Scope.APP)
    def process_payment_handler(
        self,
        service: PaymentsService,
        payments_repo: PaymentsRepo,
        gateway: PaymentGatewayEmulator,
        webhook_service: WebhookService,
        locks: RedisLocks,
        settings: Settings,
    ) -> ProcessPaymentHandler:
        return ProcessPaymentHandler(
            payments_service=service,
            payments_repo=payments_repo,
            gateway=gateway,
            webhook_service=webhook_service,
            locks=locks,
            settings=settings,
        )


class AppProvider(Provider):
    @provide(scope=Scope.APP)
    def payments_router(
        self,
        create_payment_handler: CreatePaymentHandler,
        get_payment_handler: GetPaymentHandler,
        list_payments_handler: ListPaymentsHandler,
    ) -> PaymentsRouter:
        return PaymentsRouter(
            create_payment_handler=create_payment_handler,
            get_payment_handler=get_payment_handler,
            list_payments_handler=list_payments_handler,
        )

    @provide(scope=Scope.APP)
    def app_builder(
        self,
        settings: Settings,
        payments_router: PaymentsRouter,
    ) -> AppBuilder:
        return AppBuilder(routers=[payments_router.router], settings=settings)


class MiddlewareProvider(Provider):
    @provide(scope=Scope.APP)
    def retry_middleware(
        self,
        broker: RabbitBroker,
        exchange: RabbitExchange,
        settings: Settings,
    ) -> type[RetryMiddleware]:
        RetryMiddleware.setup(broker, exchange, settings)
        return RetryMiddleware


class ConsumerProvider(Provider):
    @provide(scope=Scope.APP)
    def payment_consumer(
        self,
        broker: RabbitBroker,
        exchange: RabbitExchange,
        queue: RabbitQueue,
        handler: ProcessPaymentHandler,
        settings: Settings,
        _retry: type[RetryMiddleware],
    ) -> PaymentConsumer:
        return PaymentConsumer(
            broker=broker,
            exchange=exchange,
            queue=queue,
            handler=handler,
            settings=settings,
        )

    @provide(scope=Scope.APP)
    def consumer_app(
        self,
        broker: RabbitBroker,
        payment_consumer: PaymentConsumer,
        settings: Settings,
    ) -> ConsumerApp:
        return ConsumerApp(
            broker=broker,
            payment_consumer=payment_consumer,
            settings=settings,
        )


class WorkerProvider(Provider):
    @provide(scope=Scope.APP)
    def outbox_publisher(
        self,
        broker: RabbitBroker,
        exchange: RabbitExchange,
        outbox_repo: OutboxRepo,
        settings: Settings,
    ) -> OutboxPublisher:
        return OutboxPublisher(
            broker=broker,
            exchange=exchange,
            outbox_repo=outbox_repo,
            settings=settings,
        )


def build_providers() -> tuple[Provider, ...]:
    return (
        SettingsProvider(),
        DBProvider(),
        HttpProvider(),
        RedisProvider(),
        BrokerProvider(),
        LogicProvider(),
        AppProvider(),
        MiddlewareProvider(),
        ConsumerProvider(),
        WorkerProvider(),
    )


container = make_async_container(*build_providers())
