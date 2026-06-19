from sqlalchemy import NUMERIC, TIMESTAMP, Column, Index, String, Table, text
from sqlalchemy.dialects.postgresql import JSONB

from app.infra.db.utils import get_base_fields, metadata, now_at_utc

outbox = Table(
    "outbox",
    metadata,
    *get_base_fields(),
    Column("event_type", String(64), nullable=False),
    Column("topic", String(128), nullable=False),
    Column("payload", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("status", String(16), nullable=False, server_default="pending"),
    Column("retry_count", NUMERIC(precision=4, scale=0), nullable=False, server_default="0"),
    Column("last_error", String, nullable=True),
    Column("available_at", TIMESTAMP(timezone=True), nullable=False, server_default=now_at_utc),
    Column("published_at", TIMESTAMP(timezone=True), nullable=True),
    Index("outbox_pending_available_idx", "status", "available_at"),
)
