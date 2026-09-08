from typing import Optional, Literal
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from typing import Annotated


class PatientInfo(BaseModel):
    name: Optional[str] = Field(None, description="Patient's full name")
    dob: Optional[str] = Field(None, description="Patient's date of birth (YYYY-MM-DD)")


class AppointmentRequest(BaseModel):
    intent: Literal[
        "book", "book_slot", "schedule_appointment", "cancel", "reschedule", "inquiry", "unknown"
    ] = Field("unknown", description="The intended action by the user")
    patient: Optional[PatientInfo] = Field(default_factory=PatientInfo)
    symptom_summary: Optional[str] = Field(None, description="Brief summary of symptoms or reason for visit")

    preferred_date: Optional[str] = Field(None, alias="date", description="Preferred date (YYYY-MM-DD)")
    preferred_time: Optional[str] = Field(None, alias="time", description="Preferred time (HH:MM)")
    department: Optional[str] = Field(None, alias="department", description="Medical department")
    doctor: Optional[str] = Field(None, alias="doctor", description="Specific doctor name")
    appointment_id: Optional[str] = Field(
        None, alias="id", description="ID of the appointment/slot for booking/canceling (e.g. cardio-001)"
    )

    # Set only inside triage_node's own exception handler. Load-bearing distinction:
    # guardrail_audit_node must NOT treat "the LLM call itself failed" the same as
    # "the LLM ran fine and genuinely found no symptoms" (e.g. a benign inquiry).
    extraction_failed: bool = Field(False, description="True if structured extraction raised an exception")

    class Config:
        populate_by_name = True


class GuardrailResult(BaseModel):
    is_safe: bool = Field(..., description="True if the request passes all medical safety guardrails")
    is_emergency: bool = Field(
        ..., description="True if the symptoms indicate a medical emergency requiring immediate 911/ER attention"
    )
    reasoning: str = Field(
        ...,
        description="Explanation for the guardrail decision. Internal/logging use only — "
        "never interpolated into a patient-facing message.",
    )


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    tenant_id: str
    patient_id: str
    extracted_info: Optional[AppointmentRequest]
    guardrail_result: Optional[GuardrailResult]
    db_result: Optional[str]
    booking_verified: Optional[bool]
    final_response: Optional[str]
    # Last set of slots actually shown to the patient, so "the Tuesday 10am one" can resolve
    # back to a slot id instead of dead-ending against the "don't expose IDs" instruction.
    available_slots_cache: Optional[list[dict]]
    # True whenever no department was extracted and General Practice was substituted —
    # surfaced so it's visible during testing rather than silently defaulting.
    used_fallback_department: Optional[bool]
