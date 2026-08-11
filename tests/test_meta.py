"""Tests for Meta payload construction, normalization, and webhook helpers."""

import asyncio
import hashlib
import hmac

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import extract_message_events, extract_status_events, record_status_events, verify_meta_signature
from app.messaging import meta
from app.messaging.meta import MetaAPIError, MetaWhatsAppClient, normalize_meta_phone
from app.meta_credentials import MetaCredentials
from app.models import Contact, Message


def fake_meta_credentials(**overrides):
    """Build a MetaCredentials instance for tests, with sane defaults."""
    values = {
        "access_token": "token",
        "phone_number_id": "phone-id",
        "waba_id": "waba-id",
        "webhook_verify_token": "verify-token",
    }
    values.update(overrides)
    return MetaCredentials(**values)


def make_empty_db():
    """Create an isolated database for webhook status tests."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_normalize_egyptian_phone():
    """Egyptian local numbers are converted to international digits."""
    assert normalize_meta_phone("010 1234 5678") == "201012345678"


def test_template_payload_contains_ordered_name_parameter(monkeypatch):
    """The outreach template includes its one required body parameter."""
    monkeypatch.setattr(meta, "get_meta_credentials", fake_meta_credentials)
    client = MetaWhatsAppClient()
    captured = {}

    async def fake_send(payload):
        """Capture a payload without performing an external HTTP request."""
        captured.update(payload)
        return {"messages": [{"id": "wamid.test"}]}

    monkeypatch.setattr(client, "_send", fake_send)
    asyncio.run(client.send_template("01012345678", "itqan_lead_outreach", "ar", ["أحمد"]))
    parameter = captured["template"]["components"][0]["parameters"][0]
    assert parameter == {"type": "text", "text": "أحمد"}


def test_template_rejects_empty_name(monkeypatch):
    """An empty template identifier fails before an HTTP request is made."""
    monkeypatch.setattr(meta, "get_meta_credentials", fake_meta_credentials)
    with pytest.raises(MetaAPIError):
        asyncio.run(MetaWhatsAppClient().send_template("201012345678", "", "ar"))


def test_extract_message_and_status_events():
    """Message and delivery records are flattened from Meta's nested payload."""
    payload = {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "201", "profile": {"name": "Ahmed"}}],
        "messages": [{"from": "201", "id": "in-1", "type": "text", "text": {"body": "Hi"}}],
        "statuses": [{"id": "out-1", "status": "delivered"}],
    }}]}]}
    assert extract_message_events(payload)[0]["name"] == "Ahmed"
    assert extract_status_events(payload)[0]["status"] == "delivered"


def test_record_status_event_for_known_message():
    """A known outbound message receives one idempotent delivery event."""
    db = make_empty_db()
    contact = Contact(phone="201012345678")
    db.add(contact)
    db.commit()
    db.add(Message(contact_id=contact.id, direction="outbound", body="template", message_sid="out-1"))
    db.commit()
    status = [{"id": "out-1", "status": "read", "timestamp": "1"}]
    record_status_events(db, status)
    record_status_events(db, status)
    assert db.query(Message).filter(Message.direction == "status_read").count() == 1


def test_verify_meta_signature(monkeypatch):
    """A correctly signed webhook body passes signature verification."""
    from app import main
    monkeypatch.setattr(main.settings, "meta_validate_signature", True)
    monkeypatch.setattr(main.settings, "meta_app_secret", "secret")
    body = b'{"ok":true}'
    signature = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    verify_meta_signature(body, signature)


def test_verify_meta_signature_rejects_invalid(monkeypatch):
    """An invalid webhook signature is rejected with HTTP 403."""
    from app import main
    monkeypatch.setattr(main.settings, "meta_validate_signature", True)
    monkeypatch.setattr(main.settings, "meta_app_secret", "secret")
    with pytest.raises(HTTPException) as error:
        verify_meta_signature(b"body", "sha256=invalid")
    assert error.value.status_code == 403


def test_webhook_verify_challenge_matches_token(monkeypatch):
    """A correct hub.verify_token echoes back hub.challenge."""
    from app import main
    monkeypatch.setattr(main, "get_meta_credentials", fake_meta_credentials)
    result = main.verify_webhook(hub_mode="subscribe", hub_verify_token="verify-token", hub_challenge="123")
    assert result == "123"


def test_webhook_verify_rejects_wrong_token(monkeypatch):
    """An incorrect hub.verify_token is rejected with HTTP 403."""
    from app import main
    monkeypatch.setattr(main, "get_meta_credentials", fake_meta_credentials)
    with pytest.raises(HTTPException) as error:
        main.verify_webhook(hub_mode="subscribe", hub_verify_token="wrong-token", hub_challenge="123")
    assert error.value.status_code == 403
