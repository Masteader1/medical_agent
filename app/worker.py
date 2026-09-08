import logging
import datetime
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
from langchain_core.messages import HumanMessage
from arq.connections import RedisSettings
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import settings
from db.database import engine, DATABASE_URL
from db.models import ProcessedMessage, Tenant
from app.services.whatsapp import whatsapp_client
from agent.graph import get_compiled_graph

logger = logging.getLogger(__name__)

async def startup(ctx):
    """
    Initialize resources for the Arq worker process.
    """
    logger.info("Starting up Arq worker...")
    conn_string = DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
    
    # Needs to be assigned to ctx so it's accessible in jobs
    ctx['checkpointer_ctx'] = AsyncPostgresSaver.from_conn_string(conn_string)
    ctx['checkpointer'] = await ctx['checkpointer_ctx'].__aenter__()
    await ctx['checkpointer'].setup()
    
    ctx['agent_graph'] = get_compiled_graph(ctx['checkpointer'])
    logger.info("Worker startup complete.")

async def shutdown(ctx):
    """
    Clean up resources for the Arq worker process.
    """
    logger.info("Shutting down Arq worker...")
    if 'checkpointer_ctx' in ctx:
        await ctx['checkpointer_ctx'].__aexit__(None, None, None)
    await whatsapp_client.close()

async def process_whatsapp_message(ctx, phone_number_id: str, message_data: dict, provider: str = "meta"):
    """
    Background worker to process incoming WhatsApp messages via Arq Redis.
    """
    wamid = message_data.get("id")
    from_number = message_data.get("from")
    text_body = message_data.get("text", {}).get("body", "")

    if not wamid or not from_number or not text_body:
        logger.warning("Invalid message payload structure.")
        return

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # 1. Tenant Resolution based on phone_number_id
        stmt = select(Tenant).where(Tenant.whatsapp_phone_number_id == phone_number_id)
        result = await session.execute(stmt)
        tenant = result.scalars().first()
        
        if not tenant:
            logger.error(f"Unknown phone_number_id received: {phone_number_id}")
            return
            
        tenant_id = tenant.id

        # 2. Deduplication using ProcessedMessage
        try:
            processed_msg = ProcessedMessage(
                wamid=wamid,
                tenant_id=tenant_id,
                patient_phone=from_number
            )
            session.add(processed_msg)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.info(f"Duplicate message ignored: {wamid}")
            return
        
    # Mark message as read (Meta only)
    if provider == "meta":
        await whatsapp_client.mark_as_read(phone_number_id, wamid)

    # 3. LangGraph Dispatch
    thread_id = f"{tenant_id}:{from_number}"
    config = {"configurable": {"thread_id": thread_id, "tenant_id": tenant_id}}
    
    initial_state = {
        "messages": [HumanMessage(content=text_body)],
        "tenant_id": tenant_id,
        "patient_id": from_number,
    }

    try:
        agent_graph = ctx.get('agent_graph')
        if not agent_graph:
            logger.error("Agent graph is not initialized.")
            return

        final_state = await agent_graph.ainvoke(initial_state, config=config)
        response_text = final_state.get("final_response", "Sorry, an error occurred in processing your request.")
        
        # 4. Outbound Delivery
        if provider == "twilio":
            await whatsapp_client.send_twilio_message(
                to=from_number,
                text=response_text
            )
        else:
            await whatsapp_client.send_text_message(
                phone_number_id=phone_number_id,
                to=from_number,
                text=response_text
            )
        
    except Exception as e:
        logger.error(f"Error processing message {wamid}: {e}", exc_info=True)


class WorkerSettings:
    """
    Settings for the arq worker.
    """
    functions = [process_whatsapp_message]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
