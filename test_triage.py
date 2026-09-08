from agent import triage_node
from langchain_core.messages import HumanMessage
import os

def test_triage():
    print("Testing triage_node...")
    state = {
        "messages": [HumanMessage(content="I need to book an appointment for John Smith tomorrow at 10am for a severe headache.")],
        "tenant_id": "tenant_1"
    }
    
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        print("No API key found in environment, skipping actual LLM call.")
        return
        
    print(f"State Before: {state}")
    result = triage_node(state)
    print(f"State After Update: {result}")

if __name__ == "__main__":
    test_triage()

