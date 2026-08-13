"""FastAPI entry point for webhooks, outreach, simulation, and lead management.

This module wires the database, Gemini agent, Meta Cloud API client, and local
dashboard into one HTTP application. Administrative endpoints require the
``X-API-Key`` header; Meta webhooks use signature verification in production.
"""

from __future__ import annotations

from collections import deque
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from .agent import ACTIVE_MODELS, get_active_model, process_message, save_message, set_active_model
from .config import get_settings
from .database import Base, SessionLocal, engine, get_db
from .logging_config import LOG_FILE, configure_logging
from .messaging import MetaAPIError, MetaWhatsAppClient
from .messaging.meta import normalize_meta_phone
from .meta_credentials import MetaCredentialsError, get_meta_credentials
from .models import Contact, LocalTemplate, Message, Unit
from .schemas import (
    ActiveModelUpdate, BulkOutreachRequest, LocalTemplateCreate, OutreachRequest,
    SandboxWelcomeRequest, SimulatorRequest, TestTextRequest, UnitCreate,
)
from .seed import seed_units

configure_logging()
logger = logging.getLogger("app.main")

settings = get_settings()

# In-memory ring buffer of the last few raw webhook payloads, for /api/debug/last-payload.
LAST_PAYLOADS: deque[dict] = deque(maxlen=5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables and synchronize inventory during application startup."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_units(db)
    finally:
        db.close()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


def require_admin(x_api_key: str = Header(default="")):
    """Reject administrative requests that do not contain the configured API key."""
    if not hmac.compare_digest(x_api_key, settings.admin_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")


def verify_meta_signature(raw_body: bytes, signature_header: str | None) -> None:
    """Validate Meta's SHA-256 webhook signature when validation is enabled."""
    if not settings.meta_validate_signature:
        return
    if not settings.meta_app_secret:
        raise HTTPException(status_code=500, detail="META_APP_SECRET is required for signature validation")
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=403, detail="Missing Meta signature")
    expected = "sha256=" + hmac.new(
        settings.meta_app_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=403, detail="Invalid Meta signature")


def extract_message_events(payload: dict) -> list[dict]:
    """Flatten supported inbound WhatsApp messages from a webhook payload."""
    events: list[dict] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts_by_wa = {
                c.get("wa_id"): c.get("profile", {}).get("name")
                for c in value.get("contacts", [])
            }
            for message in value.get("messages", []):
                message_type = message.get("type")
                body = ""
                if message_type == "text":
                    body = message.get("text", {}).get("body", "")
                elif message_type == "button":
                    body = message.get("button", {}).get("text", "")
                elif message_type == "interactive":
                    interactive = message.get("interactive", {})
                    selection = interactive.get("button_reply") or interactive.get("list_reply") or {}
                    body = selection.get("title") or selection.get("id") or ""
                else:
                    body = f"[{message_type or 'unsupported'} message]"
                phone = message.get("from", "")
                events.append({
                    "phone": phone,
                    "name": contacts_by_wa.get(phone),
                    "body": body.strip(),
                    "message_id": message.get("id"),
                    "timestamp": message.get("timestamp"),
                    "type": message_type,
                })
    return events


def extract_status_events(payload: dict) -> list[dict]:
    """Flatten message delivery-status objects from a webhook payload."""
    statuses: list[dict] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            statuses.extend(change.get("value", {}).get("statuses", []))
    return statuses


def record_status_events(db: Session, statuses: list[dict]) -> None:
    """Persist Meta sent/delivered/read/failed events against known messages."""
    for status in statuses:
        message_id = status.get("id")
        if not message_id:
            continue
        outbound = db.query(Message).filter(Message.message_sid == message_id).first()
        if not outbound:
            logger.info("Ignoring status for unknown message_id=%s", message_id)
            continue
        status_name = status.get("status", "unknown")
        detail = {
            "status": status_name,
            "timestamp": status.get("timestamp"),
            "recipient_id": status.get("recipient_id"),
            "errors": status.get("errors", []),
        }
        body = json.dumps(detail, ensure_ascii=False)
        direction = f"status_{status_name}"
        duplicate = db.query(Message).filter(
            Message.message_sid == message_id,
            Message.direction == direction,
            Message.body == body,
        ).first()
        if not duplicate:
            save_message(db, outbound.contact, direction, body, message_id)


def lead_source(contact: Contact) -> str:
    """Classify a contact as "real" (has at least one non-simulator message id)
    or "sandbox" (only ever exchanged messages through the local simulator)."""
    for message in contact.messages:
        if message.message_sid and not message.message_sid.startswith("sim-"):
            return "real"
    return "sandbox"


def get_or_create_contact(db: Session, phone: str, name: str) -> Contact:
    """Find an outreach contact or create it without claiming a message was sent."""
    contact = db.query(Contact).filter(Contact.phone == phone).first()
    if not contact:
        contact = Contact(phone=phone, name=name)
        db.add(contact)
        db.commit()
        db.refresh(contact)
    elif name and contact.name != name:
        contact.name = name
        db.commit()
    return contact


async def send_template_to_contact(db: Session, contact: Contact, name: str) -> str | None:
    """Send the configured outreach template and persist its accepted state."""
    body_params = [name] if settings.meta_template_parameter_count == 1 else None
    response = await MetaWhatsAppClient().send_template(
        contact.phone,
        template_name=settings.meta_test_template_name,
        language_code=settings.meta_test_template_language,
        body_params=body_params,
    )
    message_id = (response.get("messages") or [{}])[0].get("id")
    rendered = (
        f"[Template: {settings.meta_test_template_name}/{settings.meta_test_template_language}]"
        f" parameters={json.dumps(body_params or [], ensure_ascii=False)}"
    )
    save_message(db, contact, "outbound", rendered, message_id)
    contact.contact_status = "Outreach Sent"
    db.commit()
    return message_id


@app.get("/health")
def health():
    """Return a lightweight service and provider readiness response."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "provider": "meta_cloud_api",
        "signature_validation": settings.meta_validate_signature,
    }


@app.get("/webhooks/meta/whatsapp", response_class=PlainTextResponse)
def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    """Complete Meta's GET webhook verification challenge."""
    try:
        verify_token = get_meta_credentials().webhook_verify_token
    except MetaCredentialsError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if hub_mode == "subscribe" and hub_verify_token and hmac.compare_digest(
        hub_verify_token, verify_token
    ):
        return hub_challenge or ""
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@app.post("/webhooks/meta/whatsapp")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive WhatsApp messages/statuses, run the agent, and send replies."""
    raw_body = await request.body()
    verify_meta_signature(raw_body, request.headers.get("X-Hub-Signature-256"))
    try:
        payload = json.loads(raw_body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    LAST_PAYLOADS.append(payload)
    logger.info("RAW PAYLOAD: %s", json.dumps(payload, ensure_ascii=False))

    statuses = extract_status_events(payload)
    events = extract_message_events(payload)
    record_status_events(db, statuses)
    logger.info("extracted %d message event(s), %d status update(s)", len(events), len(statuses))
    for event in events:
        logger.info(
            "event: phone=%s message_id=%s body=%r",
            event["phone"], event["message_id"], event["body"],
        )

    client = None
    if events:
        try:
            client = MetaWhatsAppClient()
        except (MetaAPIError, MetaCredentialsError) as exc:
            logger.error("Cannot initialize MetaWhatsAppClient: %s", exc)

    processed = 0
    for event in events:
        phone = normalize_meta_phone(event["phone"])
        if not phone or not event["message_id"]:
            logger.warning("SKIPPED event with missing phone/message_id: %s", event)
            continue

        # Meta retries webhooks for the same inbound message; skip reprocessing those,
        # but never skip based on an outbound message sharing the same sid.
        duplicate = (
            db.query(Message)
            .filter(Message.message_sid == event["message_id"], Message.direction == "inbound")
            .first()
        )
        if duplicate:
            logger.info("DUPLICATE SKIPPED message_id=%s phone=%s", event["message_id"], phone)
            continue

        contact = db.query(Contact).filter(Contact.phone == phone).first()
        if not contact:
            contact = Contact(phone=phone, name=event["name"])
            db.add(contact)
            db.commit()
            db.refresh(contact)
        elif event["name"] and not contact.name:
            contact.name = event["name"]
            db.commit()

        save_message(db, contact, "inbound", event["body"], event["message_id"])

        try:
            result = process_message(db, contact, event["body"])
        except Exception:
            logger.exception("process_message failed for contact_id=%s", contact.id)
            save_message(db, contact, "outbound_failed", "ERROR: process_message raised an exception, see server logs")
            processed += 1
            continue

        if client is None:
            logger.warning("no Meta client available, cannot send reply to %s", phone)
            save_message(db, contact, "outbound_failed", f"{result.reply}\nERROR: Meta client not configured")
            processed += 1
            continue

        try:
            response = await client.send_text(phone, result.reply, reply_to_message_id=event["message_id"])
            outbound_id = (response.get("messages") or [{}])[0].get("id")
            save_message(db, contact, "outbound", result.reply, outbound_id)
            logger.info("reply sent to %s message_id=%s", phone, outbound_id)
        except MetaAPIError as exc:
            logger.error("send_text failed for phone=%s: %s", phone, exc)
            save_message(db, contact, "outbound_failed", f"{result.reply}\nERROR: {exc}")
        except Exception:
            logger.exception("Unexpected error sending reply to phone=%s", phone)
            save_message(db, contact, "outbound_failed", f"{result.reply}\nERROR: unexpected exception, see server logs")
        processed += 1

    return {"status": "received", "processed_messages": processed, "status_updates": len(statuses)}


LOG_TAIL_MAX_BYTES = 200_000


@app.get("/api/logs", dependencies=[Depends(require_admin)])
def tail_logs(lines: int = Query(default=300, le=2000)):
    """Return the most recent lines from the rotating app log file, for a
    browser-based log viewer (helpful on hosts like Render where the
    dashboard's own log UI isn't otherwise reachable from this app)."""
    if not LOG_FILE.exists():
        return {"lines": []}
    with LOG_FILE.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - LOG_TAIL_MAX_BYTES))
        data = f.read().decode("utf-8", errors="replace")
    return {"lines": data.splitlines()[-lines:]}


@app.get("/api/debug/last-payload", dependencies=[Depends(require_admin)])
def last_payloads():
    """Return the last five webhook payloads held in process memory."""
    return {"count": len(LAST_PAYLOADS), "payloads": list(LAST_PAYLOADS)}


@app.post("/api/outreach", dependencies=[Depends(require_admin)])
async def send_outreach(payload: OutreachRequest, db: Session = Depends(get_db)):
    """Send the configured approved template to one named, eligible contact."""
    phone = normalize_meta_phone(payload.phone)
    if not phone:
        raise HTTPException(status_code=422, detail="Invalid phone number")

    contact = get_or_create_contact(db, phone, payload.name)
    if contact.opted_out:
        raise HTTPException(status_code=409, detail="Contact has opted out")

    try:
        message_id = await send_template_to_contact(db, contact, payload.name)
    except MetaAPIError as exc:
        contact.contact_status = "Outreach Failed"
        save_message(db, contact, "outbound_failed", str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"status": "accepted", "message_id": message_id, "to": phone}


@app.post("/api/outreach/bulk", dependencies=[Depends(require_admin)])
async def send_bulk_outreach(payload: BulkOutreachRequest, db: Session = Depends(get_db)):
    """Send the configured template to up to 100 named recipients."""
    results = []
    for recipient in payload.recipients:
        phone = normalize_meta_phone(recipient.phone)
        if not phone:
            results.append({"phone": recipient.phone, "name": recipient.name, "status": "failed", "detail": "Invalid phone number"})
            continue

        contact = get_or_create_contact(db, phone, recipient.name)
        if contact.opted_out:
            results.append({"phone": phone, "name": recipient.name, "status": "failed", "detail": "Contact has opted out"})
            continue

        try:
            message_id = await send_template_to_contact(db, contact, recipient.name)
        except (MetaAPIError, MetaCredentialsError) as exc:
            contact.contact_status = "Outreach Failed"
            save_message(db, contact, "outbound_failed", str(exc))
            results.append({"phone": phone, "name": recipient.name, "status": "failed", "detail": str(exc)})
            continue

        results.append({"phone": phone, "name": recipient.name, "status": "sent", "message_id": message_id})

    return {"results": results}


@app.post("/api/test-text", dependencies=[Depends(require_admin)])
async def send_test_text(payload: TestTextRequest, db: Session = Depends(get_db)):
    """Send free-form text. Use only after the recipient has messaged the business."""
    phone = normalize_meta_phone(payload.phone)
    if not phone:
        raise HTTPException(status_code=422, detail="Invalid phone number")
    contact = get_or_create_contact(db, phone, None)
    try:
        response = await MetaWhatsAppClient().send_text(phone, payload.body)
    except (MetaAPIError, MetaCredentialsError) as exc:
        save_message(db, contact, "outbound_failed", payload.body)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    message_id = (response.get("messages") or [{}])[0].get("id")
    save_message(db, contact, "outbound", payload.body, message_id)
    return {"status": "accepted", "to": phone, "meta_response": response, "contact_id": contact.id}


@app.post("/api/simulator/message", dependencies=[Depends(require_admin)])
def simulator_message(payload: SimulatorRequest, db: Session = Depends(get_db)):
    """Run an inbound message through the agent without contacting Meta."""
    phone = normalize_meta_phone(payload.phone)
    contact = db.query(Contact).filter(Contact.phone == phone).first()
    if not contact:
        contact = Contact(phone=phone, name=payload.name)
        db.add(contact)
        db.commit()
        db.refresh(contact)
    save_message(db, contact, "inbound", payload.message, f"sim-{contact.id}-{len(contact.messages)+1}")
    result = process_message(db, contact, payload.message)
    save_message(db, contact, "outbound", result.reply, f"sim-out-{contact.id}-{len(contact.messages)+1}")
    db.refresh(contact)
    return {"reply": result.reply, "handoff": result.handoff, "status": contact.contact_status, "contact_id": contact.id}


@app.post("/api/simulator/welcome", dependencies=[Depends(require_admin)])
def simulator_welcome(payload: SandboxWelcomeRequest, db: Session = Depends(get_db)):
    """Open a sandbox chat with a business-sent welcome message, simulating a
    Facebook/Instagram lead ad handoff where the business messages first."""
    phone = normalize_meta_phone(payload.phone)
    contact = db.query(Contact).filter(Contact.phone == phone).first()
    if not contact:
        contact = Contact(phone=phone, name=payload.name)
        db.add(contact)
        db.commit()
        db.refresh(contact)
    if not contact.notes:
        contact.notes = "Simulated: Facebook/Instagram lead ad welcome flow"
        db.commit()
    save_message(db, contact, "outbound", payload.welcome_message, f"sim-out-{contact.id}-{len(contact.messages)+1}")
    db.refresh(contact)
    return {"status": contact.contact_status, "contact_id": contact.id}


@app.get("/api/leads", dependencies=[Depends(require_admin)])
def list_leads(db: Session = Depends(get_db)):
    """List leads in descending order of their most recent update."""
    contacts = db.query(Contact).order_by(Contact.updated_at.desc()).all()
    return [{
        "id": c.id, "name": c.name, "phone": c.phone, "status": c.contact_status,
        "source": lead_source(c),
        "job": c.job, "education": c.education, "location": c.location,
        "budget_min": c.budget_min, "budget_max": c.budget_max,
        "unit_size": c.unit_size, "unit_type": c.unit_type,
        "assigned_to": c.assigned_to, "opted_out": c.opted_out,
        "scheduled_call_start": c.scheduled_call_start, "scheduled_call_end": c.scheduled_call_end,
        "updated_at": c.updated_at,
    } for c in contacts]


@app.get("/api/leads/{contact_id}", dependencies=[Depends(require_admin)])
def lead_detail(contact_id: int, db: Session = Depends(get_db)):
    """Return one lead and its complete chronological conversation."""
    c = db.get(Contact, contact_id)
    if not c:
        raise HTTPException(status_code=404, detail="Lead not found")
    messages = db.query(Message).filter(Message.contact_id == c.id).order_by(Message.created_at).all()
    lead = {k: getattr(c, k) for k in [
        "id", "name", "phone", "contact_phone", "contact_status", "job", "education",
        "location", "budget_min", "budget_max", "unit_size", "unit_type",
        "assigned_to", "opted_out", "scheduled_call_start", "scheduled_call_end", "notes",
    ]}
    lead["source"] = lead_source(c)
    return {
        "lead": lead,
        "messages": [{"direction": m.direction, "body": m.body, "message_id": m.message_sid, "created_at": m.created_at} for m in messages],
    }


@app.get("/api/templates", dependencies=[Depends(require_admin)])
def list_templates(db: Session = Depends(get_db)):
    """List local free-text templates (not registered with Meta)."""
    templates = db.query(LocalTemplate).order_by(LocalTemplate.created_at.desc()).all()
    return [{"id": t.id, "name": t.name, "body": t.body, "created_at": t.created_at} for t in templates]


@app.post("/api/templates", dependencies=[Depends(require_admin)])
def create_template(payload: LocalTemplateCreate, db: Session = Depends(get_db)):
    """Save a reusable free-text template body, e.g. containing {{name}}."""
    if db.query(LocalTemplate).filter(LocalTemplate.name == payload.name).first():
        raise HTTPException(status_code=409, detail="A template with this name already exists")
    template = LocalTemplate(name=payload.name, body=payload.body)
    db.add(template)
    db.commit()
    db.refresh(template)
    return {"id": template.id, "name": template.name, "body": template.body}


@app.delete("/api/templates/{template_id}", dependencies=[Depends(require_admin)])
def delete_template(template_id: int, db: Session = Depends(get_db)):
    """Delete a local free-text template."""
    template = db.get(LocalTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(template)
    db.commit()
    return {"deleted": True, "id": template_id}


@app.get("/api/settings/active-model", dependencies=[Depends(require_admin)])
def get_active_model_endpoint(db: Session = Depends(get_db)):
    """Return which LLM provider (gemini or qwen) currently handles conversations."""
    return {"active_model": get_active_model(db)}


@app.post("/api/settings/active-model", dependencies=[Depends(require_admin)])
def set_active_model_endpoint(payload: ActiveModelUpdate, db: Session = Depends(get_db)):
    """Switch the active LLM provider for every subsequent message, no restart needed."""
    try:
        active_model = set_active_model(db, payload.active_model)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Use one of: {', '.join(ACTIVE_MODELS)}") from exc
    return {"active_model": active_model}


@app.post("/api/units", dependencies=[Depends(require_admin)])
def create_unit(payload: UnitCreate, db: Session = Depends(get_db)):
    """Create a validated inventory unit through the administrative API."""
    unit = Unit(**payload.model_dump())
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return {"id": unit.id, "code": unit.code}


@app.get("/", response_class=HTMLResponse)
def dashboard():
    """Serve the dependency-free local simulator and lead dashboard."""
    return HTMLResponse(content=(Path(__file__).with_name("dashboard.html")).read_text(encoding="utf-8"))
