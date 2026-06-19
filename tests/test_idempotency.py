import pytest


@pytest.mark.asyncio
async def test_same_key_same_payload_returns_same_payment(client):
    body = {"amount": "10", "currency": "USD", "description": "buy"}
    first = await client.post("/api/v1/payments", json=body, headers={"Idempotency-Key": "idem-1"})
    assert first.status_code == 202
    second = await client.post("/api/v1/payments", json=body, headers={"Idempotency-Key": "idem-1"})
    assert second.status_code == 200
    assert first.json()["result"]["id"] == second.json()["result"]["id"]


@pytest.mark.asyncio
async def test_same_key_different_payload_returns_409(client):
    await client.post(
        "/api/v1/payments",
        json={"amount": "10", "currency": "USD"},
        headers={"Idempotency-Key": "idem-2"},
    )
    conflict = await client.post(
        "/api/v1/payments",
        json={"amount": "20", "currency": "USD"},
        headers={"Idempotency-Key": "idem-2"},
    )
    assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_different_keys_create_different_payments(client):
    body = {"amount": "10", "currency": "USD"}
    a = await client.post("/api/v1/payments", json=body, headers={"Idempotency-Key": "k-a"})
    b = await client.post("/api/v1/payments", json=body, headers={"Idempotency-Key": "k-b"})
    assert a.json()["result"]["id"] != b.json()["result"]["id"]


@pytest.mark.asyncio
async def test_idempotent_create_produces_single_outbox_event(client, outbox_repo):
    body = {"amount": "10", "currency": "USD"}
    for _ in range(3):
        await client.post("/api/v1/payments", json=body, headers={"Idempotency-Key": "idem-3"})
    events = await outbox_repo.search()
    assert len(events) == 1
