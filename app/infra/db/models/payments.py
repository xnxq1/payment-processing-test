from sqlalchemy import NUMERIC, TIMESTAMP, Column, Index, String, Table, text
from sqlalchemy.dialects.postgresql import JSONB

from app.infra.db.utils import get_base_fields, metadata

payments = Table(
    "payments",
    metadata,
    *get_base_fields(),
    Column("amount", NUMERIC(precision=18, scale=4), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("description", String, nullable=True),
    Column("payment_metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("status", String(16), nullable=False, server_default="pending"),
    Column("idempotency_key", String, nullable=False),
    Column("webhook_url", String, nullable=True),
    Column("last_error", String, nullable=True),
    Column("processed_at", TIMESTAMP(timezone=True), nullable=True),
    Column("webhook_delivered_at", TIMESTAMP(timezone=True), nullable=True),
    Index("payments_idempotency_key_uq", "idempotency_key", unique=True),
    Index("payments_status_idx", "status"),
    Index("payments_created_idx", "created"),
)
