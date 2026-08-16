"""Pydantic request schemas used by the public and administrative API."""

from pydantic import BaseModel, Field

class OutreachRequest(BaseModel):
    """One recipient for a template outreach or a free-form test message."""

    phone: str
    name: str = Field(min_length=1, max_length=160)

class OutreachRecipient(BaseModel):
    """A named recipient in a bulk template outreach request."""

    phone: str
    name: str = Field(min_length=1, max_length=160)

class BulkOutreachRequest(BaseModel):
    """A bounded collection of recipients for one bulk send of a saved free-text template."""

    template_id: int
    recipients: list[OutreachRecipient] = Field(min_length=1, max_length=100)

class TestTextRequest(BaseModel):
    """Diagnostic free-form text sent only inside an open service window."""

    phone: str
    body: str = Field(min_length=1, max_length=4096)

class SimulatorRequest(BaseModel):
    """An inbound message submitted through the local browser simulator."""
    phone: str = "+201000000001"
    name: str | None = "Test Client"
    message: str

class SandboxWelcomeRequest(BaseModel):
    """A business-initiated opener for the sandbox, simulating a Facebook/
    Instagram lead ad handoff where the business messages first."""
    phone: str = "+201000000001"
    name: str | None = "Test Client"
    welcome_message: str = Field(min_length=1, max_length=4096)

class LocalTemplateCreate(BaseModel):
    """A reusable free-text template body, not registered with Meta."""
    name: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=4096)

class ActiveModelUpdate(BaseModel):
    """The LLM provider to make active for all subsequent conversations."""
    active_model: str

class UnitCreate(BaseModel):
    """Validated fields required to add a property inventory unit."""
    code: str
    project_name: str
    location: str
    unit_type: str
    size_sqm: float = Field(ge=0)
    price: float = Field(ge=0)
    payment_plan: str
    delivery: str
    description: str
    active: bool = True
