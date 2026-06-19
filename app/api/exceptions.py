from collections.abc import Awaitable, Callable
from functools import partial

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse

from app.api.schemas import ErrorResponse
from app.infra.db.repos.exceptions import (
    DatabaseError,
    EntityAlreadyExistsError,
    EntityNotFoundError,
)
from app.logic.payments.exceptions import IdempotencyKeyConflictError, PaymentNotFoundError


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(PaymentNotFoundError, handler(404))
    app.add_exception_handler(EntityNotFoundError, handler(404))
    app.add_exception_handler(IdempotencyKeyConflictError, handler(409))
    app.add_exception_handler(EntityAlreadyExistsError, handler(409))
    app.add_exception_handler(DatabaseError, handler(500))
    app.add_exception_handler(RequestValidationError, pydantic_handler)
    app.add_exception_handler(Exception, handler(500))


def handler(status_code: int) -> Callable[..., Awaitable[ORJSONResponse]]:
    return partial(exception_handler, status_code=status_code)


def exception_handler(request: Request, exc: Exception, status_code: int) -> ORJSONResponse:
    return ORJSONResponse(
        content=ErrorResponse(error=str(exc)).model_dump(), status_code=status_code
    )


def pydantic_handler(request: Request, exc: RequestValidationError) -> ORJSONResponse:
    errors = [e["msg"] for e in exc.errors()]
    return ORJSONResponse(content=ErrorResponse(error=errors).model_dump(), status_code=422)
