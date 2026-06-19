import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.payments import Currency


class CreatePaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    currency: Currency
    description: str | None = Field(default=None, max_length=255)
    payment_metadata: dict[str, Any] = Field(default_factory=dict)
    webhook_url: str | None = Field(default=None, max_length=2048)

    @field_validator("webhook_url")
    @classmethod
    def _validate_url(cls, v: str | None) -> str | None:
        if v and (not (v.startswith("http://") or v.startswith("https://"))):
            raise ValueError("webhook_url must start with http:// or https://")
        return v


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    amount: Decimal
    currency: str
    description: str | None
    payment_metadata: dict[str, Any]
    status: str
    idempotency_key: str
    webhook_url: str | None
    last_error: str | None
    created: datetime.datetime
    updated: datetime.datetime
    processed_at: datetime.datetime | None


class PaymentListResponse(BaseModel):
    items: list[PaymentResponse]
    limit: int
    offset: int
