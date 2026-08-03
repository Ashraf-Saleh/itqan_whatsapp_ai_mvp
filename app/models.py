"""SQLAlchemy models for leads, messages, and real-estate inventory."""

from datetime import UTC, datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for ORM defaults."""
    return datetime.now(UTC)


class Contact(Base):
    """A WhatsApp lead and the qualification data collected for that lead."""
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    job: Mapped[str | None] = mapped_column(String(160), nullable=True)
    education: Mapped[str | None] = mapped_column(String(160), nullable=True)
    location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    budget_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    budget_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    contact_status: Mapped[str] = mapped_column(String(50), default="New Lead", index=True)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_to: Mapped[str | None] = mapped_column(String(160), nullable=True)
    scheduled_call_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scheduled_call_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    messages: Mapped[list["Message"]] = relationship(back_populates="contact", cascade="all, delete-orphan")


class Message(Base):
    """An inbound, outbound, failed, or status event associated with a lead."""
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), index=True)
    direction: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(Text)
    message_sid: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    contact: Mapped[Contact] = relationship(back_populates="messages")


class Unit(Base):
    """A searchable real-estate unit imported from the inventory JSON file."""
    __tablename__ = "units"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    project_name: Mapped[str] = mapped_column(String(160), index=True)
    location: Mapped[str] = mapped_column(String(160), index=True)
    unit_type: Mapped[str] = mapped_column(String(80), index=True)
    size_sqm: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    payment_plan: Mapped[str] = mapped_column(String(250))
    delivery: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
