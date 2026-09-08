import asyncio
from sqlmodel import SQLModel
from db.database import engine, get_async_session
from db.models import Tenant, Doctor, Slot
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

async def init_db():
    print("Creating tables in PostgreSQL...")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    
    print("Seeding database with initial slots...")
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:


        t1 = Tenant(id="tenant_default", name="Default Medical Center", whatsapp_phone_number_id="twilio")
        d1 = Doctor(id="doc_1", tenant_id="tenant_default", name="Dr. Smith", department="Cardiology")
        s1 = Slot(id="cardio-001", doctor_id="doc_1", start_time="2026-09-10T09:00:00", is_booked=False)
        s2 = Slot(id="cardio-002", doctor_id="doc_1", start_time="2026-09-10T10:00:00", is_booked=False)
        s3 = Slot(id="cardio-003", doctor_id="doc_1", start_time="2026-09-11T14:00:00", is_booked=False)
        
        # Additional tenants for integration tests or different user queries
        t2 = Tenant(id="tenant_1", name="Clinic One", whatsapp_phone_number_id="22222222222")
        d2 = Doctor(id="doc_2", tenant_id="tenant_1", name="Dr. Adams", department="General")
        s4 = Slot(id="gen-001", doctor_id="doc_2", start_time="2026-09-10T09:00:00", is_booked=False)
        s5 = Slot(id="gen-002", doctor_id="doc_2", start_time="2026-09-11T10:00:00", is_booked=False)
        
        for item in [t1, t2]: session.add(item)
        await session.flush()
        for item in [d1, d2]: session.add(item)
        await session.flush()
        for item in [s1, s2, s3, s4, s5]: session.add(item)
        await session.commit()
        print("Database seeded successfully! You are ready to book appointments.")

if __name__ == "__main__":
    asyncio.run(init_db())
