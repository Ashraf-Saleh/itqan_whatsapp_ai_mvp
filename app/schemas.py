from pydantic import BaseModel, Field

class OutreachRequest(BaseModel):
    phone: str
    name: str | None = None

class OutreachRecipient(BaseModel):
    phone: str
    name: str

class BulkOutreachRequest(BaseModel):
    recipients: list[OutreachRecipient]

class SimulatorRequest(BaseModel):
    phone: str = "+201000000001"
    name: str | None = "Test Client"
    message: str

class UnitCreate(BaseModel):
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
