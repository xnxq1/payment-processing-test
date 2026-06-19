import asyncio
import random
from typing import Any
from uuid import UUID

from app.domain.payments import Payment, PaymentStatus
from app.infra.config import Settings
from app.infra.db.repos.payments import PaymentsRepo
from app.infra.logging import get_logger
from app.infra.redis.lock import RedisLocks
from app.logic.handlers.base import BaseHandler
from app.logic.payments.service import PaymentsService
from app.logic.utils import normalize
from app.logic.webhooks.service import WebhookService

logger = get_logger(__name__)


class PaymentGatewayEmulator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def charge(self) -> bool:
        # Payment simulation
        delay = random.uniform(
            self.settings.payment_processing_min_seconds,
            self.settings.payment_processing_max_seconds,
        )
        await asyncio.sleep(delay)
        return random.random() < self.settings.payment_success_rate


class ProcessPaymentHandler(BaseHandler):
    def __init__(
        self,
        payments_service: PaymentsService,
        payments_repo: PaymentsRepo,
        gateway: PaymentGatewayEmulator,
        webhook_service: WebhookService,
        locks: RedisLocks,
        settings: Settings,
    ) -> None:
        self.payments_service = payments_service
        self.payments_repo = payments_repo
        self.gateway = gateway
        self.webhook_service = webhook_service
        self.locks = locks
        self.settings = settings

    async def execute(self, message: dict[str, Any]) -> None:
        payment_id = message["id"]
        log = logger.bind(payment_id=payment_id)

        async with self.locks.acquire(f"payment:{payment_id}:process", timeout=120):
            payment = await self.payments_repo.get_by_id(UUID(payment_id))
            if payment is None:
                log.warning("payment_not_found_in_db")
                return

            if payment.status == PaymentStatus.PENDING.value:
                # Нет транзакционности, если после charge упадем то на след. сообщение мы сделаем еще раз charge
                # То есть спишем деньги 2 раза. Тут есть несколько вариантов -
                # 1. Оставляем как есть и такие кейсы оставляем на саппорт
                # 2. Если у провайдера есть возможность передать idempotency-key то передаем его и тогда проблема решается
                # на стороне провайдера
                # 3. sql выставить первым и обернуть все в sql транзакцию - но время выполнения http-запроса это время удержания транзакции
                # Так как в ТЗ не было об этом речи оставил так
                if await self.gateway.charge():
                    payment = await self.payments_service.mark_succeeded(payment.id)
                    log.info("payment_succeeded")
                else:
                    payment = await self.payments_service.mark_failed(
                        payment.id, error="gateway returned error"
                    )
                    log.warning("payment_failed")

            if self._needs_webhook(payment):
                await self._deliver_webhook(payment)
            else:
                log.info("payment_no_webhook_action", status=payment.status)

    @staticmethod
    def _needs_webhook(payment: Payment) -> bool:
        if not payment.webhook_url or payment.webhook_delivered_at is not None:
            return False
        return payment.status in (
            PaymentStatus.SUCCEEDED.value,
            PaymentStatus.FAILED.value,
        )

    async def _deliver_webhook(self, payment: Payment) -> None:
        # Обычно вебхуки выстраиваются так что есть idempotency-key и клиент уже сам решает что ему делать
        # P.S. вообще если есть вебхуки то мы должны гарантировать at-least-once но тут этого нет
        # потому что сообщение может 3 раза упасть до этого кода, поэтому это логичнее
        # сделать через отдельный outbox со своим воркером, но не по ТЗ))
        log = logger.bind(payment_id=str(payment.id), webhook_url=payment.webhook_url)
        body = self._webhook_payload(payment)
        status = await self.webhook_service.send(payment.webhook_url, body)
        await self.payments_service.mark_webhook_delivered(payment.id)
        log.info("webhook_delivered", http_status=status)

    @staticmethod
    def _webhook_payload(payment: Payment) -> dict[str, Any]:
        data = normalize(payment)
        data["event_type"] = "payment.processed"
        return data
