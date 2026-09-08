import os
import hmac
import hashlib
import logging
from fastapi import APIRouter, Request, Response, HTTPException
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter()

WHATSAPP_WEBHOOK_VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET")

def verify_signature(payload: bytes, signature_header: str) -> bool:
    """
    Validates the X-Hub-Signature-256 header using the app secret.
    """
    if not WHATSAPP_APP_SECRET or not signature_header:
        return False
        
    expected_signature = hmac.new(
        key=WHATSAPP_APP_SECRET.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    # Header format is usually "sha256=<hash>"
    passed_signature = signature_header.split("sha256=")[-1]
    
    return hmac.compare_digest(expected_signature, passed_signature)


@router.get("/webhook")
async def verify_webhook(request: Request):
    """
    Handles the Meta Webhook Verification handshake.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == WHATSAPP_WEBHOOK_VERIFY_TOKEN:
            logger.info("Webhook verified successfully.")
            return Response(content=challenge, media_type="text/plain", status_code=200)
        else:
            logger.warning("Webhook verification failed: Token mismatch.")
            raise HTTPException(status_code=403, detail="Verification failed")
    
    raise HTTPException(status_code=400, detail="Missing parameters")


@router.post("/webhook")
async def receive_webhook(request: Request):
    """
    Ingests WhatsApp messages, verifies HMAC, and dispatches to Redis Arq worker.
    Returns 200 OK immediately.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    
    if not verify_signature(raw_body, signature):
        logger.error("Invalid webhook signature.")
        raise HTTPException(status_code=401, detail="Invalid signature")
        
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    import app.main

    # Meta webhook payload structure is deeply nested
    if payload.get("object") == "whatsapp_business_account":
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                
                # Check if it's a message
                if "messages" in value:
                    phone_number_id = value.get("metadata", {}).get("phone_number_id")
                    for message in value.get("messages", []):
                        if message.get("type") == "text":
                            # Dispatch to Arq Redis Queue
                            if app.main.redis_pool:
                                await app.main.redis_pool.enqueue_job(
                                    "process_whatsapp_message",
                                    phone_number_id=phone_number_id,
                                    message_data=message
                                )
                            else:
                                logger.error("Redis pool is not initialized")
                            
    return {"status": "ok"}

