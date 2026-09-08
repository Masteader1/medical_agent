import pytest
import os
import json
import hmac
import sys
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import hashlib
from dotenv import load_dotenv
load_dotenv()
from httpx import AsyncClient, ASGITransport
from app.main import app
from arq.connections import RedisSettings
from arq import create_pool
from app.config import settings

def sign_payload(payload_bytes: bytes) -> str:
    signature = hmac.new(
        key=settings.whatsapp_app_secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

@pytest.mark.asyncio
async def test_webhook_enqueues_to_redis():
    # Connect to the real redis pool to check jobs
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    
    # Empty queue before test
    await pool.flushdb()
    
    from fastapi.testclient import TestClient
    
    with TestClient(app) as client:
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "11111111111"},
                                "messages": [
                                    {
                                        "id": "wamid.123",
                                        "from": "patient_123",
                                        "type": "text",
                                        "text": {"body": "test"}
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = sign_payload(payload_bytes)
        
        response = client.post(
            "/api/v1/webhook",
            content=payload_bytes,
            headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"}
        )
        
        # FastAPI should return 200 OK
        assert response.status_code == 200
        
    # Verify job was enqueued in Redis
    queued_jobs = await pool.keys(b"arq:job:*")
    assert len(queued_jobs) == 1
        
    await pool.close()
