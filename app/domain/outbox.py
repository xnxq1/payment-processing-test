import dataclasses
import datetime
import enum
from typing import Any

from app.domain.base import BaseEntity

PAYMENT_CREATED_EVENT_TYPE = "payment.created"


class OutboxStatus(enum.StrEnum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclasses.dataclass
class OutboxEvent(BaseEntity):
    event_type: str
    topic: str
    payload: dict[str, Any]
    status: str
    retry_count: int
    last_error: str | None
    available_at: datetime.datetime
    published_at: datetime.datetime | None
