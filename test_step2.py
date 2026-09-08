from mock_db import db
from llm_client import LLMClient
from models import AppointmentRequest
import json
import os

# We need to set a dummy API key for LiteLLM if using a mock or simply let it fail if user hasn't set it.
# However, we'll try to execute it, so ensure it doesn't hard-crash.

def test_db():
    print("Testing Mock DB...")
    tenant = "tenant_default"
    slots = db.get_available_slots(tenant)
    print(f"Initial available slots: {len(slots)}")
    
    if not slots:
        print("No slots available, seeding failed.")
        return
        
    first_slot = slots[0]
    date = first_slot["date"]
    time = first_slot["time"]
    
    res = db.book_slot(tenant, date, time, "John Doe")
    print(f"Booking result: {res}")
    
    slots_after = db.get_available_slots(tenant)
    print(f"Available slots after booking: {len(slots_after)}")
    
    if res["success"]:
        appt_id = res["appointment"]["appointment_id"]
        res_cancel = db.cancel_appointment(tenant, appt_id)
        print(f"Cancel result: {res_cancel}")
        
    slots_final = db.get_available_slots(tenant)
    print(f"Available slots after cancellation: {len(slots_final)}")

def test_llm():
    print("\nTesting LLM Client...")
    client = LLMClient()
    prompt = "I want to book an appointment for Jane Smith born 1980-01-01. I've been having bad headaches. I prefer tomorrow at 10am."
    
    # We will only run this if an API key is present to avoid errors
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        print("No API key found in environment, skipping actual LLM call.")
        return
        
    try:
        extracted = client.extract_structured(prompt, AppointmentRequest)
        print(f"Extracted info: {extracted.model_dump_json(indent=2)}")
    except Exception as e:
        print(f"LLM test failed: {e}")

if __name__ == "__main__":
    test_db()
    test_llm()

