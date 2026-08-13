"""Unit tests for deterministic agent, inventory, and compliance behavior."""

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import Contact, Message
from app.schemas import ActiveModelUpdate
from app.seed import seed_units
from app.agent import (
    QWEN_TOOL_SCHEMAS, _qwen_base_url, call_qwen, get_active_model, process_message, rank_units,
    resolve_call_window, set_active_model, update_client_fields,
)


def make_db():
    """Create and seed an isolated in-memory database for one test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    seed_units(db)
    return db


def test_opt_out():
    """STOP opts the contact out without calling Gemini."""
    db = make_db()
    c = Contact(phone="whatsapp:+201000000002")
    db.add(c); db.commit(); db.refresh(c)
    result = process_message(db, c, "STOP")
    assert c.opted_out is True
    assert c.contact_status == "Opted Out"
    assert "unsubscribe" in result.reply.lower() or "understood" in result.reply.lower()


def test_opted_out_contact_gets_no_llm_reply_until_start():
    """An opted-out contact receives only resubscription guidance."""
    db = make_db()
    c = Contact(phone="whatsapp:+201000000003", opted_out=True, contact_status="Opted Out")
    db.add(c); db.commit(); db.refresh(c)
    result = process_message(db, c, "عايز شقة")
    assert c.opted_out is True
    assert "START" in result.reply


def test_process_message_without_gemini_key_returns_fallback(monkeypatch):
    """Missing Gemini configuration produces a safe fallback reply."""
    db = make_db()
    c = Contact(phone="whatsapp:+201000000004")
    db.add(c); db.commit(); db.refresh(c)
    from app import agent
    monkeypatch.setattr(agent.settings, "gemini_api_key", "")
    result = process_message(db, c, "عايز شقة في 6 أكتوبر")
    assert result.reply
    assert c.contact_status != "Opted Out"


def test_rank_units_prefers_location_and_type_match():
    """Location and type carry the highest inventory ranking weights."""
    db = make_db()
    ranked = rank_units(db, location="6th of October", unit_type="apartment", budget_max=2500000)
    assert ranked
    assert ranked[0].code == "PHE-A1"


def test_rank_units_returns_something_even_without_exact_match():
    """A populated portfolio returns closest alternatives for weak matches."""
    db = make_db()
    ranked = rank_units(db, location="Nowhereville", unit_type="spaceship")
    assert len(ranked) == 5


def test_rank_units_empty_portfolio_returns_empty():
    """An empty portfolio produces no invented unit suggestions."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    assert rank_units(db, location="Cairo") == []


def test_update_client_fields_only_sets_given_fields():
    """Partial CRM updates preserve fields omitted from the call."""
    db = make_db()
    c = Contact(phone="whatsapp:+201000000005", name="Ahmed")
    db.add(c); db.commit(); db.refresh(c)
    update_client_fields(c, budget_min=2000000)
    assert c.name == "Ahmed"
    assert c.budget_min == 2000000


def test_resolve_call_window_defaults_to_30_minutes():
    """Calls without an end time default to 30 minutes."""
    start, end = resolve_call_window("2026-08-01", "17:00")
    assert start.hour == 17
    assert end.hour == 17 and end.minute == 30


def test_resolve_call_window_uses_given_end_time():
    """An explicitly confirmed end time is preserved."""
    start, end = resolve_call_window("2026-08-01", "17:00", "18:30")
    assert end.hour == 18 and end.minute == 30


def test_resolve_call_window_invalid_format_raises():
    """Relative/unparsed date formats are rejected by deterministic parsing."""
    with pytest.raises(ValueError):
        resolve_call_window("tomorrow", "5pm")


def test_get_active_model_defaults_to_gemini():
    """A fresh database has no explicit selection, so Gemini is the default."""
    db = make_db()
    assert get_active_model(db) == "gemini"


def test_set_active_model_persists():
    """Switching the active model is immediately visible to later reads."""
    db = make_db()
    assert set_active_model(db, "qwen") == "qwen"
    assert get_active_model(db) == "qwen"


def test_set_active_model_rejects_unknown_value():
    """An unsupported model name is rejected rather than silently stored."""
    db = make_db()
    with pytest.raises(ValueError):
        set_active_model(db, "gpt5")


def test_process_message_qwen_selected_without_config_returns_fallback(monkeypatch):
    """Qwen selected but unconfigured degrades to the same safe fallback as Gemini."""
    db = make_db()
    c = Contact(phone="whatsapp:+201000000006")
    db.add(c); db.commit(); db.refresh(c)
    from app import agent
    monkeypatch.setattr(agent.settings, "qwen_url", "")
    monkeypatch.setattr(agent.settings, "qwen_model", "")
    set_active_model(db, "qwen")
    result = process_message(db, c, "عايز شقة في 6 أكتوبر")
    assert result.reply
    assert c.contact_status != "Opted Out"


def test_qwen_base_url_appends_v1_when_missing():
    """A bare host URL (e.g. an ngrok tunnel root) gets /v1 appended for the OpenAI SDK."""
    assert _qwen_base_url("https://example.ngrok-free.app") == "https://example.ngrok-free.app/v1"
    assert _qwen_base_url("https://example.ngrok-free.app/") == "https://example.ngrok-free.app/v1"


def test_qwen_base_url_left_unchanged_when_already_present():
    """A URL that already ends in /v1 is passed through as-is."""
    assert _qwen_base_url("https://example.ngrok-free.app/v1") == "https://example.ngrok-free.app/v1"


def test_qwen_tool_schemas_cover_every_tool():
    """Every tool exposed to Gemini also has a hand-written Qwen schema."""
    assert set(QWEN_TOOL_SCHEMAS) == {
        "search_units", "save_client", "escalate_to_agent", "book_call", "update_client_status",
    }
    for name, schema in QWEN_TOOL_SCHEMAS.items():
        assert schema["type"] == "function"
        assert schema["function"]["name"] == name
        assert "parameters" in schema["function"]


def test_qwen_tool_schema_required_fields_match_signatures():
    """Required parameters in the hand-written schemas match each closure's required args."""
    assert QWEN_TOOL_SCHEMAS["search_units"]["function"]["parameters"]["required"] == []
    assert QWEN_TOOL_SCHEMAS["book_call"]["function"]["parameters"]["required"] == ["date", "start_time"]
    assert QWEN_TOOL_SCHEMAS["update_client_status"]["function"]["parameters"]["required"] == ["status"]


class _FakeToolCallFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.function = _FakeToolCallFunction(name, arguments)


class _FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none=True):
        data = {"role": "assistant", "content": self.content, "tool_calls": self.tool_calls}
        return {k: v for k, v in data.items() if not (exclude_none and v is None)}


class _FakeResponse:
    def __init__(self, message):
        self.choices = [type("Choice", (), {"message": message})()]


class _FakeCompletions:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class _FakeOpenAIClient:
    def __init__(self, responses):
        self.chat = type("Chat", (), {"completions": _FakeCompletions(responses)})()


def test_call_qwen_runs_tool_then_returns_final_text(monkeypatch):
    """The manual tool loop invokes the requested tool and returns the model's final text."""
    from app import agent

    captured = {}

    def fake_search_units(**kwargs):
        captured["kwargs"] = kwargs
        return [{"project_name": "Test Project"}]

    tool_call = _FakeToolCall("call_1", "search_units", json.dumps({"location": "Cairo"}))
    first = _FakeMessage(content=None, tool_calls=[tool_call])
    second = _FakeMessage(content="أهلاً، لقيت لك وحدة مناسبة", tool_calls=None)
    fake_client = _FakeOpenAIClient([_FakeResponse(first), _FakeResponse(second)])

    monkeypatch.setattr(agent, "OpenAI", lambda *a, **k: fake_client)
    monkeypatch.setattr(agent.settings, "qwen_url", "http://fake-qwen")
    monkeypatch.setattr(agent.settings, "qwen_model", "qwen-test")

    reply = call_qwen("system prompt", [], {"search_units": fake_search_units})

    assert reply == "أهلاً، لقيت لك وحدة مناسبة"
    assert captured["kwargs"] == {"location": "Cairo"}
    assert len(fake_client.chat.completions.calls) == 2


def test_call_qwen_stops_after_max_iterations(monkeypatch):
    """A model that never stops calling tools doesn't loop forever."""
    from app import agent

    def fake_tool(**kwargs):
        return {"ok": True}

    tool_call = _FakeToolCall("call_1", "search_units", "{}")
    always_calls_tool = _FakeMessage(content=None, tool_calls=[tool_call])
    responses = [_FakeResponse(always_calls_tool) for _ in range(agent.MAX_TOOL_ITERATIONS)]
    fake_client = _FakeOpenAIClient(responses)

    monkeypatch.setattr(agent, "OpenAI", lambda *a, **k: fake_client)
    monkeypatch.setattr(agent.settings, "qwen_url", "http://fake-qwen")
    monkeypatch.setattr(agent.settings, "qwen_model", "qwen-test")

    reply = call_qwen("system prompt", [], {"search_units": fake_tool})

    assert reply == ""
    assert len(fake_client.chat.completions.calls) == agent.MAX_TOOL_ITERATIONS


def test_get_active_model_endpoint_and_set_active_model_endpoint():
    """The admin endpoints read and persist the active model like the underlying helpers."""
    from app import main
    db = make_db()
    assert main.get_active_model_endpoint(db=db) == {"active_model": "gemini"}
    result = main.set_active_model_endpoint(ActiveModelUpdate(active_model="qwen"), db=db)
    assert result == {"active_model": "qwen"}
    assert main.get_active_model_endpoint(db=db) == {"active_model": "qwen"}


def test_set_active_model_endpoint_rejects_invalid_value():
    """An invalid model name in the request body is rejected with HTTP 422."""
    from app import main
    db = make_db()
    with pytest.raises(HTTPException) as error:
        main.set_active_model_endpoint(ActiveModelUpdate(active_model="bad-model"), db=db)
    assert error.value.status_code == 422


def test_delete_lead_removes_contact_and_cascades_to_messages():
    """Deleting a lead also deletes its message history via the ORM cascade."""
    from app import main
    db = make_db()
    c = Contact(phone="whatsapp:+201000000007", name="Test Lead")
    db.add(c); db.commit(); db.refresh(c)
    db.add(Message(contact_id=c.id, direction="inbound", body="hi"))
    db.commit()

    result = main.delete_lead(contact_id=c.id, db=db)

    assert result == {"deleted": True, "id": c.id}
    assert db.get(Contact, c.id) is None
    assert db.query(Message).filter(Message.contact_id == c.id).count() == 0


def test_delete_lead_missing_contact_raises_404():
    """Deleting a nonexistent lead id fails clearly instead of silently no-op-ing."""
    from app import main
    db = make_db()
    with pytest.raises(HTTPException) as error:
        main.delete_lead(contact_id=999999, db=db)
    assert error.value.status_code == 404


def test_build_system_instruction_includes_whatsapp_number():
    """The model is given the contact's WhatsApp number so it can echo it back as contact_phone."""
    from app import agent
    instruction = agent.build_system_instruction("201100000082")
    assert "201100000082" in instruction
    assert "contact_phone" in instruction
