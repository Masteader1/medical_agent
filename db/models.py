from datetime import datetime

from sqlmodel import SQLModel, Field
from typing import Optional

class Tenant(SQLModel, table=True):
    id: str = Field(primary_key=True, index=True)
    name: str
    whatsapp_phone_number_id: Optional[str] = Field(default=None, index=True, description="WhatsApp Phone Number ID for webhook routing")

class ProcessedMessage(SQLModel, table=True):
    __tablename__ = "processed_messages"
    id: Optional[int] = Field(default=None, primary_key=True)
    wamid: str = Field(index=True, unique=True, description="WhatsApp Message ID")
    tenant_id: str = Field(index=True)
    patient_phone: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Doctor(SQLModel, table=True):
    id: str = Field(primary_key=True, index=True)
    tenant_id: str = Field(foreign_key="tenant.id", index=True)
    name: str
    department: str

class Slot(SQLModel, table=True):
    id: str = Field(primary_key=True, index=True)
    doctor_id: str = Field(foreign_key="doctor.id", index=True)
    start_time: str = Field(index=True)
    is_booked: bool = Field(default=False)

class Appointment(SQLModel, table=True):
    id: str = Field(primary_key=True, index=True)
    slot_id: str = Field(foreign_key="slot.id", unique=True, index=True)
    patient_id: str = Field(index=True)

