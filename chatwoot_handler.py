"""
Chatwoot Webhook Handler for Restaurant Booking Agent.

Handles incoming messages from Chatwoot (WhatsApp), processes them with the
booking agent, and sends responses back to the conversation.

File location: chatwoot_handler.py
"""

import os
import logging
import requests
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models for Structured Data
# ============================================================================

class ChatwootMessagePayload(BaseModel):
    """Pydantic model for Chatwoot webhook message payload."""
    event: str = ""
    id: Optional[int] = None
    content: Optional[str] = None
    message_type: Optional[str] = None  # incoming, outgoing
    content_type: Optional[str] = "text"
    content_attributes: Dict[str, Any] = Field(default_factory=dict)
    sender: Dict[str, Any] = Field(default_factory=dict)
    contact: Dict[str, Any] = Field(default_factory=dict)
    conversation: Dict[str, Any] = Field(default_factory=dict)
    account: Dict[str, Any] = Field(default_factory=dict)
    inbox: Dict[str, Any] = Field(default_factory=dict)
    attachments: List[Dict[str, Any]] = Field(default_factory=list)
    private: bool = False


# ============================================================================
# Chatwoot Client
# ============================================================================

class ChatwootClient:
    """
    Client for sending messages back to Chatwoot conversations.
    """
    
    def __init__(self):
        """Initialize Chatwoot client from environment variables."""
        self.base_url = os.getenv('CHATWOOT_BASE_URL', 'https://app.chatwoot.com').rstrip('/')
        self.api_access_token = os.getenv('CHATWOOT_API_ACCESS_TOKEN', '')
        self.account_id = os.getenv('CHATWOOT_ACCOUNT_ID', '')
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        return {
            'api_access_token': self.api_access_token,
            'Content-Type': 'application/json'
        }
    
    def send_message(self, conversation_id: int, message_text: str) -> bool:
        """
        Send a message to a Chatwoot conversation.
        
        Args:
            conversation_id: The conversation ID
            message_text: The message text to send
            
        Returns:
            True if successful, False otherwise
        """
        if not self.api_access_token or not self.account_id:
            logger.error("Chatwoot API credentials not configured")
            return False
        
        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/messages"
        
        payload = {
            "content": message_text,
            "message_type": "outgoing",
            "private": False,
            "content_type": "text"
        }
        
        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            logger.info(f"Message sent to conversation {conversation_id}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send message to Chatwoot: {e}")
            return False


# ============================================================================
# Audio Transcription
# ============================================================================

def extract_audio_from_payload(payload: Dict[str, Any]) -> Optional[str]:
    """
    Extract audio URL from Chatwoot webhook payload.
    
    Args:
        payload: The webhook payload dictionary
        
    Returns:
        Audio URL if found, None otherwise
    """
    attachments = payload.get("attachments", [])
    for attachment in attachments:
        if attachment.get("file_type") == "audio":
            return attachment.get("data_url")
    return None


class AudioTranscriber:
    """
    Handles audio transcription using OpenAI Whisper API.
    """
    
    def __init__(self):
        """Initialize audio transcriber."""
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.supported_formats = ['mp3', 'mp4', 'mpeg', 'mpga', 'flac', 'ogg', 'm4a', 'wav', 'webm']
    
    def transcribe_from_url(self, audio_url: str, language: str = "hr") -> Optional[str]:
        """
        Download and transcribe audio from URL.
        
        Args:
            audio_url: URL of the audio file
            language: Language code for transcription (default: Croatian)
            
        Returns:
            Transcribed text or None if failed
        """
        if not self.api_key:
            logger.error("OPENAI_API_KEY not set for audio transcription")
            return None
        
        try:
            # Download audio file
            logger.info(f"Downloading audio from: {audio_url[:50]}...")
            response = requests.get(audio_url, timeout=60)
            response.raise_for_status()
            audio_data = response.content
            
            # Determine file extension
            extension = audio_url.split('.')[-1].split('?')[0].lower()
            if extension not in self.supported_formats:
                extension = 'ogg'  # Default for WhatsApp voice messages
            
            # Save to temp file and transcribe
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=f'.{extension}', delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.api_key)
                
                with open(temp_file_path, 'rb') as audio_file:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language=language
                    )
                
                logger.info(f"Audio transcribed: {transcript.text[:100]}...")
                return transcript.text
                
            finally:
                # Clean up temp file
                import os as os_module
                if os_module.path.exists(temp_file_path):
                    os_module.unlink(temp_file_path)
                    
        except Exception as e:
            logger.error(f"Audio transcription failed: {e}", exc_info=True)
            return None


# ============================================================================
# Webhook Handler
# ============================================================================

def webhook_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main Chatwoot webhook handler for restaurant booking.
    
    Args:
        payload: The webhook payload from Chatwoot
        
    Returns:
        Result dictionary with status
    """
    conversation_id = None
    
    try:
        if not payload:
            logger.warning("Empty webhook payload received.")
            return {"error": "Empty payload"}
        
        # Extract essential data from payload
        event = payload.get("event", "")
        message_type = payload.get("message_type")
        conversation_id = payload.get("conversation", {}).get("id")
        
        # Get contact info
        sender = payload.get("sender", {})
        contact = payload.get("contact", {})
        phone_number = sender.get("phone_number") or contact.get("phone_number")
        user_name = sender.get("name") or contact.get("name") or "Guest"
        
        # Only process message_created events
        if event != "message_created":
            logger.info(f"Skipping event type: {event}")
            return {"status": "skipped", "reason": f"event_type_{event}"}
        
        # Skip outgoing messages (from agents)
        if message_type == "outgoing":
            logger.info("Skipping outgoing message")
            return {"status": "skipped_outgoing"}
        
        if not conversation_id:
            logger.warning("Webhook missing conversation_id")
            return {"error": "Missing conversation_id"}
        
        logger.info(f"Processing message from {user_name} ({phone_number}) in conversation {conversation_id}")
        
        # --- Message Content Processing ---
        content = payload.get("content", "")
        attachments = payload.get("attachments", [])
        is_audio = any(att.get("file_type") == "audio" for att in attachments)
        
        message_to_process = content
        
        # Handle audio messages - transcribe using OpenAI Whisper
        if is_audio:
            logger.info("Audio message detected, starting transcription...")
            try:
                audio_url = extract_audio_from_payload(payload)
                
                if audio_url:
                    transcriber = AudioTranscriber()
                    transcribed_text = transcriber.transcribe_from_url(audio_url)
                    
                    if transcribed_text:
                        logger.info(f"Audio transcribed successfully: {transcribed_text[:100]}...")
                        message_to_process = transcribed_text
                    else:
                        logger.warning("Audio transcription returned empty text")
                        ChatwootClient().send_message(
                            conversation_id=conversation_id,
                            message_text="❌ I couldn't understand the audio message. Please try again or send a text message."
                        )
                        return {"status": "transcription_empty"}
                else:
                    logger.warning("Could not extract audio URL from payload")
                    ChatwootClient().send_message(
                        conversation_id=conversation_id,
                        message_text="❌ I couldn't process the audio message. Please try again."
                    )
                    return {"status": "audio_url_missing"}
                    
            except Exception as e:
                logger.error(f"Audio transcription failed: {e}", exc_info=True)
                ChatwootClient().send_message(
                    conversation_id=conversation_id,
                    message_text="❌ I had trouble processing your voice message. Please try again or send a text message."
                )
                return {"status": "transcription_error", "error": str(e)}
        
        if not message_to_process:
            logger.warning("No content to process after handling attachments.")
            return {"status": "no_content"}
        
        # --- Send Fast Acknowledgment ---
        first_name = user_name.split()[0] if user_name else "there"
        ack_message = f"Hi {first_name}! 🍽️ Your message has been received. I'm processing your request and will respond in approximately 15-20 seconds."
        
        try:
            ChatwootClient().send_message(
                conversation_id=conversation_id,
                message_text=ack_message
            )
            logger.info(f"Acknowledgment sent to {first_name} for conversation {conversation_id}")
        except Exception as ack_error:
            logger.warning(f"Failed to send acknowledgment: {ack_error}")
            # Continue processing even if acknowledgment fails
        
        # --- Process with Booking Agent ---
        try:
            from booking_agent import process_chatwoot_message
            
            # Create user identifier from phone number or contact id
            user_id = phone_number or f"chatwoot_{contact.get('id', 'unknown')}"
            
            # Process the message with the booking agent (using Responses API)
            agent_response = process_chatwoot_message(
                message=message_to_process,
                user_id=user_id,
                user_name=user_name,
                phone_number=phone_number
            )
            
            if agent_response:
                final_response = agent_response
            else:
                final_response = "I apologize, but I couldn't process your request. Please try again or contact the restaurant directly."
                
        except Exception as e:
            logger.error(f"Booking agent processing failed: {e}", exc_info=True)
            final_response = "I encountered an error processing your request. Please try again or contact the restaurant directly."
        
        # --- Send Final Response ---
        if final_response:
            ChatwootClient().send_message(
                conversation_id=conversation_id,
                message_text=final_response
            )
            logger.info(f"Final response sent to Chatwoot for conversation {conversation_id}")
        else:
            logger.warning("No final response was generated to send.")
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Unhandled error in webhook_handler: {e}", exc_info=True)
        # Attempt to notify user of failure
        try:
            if conversation_id:
                ChatwootClient().send_message(
                    conversation_id=conversation_id,
                    message_text="I encountered an unexpected error. Please try again or contact the restaurant directly."
                )
        except Exception as notify_e:
            logger.error(f"Failed to send error notification to user: {notify_e}")
        return {"status": "error", "message": str(e)}
