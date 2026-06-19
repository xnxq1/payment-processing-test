from uuid import uuid4

import httpx
import pytest
import respx

from app.domain.payments import PaymentStatus
from app.infra.http import HttpPermanentError, HttpRetryableError


async def _seed_payment(payments_repo, webhook_url: str | None = "https://example.test/hook"):
    return await payments_repo.insert(
        {
            "amount": "10.0000",
            "currency": "USD",
            "description": None,
            "payment_metadata": {},
            "status": PaymentStatus.PENDING.value,
            "idempotency_key": f"k-{uuid4()}",
            "webhook_url": webhook_url,
        }
    )


@pytest.fixture
def respx_mock():
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.mark.asyncio
async def test_succeeds_and_delivers_webhook_inline(
    process_payment_handler, payments_repo, monkeypatch, respx_mock
):
    monkeypatch.setattr(process_payment_handler.gateway, "charge", _noop)
    url = "https://example.test/hook"
    respx_mock.post(url).mock(return_value=httpx.Response(200))

    payment = await _seed_payment(payments_repo, webhook_url=url)
    await process_payment_handler.execute({"id": str(payment.id)})

    updated = await payments_repo.get_by_id(payment.id)
    assert updated.status == PaymentStatus.SUCCEEDED.value
    assert updated.processed_at is not None
    assert updated.webhook_delivered_at is not None


@pytest.mark.asyncio
async def test_already_delivered_webhook_is_not_resent(
    process_payment_handler, payments_repo, monkeypatch, respx_mock
):
    monkeypatch.setattr(process_payment_handler.gateway, "charge", _noop)
    url = "https://example.test/hook"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200))

    payment = await _seed_payment(payments_repo, webhook_url=url)
    await process_payment_handler.execute({"id": str(payment.id)})
    assert route.call_count == 1

    await process_payment_handler.execute({"id": str(payment.id)})
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_gateway_failure_marks_payment_failed(
    process_payment_handler, payments_repo, monkeypatch
):
    monkeypatch.setattr(process_payment_handler.gateway, "charge", _fail)
    payment = await _seed_payment(payments_repo, webhook_url=None)

    await process_payment_handler.execute({"id": str(payment.id)})

    failed = await payments_repo.get_by_id(payment.id)
    assert failed.status == PaymentStatus.FAILED.value
    assert failed.last_error == "gateway returned error"
    assert failed.processed_at is not None


@pytest.mark.asyncio
async def test_webhook_5xx_raises_delivery_error(
    process_payment_handler, payments_repo, monkeypatch, respx_mock
):
    monkeypatch.setattr(process_payment_handler.gateway, "charge", _noop)
    url = "https://example.test/hook"
    respx_mock.post(url).mock(return_value=httpx.Response(503))

    payment = await _seed_payment(payments_repo, webhook_url=url)
    with pytest.raises(HttpRetryableError):
        await process_payment_handler.execute({"id": str(payment.id)})

    updated = await payments_repo.get_by_id(payment.id)
    assert updated.status == PaymentStatus.SUCCEEDED.value
    assert updated.webhook_delivered_at is None


@pytest.mark.asyncio
async def test_webhook_4xx_raises_permanent_error(
    process_payment_handler, payments_repo, monkeypatch, respx_mock
):
    monkeypatch.setattr(process_payment_handler.gateway, "charge", _noop)
    url = "https://example.test/hook"
    respx_mock.post(url).mock(return_value=httpx.Response(400))

    payment = await _seed_payment(payments_repo, webhook_url=url)
    with pytest.raises(HttpPermanentError):
        await process_payment_handler.execute({"id": str(payment.id)})

    updated = await payments_repo.get_by_id(payment.id)
    assert updated.webhook_delivered_at is None


@pytest.mark.asyncio
async def test_resume_skips_gateway_when_succeeded(
    process_payment_handler, payments_repo, monkeypatch, respx_mock
):
    called = {"gateway": 0}

    async def fake_charge():
        called["gateway"] += 1

    monkeypatch.setattr(process_payment_handler.gateway, "charge", fake_charge)
    url = "https://example.test/hook"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200))

    payment = await _seed_payment(payments_repo, webhook_url=url)
    await payments_repo.update_by_id(payment.id, status=PaymentStatus.SUCCEEDED.value)

    await process_payment_handler.execute({"id": str(payment.id)})

    assert called["gateway"] == 0
    assert route.called
    refetched = await payments_repo.get_by_id(payment.id)
    assert refetched.webhook_delivered_at is not None


@pytest.mark.asyncio
async def test_webhook_signature_present(
    process_payment_handler, payments_repo, monkeypatch, respx_mock, settings_obj
):
    monkeypatch.setattr(process_payment_handler.gateway, "charge", _noop)
    url = "https://example.test/hook"

    captured = {}

    def _capture(request: httpx.Request):
        captured["signature"] = request.headers.get("x-signature")
        captured["body"] = request.content
        return httpx.Response(200)

    respx_mock.post(url).mock(side_effect=_capture)

    payment = await _seed_payment(payments_repo, webhook_url=url)
    await process_payment_handler.execute({"id": str(payment.id)})

    from app.logic.webhooks.service import WebhookService

    assert captured["signature"]
    assert WebhookService.verify(
        captured["body"], settings_obj.webhook_secret, captured["signature"]
    )


async def _noop():
    return True


async def _fail():
    return False
