import os
import re
import httpx
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

from app.config import settings

class WhatsAppClient:
    def __init__(self):
        self.api_token = settings.whatsapp_api_token
        if not self.api_token:
            logger.warning("WHATSAPP_API_TOKEN not set in environment.")

        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            },
            timeout=10.0
        )

    def transform_markdown_to_whatsapp(self, text: str) -> str:
        """
        Transforms standard markdown to WhatsApp's formatting.
        - **bold** to *bold*
        - *italic* to _italic_
        """
        # Replace **bold** with *bold*
        text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
        
        # We generally won't mess with italics if they use standard lists,
        # but let's handle single asterisks for italics if any, though lists use `* `.
        # Instead, just handle headers if any.
        text = re.sub(r'^#+\s+(.*)$', r'*\1*', text, flags=re.MULTILINE)

        return text

    async def mark_as_read(self, phone_number_id: str, message_id: str):
        """
        Mark a received message as read to clear the unread notification.
        """
        url = f"{GRAPH_API_BASE_URL}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id
        }
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            logger.debug(f"Marked message {message_id} as read.")
        except Exception as e:
            logger.error(f"Failed to mark message as read: {e}")

    async def send_text_message(self, phone_number_id: str, to: str, text: str) -> Dict[str, Any]:
        """
        Sends an outbound text message via WhatsApp Cloud API.
        """
        formatted_text = self.transform_markdown_to_whatsapp(text)
        
        url = f"{GRAPH_API_BASE_URL}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": formatted_text
            }
        }
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            logger.info(f"Successfully sent WhatsApp message to {to}.")
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"WhatsApp API Error {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message: {e}")
            raise

    async def send_twilio_message(self, to: str, text: str) -> Dict[str, Any]:
        """
        Sends an outbound text message via Twilio WhatsApp Sandbox.
        """
        from app.config import settings
        formatted_text = self.transform_markdown_to_whatsapp(text)
        
        url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
        
        # Twilio expects form data, and 'to' should be formatted as 'whatsapp:+1234567890'
        # 'from_' is our sandbox number
        
        clean_to = to.strip()
        clean_from = settings.twilio_phone_number.strip()
        
        payload = {
            "To": f"whatsapp:{clean_to}" if not clean_to.startswith("whatsapp:") else clean_to,
            "From": clean_from if clean_from.startswith("whatsapp:") else f"whatsapp:{clean_from}",
            "Body": formatted_text
        }
        
        try:
            # We use a new temporary client because Twilio needs Basic Auth, not Bearer token
            async with httpx.AsyncClient(auth=(settings.twilio_account_sid, settings.twilio_auth_token)) as twilio_client:
                response = await twilio_client.post(url, data=payload)
                response.raise_for_status()
                logger.info(f"Successfully sent Twilio message to {to}.")
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Twilio API Error {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to send Twilio message: {e}")
            raise

    async def close(self):
        await self.client.aclose()

whatsapp_client = WhatsAppClient()
