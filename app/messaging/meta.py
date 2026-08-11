"""Small asynchronous client for the Meta WhatsApp Cloud API.

Only transport concerns live here: phone normalization, payload construction,
HTTP submission, and conversion of Meta error responses into ``MetaAPIError``.
"""

from __future__ import annotations

import logging
from typing import Any
import httpx

from ..config import get_settings
from ..meta_credentials import get_meta_credentials

settings = get_settings()
logger = logging.getLogger("app.messaging.meta")


class MetaAPIError(RuntimeError):
    """Raised when Meta configuration is missing or the Graph API rejects a call."""

    pass


class MetaWhatsAppClient:
    """Send text and approved template messages through WhatsApp Cloud API."""

    def __init__(self) -> None:
        """Build the Graph API endpoint and authorization headers."""
        credentials = get_meta_credentials()
        self.url = (
            f"https://graph.facebook.com/{settings.meta_graph_api_version}/"
            f"{credentials.phone_number_id}/messages"
        )
        self.headers = {
            "Authorization": f"Bearer {credentials.access_token}",
            "Content-Type": "application/json",
        }

    async def _send(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a message payload and return Meta's decoded JSON response."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.url, headers=self.headers, json=payload)
        try:
            data = response.json()
        except ValueError:
            data = {"raw": response.text}
        if response.is_error:
            error = data.get("error") if isinstance(data, dict) else None
            if isinstance(error, dict) and error.get("code") == 190:
                logger.error(
                    "Meta authentication failed; verify that ACCESS_TOKEN in meta_secrets.py is valid, unexpired, and belongs to the same app/WABA as PHONE_NUMBER_ID"
                )
            logger.error(
                "Meta API error status=%s payload=%s response=%s",
                response.status_code, payload, data,
            )
            if isinstance(error, dict) and error.get("code") == 190:
                raise MetaAPIError(
                    "Meta authentication failed (code 190). Check ACCESS_TOKEN, "
                    "PHONE_NUMBER_ID in meta_secrets.py, app/WABA ownership, token expiry, and required permissions."
                )
            raise MetaAPIError(f"Meta API error {response.status_code}: {data}")
        return data

    async def send_text(self, to: str, body: str, reply_to_message_id: str | None = None) -> dict[str, Any]:
        """Send free-form text, optionally as a reply to an inbound message."""
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalize_meta_phone(to),
            "type": "text",
            "text": {"preview_url": False, "body": body},
        }
        if reply_to_message_id and not reply_to_message_id.startswith("sim-"):
            payload["context"] = {"message_id": reply_to_message_id}
            try:
                return await self._send(payload)
            except MetaAPIError as exc:
                logger.warning(
                    "send_text with reply context failed (%s), retrying without context", exc
                )
                payload.pop("context", None)
        return await self._send(payload)

    async def send_template(
        self,
        to: str,
        template_name: str = "hello_world",
        language_code: str = "en_US",
        body_params: list[str] | None = None,
    ) -> dict[str, Any]:
        """Send an approved template with ordered body text parameters."""
        if not template_name.strip():
            raise MetaAPIError("Template name cannot be empty")
        if not language_code.strip():
            raise MetaAPIError("Template language code cannot be empty")
        payload = {
            "messaging_product": "whatsapp",
            "to": normalize_meta_phone(to),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }
        if body_params:
            payload["template"]["components"] = [
                {"type": "body", "parameters": [{"type": "text", "text": p} for p in body_params]}
            ]
        return await self._send(payload)


def normalize_meta_phone(phone: str) -> str:
    """Normalize international and Egyptian local numbers to Meta's digit format."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    # Local Egyptian format (e.g. "01090032188") -> country code 20 + drop the leading 0.
    if digits.startswith("0") and len(digits) == 11:
        digits = "20" + digits[1:]
    return digits
