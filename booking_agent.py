"""
Restaurant Booking Agent using OpenAI Responses API.
Handles table reservations with CET:Zagreb timezone support.
Integrates with knowledge base for restaurant information.
Integrates with Mem0 for persistent user memory across sessions.
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pytz
from openai import OpenAI
from pydantic import BaseModel, Field

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
# Utility Functions
# ============================================================================

def parse_date_string(date_str: str) -> str:
    """
    Parse various date formats and return standardized YYYY-MM-DD format.
    
    Supports:
    - ISO format: "2026-01-10", "2026/01/10"
    - Natural language: "today", "tomorrow", "day after tomorrow"
    - Day names: "monday", "tuesday", "next friday", etc.
    - Relative: "in 2 days", "in a week"
    
    Returns:
        str: Date in YYYY-MM-DD format
    
    Raises:
        ValueError: If the date format cannot be parsed
    """
    if not date_str:
        raise ValueError("Date string is empty")
    
    # Clean up the input
    date_str = date_str.strip().lower()
    
    # Get current date in Zagreb timezone
    now = datetime.now(ZAGREB_TZ)
    today = now.date()
    
    # Natural language dates
    if date_str in ['today', 'danas']:
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
    
    # "in a week" / "in X weeks"
    if date_str == 'in a week':
        return (today + timedelta(weeks=1)).strftime('%Y-%m-%d')
    
    in_weeks_pattern = r'^in\s+(\d+)\s+weeks?$'
    match = re.match(in_weeks_pattern, date_str)
    if match:
        weeks = int(match.group(1))
        return (today + timedelta(weeks=weeks)).strftime('%Y-%m-%d')
    
    # Day names (find next occurrence)
    day_names = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6,
        # Croatian
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
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7
            return (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
    
    # Just day name (find next occurrence, including today if it matches)
    if date_str in day_names:
        target_weekday = day_names[date_str]
        current_weekday = today.weekday()
        days_ahead = target_weekday - current_weekday
        if days_ahead < 0:  # Target day already happened this week
            days_ahead += 7
        return (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
    
    # Try to parse ISO format: YYYY-MM-DD
    try:
        parsed = datetime.strptime(date_str, '%Y-%m-%d')
        return parsed.strftime('%Y-%m-%d')
    except ValueError:
        pass
    
    # Try to parse with slashes: YYYY/MM/DD
    try:
        parsed = datetime.strptime(date_str, '%Y/%m/%d')
        return parsed.strftime('%Y-%m-%d')
    except ValueError:
        pass
    
    # Try to parse DD/MM/YYYY (European format)
    try:
        parsed = datetime.strptime(date_str, '%d/%m/%Y')
        return parsed.strftime('%Y-%m-%d')
    except ValueError:
        pass
    
    # Try to parse DD.MM.YYYY (European format with dots)
    try:
        parsed = datetime.strptime(date_str, '%d.%m.%Y')
        return parsed.strftime('%Y-%m-%d')
    except ValueError:
        pass
    
    raise ValueError(f"Unable to parse date format: '{date_str}'. Please use formats like 'tomorrow', 'next friday', or 'YYYY-MM-DD'")


def parse_time_string(time_str: str) -> str:
    """
    Parse various time formats and return standardized HH:MM format (24-hour).
    
    Supports:
    - 12-hour format: "7pm", "7:30pm", "7 pm", "7:30 PM", "11am"
    - 24-hour format: "19:00", "19:30", "09:00"
    - Hour only: "19", "9" (treated as HH:00)
    
    Returns:
        str: Time in HH:MM format (24-hour)
    
    Raises:
        ValueError: If the time format cannot be parsed
    """
    if not time_str:
        raise ValueError("Time string is empty")
    
    # Clean up the input
    time_str = time_str.strip().lower().replace(' ', '')
    
    # Pattern for 12-hour format with am/pm: "7pm", "7:30pm", "11am", "12:30am"
    pattern_12h = r'^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$'
    match = re.match(pattern_12h, time_str)
    
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        period = match.group(3)
        
        # Validate hour for 12-hour format
        if hour < 1 or hour > 12:
            raise ValueError(f"Invalid hour in 12-hour format: {hour}")
        if minute < 0 or minute > 59:
            raise ValueError(f"Invalid minute: {minute}")
        
        # Convert to 24-hour format
        if period == 'am':
            if hour == 12:  # 12am is midnight (00:00)
                hour = 0
        else:  # pm
            if hour != 12:  # 12pm stays as 12
                hour += 12
        
        return f"{hour:02d}:{minute:02d}"
    
    # Pattern for 24-hour format: "19:00", "19:30", "09:00", "9:00"
    pattern_24h = r'^(\d{1,2}):(\d{2})$'
    match = re.match(pattern_24h, time_str)
    
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        
        # Validate hour and minute
        if hour < 0 or hour > 23:
            raise ValueError(f"Invalid hour in 24-hour format: {hour}")
        if minute < 0 or minute > 59:
            raise ValueError(f"Invalid minute: {minute}")
        
        return f"{hour:02d}:{minute:02d}"
    
    # Pattern for hour-only 24-hour format: "19", "9"
    pattern_hour_only = r'^(\d{1,2})$'
    match = re.match(pattern_hour_only, time_str)
    
    if match:
        hour = int(match.group(1))
        if hour < 0 or hour > 23:
            raise ValueError(f"Invalid hour: {hour}")
        return f"{hour:02d}:00"
    
    raise ValueError(f"Unable to parse time format: '{time_str}'. Please use formats like '7pm', '7:30pm', '19:00', or '19:30'")


# ============================================================================
# Tool Function Implementations
# ============================================================================

def tool_get_current_datetime() -> Dict[str, Any]:
    """Get the current date and time for CET:Zagreb timezone."""
    now = datetime.now(ZAGREB_TZ)
    return {
        "current_date": now.strftime('%Y-%m-%d'),
        "current_time": now.strftime('%H:%M'),
        "day_of_week": now.strftime('%A'),
        "timezone": "Europe/Zagreb (CET)",
        "full_datetime": now.strftime('%Y-%m-%d %H:%M:%S %Z')
    }


def tool_recall_user_info(user_id: str) -> str:
    """Recall what we know about a user from memory."""
    if not memory.is_available:
        return "Memory system is not available. Treating as a new guest."
    
    context = memory.get_user_context(user_id)
    return context


def tool_remember_user_preference(user_id: str, preference_type: str, preference: str) -> Dict[str, Any]:
    """Remember a user's preference for future visits."""
    if not memory.is_available:
        return {"success": False, "message": "Memory system is not available."}
    
    try:
        if preference_type == "dietary":
            success = memory.remember_dietary_preference(user_id, preference)
        elif preference_type == "seating":
            success = memory.remember_seating_preference(user_id, preference)
        else:
            messages = [
                {"role": "user", "content": f"I prefer: {preference}"},
                {"role": "assistant", "content": f"I'll remember that preference."}
            ]
            result = memory.add_memory(messages, user_id, metadata={"info_type": "preference"})
            success = result is not None
        
        if success:
            return {"success": True, "message": f"I'll remember that you {preference}."}
        else:
            return {"success": False, "message": "Could not save the preference at this time."}
    except Exception as e:
        logger.error(f"Error remembering preference: {e}")
        return {"success": False, "message": "An error occurred while saving the preference."}


def tool_remember_user_name(user_id: str, name: str) -> Dict[str, Any]:
    """Remember a user's name for future interactions."""
    if not memory.is_available:
        return {"success": False, "message": "Memory system is not available."}
    
    success = memory.remember_user_name(user_id, name)
    
    if success:
        return {"success": True, "message": f"Nice to meet you, {name}! I'll remember your name."}
    else:
        return {"success": False, "message": "Could not save the name at this time."}


def tool_search_user_memories(user_id: str, query: str) -> str:
    """Search for specific information in a user's memories."""
    if not memory.is_available:
        return "Memory system is not available."
    
    results = memory.search_memories(query, user_id, limit=5)
    
    if results.count == 0:
        return f"No memories found for query: '{query}'"
    
    response_parts = [f"Found {results.count} relevant memories:"]
    for mem in results.memories:
        response_parts.append(f"- {mem.memory}")
    
    return "\n".join(response_parts)


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


def tool_get_restaurant_address() -> str:
    """Get the restaurant's address and location information."""
    address = kb.get_address()
    contact = kb.get_contact_info()
    
    return f"""Restaurant Address:
{address.full_address}

Google Maps: {address.google_maps_url}

Contact:
Phone: {contact.phone}
Email: {contact.email}
Website: {contact.website}"""


def tool_get_menu_info() -> str:
    """Get the restaurant's menu with all categories and items."""
    menu_text = kb.get_menu_formatted()
    menu_data = kb.get_menu()
    lunch = menu_data.get('lunch_menu', {})
    
    result = menu_text
    
    if lunch.get('available'):
        result += f"\n\n=== LUNCH SPECIAL ===\n"
        result += f"{lunch.get('description', '')}\n"
        result += f"Available: {', '.join(d.capitalize() for d in lunch.get('days', []))}\n"
        result += f"Hours: {lunch.get('hours', '')}\n"
        result += f"Price: EUR {lunch.get('price', 0):.2f}"
    
    return result


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


def tool_get_about_restaurant() -> str:
    """Get the 'About Us' story of the restaurant."""
    about = kb.get_about_us()
    
    story = about.get('story', {})
    chef = about.get('chef', {})
    values = about.get('values', [])
    
    result = f"=== {story.get('title', 'Our Story')} ===\n\n"
    result += '\n\n'.join(story.get('paragraphs', []))
    
    result += f"\n\n=== Meet Our Chef ===\n"
    result += f"{chef.get('name', '')} - {chef.get('title', '')}\n\n"
    result += f"{chef.get('bio', '')}\n\n"
    result += f'"{chef.get("philosophy", "")}"'
    
    if values:
        result += "\n\n=== Our Values ===\n"
        for value in values:
            result += f"\n{value.get('title', '')}: {value.get('description', '')}"
    
    return result


def tool_get_reservation_rules() -> str:
    """Get the restaurant's reservation rules and policies."""
    settings = kb.get_reservation_settings()
    
    return f"""Reservation Rules and Policies:

Guest Limits:
- Minimum guests per reservation: {settings.min_guests}
- Maximum guests per reservation: {settings.max_guests}
- For parties of {settings.large_party_threshold} or more: {settings.large_party_note}

Time Slots:
- Default reservation duration: {settings.default_time_slot_hours} hours
- Reservations must be made at least {settings.advance_booking_hours} hour(s) in advance
- Advance booking available up to {settings.max_advance_booking_days} days ahead

Note: Kitchen closes 1 hour before restaurant closing time.
Last reservation accepted 2 hours before closing."""


def tool_create_reservation(
    user_id: str,
    user_name: str,
    phone_number: str,
    number_of_guests: int,
    date: str,
    time: str,
    time_slot: float = 2.0
) -> Dict[str, Any]:
    """Create a new table reservation at the restaurant."""
    try:
        settings = kb.get_reservation_settings()
        
        if number_of_guests < settings.min_guests:
            return {
                "success": False,
                "message": f"Minimum {settings.min_guests} guest required for a reservation."
            }
        
        if number_of_guests > settings.max_guests:
            return {
                "success": False,
                "message": f"Maximum {settings.max_guests} guests per reservation. {settings.large_party_note}"
            }
        
        # Parse date
        try:
            parsed_date = parse_date_string(date)
        except ValueError as e:
            return {"success": False, "message": str(e)}
        
        # Parse time
        try:
            parsed_time = parse_time_string(time)
        except ValueError as e:
            return {"success": False, "message": str(e)}
        
        # Parse date and time
        reservation_datetime = datetime.strptime(f"{parsed_date} {parsed_time}", "%Y-%m-%d %H:%M")
        reservation_datetime = ZAGREB_TZ.localize(reservation_datetime)
        
        # Check if reservation is in the past
        now = datetime.now(ZAGREB_TZ)
        if reservation_datetime <= now:
            return {"success": False, "message": "Cannot make reservations for past dates/times."}
        
        # Check advance booking requirement
        hours_until = (reservation_datetime - now).total_seconds() / 3600
        if hours_until < settings.advance_booking_hours:
            return {
                "success": False,
                "message": f"Reservations must be made at least {settings.advance_booking_hours} hour(s) in advance."
            }
        
        # Check if restaurant is open on that day/time
        day_name = reservation_datetime.strftime('%A').lower()
        hours = kb.get_operating_hours(day_name)
        day_hours = hours.get(day_name)
        
        if day_hours.is_closed:
            return {
                "success": False,
                "message": f"Sorry, the restaurant is closed on {day_name.capitalize()}s."
            }
        
        # Parse operating hours
        open_time = datetime.strptime(day_hours.open, "%H:%M").time()
        close_time = datetime.strptime(day_hours.close, "%H:%M").time()
        reservation_time = reservation_datetime.time()
        
        # Handle midnight closing time
        closes_at_midnight = (close_time.hour == 0 and close_time.minute == 0)
        
        if closes_at_midnight:
            if reservation_time < open_time:
                return {
                    "success": False,
                    "message": f"Sorry, the restaurant opens at {day_hours.open} on {day_name.capitalize()}s."
                }
        else:
            if reservation_time < open_time or reservation_time >= close_time:
                return {
                    "success": False,
                    "message": f"Sorry, the restaurant is only open from {day_hours.open} to {day_hours.close} on {day_name.capitalize()}s."
                }
        
        # Create the reservation
        db = DatabaseManager.get_instance()
        time_created = now.strftime('%Y-%m-%d %H:%M:%S')
        
        reservation = db.create_reservation(
            user_id=user_id,
            user_name=user_name,
            phone_number=phone_number,
            number_of_guests=number_of_guests,
            date_time=reservation_datetime,
            time_slot=time_slot,
            time_created=time_created
        )
        
        if reservation:
            # Store in memory
            if memory.is_available:
                memory.remember_reservation(
                    user_id,
                    reservation.id,
                    reservation_datetime.strftime('%Y-%m-%d %H:%M'),
                    number_of_guests
                )
            
            return {
                "success": True,
                "message": f"Reservation confirmed! Your reservation ID is #{reservation.id}.",
                "reservation": {
                    "reservation_id": reservation.id,
                    "user_name": reservation.user_name,
                    "phone_number": reservation.phone_number,
                    "number_of_guests": reservation.number_of_guests,
                    "date_time": reservation.date_time.strftime('%Y-%m-%d %H:%M'),
                    "time_slot": reservation.time_slot,
                    "status": reservation.status
                }
            }
        else:
            return {"success": False, "message": "Failed to create reservation. Please try again."}
            
    except Exception as e:
        logger.error(f"Error creating reservation: {e}", exc_info=True)
        return {"success": False, "message": f"An error occurred: {str(e)}"}


def tool_get_reservation(reservation_id: int) -> Dict[str, Any]:
    """Get details of a specific reservation by ID."""
    try:
        db = DatabaseManager.get_instance()
        reservation = db.get_reservation(reservation_id)
        
        if reservation:
            return {
                "success": True,
                "reservation": {
                    "reservation_id": reservation.id,
                    "user_name": reservation.user_name,
                    "phone_number": reservation.phone_number,
                    "number_of_guests": reservation.number_of_guests,
                    "date_time": reservation.date_time.strftime('%Y-%m-%d %H:%M'),
                    "time_slot": reservation.time_slot,
                    "status": reservation.status
                }
            }
        else:
            return {"success": False, "message": f"No reservation found with ID #{reservation_id}."}
            
    except Exception as e:
        logger.error(f"Error getting reservation: {e}")
        return {"success": False, "message": f"An error occurred: {str(e)}"}


def tool_get_user_reservations(user_id: str) -> Dict[str, Any]:
    """Get all reservations for a specific user."""
    try:
        db = DatabaseManager.get_instance()
        reservations = db.get_user_reservations(user_id)
        
        return {
            "reservations": [
                {
                    "reservation_id": r.id,
                    "user_name": r.user_name,
                    "phone_number": r.phone_number,
                    "number_of_guests": r.number_of_guests,
                    "date_time": r.date_time.strftime('%Y-%m-%d %H:%M'),
                    "time_slot": r.time_slot,
                    "status": r.status
                }
                for r in reservations
            ],
            "count": len(reservations)
        }
    except Exception as e:
        logger.error(f"Error getting user reservations: {e}")
        return {"reservations": [], "count": 0, "error": str(e)}


def tool_cancel_reservation(reservation_id: int, user_id: str) -> Dict[str, Any]:
    """Cancel an existing reservation."""
    try:
        db = DatabaseManager.get_instance()
        reservation = db.get_reservation(reservation_id)
        
        if not reservation:
            return {"success": False, "message": f"No reservation found with ID #{reservation_id}."}
        
        if reservation.user_id != user_id:
            return {"success": False, "message": "You can only cancel your own reservations."}
        
        if reservation.status == 'cancelled':
            return {"success": False, "message": "This reservation is already cancelled."}
        
        success = db.cancel_reservation(reservation_id)
        
        if success:
            return {
                "success": True,
                "message": f"Reservation #{reservation_id} has been cancelled successfully."
            }
        else:
            return {"success": False, "message": "Failed to cancel reservation. Please try again."}
            
    except Exception as e:
        logger.error(f"Error cancelling reservation: {e}")
        return {"success": False, "message": f"An error occurred: {str(e)}"}


def tool_update_reservation(
    reservation_id: int,
    user_id: str,
    new_date: Optional[str] = None,
    new_time: Optional[str] = None,
    new_guests: Optional[int] = None
) -> Dict[str, Any]:
    """Update an existing reservation."""
    try:
        db = DatabaseManager.get_instance()
        reservation = db.get_reservation(reservation_id)
        
        if not reservation:
            return {"success": False, "message": f"No reservation found with ID #{reservation_id}."}
        
        if reservation.user_id != user_id:
            return {"success": False, "message": "You can only modify your own reservations."}
        
        if reservation.status == 'cancelled':
            return {"success": False, "message": "Cannot modify a cancelled reservation."}
        
        # Prepare updates
        updates = {}
        
        if new_guests is not None:
            settings = kb.get_reservation_settings()
            if new_guests < settings.min_guests or new_guests > settings.max_guests:
                return {
                    "success": False,
                    "message": f"Number of guests must be between {settings.min_guests} and {settings.max_guests}."
                }
            updates['number_of_guests'] = new_guests
        
        if new_date or new_time:
            current_date = reservation.date_time.strftime('%Y-%m-%d')
            current_time = reservation.date_time.strftime('%H:%M')
            
            # Parse new date if provided
            if new_date:
                try:
                    parsed_date = parse_date_string(new_date)
                except ValueError as e:
                    return {"success": False, "message": str(e)}
            else:
                parsed_date = current_date
            
            # Parse new time if provided
            if new_time:
                try:
                    parsed_time = parse_time_string(new_time)
                except ValueError as e:
                    return {"success": False, "message": str(e)}
            else:
                parsed_time = current_time
            
            new_datetime = datetime.strptime(f"{parsed_date} {parsed_time}", "%Y-%m-%d %H:%M")
            new_datetime = ZAGREB_TZ.localize(new_datetime)
            
            # Validate new datetime
            now = datetime.now(ZAGREB_TZ)
            if new_datetime <= now:
                return {"success": False, "message": "Cannot set reservation to a past date/time."}
            
            # Check operating hours
            day_name = new_datetime.strftime('%A').lower()
            hours = kb.get_operating_hours(day_name)
            day_hours = hours.get(day_name)
            
            if day_hours.is_closed:
                return {
                    "success": False,
                    "message": f"Sorry, the restaurant is closed on {day_name.capitalize()}s."
                }
            
            open_time = datetime.strptime(day_hours.open, "%H:%M").time()
            close_time = datetime.strptime(day_hours.close, "%H:%M").time()
            reservation_time = new_datetime.time()
            
            closes_at_midnight = (close_time.hour == 0 and close_time.minute == 0)
            
            if closes_at_midnight:
                if reservation_time < open_time:
                    return {
                        "success": False,
                        "message": f"Sorry, the restaurant opens at {day_hours.open} on {day_name.capitalize()}s."
                    }
            else:
                if reservation_time < open_time or reservation_time >= close_time:
                    return {
                        "success": False,
                        "message": f"Sorry, the restaurant is only open from {day_hours.open} to {day_hours.close} on {day_name.capitalize()}s."
                    }
            
            updates['date_time'] = new_datetime
        
        if not updates:
            return {"success": False, "message": "No changes specified."}
        
        success = db.update_reservation(reservation_id, **updates)
        
        if success:
            updated = db.get_reservation(reservation_id)
            return {
                "success": True,
                "message": f"Reservation #{reservation_id} has been updated successfully.",
                "reservation": {
                    "reservation_id": updated.id,
                    "user_name": updated.user_name,
                    "phone_number": updated.phone_number,
                    "number_of_guests": updated.number_of_guests,
                    "date_time": updated.date_time.strftime('%Y-%m-%d %H:%M'),
                    "time_slot": updated.time_slot,
                    "status": updated.status
                }
            }
        else:
            return {"success": False, "message": "Failed to update reservation. Please try again."}
            
    except Exception as e:
        logger.error(f"Error updating reservation: {e}")
        return {"success": False, "message": f"An error occurred: {str(e)}"}


def tool_check_availability(date: str) -> str:
    """Check table availability for a specific date."""
    try:
        # Parse date
        try:
            parsed_date = parse_date_string(date)
        except ValueError as e:
            return str(e)
        
        target_date = datetime.strptime(parsed_date, '%Y-%m-%d').date()
        day_name = target_date.strftime('%A').lower()
        
        hours = kb.get_operating_hours(day_name)
        day_hours = hours.get(day_name)
        
        if day_hours.is_closed:
            return f"The restaurant is closed on {day_name.capitalize()}s."
        
        db = DatabaseManager.get_instance()
        reservations = db.get_reservations_by_date(target_date)
        
        confirmed = [r for r in reservations if r.status == 'confirmed']
        
        summary = f"Availability for {parsed_date} ({day_name.capitalize()}):\n"
        summary += f"Operating hours: {day_hours.open} - {day_hours.close}\n\n"
        
        if not confirmed:
            summary += "All time slots are currently available!"
        else:
            summary += f"Current reservations ({len(confirmed)}):\n"
            for r in confirmed:
                end_time = r.date_time.hour + r.time_slot
                summary += f"- {r.date_time.strftime('%H:%M')} - {int(end_time):02d}:{int((end_time % 1) * 60):02d} ({r.number_of_guests} guests)\n"
        
        return summary
        
    except Exception as e:
        return f"An error occurred while checking availability: {str(e)}"


# ============================================================================
# Tool Definitions for Responses API
# ============================================================================

TOOLS = [
    {
        "type": "function",
        "name": "get_current_datetime",
        "description": "Get the current date and time for CET:Zagreb timezone. Call this at the start of each session.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "recall_user_info",
        "description": "Recall what we know about a user from memory. Use this at the start of a conversation to personalize the interaction.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The unique identifier for the user (phone number or contact ID)"
                }
            },
            "required": ["user_id"],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "remember_user_preference",
        "description": "Remember a user's preference for future visits. Use when a user mentions dietary restrictions, seating preferences, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The unique identifier for the user"},
                "preference_type": {"type": "string", "enum": ["dietary", "seating", "general"], "description": "Type of preference"},
                "preference": {"type": "string", "description": "The preference to remember"}
            },
            "required": ["user_id", "preference_type", "preference"],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "remember_user_name",
        "description": "Remember a user's name for future interactions.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The unique identifier for the user"},
                "name": {"type": "string", "description": "The user's name"}
            },
            "required": ["user_id", "name"],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "search_user_memories",
        "description": "Search for specific information in a user's memories.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The unique identifier for the user"},
                "query": {"type": "string", "description": "What to search for in the user's memories"}
            },
            "required": ["user_id", "query"],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "get_restaurant_info",
        "description": "Get general information about the restaurant including name, description, address, and contact details.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "get_operating_hours",
        "description": "Get the restaurant's operating hours for all days of the week.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "get_restaurant_address",
        "description": "Get the restaurant's address and location information.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "get_menu_info",
        "description": "Get the restaurant's menu with all categories and items.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "search_menu",
        "description": "Search the menu for specific items by name, description, or dietary tags.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term (e.g., 'vegetarian', 'fish', 'truffle')"}
            },
            "required": ["query"],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "get_about_restaurant",
        "description": "Get the 'About Us' story of the restaurant including history, chef info, and values.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "get_reservation_rules",
        "description": "Get the restaurant's reservation rules and policies.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "create_reservation",
        "description": "Create a new table reservation. Date supports 'today', 'tomorrow', day names, or YYYY-MM-DD. Time supports 12-hour (7pm) or 24-hour (19:00) formats.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "Unique identifier for the user"},
                "user_name": {"type": "string", "description": "Name of the guest"},
                "phone_number": {"type": "string", "description": "Contact phone number"},
                "number_of_guests": {"type": "integer", "description": "Number of guests"},
                "date": {"type": "string", "description": "Date - 'today', 'tomorrow', day name, or YYYY-MM-DD"},
                "time": {"type": "string", "description": "Time - '7pm', '7:30pm', '19:00', etc."},
                "time_slot": {"type": "number", "description": "Duration in hours (default 2.0)"}
            },
            "required": ["user_id", "user_name", "phone_number", "number_of_guests", "date", "time"],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "get_reservation",
        "description": "Get details of a specific reservation by ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "reservation_id": {"type": "integer", "description": "The reservation ID"}
            },
            "required": ["reservation_id"],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "get_user_reservations",
        "description": "Get all reservations for a specific user.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's identifier"}
            },
            "required": ["user_id"],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "cancel_reservation",
        "description": "Cancel an existing reservation.",
        "parameters": {
            "type": "object",
            "properties": {
                "reservation_id": {"type": "integer", "description": "The reservation ID"},
                "user_id": {"type": "string", "description": "The user's identifier (for verification)"}
            },
            "required": ["reservation_id", "user_id"],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "update_reservation",
        "description": "Update an existing reservation (date, time, or number of guests).",
        "parameters": {
            "type": "object",
            "properties": {
                "reservation_id": {"type": "integer", "description": "The reservation ID"},
                "user_id": {"type": "string", "description": "The user's identifier (for verification)"},
                "new_date": {"type": "string", "description": "New date (optional)"},
                "new_time": {"type": "string", "description": "New time (optional)"},
                "new_guests": {"type": "integer", "description": "New number of guests (optional)"}
            },
            "required": ["reservation_id", "user_id"],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "check_availability",
        "description": "Check table availability for a specific date.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date to check - 'today', 'tomorrow', day name, or YYYY-MM-DD"}
            },
            "required": ["date"],
            "additionalProperties": False
        },
        "strict": True
    }
]


# ============================================================================
# Tool Execution
# ============================================================================

def execute_tool(name: str, arguments: Dict[str, Any]) -> Any:
    """Execute a tool by name with the given arguments."""
    tool_map = {
        "get_current_datetime": lambda args: tool_get_current_datetime(),
        "recall_user_info": lambda args: tool_recall_user_info(args["user_id"]),
        "remember_user_preference": lambda args: tool_remember_user_preference(args["user_id"], args["preference_type"], args["preference"]),
        "remember_user_name": lambda args: tool_remember_user_name(args["user_id"], args["name"]),
        "search_user_memories": lambda args: tool_search_user_memories(args["user_id"], args["query"]),
        "get_restaurant_info": lambda args: tool_get_restaurant_info(),
        "get_operating_hours": lambda args: tool_get_operating_hours(),
        "get_restaurant_address": lambda args: tool_get_restaurant_address(),
        "get_menu_info": lambda args: tool_get_menu_info(),
        "search_menu": lambda args: tool_search_menu(args["query"]),
        "get_about_restaurant": lambda args: tool_get_about_restaurant(),
        "get_reservation_rules": lambda args: tool_get_reservation_rules(),
        "create_reservation": lambda args: tool_create_reservation(
            args["user_id"], args["user_name"], args["phone_number"],
            args["number_of_guests"], args["date"], args["time"],
            args.get("time_slot", 2.0)
        ),
        "get_reservation": lambda args: tool_get_reservation(args["reservation_id"]),
        "get_user_reservations": lambda args: tool_get_user_reservations(args["user_id"]),
        "cancel_reservation": lambda args: tool_cancel_reservation(args["reservation_id"], args["user_id"]),
        "update_reservation": lambda args: tool_update_reservation(
            args["reservation_id"], args["user_id"],
            args.get("new_date"), args.get("new_time"), args.get("new_guests")
        ),
        "check_availability": lambda args: tool_check_availability(args["date"])
    }
    
    if name not in tool_map:
        return {"error": f"Unknown tool: {name}"}
    
    try:
        result = tool_map[name](arguments)
        return result
    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}", exc_info=True)
        return {"error": str(e)}


# ============================================================================
# System Instructions
# ============================================================================

def get_system_instructions() -> str:
    """Get the system instructions for the booking agent."""
    restaurant_name = kb.get_restaurant_name()
    settings = kb.get_reservation_settings()
    memory_status = "enabled" if memory.is_available else "disabled (MEM0_API_KEY not set)"
    
    return f"""You are a friendly and professional restaurant booking assistant for {restaurant_name}.
Your role is to help customers make, view, modify, and cancel table reservations, as well as provide information about the restaurant.

IMPORTANT: At the start of EVERY conversation, you MUST:
1. Call the get_current_datetime tool to know the current date and time in CET:Zagreb timezone
2. Call the recall_user_info tool with the user's ID to check if we have any previous information about them

Memory System Status: {memory_status}

You have access to the restaurant's knowledge base with information about:
- Restaurant details (name, description, address, contact)
- Operating hours for each day of the week
- Full menu with prices and dietary information
- About us / restaurant story
- Reservation rules and policies

You also have access to a memory system (Mem0) that allows you to:
- Remember user names, preferences, and dietary restrictions
- Recall previous interactions with returning guests
- Personalize the experience based on past visits

When helping customers with reservations:
1. Always be polite and helpful
2. If this is a returning guest (recall_user_info returns information), greet them by name and acknowledge their preferences
3. Collect all necessary information: name, phone number, number of guests, preferred date and time
4. If the user mentions any preferences (dietary, seating, etc.), use remember_user_preference to save them
5. Confirm all details before making a reservation
6. Provide the reservation ID after successful booking

Reservation Rules (from knowledge base):
- Minimum {settings.min_guests} guest, maximum {settings.max_guests} guests per reservation
- Default time slot is {settings.default_time_slot_hours} hours
- Reservations must be made at least {settings.advance_booking_hours} hour(s) in advance
- Phone number is required for all reservations
- {settings.large_party_note}

When a user wants to make a reservation:
1. First call get_current_datetime to know the current date/time
2. Call recall_user_info to check for returning guest information
3. If returning guest, greet them and pre-fill known information
4. Ask for any missing information (name, phone, guests, date/time)
5. Remember any new preferences mentioned
6. Confirm all details before creating the reservation
7. Use the create_reservation tool to complete the booking

When users ask about the restaurant:
- Use get_restaurant_info for general information
- Use get_operating_hours for business hours
- Use get_restaurant_address for location and directions
- Use get_menu_info for the full menu
- Use search_menu to find specific dishes or dietary options
- Use get_about_restaurant for the restaurant's story
- Use get_reservation_rules for booking policies

Memory Tools:
- Use recall_user_info at the start of conversations to personalize the experience
- Use remember_user_name when a user introduces themselves
- Use remember_user_preference when users mention dietary restrictions, seating preferences, or other preferences
- Use search_user_memories to find specific information about a user

Always respond in a natural, conversational manner while being efficient and helpful.
Only provide information that is available from your tools - do not make up or hallucinate information.
If you don't have information about a user in memory, simply ask them - don't pretend to remember."""


# ============================================================================
# Main Agent Function - Using Responses API
# ============================================================================

def process_booking_message(
    message: str,
    user_id: str,
    conversation_history: List[Dict] = None,
    user_name: str = None,
    phone_number: str = None
) -> tuple[str, List[Dict]]:
    """
    Process a booking message using OpenAI Responses API.
    
    Args:
        message: The user's message text
        user_id: Unique identifier for the user (phone number or contact ID)
        conversation_history: Previous conversation history
        user_name: User's name (optional)
        phone_number: User's phone number (optional)
        
    Returns:
        Tuple of (agent_response, updated_conversation_history)
    """
    if conversation_history is None:
        conversation_history = []
    
    # Add user message to history
    conversation_history.append({
        "role": "user",
        "content": message
    })
    
    # Build input for the API
    input_items = conversation_history.copy()
    
    # Add context about the user for new conversations
    if len(conversation_history) == 1 and (user_name or phone_number):
        context = f"[Context: User ID: {user_id}"
        if user_name:
            context += f", Name: {user_name}"
        if phone_number:
            context += f", Phone: {phone_number}"
        context += "]"
        input_items.insert(0, {"role": "system", "content": context})
    
    try:
        # Make initial API request
        response = client.responses.create(
            model="gpt-4.1-mini",  # Fast and cost-effective
            instructions=get_system_instructions(),
            tools=TOOLS,
            input=input_items
        )
        
        # Process tool calls in a loop
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # Check if there are any function calls in the output
            function_calls = [item for item in response.output if item.type == "function_call"]
            
            if not function_calls:
                # No more function calls, we have the final response
                break
            
            # Add all outputs to input for next request
            input_items.extend([item.model_dump() for item in response.output])
            
            # Execute each function call and add results
            for call in function_calls:
                logger.info(f"Executing tool: {call.name} with args: {call.arguments}")
                
                # Parse arguments and execute
                args = json.loads(call.arguments) if call.arguments else {}
                result = execute_tool(call.name, args)
                
                logger.info(f"Tool {call.name} result: {str(result)[:200]}...")
                
                # Add function output
                input_items.append({
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result) if not isinstance(result, str) else result
                })
            
            # Make next API request with function outputs
            response = client.responses.create(
                model="gpt-4.1-mini",
                instructions=get_system_instructions(),
                tools=TOOLS,
                input=input_items
            )
        
        # Get the final text response
        agent_response = response.output_text or "I apologize, but I couldn't generate a response. Please try again."
        
        # Update conversation history with assistant response
        conversation_history.append({
            "role": "assistant",
            "content": agent_response
        })
        
        # Store in memory if available
        if memory.is_available:
            memory.store_conversation_memory(user_id, message, agent_response)
        
        logger.info(f"Agent response for user {user_id}: {agent_response[:100]}...")
        return agent_response, conversation_history
        
    except Exception as e:
        logger.error(f"Error processing booking message: {e}", exc_info=True)
        error_response = f"I apologize, but I encountered an error: {str(e)}. Please try again."
        conversation_history.append({
            "role": "assistant",
            "content": error_response
        })
        return error_response, conversation_history


# ============================================================================
# Conversation History Management
# ============================================================================

# Store conversation histories by user_id
_conversation_histories: Dict[str, List[Dict]] = {}


def get_or_create_history(user_id: str) -> List[Dict]:
    """Get or create conversation history for a user."""
    if user_id not in _conversation_histories:
        _conversation_histories[user_id] = []
        logger.info(f"New conversation started for user: {user_id}")
    return _conversation_histories[user_id]


def update_history(user_id: str, history: List[Dict]) -> None:
    """Update conversation history for a user."""
    # Limit history size to prevent memory issues (keep last 20 exchanges = 40 messages)
    if len(history) > 40:
        history = history[-40:]
    _conversation_histories[user_id] = history


def clear_user_conversation(user_id: str) -> bool:
    """Clear conversation history for a specific user."""
    if user_id in _conversation_histories:
        del _conversation_histories[user_id]
        return True
    return False


def get_active_conversations() -> List[str]:
    """Get list of active conversation user IDs."""
    return list(_conversation_histories.keys())


# ============================================================================
# Wrapper for Chatwoot Integration
# ============================================================================

def process_chatwoot_message(
    message: str,
    user_id: str,
    user_name: str = None,
    phone_number: str = None
) -> str:
    """
    Process a message from Chatwoot webhook.
    
    This is the main entry point for Chatwoot integration.
    Maintains conversation history per user.
    
    Args:
        message: The user's message text
        user_id: Unique identifier for the user
        user_name: User's name (optional)
        phone_number: User's phone number (optional)
        
    Returns:
        Agent's response text
    """
    # Get existing history
    history = get_or_create_history(user_id)
    
    # Process message
    response, updated_history = process_booking_message(
        message=message,
        user_id=user_id,
        conversation_history=history,
        user_name=user_name,
        phone_number=phone_number
    )
    
    # Update stored history
    update_history(user_id, updated_history)
    
    return response


# ============================================================================
# Test Function
# ============================================================================

if __name__ == "__main__":
    print("Testing Restaurant Booking Agent with Responses API...")
    print("-" * 50)
    
    # Test getting current datetime
    print("\n1. Testing get_current_datetime tool:")
    dt_info = tool_get_current_datetime()
    print(f"   Current datetime: {dt_info['full_datetime']}")
    
    # Test memory availability
    print("\n2. Testing Mem0 Memory:")
    print(f"   Memory available: {memory.is_available}")
    
    # Test knowledge base tools
    print("\n3. Testing get_restaurant_info tool:")
    info = tool_get_restaurant_info()
    print(f"   Restaurant: {info['name']}")
    print(f"   Address: {info['address']}")
    print(f"   Currently open: {info['is_currently_open']}")
    
    print("\n4. Testing get_operating_hours tool:")
    hours = tool_get_operating_hours()
    print(f"   Today's hours: {hours['today_hours']}")
    print(f"   Status: {hours['current_status']}")
    
    print("\n5. Testing search_menu tool:")
    results = tool_search_menu("truffle")
    print(f"   Found {results['count']} items with 'truffle'")
    for item in results['results'][:2]:
        print(f"   - {item['name']}: EUR {item['price']}")
    
    # Test conversation
    print("\n6. Testing agent conversation:")
    response, history = process_booking_message(
        "What are your opening hours?",
        "test_user_123"
    )
    print(f"   Agent: {response[:200]}...")
