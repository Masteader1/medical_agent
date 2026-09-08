from agent import guardrail_audit_node
from models import AppointmentRequest
import os

def test_guardrail():
    print("Testing guardrail_audit_node...")
    
    state_safe = {
        "extracted_info": AppointmentRequest(intent="book", symptom_summary="Mild headache for 2 days")
    }
    
    state_emergency = {
        "extracted_info": AppointmentRequest(intent="book", symptom_summary="Severe chest pain radiating to left arm")
    }
    
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        print("No API key found in environment, skipping actual LLM call.")
        return
        
    print("\n--- Safe Case ---")
    result_safe = guardrail_audit_node(state_safe)
    print(f"Result: {result_safe}")

    print("\n--- Emergency Case ---")
    result_emergency = guardrail_audit_node(state_emergency)
    print(f"Result: {result_emergency}")

if __name__ == "__main__":
    test_guardrail()

