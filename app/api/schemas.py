from typing import Generic, TypeVar

from pydantic import BaseModel

TResult = TypeVar("TResult")
TError = TypeVar("TError")


class OkResponse(BaseModel, Generic[TResult]):
    result: TResult | None = None


class ErrorResponse(BaseModel, Generic[TError]):
    error: TError | None = None
