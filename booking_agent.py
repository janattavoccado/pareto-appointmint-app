"""
Restaurant Booking Agent using OpenAI Responses API.
Handles table reservations with CET:Zagreb timezone support.
Integrates with knowledge base for restaurant information.
Integrates with Mem0 for persistent user memory across sessions.

VERSION 3.1 - STRUCTURED RESERVATION FLOW WITH DATABASE-BACKED STATE
=====================================================================
This version implements a state machine for reservations where:
1. The Python code tracks the reservation state (not the LLM)
2. Each step collects specific information in order
3. The LLM extracts structured data from user messages
4. Confirmation is required before finalizing
5. Session state is stored in PostgreSQL for multi-worker support

Reservation Steps:
1. WELCOME -> Ask for date and time
2. COLLECT_GUESTS -> Ask for number of guests
3. COLLECT_NAME -> Ask for name
4. COLLECT_PHONE -> Ask for phone number
5. COLLECT_SPECIAL_REQUESTS -> Ask for any special requests
6. CONFIRM -> Show summary and ask for confirmation
7. COMPLETE -> Create reservation or handle corrections
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import pytz
from openai import OpenAI

from models import DatabaseManager, Reservation
from knowledgebase_manager import KnowledgeBaseManager
from memory_manager import Mem0MemoryManager

# Configure logging
logger = logging.getLogger(__name__)

# CET:Zagreb timezone
ZAGREB_TZ = pytz.timezone('Europe/Zagreb')

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Initialize knowledge base
kb = KnowledgeBaseManager.get_instance()

# Initialize memory manager
memory = Mem0MemoryManager.get_instance()


# ============================================================================
# Reservation State Machine
# ============================================================================

class ReservationStep(Enum):
    """Steps in the reservation flow."""
    IDLE = "idle"  # Not in reservation flow
    COLLECT_DATETIME = "collect_datetime"  # Step 1: Get date and time
    COLLECT_GUESTS = "collect_guests"  # Step 2: Get number of guests
    COLLECT_NAME = "collect_name"  # Step 3: Get name
    COLLECT_PHONE = "collect_phone"  # Step 4: Get phone number
    COLLECT_SPECIAL = "collect_special"  # Step 5: Get special requests
    CONFIRM = "confirm"  # Step 6: Confirm details
    COMPLETE = "complete"  # Step 7: Reservation complete


@dataclass
class ReservationData:
    """Structured data for a reservation being built."""
    date: Optional[str] = None  # YYYY-MM-DD format
    time: Optional[str] = None  # HH:MM format
    guests: Optional[int] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    special_requests: Optional[str] = None
    
    def is_complete(self) -> bool:
        """Check if all required fields are filled."""
        return all([self.date, self.time, self.guests, self.name, self.phone])
    
    def get_summary(self) -> str:
        """Get a formatted summary of the reservation."""
        lines = []
        if self.date:
            lines.append(f"📅 Date: {self.date}")
        if self.time:
            lines.append(f"🕐 Time: {self.time}")
        if self.guests:
            lines.append(f"👥 Guests: {self.guests}")
        if self.name:
            lines.append(f"👤 Name: {self.name}")
        if self.phone:
            lines.append(f"📞 Phone: {self.phone}")
        if self.special_requests:
            lines.append(f"📝 Special requests: {self.special_requests}")
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "date": self.date,
            "time": self.time,
            "guests": self.guests,
            "name": self.name,
            "phone": self.phone,
            "special_requests": self.special_requests
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReservationData':
        """Create from dictionary."""
        return cls(
            date=data.get("date"),
            time=data.get("time"),
            guests=data.get("guests"),
            name=data.get("name"),
            phone=data.get("phone"),
            special_requests=data.get("special_requests")
        )


@dataclass
class SessionState:
    """State for a user session."""
    step: ReservationStep = ReservationStep.IDLE
    reservation: ReservationData = field(default_factory=ReservationData)
    conversation_history: List[Dict] = field(default_factory=list)
    last_activity: str = ""
    
    def reset_reservation(self):
        """Reset the reservation data but keep conversation history."""
        self.step = ReservationStep.IDLE
        self.reservation = ReservationData()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "step": self.step.value,
            "reservation": self.reservation.to_dict(),
            "conversation_history": self.conversation_history,
            "last_activity": self.last_activity
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionState':
        """Create from dictionary."""
        state = cls()
        state.step = ReservationStep(data.get("step", "idle"))
        state.reservation = ReservationData.from_dict(data.get("reservation", {}))
        state.conversation_history = data.get("conversation_history", [])
        state.last_activity = data.get("last_activity", "")
        return state


# ============================================================================
# Database-backed Session State Storage
# ============================================================================

def get_session_state(user_id: str) -> SessionState:
    """Get session state for a user from database."""
    db = DatabaseManager.get_instance()
    
    try:
        # Try to get from database
        state_json = db.get_session_state(user_id)
        if state_json:
            state = SessionState.from_dict(json.loads(state_json))
            logger.info(f"Loaded session state for {user_id}: step={state.step.value}")
            return state
    except Exception as e:
        logger.error(f"Error loading session state for {user_id}: {e}")
    
    # Return new state if not found
    state = SessionState()
    state.last_activity = datetime.now(ZAGREB_TZ).isoformat()
    logger.info(f"Created new session state for {user_id}")
    return state


def save_session_state(user_id: str, state: SessionState) -> bool:
    """Save session state for a user to database."""
    db = DatabaseManager.get_instance()
    
    try:
        state.last_activity = datetime.now(ZAGREB_TZ).isoformat()
        state_json = json.dumps(state.to_dict())
        db.save_session_state(user_id, state_json)
        logger.info(f"Saved session state for {user_id}: step={state.step.value}")
        return True
    except Exception as e:
        logger.error(f"Error saving session state for {user_id}: {e}")
        return False


def clear_session_state(user_id: str) -> bool:
    """Clear session state for a user."""
    db = DatabaseManager.get_instance()
    
    try:
        db.delete_session_state(user_id)
        logger.info(f"Cleared session state for {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error clearing session state for {user_id}: {e}")
        return False


# ============================================================================
# Utility Functions
# ============================================================================

def parse_date_string(date_str: str) -> str:
    """
    Parse various date formats and return standardized YYYY-MM-DD format.
    """
    if not date_str:
        raise ValueError("Date string is empty")
    
    date_str = date_str.strip().lower()
    now = datetime.now(ZAGREB_TZ)
    today = now.date()
    
    # Natural language dates
    if date_str in ['today', 'danas', 'tonight', 'this evening']:
        return today.strftime('%Y-%m-%d')
    
    if date_str in ['tomorrow', 'sutra']:
        return (today + timedelta(days=1)).strftime('%Y-%m-%d')
    
    if date_str in ['day after tomorrow', 'prekosutra']:
        return (today + timedelta(days=2)).strftime('%Y-%m-%d')
    
    # "in X days" pattern
    in_days_pattern = r'^in\s+(\d+)\s+days?$'
    match = re.match(in_days_pattern, date_str)
    if match:
        days = int(match.group(1))
        return (today + timedelta(days=days)).strftime('%Y-%m-%d')
    
    # Day names
    day_names = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6,
        'ponedjeljak': 0, 'utorak': 1, 'srijeda': 2, 'cetvrtak': 3,
        'petak': 4, 'subota': 5, 'nedjelja': 6
    }
    
    # Check for "next <day>" pattern
    next_day_pattern = r'^next\s+(\w+)$'
    match = re.match(next_day_pattern, date_str)
    if match:
        day_name = match.group(1).lower()
        if day_name in day_names:
            target_weekday = day_names[day_name]
            current_weekday = today.weekday()
            days_ahead = target_weekday - current_weekday
            if days_ahead <= 0:
                days_ahead += 7
            return (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
    
    # Just day name
    if date_str in day_names:
        target_weekday = day_names[date_str]
        current_weekday = today.weekday()
        days_ahead = target_weekday - current_weekday
        if days_ahead < 0:
            days_ahead += 7
        return (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
    
    # Try various date formats
    for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%d.%m.%Y', '%d-%m-%Y']:
        try:
            parsed = datetime.strptime(date_str, fmt)
            return parsed.strftime('%Y-%m-%d')
        except ValueError:
            pass
    
    raise ValueError(f"Unable to parse date: '{date_str}'")


def parse_time_string(time_str: str) -> str:
    """
    Parse various time formats and return standardized HH:MM format (24-hour).
    """
    if not time_str:
        raise ValueError("Time string is empty")
    
    time_str = time_str.strip().lower().replace(' ', '')
    
    # 12-hour format: "7pm", "7:30pm", "11am"
    pattern_12h = r'^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$'
    match = re.match(pattern_12h, time_str)
    
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        period = match.group(3)
        
        if hour < 1 or hour > 12:
            raise ValueError(f"Invalid hour: {hour}")
        if minute < 0 or minute > 59:
            raise ValueError(f"Invalid minute: {minute}")
        
        if period == 'am':
            if hour == 12:
                hour = 0
        else:
            if hour != 12:
                hour += 12
        
        return f"{hour:02d}:{minute:02d}"
    
    # 24-hour format: "19:00", "19:30"
    pattern_24h = r'^(\d{1,2}):(\d{2})$'
    match = re.match(pattern_24h, time_str)
    
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        
        if hour < 0 or hour > 23:
            raise ValueError(f"Invalid hour: {hour}")
        if minute < 0 or minute > 59:
            raise ValueError(f"Invalid minute: {minute}")
        
        return f"{hour:02d}:{minute:02d}"
    
    # Hour only: "19", "9"
    pattern_hour_only = r'^(\d{1,2})$'
    match = re.match(pattern_hour_only, time_str)
    
    if match:
        hour = int(match.group(1))
        if hour < 0 or hour > 23:
            raise ValueError(f"Invalid hour: {hour}")
        return f"{hour:02d}:00"
    
    raise ValueError(f"Unable to parse time: '{time_str}'")


def get_current_datetime() -> Dict[str, Any]:
    """Get the current date and time for CET:Zagreb timezone."""
    now = datetime.now(ZAGREB_TZ)
    return {
        "current_date": now.strftime('%Y-%m-%d'),
        "current_time": now.strftime('%H:%M'),
        "day_of_week": now.strftime('%A'),
        "timezone": "Europe/Zagreb (CET)",
        "full_datetime": now.strftime('%Y-%m-%d %H:%M:%S %Z')
    }


# ============================================================================
# LLM-based Information Extraction
# ============================================================================

def extract_reservation_info(message: str, current_step: ReservationStep) -> Dict[str, Any]:
    """
    Use LLM to extract structured reservation information from user message.
    Returns a dictionary with extracted fields.
    """
    now = datetime.now(ZAGREB_TZ)
    
    extraction_prompt = f"""Extract reservation information from the user's message.
Current date/time: {now.strftime('%Y-%m-%d %H:%M')} ({now.strftime('%A')})
Current step in reservation: {current_step.value}

User message: "{message}"

Extract any of the following information if present:
- date: The reservation date (convert to YYYY-MM-DD format, "today"/"tonight" = {now.strftime('%Y-%m-%d')}, "tomorrow" = {(now + timedelta(days=1)).strftime('%Y-%m-%d')})
- time: The reservation time (convert to HH:MM 24-hour format, e.g., "8pm" = "20:00", "8 o'clock tonight" = "20:00")
- guests: Number of guests (integer, e.g., "three persons" = 3, "5 people" = 5)
- name: Guest name (first name or full name)
- phone: Phone number (any format)
- special_requests: Any special requests or preferences (window seat, dietary requirements, etc.)
- wants_reservation: true if user wants to make a reservation, false if asking about something else
- confirmation: "yes" if user confirms, "no" if user wants to change something, null otherwise
- correction_field: If user wants to correct something, which field (date/time/guests/name/phone/special_requests)
- correction_value: The new value for the correction

Return ONLY a valid JSON object with these fields. Use null for fields not mentioned.
Example: {{"date": "2026-01-12", "time": "20:00", "guests": 3, "name": null, "phone": null, "special_requests": null, "wants_reservation": true, "confirmation": null, "correction_field": null, "correction_value": null}}"""

    try:
        response = client.responses.create(
            model="gpt-4.1-nano",  # Fast extraction model
            input=[{"role": "user", "content": extraction_prompt}],
            temperature=0
        )
        
        result_text = response.output_text.strip()
        
        # Clean up the response - remove markdown code blocks if present
        if result_text.startswith("```"):
            result_text = re.sub(r'^```(?:json)?\n?', '', result_text)
            result_text = re.sub(r'\n?```$', '', result_text)
        
        extracted = json.loads(result_text)
        logger.info(f"Extracted from message: {extracted}")
        return extracted
        
    except Exception as e:
        logger.error(f"Error extracting reservation info: {e}")
        return {}


def generate_response(
    user_message: str,
    session: SessionState,
    user_id: str,
    system_context: str
) -> str:
    """
    Generate a conversational response using the LLM.
    The LLM handles natural language; Python handles state.
    """
    restaurant_name = kb.get_restaurant_name()
    now = datetime.now(ZAGREB_TZ)
    
    # Build the prompt based on current state
    state_info = f"""
Current reservation state:
- Step: {session.step.value}
- Collected data:
{session.reservation.get_summary() if session.reservation.date or session.reservation.guests else "  (none yet)"}
"""

    system_prompt = f"""You are a friendly restaurant booking assistant for {restaurant_name}.
Current date/time: {now.strftime('%Y-%m-%d %H:%M')} ({now.strftime('%A')})

{system_context}

{state_info}

IMPORTANT RULES:
1. Be friendly, professional, and concise
2. Stay focused on the current step - don't ask for information from future steps
3. If the user provides information for the current step, acknowledge it
4. If the user asks about something else (menu, hours, etc.), answer briefly then return to the reservation
5. Use natural, conversational language
6. Keep responses short (1-3 sentences)"""

    # Include recent conversation history for context
    messages = []
    for msg in session.conversation_history[-6:]:  # Last 3 exchanges
        messages.append(msg)
    messages.append({"role": "user", "content": user_message})
    
    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            instructions=system_prompt,
            input=messages
        )
        return response.output_text
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        return "I apologize, but I encountered an error. Please try again."


# ============================================================================
# Reservation Flow Logic
# ============================================================================

def validate_datetime(date_str: str, time_str: str) -> Tuple[bool, str]:
    """Validate that the date and time are valid for a reservation."""
    try:
        reservation_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        reservation_datetime = ZAGREB_TZ.localize(reservation_datetime)
        
        now = datetime.now(ZAGREB_TZ)
        settings = kb.get_reservation_settings()
        
        # Check if in the past
        if reservation_datetime <= now:
            return False, "That time has already passed. Please choose a future date and time."
        
        # Check advance booking
        hours_until = (reservation_datetime - now).total_seconds() / 3600
        if hours_until < settings.advance_booking_hours:
            return False, f"Reservations must be made at least {settings.advance_booking_hours} hour(s) in advance."
        
        # Check if restaurant is open
        day_name = reservation_datetime.strftime('%A').lower()
        hours = kb.get_operating_hours(day_name)
        day_hours = hours.get(day_name)
        
        if day_hours.is_closed:
            return False, f"Sorry, we're closed on {day_name.capitalize()}s."
        
        open_time = datetime.strptime(day_hours.open, "%H:%M").time()
        close_time = datetime.strptime(day_hours.close, "%H:%M").time()
        res_time = reservation_datetime.time()
        
        closes_at_midnight = (close_time.hour == 0 and close_time.minute == 0)
        
        if closes_at_midnight:
            if res_time < open_time:
                return False, f"We open at {day_hours.open} on {day_name.capitalize()}s."
        else:
            if res_time < open_time or res_time >= close_time:
                return False, f"We're open from {day_hours.open} to {day_hours.close} on {day_name.capitalize()}s."
        
        return True, "Valid"
        
    except Exception as e:
        return False, str(e)


def process_reservation_step(
    message: str,
    session: SessionState,
    user_id: str,
    extracted: Dict[str, Any]
) -> str:
    """
    Process the current reservation step and return the response.
    This is the main state machine logic.
    """
    restaurant_name = kb.get_restaurant_name()
    step = session.step
    res = session.reservation
    
    # Handle non-reservation queries
    if step == ReservationStep.IDLE:
        # Check if user wants to make a reservation
        if extracted.get('wants_reservation') or extracted.get('date') or extracted.get('time') or extracted.get('guests'):
            # Start reservation flow
            session.step = ReservationStep.COLLECT_DATETIME
            
            # Check if they already provided date/time
            if extracted.get('date'):
                try:
                    res.date = parse_date_string(extracted['date'])
                except:
                    res.date = extracted.get('date')
            
            if extracted.get('time'):
                try:
                    res.time = parse_time_string(extracted['time'])
                except:
                    res.time = extracted.get('time')
            
            if extracted.get('guests'):
                res.guests = extracted['guests']
            
            if extracted.get('name'):
                res.name = extracted['name']
            
            if extracted.get('phone'):
                res.phone = extracted['phone']
            
            # Determine which step we should be on based on what we have
            if res.date and res.time:
                # Validate datetime
                valid, error_msg = validate_datetime(res.date, res.time)
                if not valid:
                    res.date = None
                    res.time = None
                    return f"Welcome to {restaurant_name}! I'd love to help you with a reservation. {error_msg} When would you like to visit us?"
                
                if res.guests:
                    if res.name:
                        if res.phone:
                            session.step = ReservationStep.COLLECT_SPECIAL
                            return f"Great! I have your reservation for {res.date} at {res.time} for {res.guests} guests under the name {res.name}. Do you have any special requests or dietary requirements?"
                        else:
                            session.step = ReservationStep.COLLECT_PHONE
                            return f"Thank you, {res.name}! What phone number can we reach you at for the reservation?"
                    else:
                        session.step = ReservationStep.COLLECT_NAME
                        return f"Perfect! A table for {res.guests} on {res.date} at {res.time}. May I have your name for the reservation?"
                else:
                    session.step = ReservationStep.COLLECT_GUESTS
                    return f"Wonderful! {res.date} at {res.time}. How many guests will be joining?"
            else:
                return f"Welcome to {restaurant_name}! I'd be happy to help you make a reservation. What date and time would you like to visit us?"
        else:
            # General query - let LLM handle it
            return generate_response(
                message, session, user_id,
                "The user is asking a general question. Answer it helpfully, then ask if they'd like to make a reservation."
            )
    
    # Step 1: Collect date and time
    elif step == ReservationStep.COLLECT_DATETIME:
        if extracted.get('date'):
            try:
                res.date = parse_date_string(extracted['date'])
            except:
                res.date = extracted.get('date')
        
        if extracted.get('time'):
            try:
                res.time = parse_time_string(extracted['time'])
            except:
                res.time = extracted.get('time')
        
        # Also capture any other info they provide
        if extracted.get('guests'):
            res.guests = extracted['guests']
        if extracted.get('name'):
            res.name = extracted['name']
        if extracted.get('phone'):
            res.phone = extracted['phone']
        
        if res.date and res.time:
            # Validate
            valid, error_msg = validate_datetime(res.date, res.time)
            if not valid:
                res.date = None
                res.time = None
                return f"{error_msg} What date and time would work for you?"
            
            session.step = ReservationStep.COLLECT_GUESTS
            if res.guests:
                # Already have guests, move to next step
                session.step = ReservationStep.COLLECT_NAME
                if res.name:
                    session.step = ReservationStep.COLLECT_PHONE
                    if res.phone:
                        session.step = ReservationStep.COLLECT_SPECIAL
                        return f"Excellent! I have {res.date} at {res.time} for {res.guests} guests, name {res.name}, phone {res.phone}. Any special requests?"
                    return f"Thank you, {res.name}! What's the best phone number to reach you?"
                return f"Perfect! {res.date} at {res.time} for {res.guests} guests. May I have your name?"
            return f"Great! {res.date} at {res.time}. How many guests will be dining with us?"
        elif res.date:
            return f"Got it, {res.date}. What time would you like to arrive?"
        elif res.time:
            return f"Got it, {res.time}. What date would you like to come?"
        else:
            return "I didn't catch the date and time. When would you like to make your reservation? For example, 'tomorrow at 7pm' or 'Saturday at 8pm'."
    
    # Step 2: Collect number of guests
    elif step == ReservationStep.COLLECT_GUESTS:
        if extracted.get('guests'):
            res.guests = extracted['guests']
            
            # Validate guest count
            settings = kb.get_reservation_settings()
            if res.guests < settings.min_guests:
                res.guests = None
                return f"We require at least {settings.min_guests} guest for a reservation. How many will be joining?"
            if res.guests > settings.max_guests:
                res.guests = None
                return f"For parties larger than {settings.max_guests}, please call us directly. How many guests (up to {settings.max_guests})?"
            
            session.step = ReservationStep.COLLECT_NAME
            if extracted.get('name'):
                res.name = extracted['name']
                session.step = ReservationStep.COLLECT_PHONE
                if extracted.get('phone'):
                    res.phone = extracted['phone']
                    session.step = ReservationStep.COLLECT_SPECIAL
                    return f"Perfect! Reservation for {res.guests} under {res.name}. Any special requests or dietary requirements?"
                return f"Thank you, {res.name}! What phone number can we reach you at?"
            return f"Wonderful, a table for {res.guests}! May I have your name for the reservation?"
        else:
            return "How many guests will be joining you? Please let me know the number of people."
    
    # Step 3: Collect name
    elif step == ReservationStep.COLLECT_NAME:
        if extracted.get('name'):
            res.name = extracted['name']
            session.step = ReservationStep.COLLECT_PHONE
            if extracted.get('phone'):
                res.phone = extracted['phone']
                session.step = ReservationStep.COLLECT_SPECIAL
                return f"Thank you, {res.name}! Do you have any special requests or dietary requirements for your visit?"
            return f"Thank you, {res.name}! What phone number can we reach you at for the reservation?"
        else:
            return "May I have your name for the reservation?"
    
    # Step 4: Collect phone
    elif step == ReservationStep.COLLECT_PHONE:
        if extracted.get('phone'):
            res.phone = extracted['phone']
            session.step = ReservationStep.COLLECT_SPECIAL
            return f"Got it! Do you have any special requests or dietary requirements? (Say 'no' or 'none' if not)"
        else:
            return "What phone number can we reach you at? This is required for the reservation."
    
    # Step 5: Collect special requests
    elif step == ReservationStep.COLLECT_SPECIAL:
        # Accept any response - even "no" or "none"
        if extracted.get('special_requests'):
            res.special_requests = extracted['special_requests']
        elif message.lower().strip() not in ['no', 'none', 'nothing', 'nope', 'n/a']:
            # If they said something that wasn't extracted as special request, use the message
            if len(message.strip()) > 2:
                res.special_requests = message.strip()
        
        session.step = ReservationStep.CONFIRM
        
        # Show confirmation
        summary = f"""
Perfect! Here's your reservation summary:

📅 Date: {res.date}
🕐 Time: {res.time}
👥 Guests: {res.guests}
👤 Name: {res.name}
📞 Phone: {res.phone}"""
        
        if res.special_requests:
            summary += f"\n📝 Special requests: {res.special_requests}"
        
        summary += "\n\nIs everything correct? (Yes to confirm, or tell me what to change)"
        return summary
    
    # Step 6: Confirmation
    elif step == ReservationStep.CONFIRM:
        confirmation = extracted.get('confirmation')
        
        if confirmation == 'yes' or message.lower().strip() in ['yes', 'yeah', 'yep', 'correct', 'confirmed', 'confirm', 'da', 'ok', 'okay']:
            # Create the reservation
            return create_reservation(session, user_id)
        
        elif confirmation == 'no' or extracted.get('correction_field'):
            # Handle correction
            field = extracted.get('correction_field')
            value = extracted.get('correction_value')
            
            if field and value:
                if field == 'date':
                    try:
                        res.date = parse_date_string(value)
                    except:
                        res.date = value
                elif field == 'time':
                    try:
                        res.time = parse_time_string(value)
                    except:
                        res.time = value
                elif field == 'guests':
                    res.guests = int(value) if isinstance(value, str) else value
                elif field == 'name':
                    res.name = value
                elif field == 'phone':
                    res.phone = value
                elif field == 'special_requests':
                    res.special_requests = value
                
                # Show updated summary
                summary = f"""
Updated! Here's your reservation:

📅 Date: {res.date}
🕐 Time: {res.time}
👥 Guests: {res.guests}
👤 Name: {res.name}
📞 Phone: {res.phone}"""
                
                if res.special_requests:
                    summary += f"\n📝 Special requests: {res.special_requests}"
                
                summary += "\n\nIs this correct now? (Yes to confirm)"
                return summary
            else:
                return "What would you like to change? Please tell me the field (date, time, guests, name, phone, or special requests) and the new value."
        else:
            return "Please confirm your reservation by saying 'yes', or tell me what you'd like to change."
    
    # Step 7: Complete (shouldn't normally reach here)
    elif step == ReservationStep.COMPLETE:
        session.reset_reservation()
        return "Your reservation is complete! Is there anything else I can help you with?"
    
    return "I'm sorry, I didn't understand that. How can I help you?"


def create_reservation(session: SessionState, user_id: str) -> str:
    """Create the actual reservation in the database."""
    res = session.reservation
    
    try:
        # Final validation
        if not res.is_complete():
            return "I'm missing some information. Let me start over. What date and time would you like?"
        
        valid, error_msg = validate_datetime(res.date, res.time)
        if not valid:
            session.step = ReservationStep.COLLECT_DATETIME
            res.date = None
            res.time = None
            return f"{error_msg} What date and time would work instead?"
        
        # Create reservation
        reservation_datetime = datetime.strptime(f"{res.date} {res.time}", "%Y-%m-%d %H:%M")
        reservation_datetime = ZAGREB_TZ.localize(reservation_datetime)
        
        db = DatabaseManager.get_instance()
        now = datetime.now(ZAGREB_TZ)
        
        reservation = db.create_reservation(
            user_id=user_id,
            user_name=res.name,
            phone_number=res.phone,
            number_of_guests=res.guests,
            date_time=reservation_datetime,
            time_slot=2.0,
            time_created=now.strftime('%Y-%m-%d %H:%M:%S')
        )
        
        if reservation:
            # Store in memory
            if memory.is_available:
                memory.remember_user_name(user_id, res.name)
                memory.remember_reservation(
                    user_id,
                    reservation.id,
                    reservation_datetime.strftime('%Y-%m-%d %H:%M'),
                    res.guests
                )
                if res.special_requests:
                    memory.remember_seating_preference(user_id, res.special_requests)
            
            session.step = ReservationStep.COMPLETE
            
            restaurant_name = kb.get_restaurant_name()
            return f"""
✅ Reservation Confirmed!

Your reservation ID is #{reservation.id}

📅 {res.date} at {res.time}
👥 {res.guests} guests
👤 {res.name}
📞 {res.phone}
{f"📝 {res.special_requests}" if res.special_requests else ""}

Thank you for choosing {restaurant_name}! We look forward to seeing you.

Is there anything else I can help you with?"""
        else:
            return "I'm sorry, there was an error creating your reservation. Please try again or call us directly."
            
    except Exception as e:
        logger.error(f"Error creating reservation: {e}", exc_info=True)
        return f"I apologize, but there was an error: {str(e)}. Please try again."


# ============================================================================
# Main Processing Function
# ============================================================================

def process_booking_message(
    message: str,
    user_id: str,
    conversation_history: List[Dict] = None,
    user_name: str = None,
    phone_number: str = None
) -> Tuple[str, List[Dict]]:
    """
    Process a booking message using the structured state machine.
    
    Args:
        message: The user's message text
        user_id: Unique identifier for the user
        conversation_history: Previous conversation history (for compatibility)
        user_name: User's name (optional)
        phone_number: User's phone number (optional)
        
    Returns:
        Tuple of (agent_response, updated_conversation_history)
    """
    # Get session state from database
    session = get_session_state(user_id)
    
    # Update conversation history from parameter if provided and session is empty
    if conversation_history and not session.conversation_history:
        session.conversation_history = conversation_history
    
    session.conversation_history.append({
        "role": "user",
        "content": message
    })
    
    # Pre-fill known info if provided
    if user_name and not session.reservation.name:
        session.reservation.name = user_name
    if phone_number and not session.reservation.phone:
        session.reservation.phone = phone_number
    
    # Extract structured information from the message
    extracted = extract_reservation_info(message, session.step)
    
    # Process based on current step
    response = process_reservation_step(message, session, user_id, extracted)
    
    # Update conversation history
    session.conversation_history.append({
        "role": "assistant",
        "content": response
    })
    
    # Limit history size
    if len(session.conversation_history) > 40:
        session.conversation_history = session.conversation_history[-40:]
    
    # Save session state to database
    save_session_state(user_id, session)
    
    # Store in memory
    if memory.is_available:
        memory.store_conversation_memory(user_id, message, response)
    
    logger.info(f"User {user_id} - Step: {session.step.value} - Response: {response[:100]}...")
    
    return response, session.conversation_history


# ============================================================================
# Compatibility Functions
# ============================================================================

def get_or_create_history(user_id: str) -> List[Dict]:
    """Get or create conversation history for a user."""
    session = get_session_state(user_id)
    return session.conversation_history


def update_history(user_id: str, history: List[Dict]) -> None:
    """Update conversation history for a user."""
    session = get_session_state(user_id)
    session.conversation_history = history
    save_session_state(user_id, session)


def clear_user_conversation(user_id: str) -> bool:
    """Clear conversation history for a specific user."""
    return clear_session_state(user_id)


def get_active_conversations() -> List[str]:
    """Get list of active conversation user IDs."""
    # This would need to query the database
    return []


def process_chatwoot_message(
    message: str,
    user_id: str,
    user_name: str = None,
    phone_number: str = None
) -> str:
    """
    Process a message from Chatwoot webhook.
    """
    response, _ = process_booking_message(
        message=message,
        user_id=user_id,
        user_name=user_name,
        phone_number=phone_number
    )
    return response


# ============================================================================
# Knowledge Base and Menu Tools (for general queries)
# ============================================================================

def tool_get_restaurant_info() -> Dict[str, Any]:
    """Get general information about the restaurant."""
    info = kb.get_restaurant_info_for_agent()
    is_open, status_message = kb.is_restaurant_open()
    
    return {
        "name": info.name,
        "tagline": info.tagline,
        "description": info.description,
        "address": info.full_address,
        "phone": info.phone,
        "email": info.email,
        "website": info.website,
        "is_currently_open": is_open,
        "current_status": status_message
    }


def tool_get_operating_hours() -> Dict[str, Any]:
    """Get the restaurant's operating hours for all days of the week."""
    hours_formatted = kb.get_operating_hours_formatted()
    is_open, status_message = kb.is_restaurant_open()
    
    now = datetime.now(ZAGREB_TZ)
    day_name = now.strftime('%A').lower()
    hours = kb.get_operating_hours(day_name)
    day_hours = hours.get(day_name)
    
    today_hours = "Closed" if day_hours.is_closed else f"{day_hours.open} - {day_hours.close}"
    
    return {
        "hours_formatted": hours_formatted,
        "is_currently_open": is_open,
        "current_status": status_message,
        "today_hours": today_hours
    }


def tool_search_menu(query: str) -> Dict[str, Any]:
    """Search the menu for specific items."""
    results = kb.search_menu(query)
    
    return {
        "query": query,
        "results": [
            {
                "name": item.name,
                "description": item.description,
                "price": item.price,
                "tags": item.tags
            }
            for item in results
        ],
        "count": len(results)
    }


# ============================================================================
# Test Function
# ============================================================================

if __name__ == "__main__":
    print("Testing Restaurant Booking Agent v3.1 - Database-backed State")
    print("-" * 60)
    
    test_user = "test_user_db_state"
    
    # Simulate a conversation
    messages = [
        "Hi, I'd like to book a table",
        "Tomorrow at 7pm",
        "4 people",
        "John Smith",
        "+1234567890",
        "Window seat please",
        "Yes"
    ]
    
    for msg in messages:
        print(f"\nUser: {msg}")
        response, _ = process_booking_message(msg, test_user)
        print(f"Agent: {response}")
        print("-" * 40)
