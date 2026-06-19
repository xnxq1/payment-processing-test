import asyncio
import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def postgres_container():
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver=None) as c:
        yield c


@pytest.fixture(scope="session")
def redis_container():
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def _env_setup(postgres_container, redis_container):
    os.environ["POSTGRES_HOST"] = postgres_container.get_container_host_ip()
    os.environ["POSTGRES_PORT"] = str(postgres_container.get_exposed_port(5432))
    os.environ["POSTGRES_USER"] = postgres_container.username
    os.environ["POSTGRES_PASSWORD"] = postgres_container.password
    os.environ["POSTGRES_DB"] = postgres_container.dbname
    os.environ["REDIS_HOST"] = redis_container.get_container_host_ip()
    os.environ["REDIS_PORT"] = str(redis_container.get_exposed_port(6379))
    os.environ["API_KEY"] = "test-api-key"
    os.environ["WEBHOOK_SECRET"] = "test-webhook-secret"
    os.environ["LOG_LEVEL"] = "WARNING"
    os.environ["JSON_LOGS"] = "false"
    os.environ["PAYMENT_PROCESSING_MIN_SECONDS"] = "0"
    os.environ["PAYMENT_PROCESSING_MAX_SECONDS"] = "0"
    os.environ["RABBITMQ_URL"] = "amqp://guest:guest@rabbitmq:5672/"
    yield


@pytest_asyncio.fixture(scope="session")
async def container(_env_setup):
    from dishka import make_async_container

    from app.di import build_providers

    c = make_async_container(*build_providers())
    yield c
    await c.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_schema(container):
    from sqlalchemy.ext.asyncio import AsyncEngine

    from app.infra.db.utils import metadata

    engine = await container.get(AsyncEngine)
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
    yield


@pytest_asyncio.fixture(autouse=True)
async def _truncate_tables(_create_schema, container):
    from sqlalchemy.ext.asyncio import AsyncEngine

    engine = await container.get(AsyncEngine)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE payments, outbox RESTART IDENTITY CASCADE"))
    yield


@pytest_asyncio.fixture
async def app_builder(container):
    from app.main import AppBuilder

    return await container.get(AppBuilder)


@pytest_asyncio.fixture
async def client(app_builder) -> AsyncGenerator[AsyncClient, None]:
    settings = app_builder.settings
    async with AsyncClient(
        transport=ASGITransport(app=app_builder.create_app()),
        base_url="http://test",
        headers={"X-API-Key": settings.api_key},
        follow_redirects=True,
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def payments_repo(container):
    from app.infra.db.repos.payments import PaymentsRepo

    return await container.get(PaymentsRepo)


@pytest_asyncio.fixture
async def outbox_repo(container):
    from app.infra.db.repos.outbox import OutboxRepo

    return await container.get(OutboxRepo)


@pytest_asyncio.fixture
async def process_payment_handler(container):
    from app.logic.handlers.processing import ProcessPaymentHandler

    return await container.get(ProcessPaymentHandler)


@pytest_asyncio.fixture
async def settings_obj(container):
    from app.infra.config import Settings

    return await container.get(Settings)
