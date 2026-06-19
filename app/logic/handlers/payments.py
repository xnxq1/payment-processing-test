from uuid import UUID

from app.domain.payments import Payment
from app.logic.handlers.base import BaseHandler
from app.logic.payments.models import CreatePaymentDict
from app.logic.payments.service import PaymentsService


class CreatePaymentHandler(BaseHandler):
    def __init__(self, payments_service: PaymentsService) -> None:
        self.payments_service = payments_service

    async def execute(self, payload: CreatePaymentDict, idempotency_key: str) -> Payment:
        return await self.payments_service.create(payload, idempotency_key=idempotency_key)


class GetPaymentHandler(BaseHandler):
    def __init__(self, payments_service: PaymentsService) -> None:
        self.payments_service = payments_service

    async def execute(self, payment_id: UUID) -> Payment:
        return await self.payments_service.get(payment_id)


class ListPaymentsHandler(BaseHandler):
    def __init__(self, payments_service: PaymentsService) -> None:
        self.payments_service = payments_service

    async def execute(
        self,
        status: str | None = None,
        currency: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Payment]:
        return await self.payments_service.list(
            status=status, currency=currency, limit=limit, offset=offset
        )
