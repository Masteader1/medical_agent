import os
import sys
from agent import agent_graph
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

def main():
    load_dotenv()
    
    # We enforce an API key for the main loop.
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        print("ERROR: No API key found in environment. Please set OPENAI_API_KEY or GEMINI_API_KEY.")
        sys.exit(1)

    print("==================================================")
    print(" Welcome to the Multi-Tenant Medical AI Assistant ")
    print("==================================================")
    print("Type 'exit' or 'quit' to stop.")
    
    tenant_id = input("Enter your Tenant ID (or press Enter for 'tenant_default'): ").strip()
    if not tenant_id:
        tenant_id = "tenant_default"
        
    thread_id = input("Enter your Session/Thread ID (or press Enter for 'session_1'): ").strip()
    if not thread_id:
        thread_id = "session_1"
        
    config = {"configurable": {"thread_id": thread_id}}
    
    print(f"\n[Session initialized. Tenant: {tenant_id} | Thread: {thread_id}]")
    print("How can I help you today?")
    print("--------------------------------------------------")

    while True:
        try:
            user_input = input("\nYou: ")
            if user_input.lower() in ["exit", "quit"]:
                print("Goodbye!")
                break
                
            if not user_input.strip():
                continue

            # We structure the input using langgraph's expected format
            initial_state = {
                "messages": [HumanMessage(content=user_input)],
                "tenant_id": tenant_id
            }

            # Run graph with the checkpointer configuration
            # To hide node transition prints, we could suppress stdout, but we keep them for visibility in Phase 1
            print("\n[System Working...]")
            final_state = agent_graph.invoke(initial_state, config=config)
            
            response = final_state.get("final_response", "Sorry, an error occurred in processing your request.")
            print(f"\nAgent: {response}")
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"\n[System Error]: {e}")

if __name__ == "__main__":
    main()

