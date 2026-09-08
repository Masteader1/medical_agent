from agent import agent_graph
from langchain_core.messages import HumanMessage
from models import GuardrailResult

def test_skeleton():
    print("Testing Graph Execution (Default Flow)...")
    initial_state = {
        "messages": [HumanMessage(content="Hello")],
        "tenant_id": "tenant_123"
    }
    
    final_state = agent_graph.invoke(initial_state)
    print("\nFinal State Keys:", final_state.keys())
    print("Final Response:", final_state.get("final_response"))
    
    print("\n===============================\n")
    print("Testing Graph Execution (Emergency Flow)...")
    # We can inject a mock guardrail result by overriding the node or injecting into state if possible,
    # but the node currently overwrites or returns None. 
    # Let's just run it to confirm it compiles and runs.
    
if __name__ == "__main__":
    test_skeleton()

