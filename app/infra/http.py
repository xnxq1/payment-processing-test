from typing import Any

import httpx

from app.infra.logging import get_logger

logger = get_logger(__name__)

RETRYABLE_STATUSES = {408, 425, 429}


class HttpRetryableError(Exception):
    """5xx / 408 / 425 / 429 / network error — есть смысл повторять."""


class HttpPermanentError(Exception):
    """4xx (кроме RETRYABLE_STATUSES) — повтор бесполезен."""


class HttpClient:
    def __init__(self, timeout: float = 5.0, max_connections: int = 100) -> None:
        self._client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_connections,
            ),
        )

    async def post(
        self,
        url: str,
        *,
        content: bytes | None = None,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        try:
            response = await self._client.post(url, content=content, json=json, headers=headers)
        except httpx.RequestError as e:
            raise HttpRetryableError(f"network error: {e}") from e
        return self._raise_for_status(response)

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> httpx.Response:
        code = response.status_code
        if 200 <= code < 300:
            return response
        if code in RETRYABLE_STATUSES or code >= 500:
            raise HttpRetryableError(f"retryable status {code}: {response.text[:200]}")
        raise HttpPermanentError(f"non-retryable status {code}: {response.text[:200]}")

    async def close(self) -> None:
        await self._client.aclose()
