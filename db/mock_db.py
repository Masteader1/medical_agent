import os
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import SQLModel
from sqlalchemy.orm import sessionmaker
from db.models import Tenant, Doctor, Slot

# We use an async sqlite in-memory db for testing the endpoints
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, future=True)

async def init_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
        
    async_session = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        # Seed Data
        t1 = Tenant(id="tenant_1", name="Cardio Clinic")
        t2 = Tenant(id="tenant_2", name="Neuro Center")
        
        d1 = Doctor(id="doc_1", tenant_id="tenant_1", name="Dr. Smith", department="Cardiology")
        d2 = Doctor(id="doc_2", tenant_id="tenant_2", name="Dr. Jones", department="Neurology")
        
        s1 = Slot(id="cardio-001", doctor_id="doc_1", start_time="2026-09-10T09:00:00", is_booked=False)
        s2 = Slot(id="cardio-002", doctor_id="doc_1", start_time="2026-09-10T10:00:00", is_booked=False)
        s3 = Slot(id="neuro-001", doctor_id="doc_2", start_time="2026-09-11T14:00:00", is_booked=False)
        
        session.add_all([t1, t2, d1, d2, s1, s2, s3])
        await session.commit()

async def get_test_session() -> AsyncSession:
    async_session = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

