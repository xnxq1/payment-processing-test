from sqlalchemy import TIMESTAMP, Column, MetaData, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

now_at_utc = text("(now() at time zone 'utc')")
create_uuid = text("gen_random_uuid()")
metadata = MetaData()


def get_base_fields() -> tuple:
    return (
        Column("id", PG_UUID(as_uuid=True), primary_key=True, server_default=create_uuid),
        Column("created", TIMESTAMP(timezone=True), server_default=now_at_utc, nullable=False),
        Column("updated", TIMESTAMP(timezone=True), server_default=now_at_utc, nullable=False),
    )
