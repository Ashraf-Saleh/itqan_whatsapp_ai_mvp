from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
import logging
from pathlib import Path
import re
import traceback

from sqlalchemy.orm import Session

from .config import get_settings
from .models import Contact, Message, Unit

settings = get_settings()
logger = logging.getLogger("app.agent")

SYSTEM_MESSAGE_PATH = Path(__file__).resolve().parent.parent / "system_message.md"
HISTORY_LIMIT = 40

STOP_WORDS = {"stop", "unsubscribe", "cancel", "no more", "الغاء", "إلغاء", "توقف", "متبعتليش", "لا ترسل", "مش مهتم", "غير مهتم"}
START_WORDS = {"start", "subscribe", "اشتراك", "ابدأ"}

ALLOWED_STATUSES = {
    "New Lead", "Qualifying", "Matched", "Escalated",
    "Call Booked", "Not Interested", "Follow Up Later", "Opted Out",
}


@dataclass
class AgentResult:
    reply: str
    handoff: bool = False


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def contains_any(text: str, words) -> bool:
    return any(word in text for word in words)


@lru_cache
def _load_system_message_template() -> str:
    return SYSTEM_MESSAGE_PATH.read_text(encoding="utf-8")


def build_system_instruction() -> str:
    template = _load_system_message_template().replace("[Agency Name]", settings.company_name)
    now = datetime.now()
    return (
        f"{template}\n\n"
        "## Current context\n"
        f"- Current date and time: {now.strftime('%A %Y-%m-%d %H:%M')}\n"
        "- Resolve any relative date or time the client mentions (e.g. \"بكرة\", \"الجمعة الجاي\") "
        "against this current date and time before calling book_call."
    )


def rank_units(
    db: Session,
    location: str | None = None,
    unit_type: str | None = None,
    budget_min: float | None = None,
    budget_max: float | None = None,
    size_min: float | None = None,
    size_max: float | None = None,
    limit: int = 5,
) -> list[Unit]:
    units = db.query(Unit).filter(Unit.active.is_(True)).all()
    if not units:
        return []

    def score(u: Unit) -> int:
        s = 0
        if location:
            loc = location.strip().lower()
            if loc in u.location.lower() or u.location.lower() in loc:
                s += 4
        if unit_type:
            ut = unit_type.strip().lower()
            if ut in u.unit_type.lower() or u.unit_type.lower() in ut:
                s += 4
        if budget_min is not None and u.price >= budget_min:
            s += 1
        if budget_max is not None and u.price <= budget_max:
            s += 2
        if budget_min is not None and budget_max is not None and budget_min <= u.price <= budget_max:
            s += 1
        if size_min is not None and u.size_sqm >= size_min:
            s += 1
        if size_max is not None and u.size_sqm <= size_max:
            s += 1
        return s

    return sorted(units, key=score, reverse=True)[:limit]


def unit_to_dict(u: Unit) -> dict:
    return {
        "project_name": u.project_name,
        "location": u.location,
        "unit_type": u.unit_type,
        "size_sqm": u.size_sqm,
        "price": u.price,
        "payment_plan": u.payment_plan,
        "delivery": u.delivery,
        "description": u.description,
    }


def update_client_fields(
    contact: Contact,
    name: str | None = None,
    contact_phone: str | None = None,
    job: str | None = None,
    education: str | None = None,
    budget_min: float | None = None,
    budget_max: float | None = None,
    location: str | None = None,
    unit_size: float | None = None,
    unit_type: str | None = None,
) -> dict:
    updates = {
        "name": name, "contact_phone": contact_phone, "job": job, "education": education,
        "budget_min": budget_min, "budget_max": budget_max, "location": location,
        "unit_size": unit_size, "unit_type": unit_type,
    }
    for field, value in updates.items():
        if value is not None:
            setattr(contact, field, value)
    return {field: getattr(contact, field) for field in updates}


def resolve_call_window(date: str, start_time: str, end_time: str | None = None) -> tuple[datetime, datetime]:
    start_dt = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
    end_dt = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M") if end_time else start_dt + timedelta(minutes=30)
    return start_dt, end_dt


def process_message(db: Session, contact: Contact, body: str) -> AgentResult:
    text = normalize(body)

    if contains_any(text, STOP_WORDS):
        contact.opted_out = True
        contact.contact_status = "Opted Out"
        db.commit()
        return AgentResult("تم إلغاء الاشتراك ولن نرسل رسائل أخرى. Understood — you will not receive further messages from us.")

    if contact.opted_out:
        if text not in START_WORDS:
            return AgentResult("هذا الرقم غير مشترك حاليًا. اكتب START للاشتراك مرة أخرى.")
        contact.opted_out = False
        contact.contact_status = "New Lead"
        db.commit()

    if not settings.gemini_api_key:
        return AgentResult("عذرًا، المساعد غير متاح حاليًا. سيتواصل معك أحد الزملاء في أقرب وقت.")

    def search_units(
        location: str | None = None,
        unit_type: str | None = None,
        budget_min: float | None = None,
        budget_max: float | None = None,
        size_min: float | None = None,
        size_max: float | None = None,
    ) -> list[dict]:
        """Search the available real-estate unit inventory and return the closest-matching options, ranked best first.

        Call this as soon as the client mentions even one preference below — do not wait to
        collect every field first. Call it again whenever the client adds or changes a preference,
        so the options being discussed stay current. Results are ranked by how many of the given
        criteria they satisfy; the list can include options that only partially match (e.g. right
        budget and type but a different location), so treat any non-empty result as a match or
        close match. An empty list means there are no active units in the portfolio at all.

        Args:
            location: desired city or area, in Arabic or English (e.g. "6 أكتوبر", "New Cairo").
            unit_type: desired unit type, e.g. "apartment", "duplex", "villa", "chalet", "office", "shop", "land".
            budget_min: minimum budget in EGP, if the client gave a range or a floor (e.g. "فوق 3 مليون").
            budget_max: maximum budget in EGP, if the client gave a range or a ceiling (e.g. "تحت 2 مليون").
            size_min: minimum desired unit size in square meters.
            size_max: maximum desired unit size in square meters.

        Returns:
            Up to 5 matching units, best match first. Each item has: project_name, location,
            unit_type, size_sqm, price, payment_plan, delivery, description.
        """
        return [unit_to_dict(u) for u in rank_units(db, location, unit_type, budget_min, budget_max, size_min, size_max)]

    def save_client(
        name: str | None = None,
        contact_phone: str | None = None,
        job: str | None = None,
        education: str | None = None,
        budget_min: float | None = None,
        budget_max: float | None = None,
        location: str | None = None,
        unit_size: float | None = None,
        unit_type: str | None = None,
    ) -> dict:
        """Save or update this client's information in the CRM.

        Call this as soon as you have at least their name and phone number, and again any time
        you learn something new. Only pass fields you actually learned in this turn or already
        know — omit fields you don't have yet, since omitted fields are left unchanged rather
        than cleared.

        Args:
            name: the client's full name.
            contact_phone: the phone number the client stated, if it differs from this WhatsApp number.
            job: the client's job or profession, if they shared it.
            education: the client's education background, if they shared it.
            budget_min: minimum budget in EGP, if given as a range or a floor.
            budget_max: maximum budget in EGP, if given as a range or a ceiling.
            location: desired city or area.
            unit_size: desired unit size in square meters.
            unit_type: desired unit type (apartment, duplex, villa, chalet, etc.).

        Returns:
            A confirmation dict with the fields now stored for this client.
        """
        saved = update_client_fields(
            contact, name=name, contact_phone=contact_phone, job=job, education=education,
            budget_min=budget_min, budget_max=budget_max, location=location,
            unit_size=unit_size, unit_type=unit_type,
        )
        db.commit()
        return {"saved": True, **saved}

    def escalate_to_agent(reason: str | None = None) -> dict:
        """Hand this conversation off to a human sales agent right away.

        Use this when the client asks for a human, when the escalation triggers in the system
        message are met (frustration, repeated unanswered questions, out-of-scope requests), or
        when the client agrees to speak with a human after reviewing options.

        Args:
            reason: a short note on why the handoff is happening, for the human agent's context.

        Returns:
            A confirmation dict with the assigned agent's name.
        """
        contact.assigned_to = settings.human_sales_name
        contact.contact_status = "Escalated"
        if reason:
            contact.notes = reason
        db.commit()
        return {"handed_off": True, "agent_name": settings.human_sales_name}

    def book_call(date: str, start_time: str, end_time: str | None = None, notes: str | None = None) -> dict:
        """Book a phone call with the client at an exact, already-confirmed date and time.

        Only call this after resolving any relative date/time phrase into an exact date and time
        and having the client confirm it back to you — never pass their relative phrasing through
        as-is.

        Args:
            date: the confirmed call date, in YYYY-MM-DD format.
            start_time: the confirmed call start time, in 24-hour HH:MM format.
            end_time: the confirmed call end time, in 24-hour HH:MM format, if the client gave a
                time range. If omitted, the call is booked for 30 minutes starting at start_time.
            notes: a short note on what the client wants to discuss on the call.

        Returns:
            A confirmation dict with the booked date and time range, or an error if the date or
            time could not be understood — in that case, ask the client to restate it.
        """
        try:
            start_dt, end_dt = resolve_call_window(date, start_time, end_time)
        except ValueError:
            return {"booked": False, "error": "Invalid date or time format. Use YYYY-MM-DD and 24-hour HH:MM."}
        contact.scheduled_call_start = start_dt
        contact.scheduled_call_end = end_dt
        contact.contact_status = "Call Booked"
        if notes:
            contact.notes = notes
        db.commit()
        return {
            "booked": True,
            "date": start_dt.strftime("%Y-%m-%d"),
            "start_time": start_dt.strftime("%H:%M"),
            "end_time": end_dt.strftime("%H:%M"),
        }

    def update_client_status(status: str) -> dict:
        """Update this client's CRM pipeline status.

        Args:
            status: one of "New Lead", "Qualifying", "Matched", "Escalated", "Call Booked",
                "Not Interested", "Follow Up Later".

        Returns:
            A confirmation dict, or an error if the status is not one of the allowed values.
        """
        if status not in ALLOWED_STATUSES:
            return {"updated": False, "error": f"Unknown status. Use one of: {', '.join(sorted(ALLOWED_STATUSES))}."}
        contact.contact_status = status
        db.commit()
        return {"updated": True, "status": status}

    history = (
        db.query(Message)
        .filter(Message.contact_id == contact.id)
        .order_by(Message.created_at.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    history.reverse()
    logger.info("contact_id=%s history_length=%d", contact.id, len(history))

    from google import genai
    from google.genai import types

    contents = [
        types.Content(role="user" if m.direction == "inbound" else "model", parts=[types.Part(text=m.body)])
        for m in history
        if m.body
    ]

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=build_system_instruction(),
                tools=[search_units, save_client, escalate_to_agent, book_call, update_client_status],
            ),
        )
        reply = (response.text or "").strip()
    except Exception as e:
        logger.error("GEMINI ERROR for contact_id=%s: %s", contact.id, e)
        traceback.print_exc()
        reply = ""

    if not reply:
        reply = "حصل عندنا تأخير بسيط، هنرد عليك في أقرب وقت. شكرًا لصبرك."

    return AgentResult(reply, handoff=contact.contact_status == "Escalated")


def save_message(db: Session, contact: Contact, direction: str, body: str, sid: str | None = None) -> None:
    db.add(Message(contact_id=contact.id, direction=direction, body=body, message_sid=sid))
    db.commit()
