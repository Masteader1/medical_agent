from agent import response_node, emergency_bypass_node
from langchain_core.messages import HumanMessage
from models import GuardrailResult
import os

def test_responses():
    print("Testing response_node and emergency_bypass_node...")
    
    state_emergency = {
        "guardrail_result": GuardrailResult(is_safe=False, is_emergency=True, reasoning="Patient reports severe chest pain.")
    }
    
    state_normal = {
        "messages": [HumanMessage(content="I want to book an appointment.")],
        "db_result": '{"success": true, "appointment": {"appointment_id": "appt_123", "date": "2026-09-10", "time": "09:00"}}'
    }
    
    print("\n--- Emergency Case ---")
    res1 = emergency_bypass_node(state_emergency)
    print(f"Result: {res1['final_response']}")

    print("\n--- Normal Case ---")
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        print("No API key found in environment, skipping actual LLM call.")
    else:
        res2 = response_node(state_normal)
        print(f"Result: {res2['final_response']}")

if __name__ == "__main__":
    test_responses()

