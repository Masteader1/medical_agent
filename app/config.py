import os
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv
load_dotenv()

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # LLM Configuration
    default_model: str = "gemini/gemini-3.6-flash"
    gemini_api_key: str

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/medical_db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # WhatsApp Cloud API Webhook Configuration
    whatsapp_webhook_verify_token: str
    whatsapp_app_secret: str

    # WhatsApp Cloud API Outbound Configuration
    whatsapp_api_token: str

    # Twilio Sandbox Configuration (Temporary Bridge)
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    
    # Ngrok Configuration (Testing)
    ngrok_authtoken: Optional[str] = None
    ngrok_domain: Optional[str] = None
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

