from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.outbox import PAYMENT_CREATED_EVENT_TYPE, OutboxStatus


@pytest.mark.asyncio
async def test_lock_pending_skips_future_available_at(outbox_repo, settings_obj):
    payment_id = str(uuid4())
    await outbox_repo.insert(
        {
            "event_type": PAYMENT_CREATED_EVENT_TYPE,
            "topic": settings_obj.topic_payments_new,
            "payload": {"id": payment_id},
            "status": OutboxStatus.PENDING.value,
            "available_at": datetime.now(tz=UTC) + timedelta(minutes=10),
        }
    )
    pending = await outbox_repo.lock_pending_batch(10)
    assert pending == []


@pytest.mark.asyncio
async def test_lock_pending_picks_ready_events(outbox_repo, settings_obj):
    payment_id = str(uuid4())
    await outbox_repo.insert(
        {
            "event_type": PAYMENT_CREATED_EVENT_TYPE,
            "topic": settings_obj.topic_payments_new,
            "payload": {"id": payment_id},
            "status": OutboxStatus.PENDING.value,
        }
    )
    ready = await outbox_repo.lock_pending_batch(10)
    assert len(ready) == 1
    await outbox_repo.mark_published(ready[0].id)
    after = await outbox_repo.lock_pending_batch(10)
    assert after == []


@pytest.mark.asyncio
async def test_mark_failed_non_terminal_keeps_pending(outbox_repo, settings_obj):
    payment_id = str(uuid4())
    event = await outbox_repo.insert(
        {
            "event_type": PAYMENT_CREATED_EVENT_TYPE,
            "topic": settings_obj.topic_payments_new,
            "payload": {"id": payment_id},
            "status": OutboxStatus.PENDING.value,
        }
    )
    future = datetime.now(tz=UTC) + timedelta(seconds=60)
    await outbox_repo.mark_failed(event.id, "boom", 1, future, terminal=False)
    again = await outbox_repo.search_first(id=event.id)
    assert again.status == OutboxStatus.PENDING.value
    assert again.retry_count == 1
    assert again.last_error == "boom"
