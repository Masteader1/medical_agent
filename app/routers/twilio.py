import logging
import urllib.parse
from fastapi import APIRouter, Request, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/webhook")
async def twilio_webhook(request: Request):
    """
    Ingests Twilio Sandbox WhatsApp messages.
    Converts form data to the unified format and dispatches to Arq worker.
    """
    # Twilio sends data as URL-encoded form data
    body = await request.body()
    decoded = urllib.parse.parse_qs(body.decode("utf-8"))
    
    # parse_qs returns lists for values
    data = {k: v[0] for k, v in decoded.items()}

    from_number = data.get("From", "")
    message_body = data.get("Body", "")
    message_sid = data.get("MessageSid", "")

    if not message_sid or not from_number:
        raise HTTPException(status_code=400, detail="Missing required fields")

    # Twilio prepends 'whatsapp:' to the number
    if from_number.startswith("whatsapp:"):
        from_number = from_number.split("whatsapp:")[1]

    # Create unified message dict exactly like Meta's format
    unified_message = {
        "id": message_sid,
        "from": from_number,
        "type": "text",
        "text": {"body": message_body}
    }

    import app.main
    if app.main.redis_pool:
        # We pass phone_number_id="twilio" so the worker can map it to tenant_default
        # and we pass provider="twilio" so the worker knows to send via Twilio API.
        await app.main.redis_pool.enqueue_job(
            "process_whatsapp_message",
            phone_number_id="twilio",
            message_data=unified_message,
            provider="twilio"
        )
    else:
        logger.error("Redis pool is not initialized")
        
    # Twilio requires a 200 OK or TwiML. An empty response is fine.
    return {"status": "ok"}

