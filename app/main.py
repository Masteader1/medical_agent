from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langchain_core.messages import HumanMessage
from typing import Annotated
import logging
from arq import create_pool
from arq.connections import RedisSettings

from app.config import settings
from db.database import DATABASE_URL
# agent.graph imports removed from main to avoid loading ML models on web tier if desired,
# but we need it for `/chat`. The background queue handles webhooks.
from agent.graph import get_compiled_graph

logger = logging.getLogger(__name__)

# For testing override
test_checkpointer = None
test_session_maker = None

checkpointer_ctx = None
checkpointer = None
agent_graph = None
redis_pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global checkpointer_ctx, checkpointer, agent_graph, redis_pool

    # Init Redis Pool
    redis_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))

    if test_checkpointer is not None:
        agent_graph = get_compiled_graph(test_checkpointer)
    else:
        conn_string = DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
        checkpointer_ctx = AsyncPostgresSaver.from_conn_string(conn_string)
        checkpointer = await checkpointer_ctx.__aenter__()
        await checkpointer.setup()
        agent_graph = get_compiled_graph(checkpointer)

    # Start Ngrok Tunnel
    if settings.ngrok_authtoken and settings.ngrok_domain:
        import ngrok
        import os
        # Set env var so ngrok.forward picks it up if authtoken_from_env=True
        os.environ["NGROK_AUTHTOKEN"] = settings.ngrok_authtoken
        try:
            forwarder = await ngrok.forward(
                "localhost:8000",
                authtoken_from_env=True,
                domain=settings.ngrok_domain
            )
            print(f"\n=======================================================")
            print(f"NGROK TUNNEL URL: {forwarder.url()}")
            print(f"=======================================================\n")
            logger.info(f"Ngrok tunnel established: {forwarder.url()}")
        except Exception as e:
            print(f"Failed to start ngrok tunnel: {e}")
            logger.error(f"Failed to start ngrok tunnel: {e}")

    yield

    if redis_pool:
        await redis_pool.close()
    if test_checkpointer is None and checkpointer_ctx:
        await checkpointer_ctx.__aexit__(None, None, None)

from app.routers.webhook import router as webhook_router
from app.routers.twilio import router as twilio_router

app = FastAPI(lifespan=lifespan)
app.include_router(webhook_router, prefix="/api/v1")
app.include_router(twilio_router, prefix="/api/v1/twilio")

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/metrics")
async def metrics():
    # Simple metrics
    return {"status": "ok"}

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    x_tenant_id: Annotated[str, Header()],
    x_patient_id: Annotated[str, Header()],
):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Empty message")

    # Composite thread_id: patient_id alone isn't guaranteed unique across tenants, and the
    # same real person messaging two different clinics is a realistic case once this is
    # phone-number-based on WhatsApp, not just a test-data edge case. Without the tenant_id
    # component, each clinic's chat history — including symptom descriptions — would collide
    # in the checkpointer.
    thread_id = f"{x_tenant_id}:{x_patient_id}"

    config = {"configurable": {"thread_id": thread_id, "tenant_id": x_tenant_id}}
    if test_session_maker:
        config["configurable"]["session_maker"] = test_session_maker

    initial_state = {
        "messages": [HumanMessage(content=request.message)],
        "tenant_id": x_tenant_id,
        "patient_id": x_patient_id,
    }

    try:
        final_state = await agent_graph.ainvoke(initial_state, config=config)
        response_text = final_state.get("final_response", "Sorry, an error occurred in processing your request.")
        return ChatResponse(response=response_text)
    except Exception as e:
        # Log the real error server-side; never return raw exception text to the client — it
        # can leak internal details (schema, stack info) through the API response.
        logger.error(f"Unhandled error in /chat for tenant={x_tenant_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
