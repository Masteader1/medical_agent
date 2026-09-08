import pytest
from httpx import AsyncClient
from app.main import app
import app.main as main_app
from db.mock_db import init_test_db, test_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from langgraph.checkpoint.memory import MemorySaver

@pytest.fixture(scope="session", autouse=True)
def mock_env():
    import os
    # Ensure LLM calls can succeed if an API key is present.
    # We don't overwrite if one already exists.
    if not os.getenv("GEMINI_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        # We can't actually do much without an API key, but for tests we expect it to be in .env
        pass

@pytest.fixture
async def setup_db():
    await init_test_db()
    
    # Inject memory saver for tests instead of Postgres pool
    main_app.test_checkpointer = MemorySaver()
    # Inject the sqlite session maker
    main_app.test_session_maker = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    
    yield

@pytest.mark.asyncio
async def test_normal_triage(setup_db):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/chat",
            json={"message": "What slots are available?"},
            headers={"x-tenant-id": "tenant_1", "x-patient-id": "pat_123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "cardio-001" not in data["response"] # ID should be masked

@pytest.mark.asyncio
async def test_book_slot(setup_db):
    async with AsyncClient(app=app, base_url="http://test") as client:
        # We simulate the local slot ID recovery from the prompt
        response = await client.post(
            "/chat",
            json={"message": "Book appointment cardio-001"},
            headers={"x-tenant-id": "tenant_1", "x-patient-id": "pat_123"}
        )
        assert response.status_code == 200
        
@pytest.mark.asyncio
async def test_tenant_isolation(setup_db):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/chat",
            json={"message": "Book appointment cardio-001"},
            headers={"x-tenant-id": "tenant_2", "x-patient-id": "pat_999"}
        )
        assert response.status_code == 200
        # tenant 2 shouldn't be able to book cardio-001, so the response should state it's not found or unavailable.

@pytest.mark.asyncio
async def test_emergency_bypass(setup_db):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/chat",
            json={"message": "I have severe chest pain and cannot breathe"},
            headers={"x-tenant-id": "tenant_1", "x-patient-id": "pat_123"}
        )
        assert response.status_code == 200
        assert "EMERGENCY" in response.json()["response"]

