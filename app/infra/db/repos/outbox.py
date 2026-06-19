from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, select

from app.domain.outbox import OutboxEvent, OutboxStatus
from app.infra.db.models import outbox
from app.infra.db.repos.base import EntityRepo
from app.infra.db.repos.exceptions import handle_db_errors


class OutboxRepo(EntityRepo):
    db_entity = outbox
    domain_entity = OutboxEvent

    @handle_db_errors
    async def lock_pending_batch(self, limit: int) -> list[OutboxEvent]:
        query = (
            select(outbox)
            .where(
                and_(
                    outbox.c.status == OutboxStatus.PENDING.value,
                    outbox.c.available_at <= datetime.now(tz=UTC),
                )
            )
            .order_by(outbox.c.available_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = await self.fetch(query)
        return [self._row_to_entity(r) for r in rows]

    @handle_db_errors
    async def mark_published(self, event_id: UUID) -> None:
        query = (
            outbox.update()
            .where(outbox.c.id == event_id)
            .values(
                status=OutboxStatus.PUBLISHED.value,
                published_at=datetime.now(tz=UTC),
                updated=datetime.now(tz=UTC),
            )
        )
        await self.execute(query)

    @handle_db_errors
    async def mark_failed(
        self,
        event_id: UUID,
        last_error: str,
        retry_count: int,
        available_at: datetime,
        terminal: bool,
    ) -> None:
        query = (
            outbox.update()
            .where(outbox.c.id == event_id)
            .values(
                status=OutboxStatus.FAILED.value if terminal else OutboxStatus.PENDING.value,
                retry_count=retry_count,
                last_error=last_error,
                available_at=available_at,
                updated=datetime.now(tz=UTC),
            )
        )
        await self.execute(query)
