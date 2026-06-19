from datetime import UTC
from decimal import Decimal

from app.logic.utils import exponential_backoff_seconds, normalize
from app.logic.webhooks.service import WebhookService


def test_normalize_decimal_uuid_datetime():
    from datetime import datetime
    from uuid import UUID

    payload = {
        "amount": Decimal("123.456789"),
        "id": UUID("00000000-0000-0000-0000-000000000001"),
        "ts": datetime(2026, 1, 1, tzinfo=UTC),
        "nested": {"x": Decimal("0.0001")},
        "items": [Decimal("1")],
    }
    out = normalize(payload)
    assert out["amount"] == "123.4568"
    assert out["id"] == "00000000-0000-0000-0000-000000000001"
    assert out["ts"] == "2026-01-01T00:00:00+00:00"
    assert out["nested"] == {"x": "0.0001"}
    assert out["items"] == ["1.0000"]


def test_exponential_backoff_progression():
    assert exponential_backoff_seconds(1) == 1.0
    assert exponential_backoff_seconds(2) == 5.0
    assert exponential_backoff_seconds(3) == 25.0


def test_hmac_sign_and_verify_roundtrip():
    body = b'{"event_type":"payment.processed","id":"x"}'
    signature = WebhookService.sign(body, "my-secret")
    assert WebhookService.verify(body, "my-secret", signature) is True
    assert WebhookService.verify(body, "my-secret", "ff" * 32) is False
    assert WebhookService.verify(body + b"x", "my-secret", signature) is False
