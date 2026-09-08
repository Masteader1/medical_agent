import pytest
import json
import hmac
import hashlib
import sys
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os
from dotenv import load_dotenv
load_dotenv()
from httpx import AsyncClient, ASGITransport
from app.main import app

WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "dummy_secret")
WHATSAPP_WEBHOOK_VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "secret_verify_token")

def sign_payload(payload_bytes: bytes) -> str:
    signature = hmac.new(
        key=WHATSAPP_APP_SECRET.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

from fastapi.testclient import TestClient

@pytest.mark.asyncio
async def test_verify_webhook():
    with TestClient(app) as client:
        # Valid verification
        response = client.get(
            f"/api/v1/webhook?hub.mode=subscribe&hub.verify_token={WHATSAPP_WEBHOOK_VERIFY_TOKEN}&hub.challenge=123456"
        )
        assert response.status_code == 200
        assert response.text == "123456"

        # Invalid token
        response = client.get(
            "/api/v1/webhook?hub.mode=subscribe&hub.verify_token=wrong_token&hub.challenge=123456"
        )
        assert response.status_code == 403

@pytest.mark.asyncio
async def test_receive_webhook_invalid_signature():
    with TestClient(app) as client:
        payload = {"object": "whatsapp_business_account"}
        response = client.post(
            "/api/v1/webhook",
            json=payload,
            headers={"X-Hub-Signature-256": "sha256=invalid_hash"}
        )
        assert response.status_code == 401

@pytest.mark.asyncio
async def test_receive_webhook_valid_signature():
    with TestClient(app) as client:
        payload = {
            "object": "whatsapp_business_account",
            "entry": []
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = sign_payload(payload_bytes)
        
        response = client.post(
            "/api/v1/webhook",
            content=payload_bytes,
            headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"}
        )
        # Should return 200 OK immediately
        assert response.status_code == 200
