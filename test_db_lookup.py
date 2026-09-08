from agent import db_lookup_node
from models import AppointmentRequest

def test_db_lookup():
    print("Testing db_lookup_node...")
    
    state_inquiry = {
        "tenant_id": "tenant_default",
        "extracted_info": AppointmentRequest(intent="inquiry")
    }
    
    state_book = {
        "tenant_id": "tenant_default",
        "extracted_info": AppointmentRequest(
            intent="book", 
            preferred_date="2026-09-10", 
            preferred_time="09:00",
            patient={"name": "Alice"}
        )
    }
    
    print("\n--- Inquiry Case ---")
    res1 = db_lookup_node(state_inquiry)
    print(f"Result: {res1}")

    print("\n--- Book Case ---")
    res2 = db_lookup_node(state_book)
    print(f"Result: {res2}")

if __name__ == "__main__":
    test_db_lookup()

