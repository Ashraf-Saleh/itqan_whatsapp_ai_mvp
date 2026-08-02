import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import Contact
from app.seed import seed_units
from app.agent import process_message, rank_units, resolve_call_window, update_client_fields


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    seed_units(db)
    return db


def test_opt_out():
    db = make_db()
    c = Contact(phone="whatsapp:+201000000002")
    db.add(c); db.commit(); db.refresh(c)
    result = process_message(db, c, "STOP")
    assert c.opted_out is True
    assert c.contact_status == "Opted Out"
    assert "unsubscribe" in result.reply.lower() or "understood" in result.reply.lower()


def test_opted_out_contact_gets_no_llm_reply_until_start():
    db = make_db()
    c = Contact(phone="whatsapp:+201000000003", opted_out=True, contact_status="Opted Out")
    db.add(c); db.commit(); db.refresh(c)
    result = process_message(db, c, "عايز شقة")
    assert c.opted_out is True
    assert "START" in result.reply


def test_process_message_without_gemini_key_returns_fallback(monkeypatch):
    db = make_db()
    c = Contact(phone="whatsapp:+201000000004")
    db.add(c); db.commit(); db.refresh(c)
    from app import agent
    monkeypatch.setattr(agent.settings, "gemini_api_key", "")
    result = process_message(db, c, "عايز شقة في 6 أكتوبر")
    assert result.reply
    assert c.contact_status != "Opted Out"


def test_rank_units_prefers_location_and_type_match():
    db = make_db()
    ranked = rank_units(db, location="6th of October", unit_type="apartment", budget_max=2500000)
    assert ranked
    assert ranked[0].code == "PHE-A1"


def test_rank_units_returns_something_even_without_exact_match():
    db = make_db()
    ranked = rank_units(db, location="Nowhereville", unit_type="spaceship")
    assert len(ranked) == 5


def test_rank_units_empty_portfolio_returns_empty():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    assert rank_units(db, location="Cairo") == []


def test_update_client_fields_only_sets_given_fields():
    db = make_db()
    c = Contact(phone="whatsapp:+201000000005", name="Ahmed")
    db.add(c); db.commit(); db.refresh(c)
    update_client_fields(c, budget_min=2000000)
    assert c.name == "Ahmed"
    assert c.budget_min == 2000000


def test_resolve_call_window_defaults_to_30_minutes():
    start, end = resolve_call_window("2026-08-01", "17:00")
    assert start.hour == 17
    assert end.hour == 17 and end.minute == 30


def test_resolve_call_window_uses_given_end_time():
    start, end = resolve_call_window("2026-08-01", "17:00", "18:30")
    assert end.hour == 18 and end.minute == 30


def test_resolve_call_window_invalid_format_raises():
    with pytest.raises(ValueError):
        resolve_call_window("tomorrow", "5pm")
