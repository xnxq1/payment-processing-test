import dataclasses
import datetime
from decimal import Decimal
from typing import Any, ParamSpec, TypeVar
from uuid import UUID

from app.infra.logging import get_logger

logger = get_logger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def _normalize_value(value):
    if isinstance(value, Decimal):
        return f"{value:.4f}"
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _normalize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_value(v) for v in value]
    return value


def normalize(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and (not isinstance(value, type)):
        value = dataclasses.asdict(value)
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, dict):
        return {k: _normalize_value(v) for k, v in value.items()}
    return _normalize_value(value)


def exponential_backoff_seconds(retry_count: int, base: float = 1.0, factor: float = 5.0) -> float:
    if retry_count <= 0:
        return base
    return base * factor ** (retry_count - 1)
