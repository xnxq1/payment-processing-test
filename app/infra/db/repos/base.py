import contextvars
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import column, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.infra.db.repos.exceptions import handle_db_errors

_conn_ctx: contextvars.ContextVar[AsyncConnection | None] = contextvars.ContextVar(
    "db_conn", default=None
)


class BaseRepo:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    @asynccontextmanager
    async def connection(self):
        existing = _conn_ctx.get()
        if existing is not None:
            yield existing
            return
        async with self.engine.begin() as conn:
            token = _conn_ctx.set(conn)
            try:
                yield conn
            finally:
                _conn_ctx.reset(token)

    @asynccontextmanager
    async def transaction(self):
        existing = _conn_ctx.get()
        if existing is not None and existing.in_transaction():
            yield existing
            return
        async with self.connection() as conn:
            if conn.in_transaction():
                yield conn
            else:
                async with conn.begin():
                    yield conn

    async def execute(self, query):
        async with self.connection() as conn:
            return await conn.execute(query)

    async def fetch(self, query) -> list[dict]:
        async with self.connection() as conn:
            result = await conn.execute(query)
            return [dict(r._mapping) for r in result.fetchall()]

    async def fetchrow(self, query) -> dict | None:
        async with self.connection() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            return dict(row._mapping) if row else None


class EntityRepo(BaseRepo):
    db_entity = None
    domain_entity = None

    def _filter_expression(self, name: str, value, table):
        if name in table.columns:
            return column(name).__eq__(value)
        parts = name.split("_")
        sign = parts.pop()
        col_name = "_".join(parts)
        col = column(col_name)
        if sign in {"lt", "le", "gt", "ge", "ne"}:
            return getattr(col, f"__{sign}__")(value)
        if sign == "in":
            return col.in_(value)
        if sign == "notin":
            return ~col.in_(value)
        if sign == "is":
            return col.is_(value)
        if sign == "isnot":
            return col.is_not(value)
        if sign == "like":
            return col.like(value)
        if sign == "ilike":
            return col.ilike(value)
        raise ValueError(f"Unknown filter: {name}")

    def _apply_filters(self, query, **filters):
        for name, value in filters.items():
            query = query.where(self._filter_expression(name, value, query))
        return query

    def _row_to_entity(self, row: dict):
        return self.domain_entity(**row) if self.domain_entity else row

    @handle_db_errors
    async def search(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        order_by: str | None = "id",
        **filters,
    ) -> list:
        query = self._apply_filters(select(self.db_entity), **filters)
        if order_by:
            query = query.order_by(self.db_entity.c[order_by])
        if limit is not None:
            query = query.limit(limit)
        if offset:
            query = query.offset(offset)
        rows = await self.fetch(query)
        return [self._row_to_entity(r) for r in rows]

    @handle_db_errors
    async def search_first(self, **filters):
        rows = await self.search(limit=1, **filters)
        return rows[0] if rows else None

    @handle_db_errors
    async def insert(self, payload: dict):
        query = self.db_entity.insert().values(payload).returning(self.db_entity)
        row = await self.fetchrow(query)
        return self._row_to_entity(row) if row else None

    @handle_db_errors
    async def get_by_id(self, entity_id: UUID):
        return await self.search_first(id=entity_id)

    @handle_db_errors
    async def update_by_id(self, entity_id: UUID, **payload):
        query = (
            self.db_entity.update()
            .where(self.db_entity.c.id == entity_id)
            .values(updated=datetime.now(tz=UTC), **payload)
            .returning(self.db_entity)
        )
        row = await self.fetchrow(query)
        return self._row_to_entity(row) if row else None
