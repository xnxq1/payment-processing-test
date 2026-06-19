from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status

from app.api.auth import require_api_key
from app.api.payments.schemas import CreatePaymentRequest, PaymentListResponse, PaymentResponse
from app.api.schemas import OkResponse
from app.logic.handlers.payments import CreatePaymentHandler, GetPaymentHandler, ListPaymentsHandler


class PaymentsRouter:
    def __init__(
        self,
        create_payment_handler: CreatePaymentHandler,
        get_payment_handler: GetPaymentHandler,
        list_payments_handler: ListPaymentsHandler,
    ) -> None:
        self.create_payment_handler = create_payment_handler
        self.get_payment_handler = get_payment_handler
        self.list_payments_handler = list_payments_handler
        self.router = APIRouter(
            prefix="/api/v1/payments", tags=["Payments"], dependencies=[Depends(require_api_key)]
        )
        self.register_routes()

    def register_routes(self) -> None:
        self.router.post("", status_code=status.HTTP_202_ACCEPTED)(self.create_payment)
        self.router.get("/{payment_id}")(self.get_payment)
        self.router.get("")(self.list_payments)

    async def create_payment(
        self,
        payload: CreatePaymentRequest,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    ) -> OkResponse[PaymentResponse]:
        payment = await self.create_payment_handler.execute(
            payload.model_dump(), idempotency_key=idempotency_key
        )
        return OkResponse(result=PaymentResponse.model_validate(payment))

    async def get_payment(self, payment_id: UUID) -> OkResponse[PaymentResponse]:
        payment = await self.get_payment_handler.execute(payment_id)
        return OkResponse(result=PaymentResponse.model_validate(payment))

    async def list_payments(
        self,
        status_filter: str | None = Query(default=None, alias="status"),
        currency: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> OkResponse[PaymentListResponse]:
        items = await self.list_payments_handler.execute(
            status=status_filter, currency=currency, limit=limit, offset=offset
        )
        return OkResponse(
            result=PaymentListResponse(
                items=[PaymentResponse.model_validate(p) for p in items], limit=limit, offset=offset
            )
        )
