import os
import hmac
import hashlib
import json
import httpx
import asyncio
from dotenv import load_dotenv

load_dotenv()

WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "dummy_secret")

def generate_signature(payload_bytes: bytes) -> str:
    signature = hmac.new(
        key=WHATSAPP_APP_SECRET.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

async def simulate_webhook():
    url = "http://127.0.0.1:8000/api/v1/webhook"
    
    # We will simulate a message to "tenant_default" whose phone number ID is "11111111111"
    # and coming from patient "patient_123"
    import uuid
    wamid = f"wamid.{uuid.uuid4().hex}"
    
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "11111111111",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "11111111111",
                                "phone_number_id": "11111111111"
                            },
                            "contacts": [{"profile": {"name": "Test User"}, "wa_id": "patient_123"}],
                            "messages": [
                                {
                                    "from": "patient_123",
                                    "id": wamid,
                                    "timestamp": "1725700000",
                                    "type": "text",
                                    "text": {"body": "Are there any appointments on Friday?"}
                                }
                            ]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    }
    
    payload_bytes = json.dumps(payload).encode("utf-8")
    signature = generate_signature(payload_bytes)
    
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": signature
    }
    
    print(f"Sending simulated webhook with wamid: {wamid}")
    async with httpx.AsyncClient() as client:
        response = await client.post(url, content=payload_bytes, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")

if __name__ == "__main__":
    asyncio.run(simulate_webhook())

