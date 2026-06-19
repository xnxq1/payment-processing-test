from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.domain.outbox import PAYMENT_CREATED_EVENT_TYPE, OutboxStatus
from app.domain.payments import Payment, PaymentStatus
from app.infra.config import settings
from app.infra.db.repos.outbox import OutboxRepo
from app.infra.db.repos.payments import PaymentsRepo
from app.infra.redis.lock import RedisLocks
from app.logic.payments.exceptions import IdempotencyKeyConflictError, PaymentNotFoundError
from app.logic.payments.models import CreatePaymentDict
from app.logic.utils import normalize


class PaymentsService:
    def __init__(
        self,
        payments_repo: PaymentsRepo,
        outbox_repo: OutboxRepo,
        locks: RedisLocks,
    ):
        self.payments_repo = payments_repo
        self.outbox_repo = outbox_repo
        self.locks = locks

    async def create(self, payload: CreatePaymentDict, idempotency_key: str) -> Payment:
        async with self.locks.acquire(f"idempotency:{idempotency_key}", timeout=30):
            async with self.payments_repo.transaction():
                existing = await self.payments_repo.search_first(idempotency_key=idempotency_key)
                if existing is not None:
                    if not self._payload_matches(existing, payload):
                        raise IdempotencyKeyConflictError(
                            "Idempotency-Key reused with a different request payload"
                        )
                    return existing
                payment = await self.payments_repo.insert(
                    {
                        "amount": payload["amount"],
                        "currency": payload["currency"],
                        "description": payload.get("description"),
                        "payment_metadata": payload.get("payment_metadata") or {},
                        "status": PaymentStatus.PENDING.value,
                        "idempotency_key": idempotency_key,
                        "webhook_url": payload.get("webhook_url"),
                    }
                )
                await self.outbox_repo.insert(
                    {
                        "event_type": PAYMENT_CREATED_EVENT_TYPE,
                        "topic": settings.topic_payments_new,
                        "payload": normalize(payment),
                        "status": OutboxStatus.PENDING.value,
                    }
                )
                return payment

    async def get(self, payment_id: UUID) -> Payment:
        payment = await self.payments_repo.get_by_id(payment_id)
        if payment is None:
            raise PaymentNotFoundError(f"payment {payment_id} not found")
        return payment

    async def list(
        self,
        status: str | None = None,
        currency: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Payment]:
        filters: dict[str, Any] = {}
        if status:
            filters["status"] = status
        if currency:
            filters["currency"] = currency
        return await self.payments_repo.search(limit=limit, offset=offset, **filters)

    async def mark_succeeded(self, payment_id: UUID) -> Payment:
        return await self.payments_repo.update_by_id(
            payment_id,
            status=PaymentStatus.SUCCEEDED.value,
            processed_at=datetime.now(tz=UTC),
            last_error=None,
        )

    async def mark_failed(self, payment_id: UUID, error: str) -> Payment:
        return await self.payments_repo.update_by_id(
            payment_id,
            status=PaymentStatus.FAILED.value,
            processed_at=datetime.now(tz=UTC),
            last_error=error,
        )

    async def mark_webhook_delivered(self, payment_id: UUID) -> Payment:
        return await self.payments_repo.update_by_id(
            payment_id, webhook_delivered_at=datetime.now(tz=UTC)
        )

    @staticmethod
    def _payload_matches(payment: Payment, payload: CreatePaymentDict) -> bool:
        return (
            payment.amount == payload["amount"]
            and payment.currency == payload["currency"]
            and ((payment.description or None) == (payload.get("description") or None))
            and ((payment.payment_metadata or {}) == (payload.get("payment_metadata") or {}))
            and ((payment.webhook_url or None) == (payload.get("webhook_url") or None))
        )
