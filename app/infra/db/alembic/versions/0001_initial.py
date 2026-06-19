from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.create_table(
        "payments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("(now() at time zone 'utc')"),
        ),
        sa.Column(
            "updated",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("(now() at time zone 'utc')"),
        ),
        sa.Column("amount", sa.NUMERIC(precision=18, scale=4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "payment_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("webhook_url", sa.String(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("webhook_delivered_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("payments_idempotency_key_uq", "payments", ["idempotency_key"], unique=True)
    op.create_index("payments_status_idx", "payments", ["status"])
    op.create_index("payments_created_idx", "payments", ["created"])
    op.create_table(
        "outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("(now() at time zone 'utc')"),
        ),
        sa.Column(
            "updated",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("(now() at time zone 'utc')"),
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("topic", sa.String(128), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "retry_count", sa.NUMERIC(precision=4, scale=0), nullable=False, server_default="0"
        ),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column(
            "available_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("(now() at time zone 'utc')"),
        ),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("outbox_pending_available_idx", "outbox", ["status", "available_at"])


def downgrade() -> None:
    op.drop_index("outbox_pending_available_idx", table_name="outbox")
    op.drop_table("outbox")
    op.drop_index("payments_created_idx", table_name="payments")
    op.drop_index("payments_status_idx", table_name="payments")
    op.drop_index("payments_idempotency_key_uq", table_name="payments")
    op.drop_table("payments")
