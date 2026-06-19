import pytest


@pytest.mark.asyncio
async def test_create_payment_returns_202(client):
    response = await client.post(
        "/api/v1/payments",
        json={"amount": "100.50", "currency": "USD"},
        headers={"Idempotency-Key": "key-create-1"},
    )
    assert response.status_code == 202
    data = response.json()["result"]
    assert data["status"] == "pending"
    assert data["amount"] == "100.5000"
    assert data["currency"] == "USD"
    assert data["idempotency_key"] == "key-create-1"


@pytest.mark.asyncio
async def test_get_payment_by_id(client):
    create = await client.post(
        "/api/v1/payments",
        json={
            "amount": "1",
            "currency": "EUR",
            "description": "test",
            "payment_metadata": {"order_id": "o-1"},
        },
        headers={"Idempotency-Key": "key-get-1"},
    )
    payment_id = create.json()["result"]["id"]
    got = await client.get(f"/api/v1/payments/{payment_id}")
    assert got.status_code == 200
    assert got.json()["result"]["id"] == payment_id


@pytest.mark.asyncio
async def test_get_payment_404(client):
    response = await client.get("/api/v1/payments/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_payments_filter_by_currency(client):
    await client.post(
        "/api/v1/payments",
        json={"amount": "1", "currency": "USD"},
        headers={"Idempotency-Key": "list-1"},
    )
    await client.post(
        "/api/v1/payments",
        json={"amount": "1", "currency": "RUB"},
        headers={"Idempotency-Key": "list-2"},
    )
    response = await client.get("/api/v1/payments?currency=USD")
    assert response.status_code == 200
    items = response.json()["result"]["items"]
    assert all(i["currency"] == "USD" for i in items)
    assert len(items) == 1


@pytest.mark.asyncio
async def test_validation_amount_must_be_positive(client):
    response = await client.post(
        "/api/v1/payments",
        json={"amount": "0", "currency": "USD"},
        headers={"Idempotency-Key": "v-1"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_unknown_currency(client):
    response = await client.post(
        "/api/v1/payments",
        json={"amount": "1", "currency": "XYZ"},
        headers={"Idempotency-Key": "v-2"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_missing_idempotency_key(client):
    response = await client.post("/api/v1/payments", json={"amount": "1", "currency": "USD"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_missing_api_key_returns_401(client):
    response = await client.post(
        "/api/v1/payments",
        json={"amount": "1", "currency": "USD"},
        headers={"Idempotency-Key": "v-3", "X-API-Key": ""},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_wrong_api_key_returns_401(client):
    response = await client.post(
        "/api/v1/payments",
        json={"amount": "1", "currency": "USD"},
        headers={"Idempotency-Key": "v-4", "X-API-Key": "nope"},
    )
    assert response.status_code == 401
