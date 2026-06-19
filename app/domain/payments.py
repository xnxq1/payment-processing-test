import dataclasses
import datetime
import enum
from decimal import Decimal
from typing import Any

from app.domain.base import BaseEntity


class PaymentStatus(enum.StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Currency(enum.StrEnum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


@dataclasses.dataclass
class Payment(BaseEntity):
    amount: Decimal
    currency: str
    description: str | None
    payment_metadata: dict[str, Any]
    status: str
    idempotency_key: str
    webhook_url: str | None
    last_error: str | None
    processed_at: datetime.datetime | None
    webhook_delivered_at: datetime.datetime | None
