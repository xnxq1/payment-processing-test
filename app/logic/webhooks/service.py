import hashlib
import hmac
import json
from typing import Any

from app.infra.http import HttpClient
from app.infra.logging import get_logger

logger = get_logger(__name__)


class WebhookService:
    def __init__(self, http_client: HttpClient, secret: str) -> None:
        self.http_client = http_client
        self.secret = secret

    @staticmethod
    def sign(body: bytes, secret: str) -> str:
        return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    @staticmethod
    def verify(body: bytes, secret: str, signature: str) -> bool:
        expected = WebhookService.sign(body, secret)
        return hmac.compare_digest(expected, signature)

    async def send(self, url: str, payload: dict[str, Any]) -> int:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Signature": self.sign(body, self.secret),
            "X-Event-Type": payload.get("event_type", "payment.processed"),
        }
        response = await self.http_client.post(url, content=body, headers=headers)
        return response.status_code
