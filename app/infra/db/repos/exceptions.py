import re
from functools import wraps

from sqlalchemy.exc import DBAPIError, IntegrityError, NoResultFound, SQLAlchemyError

from app.infra.logging import get_logger


class EntityNotFoundError(Exception):
    def __init__(self, entity_name: str, entity_id: str):
        self.entity_name = entity_name
        self.entity_id = entity_id
        super().__init__(f"{entity_name} with id={entity_id} not found")


class EntityAlreadyExistsError(Exception):
    def __init__(self, entity_name: str, field: str, value: str):
        self.entity_name = entity_name
        self.field = field
        self.value = value
        super().__init__(f"{entity_name} with {field}={value} already exists")


class DatabaseError(Exception):
    def __init__(self, message: str, original_error: Exception | None = None):
        self.original_error = original_error
        super().__init__(message)


logger = get_logger(__name__)


def map_db_error(error: Exception, entity_name: str) -> Exception:
    if isinstance(error, IntegrityError):
        msg = str(error.orig).lower()
        if "unique constraint" in msg or "duplicate key" in msg:
            match = re.search("Key \\((\\w+)\\)=\\((.+?)\\)", str(error.orig))
            if match:
                return EntityAlreadyExistsError(entity_name, match.group(1), match.group(2))
            return EntityAlreadyExistsError(entity_name, "field", "value")
        return DatabaseError(f"Data integrity violation: {error.orig}")
    if isinstance(error, NoResultFound):
        return EntityNotFoundError(entity_name, "unknown")
    if isinstance(error, DBAPIError):
        return DatabaseError(f"Database connection error: {error.orig}")
    if isinstance(error, SQLAlchemyError):
        return DatabaseError(f"Database error: {error}")
    return DatabaseError(f"Unexpected database error: {error}", error)


def handle_db_errors(func):

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        entity_name = self.db_entity.name.capitalize().rstrip("s")
        try:
            return await func(self, *args, **kwargs)
        except (EntityNotFoundError, EntityAlreadyExistsError, DatabaseError):
            raise
        except Exception as e:
            mapped = map_db_error(e, entity_name)
            logger.error("db_error", method=func.__name__, entity=entity_name, error=str(e))
            raise mapped from e

    return wrapper
