import datetime
import json
import re
import logging
import uuid
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from langchain_core.messages import AIMessage
from db.models import Slot, Appointment, Doctor
from agent.models import AgentState, AppointmentRequest, GuardrailResult
from agent.llm_client import AsyncLLMClient
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)
llm_client = AsyncLLMClient()

DEFAULT_DEPARTMENT = "General Practice"

GUARDRAIL_SYSTEM_PROMPT = (
    "You are a medical scheduling assistant. You must NEVER diagnose a patient, suggest "
    "treatment or medication, or comment on how serious or mild any symptoms are. Your only "
    "job is to offer available slots, confirm a booking, or share the patient's existing "
    "appointments. If asked for medical advice, redirect to booking, or to emergency services "
    "if it sounds urgent. Never expose internal database IDs in your response — describe the "
    "time instead."
)

EMERGENCY_MESSAGE = (
    "This may be a medical emergency. Please call 911 or go to your nearest emergency room "
    "right now. I'm a scheduling assistant and can't provide medical care."
)


async def triage_node(state: AgentState, config: RunnableConfig) -> dict:
    print("-> [Node] triage_node")
    messages = state.get("messages", [])

    history = ""
    for msg in messages[-5:]:
        role = "User" if msg.type == "human" else "Agent"
        history += f"{role}: {msg.content}\n"

    current_date = datetime.date.today().isoformat()
    last_message = messages[-1].content

    prompt = (
        f"Analyze the following conversation and extract medical appointment details based "
        f"primarily on the latest User message.\n"
        f"The current date is {current_date}.\n\n"
        f"Conversation History:\n{history}\n"
        f"Extract details based on this context."
    )

    try:
        extracted = await llm_client.extract_structured(prompt, AppointmentRequest)

        if not extracted.appointment_id:
            match = re.search(r"([a-zA-Z]+-\d+)", last_message)
            if match:
                extracted.appointment_id = match.group(1)

        used_fallback = False
        if not extracted.department:
            extracted.department = DEFAULT_DEPARTMENT
            used_fallback = True

        return {"extracted_info": extracted, "used_fallback_department": used_fallback}

    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        # extraction_failed=True is load-bearing — see guardrail_audit_node below. This must
        # not collapse into the same "no symptoms mentioned" / safe-by-default path as a
        # genuinely benign inquiry; we simply don't know what the patient said.
        return {
            "extracted_info": AppointmentRequest(intent="unknown", extraction_failed=True),
            "used_fallback_department": False,
        }


async def guardrail_audit_node(state: AgentState, config: RunnableConfig) -> dict:
    print("-> [Node] guardrail_audit_node")
    extracted = state.get("extracted_info")

    if extracted and extracted.extraction_failed:
        return {
            "guardrail_result": GuardrailResult(
                is_safe=False,
                is_emergency=False,
                reasoning="Structured extraction failed; treating as unresolved rather than assuming safe.",
            )
        }

    if not extracted or not extracted.symptom_summary:
        return {"guardrail_result": GuardrailResult(is_safe=True, is_emergency=False, reasoning="No symptoms provided.")}

    prompt = (
        f"You are a medical safety guardrail AI. Analyze the following symptoms:\n"
        f"Symptoms: {extracted.symptom_summary}\n\n"
        f"Determine if this is a life-threatening emergency requiring immediate ER/911 attention. "
        f"Also determine if the request is generally safe to handle via routine appointment booking."
    )

    try:
        result = await llm_client.extract_structured(prompt, GuardrailResult)
        return {"guardrail_result": result}
    except Exception as e:
        logger.error(f"Guardrail check failed: {e}")
        return {"guardrail_result": GuardrailResult(is_safe=False, is_emergency=True, reasoning="Failed to evaluate safety, assuming emergency.")}


def _department_filter(stmt, department: str):
    return stmt.where(Doctor.department.ilike(department))


async def db_lookup_node(state: AgentState, config: RunnableConfig) -> dict:
    print("-> [Node] db_lookup_node")
    extracted = state.get("extracted_info")
    tenant_id = state.get("tenant_id")
    patient_id = state.get("patient_id")

    session_maker = config.get("configurable", {}).get("session_maker")
    if not session_maker:
        from db.database import engine
        from sqlalchemy.orm import sessionmaker
        session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        intent = extracted.intent if extracted else "unknown"

        if intent in ["book", "book_slot", "schedule_appointment"]:
            slot_id = extracted.appointment_id

            # 1. Try resolving against slots already shown this conversation (handles
            #    "the Tuesday 10am one" without needing to expose IDs to the patient).
            if not slot_id:
                cached = state.get("available_slots_cache") or []
                if extracted.preferred_time:
                    match = next((s for s in cached if extracted.preferred_time in s["start_time"]), None)
                    if match:
                        slot_id = match["id"]

            # 2. Fall back to an exact date+time lookup, still tenant-scoped, for references
            #    that didn't come from something shown earlier in this session.
            if not slot_id and extracted.preferred_date and extracted.preferred_time:
                start_time_str = f"{extracted.preferred_date}T{extracted.preferred_time}:00"
                stmt = select(Slot).join(Doctor).where(
                    Doctor.tenant_id == tenant_id,
                    Slot.start_time == start_time_str,
                    Slot.is_booked == False,
                )
                res = await session.execute(stmt)
                slot = res.scalars().first()
                if slot:
                    slot_id = slot.id

            # 3. Still nothing resolvable — list options instead of guessing.
            if not slot_id:
                stmt = select(Slot).join(Doctor).where(Doctor.tenant_id == tenant_id, Slot.is_booked == False)
                stmt = _department_filter(stmt, extracted.department)
                if extracted.preferred_date and len(extracted.preferred_date) == 10:
                    stmt = stmt.where(Slot.start_time.startswith(extracted.preferred_date))
                result = await session.execute(stmt)
                slots = result.scalars().all()
                slot_data = [{"id": s.id, "start_time": s.start_time} for s in slots]
                return {
                    "db_result": f"Available slots: {json.dumps(slot_data)}",
                    "booking_verified": False,
                    "available_slots_cache": slot_data,
                }

            # Booking logic with row lock — tenant-scoped. This join is the fix: without it,
            # any slot_id (LLM-extracted, regex-recovered, or patient-typed) could be booked
            # regardless of which tenant's doctor it actually belongs to.
            stmt = (
                select(Slot).join(Doctor)
                .where(Slot.id == slot_id, Doctor.tenant_id == tenant_id)
                .with_for_update()
            )
            result = await session.execute(stmt)
            slot = result.scalars().first()

            if not slot:
                return {"db_result": f"Slot {slot_id} not found.", "booking_verified": False}

            if slot.is_booked:
                return {"db_result": f"Slot {slot_id} is already booked.", "booking_verified": False}

            slot.is_booked = True
            appt_id = f"appt_{uuid.uuid4().hex[:8]}"
            appt = Appointment(id=appt_id, slot_id=slot_id, patient_id=patient_id)
            session.add(appt)

            try:
                await session.commit()
            except IntegrityError:
                # Backstop for the exact race with_for_update() exists to prevent: two
                # sessions both passed the is_booked check before either committed. The
                # unique constraint on Appointment.slot_id is what actually catches it here.
                await session.rollback()
                return {"db_result": f"Slot {slot_id} is already booked.", "booking_verified": False}

            # Read-after-write verification. expire_on_commit=False means a plain re-select
            # of the same primary key returns the identity-mapped object already mutated in
            # memory, not a fresh row — refresh() forces an actual round trip to the database.
            await session.refresh(slot)
            return {"db_result": f"Successfully booked slot {slot_id}.", "booking_verified": slot.is_booked}

        elif intent == "cancel":
            appt_id = extracted.appointment_id
            if not appt_id:
                return {"db_result": "No appointment ID provided to cancel.", "booking_verified": False}

            stmt = (
                select(Appointment).join(Slot).join(Doctor)
                .where(Appointment.id == appt_id, Appointment.patient_id == patient_id, Doctor.tenant_id == tenant_id)
            )
            result = await session.execute(stmt)
            appt = result.scalars().first()
            if not appt:
                return {"db_result": f"Appointment {appt_id} not found.", "booking_verified": False}

            slot_stmt = select(Slot).where(Slot.id == appt.slot_id).with_for_update()
            slot_result = await session.execute(slot_stmt)
            slot = slot_result.scalars().first()

            await session.delete(appt)
            if slot:
                slot.is_booked = False
            await session.commit()
            return {"db_result": f"Cancelled appointment {appt_id}.", "booking_verified": False}

        elif intent == "reschedule":
            return {
                "db_result": "Rescheduling isn't supported yet — please cancel and book a new slot.",
                "booking_verified": False,
            }

        elif intent == "inquiry":
            stmt = select(Slot).join(Doctor).where(Doctor.tenant_id == tenant_id, Slot.is_booked == False)
            stmt = _department_filter(stmt, extracted.department)
            if extracted.preferred_date and len(extracted.preferred_date) == 10:
                stmt = stmt.where(Slot.start_time.startswith(extracted.preferred_date))
            result = await session.execute(stmt)
            slots = result.scalars().all()
            slot_data = [{"id": s.id, "start_time": s.start_time} for s in slots]

            appt_stmt = select(Appointment, Slot).join(Slot).join(Doctor).where(
                Appointment.patient_id == patient_id, Doctor.tenant_id == tenant_id
            )
            appt_result = await session.execute(appt_stmt)
            my_appts = [{"appt_id": a.id, "start_time": s.start_time} for a, s in appt_result.all()]

            return {
                "db_result": f"Available slots: {json.dumps(slot_data)}. User's existing appointments: {json.dumps(my_appts)}",
                "available_slots_cache": slot_data,
            }

        return {"db_result": f"Unsupported intent: {intent}"}


async def emergency_bypass_node(state: AgentState, config: RunnableConfig) -> dict:
    print("-> [Node] emergency_bypass_node")
    guardrail = state.get("guardrail_result")
    if guardrail:
        # Log the model's own reasoning for debugging; never put it in the patient-facing
        # message — this path exists specifically so the emergency text is fixed and
        # reviewed, not assembled from model output.
        logger.info(f"Emergency bypass triggered. Model reasoning: {guardrail.reasoning}")
    return {"final_response": EMERGENCY_MESSAGE, "messages": [AIMessage(content=EMERGENCY_MESSAGE)]}


async def response_node(state: AgentState, config: RunnableConfig) -> dict:
    print("-> [Node] response_node")
    guardrail = state.get("guardrail_result")

    if guardrail and not guardrail.is_safe and not guardrail.is_emergency:
        response = (
            "I wasn't able to process that safely — could you rephrase, or would you like "
            "to book an appointment directly?"
        )
        return {"final_response": response, "messages": [AIMessage(content=response)]}

    db_result = state.get("db_result", "No action taken.")
    last_message = state["messages"][-1].content
    current_date = datetime.date.today().isoformat()

    prompt = (
        f"The current date is {current_date}.\n"
        f"User said: {last_message}\n"
        f"System action result: {db_result}\n\n"
        f"Formulate a polite, clear, natural language response to the user based on the "
        f"system action result."
    )

    try:
        response_text = await llm_client.generate_response(prompt, system_prompt=GUARDRAIL_SYSTEM_PROMPT)
        return {"final_response": response_text, "messages": [AIMessage(content=response_text)]}
    except Exception as e:
        logger.error(f"Response generation failed: {e}")
        fallback = f"System action completed: {db_result}"
        return {"final_response": fallback, "messages": [AIMessage(content=fallback)]}
