from decimal import Decimal
from typing import Any, TypedDict


class CreatePaymentDict(TypedDict, total=False):
    amount: Decimal
    currency: str
    description: str | None
    payment_metadata: dict[str, Any]
    webhook_url: str | None
