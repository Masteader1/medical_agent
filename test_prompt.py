import os
from dotenv import load_dotenv
load_dotenv()
from llm_client import LLMClient

client = LLMClient()
prompt = """You are a helpful medical receptionist AI.
User said: check the available dates in the future
System action result: Available slots: [{"slot_id": "slot_1", "date": "2026-09-10", "time": "09:00", "is_available": true}, {"slot_id": "slot_2", "date": "2026-09-10", "time": "10:00", "is_available": true}, {"slot_id": "slot_3", "date": "2026-09-11", "time": "14:00", "is_available": true}]

Formulate a polite, clear, natural language response to the user based on the system action result. If slots are available, list them. If booked, confirm the booking."""

print(client.generate_response(prompt))

