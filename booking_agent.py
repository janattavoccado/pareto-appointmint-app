"""
Restaurant Booking Agent using OpenAI Agents SDK.
Handles table reservations with CET:Zagreb timezone support.
Integrates with knowledge base for restaurant information.
Integrates with Mem0 for persistent user memory across sessions.
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Annotated, Optional, List
import pytz

from pydantic import BaseModel, Field
from agents import Agent, Runner, function_tool

from models import DatabaseManager, Reservation
from knowledgebase_manager import KnowledgeBaseManager
from memory_manager import Mem0MemoryManager, MemorySearchResult, UserMemoryProfile

# Configure logging
logger = logging.getLogger(__name__)

# CET:Zagreb timezone
ZAGREB_TZ = pytz.timezone('Europe/Zagreb')


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
    - 24-hour format: "19:00", "19:30", "9:00"
    - 12-hour format: "7pm", "7:30pm", "7 pm", "7:30 pm", "7PM", "7:30 PM"
    - 12-hour with am/pm: "7:00am", "11:30 AM", "12pm", "12:00am"
    
    Returns:
        str: Time in HH:MM format (24-hour)
    
    Raises:
        ValueError: If the time format cannot be parsed
    """
    if not time_str:
        raise ValueError("Time string is empty")
    
    # Clean up the input
    time_str = time_str.strip().lower()
    
    # Pattern for 12-hour format: 7pm, 7:30pm, 7 pm, 7:30 pm, etc.
    pattern_12h = r'^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$'
    match = re.match(pattern_12h, time_str)
    
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        period = match.group(3)
        
        # Validate hour and minute
        if hour < 1 or hour > 12:
            raise ValueError(f"Invalid hour in 12-hour format: {hour}")
        if minute < 0 or minute > 59:
            raise ValueError(f"Invalid minute: {minute}")
        
        # Convert to 24-hour format
        if period == 'am':
            if hour == 12:
                hour = 0  # 12am is midnight (00:00)
        else:  # pm
            if hour != 12:
                hour += 12  # 1pm-11pm -> 13-23
            # 12pm stays as 12
        
        return f"{hour:02d}:{minute:02d}"
    
    # Pattern for 24-hour format: 19:00, 9:00, 09:00
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


# Initialize knowledge base
kb = KnowledgeBaseManager.get_instance()

# Initialize memory manager
memory = Mem0MemoryManager.get_instance()


# ============================================================================
# Pydantic Models for Structured Outputs
# ============================================================================

class DateTimeInfo(BaseModel):
    """Current date and time information for CET:Zagreb timezone."""
    current_date: str = Field(description="Current date in YYYY-MM-DD format")
    current_time: str = Field(description="Current time in HH:MM format")
    day_of_week: str = Field(description="Day of the week (e.g., Monday)")
    timezone: str = Field(description="Timezone name")
    full_datetime: str = Field(description="Full datetime string")


class ReservationDetails(BaseModel):
    """Details of a reservation."""
    reservation_id: int = Field(description="Unique reservation ID")
    user_name: str = Field(description="Name of the guest")
    phone_number: str = Field(description="Contact phone number")
    number_of_guests: int = Field(description="Number of guests")
    date_time: str = Field(description="Reservation date and time")
    time_slot: float = Field(description="Duration of reservation in hours")
    status: str = Field(description="Reservation status")


class ReservationResult(BaseModel):
    """Result of a reservation operation."""
    success: bool = Field(description="Whether the operation was successful")
    message: str = Field(description="Result message")
    reservation: Optional[ReservationDetails] = Field(default=None, description="Reservation details if successful")


class ReservationsList(BaseModel):
    """List of reservations."""
    reservations: list[ReservationDetails] = Field(description="List of reservations")
    count: int = Field(description="Total number of reservations")


class RestaurantInfoResponse(BaseModel):
    """Restaurant information response."""
    name: str = Field(description="Restaurant name")
    tagline: str = Field(description="Restaurant tagline")
    description: str = Field(description="Restaurant description")
    address: str = Field(description="Full address")
    phone: str = Field(description="Contact phone number")
    email: str = Field(description="Contact email")
    website: str = Field(description="Website URL")
    is_currently_open: bool = Field(description="Whether the restaurant is currently open")
    current_status: str = Field(description="Current opening status message")


class OperatingHoursResponse(BaseModel):
    """Operating hours response."""
    hours_formatted: str = Field(description="Formatted operating hours for all days")
    is_currently_open: bool = Field(description="Whether the restaurant is currently open")
    current_status: str = Field(description="Current opening status message")
    today_hours: str = Field(description="Today's operating hours")


class MenuItemInfo(BaseModel):
    """Menu item information."""
    name: str = Field(description="Item name")
    description: str = Field(description="Item description")
    price: float = Field(description="Item price")
    tags: List[str] = Field(description="Dietary tags (vegetarian, vegan, gluten_free)")


class MenuSearchResponse(BaseModel):
    """Menu search response."""
    query: str = Field(description="Search query")
    results: List[MenuItemInfo] = Field(description="Matching menu items")
    count: int = Field(description="Number of results found")


class MemoryResponse(BaseModel):
    """Response from memory operations."""
    success: bool = Field(description="Whether the operation was successful")
    message: str = Field(description="Result message")
    data: Optional[str] = Field(default=None, description="Retrieved data if applicable")


# ============================================================================
# Agent Tools - Date/Time
# ============================================================================

@function_tool
def get_current_datetime() -> DateTimeInfo:
    """
    Get the current date and time for CET:Zagreb timezone.
    This tool should be called at the start of each session to know the current date and time.
    """
    now = datetime.now(ZAGREB_TZ)
    return DateTimeInfo(
        current_date=now.strftime('%Y-%m-%d'),
        current_time=now.strftime('%H:%M'),
        day_of_week=now.strftime('%A'),
        timezone='Europe/Zagreb (CET)',
        full_datetime=now.strftime('%Y-%m-%d %H:%M:%S %Z')
    )


# ============================================================================
# Agent Tools - Memory (Mem0)
# ============================================================================

@function_tool
def recall_user_info(
    user_id: Annotated[str, "The unique identifier for the user (phone number or contact ID)"]
) -> str:
    """
    Recall what we know about a user from memory.
    Use this at the start of a conversation to personalize the interaction.
    This retrieves the user's name, preferences, dietary restrictions, and past interactions.
    """
    if not memory.is_available:
        return "Memory system is not available. Treating as a new guest."
    
    context = memory.get_user_context(user_id)
    return context


@function_tool
def remember_user_preference(
    user_id: Annotated[str, "The unique identifier for the user"],
    preference_type: Annotated[str, "Type of preference: 'dietary', 'seating', 'general'"],
    preference: Annotated[str, "The preference to remember (e.g., 'vegetarian', 'window seat', 'quiet area')"]
) -> MemoryResponse:
    """
    Remember a user's preference for future visits.
    Use this when a user mentions a preference, dietary restriction, or special request.
    """
    if not memory.is_available:
        return MemoryResponse(
            success=False,
            message="Memory system is not available."
        )
    
    try:
        if preference_type == "dietary":
            success = memory.remember_dietary_preference(user_id, preference)
        elif preference_type == "seating":
            success = memory.remember_seating_preference(user_id, preference)
        else:
            # General preference
            messages = [
                {"role": "user", "content": f"I prefer: {preference}"},
                {"role": "assistant", "content": f"I'll remember that preference."}
            ]
            result = memory.add_memory(messages, user_id, metadata={"info_type": "preference"})
            success = result is not None
        
        if success:
            return MemoryResponse(
                success=True,
                message=f"I'll remember that you {preference}."
            )
        else:
            return MemoryResponse(
                success=False,
                message="Could not save the preference at this time."
            )
    except Exception as e:
        logger.error(f"Error remembering preference: {e}")
        return MemoryResponse(
            success=False,
            message="An error occurred while saving the preference."
        )


@function_tool
def remember_user_name(
    user_id: Annotated[str, "The unique identifier for the user"],
    name: Annotated[str, "The user's name"]
) -> MemoryResponse:
    """
    Remember a user's name for future interactions.
    Use this when a user introduces themselves or provides their name.
    """
    if not memory.is_available:
        return MemoryResponse(
            success=False,
            message="Memory system is not available."
        )
    
    success = memory.remember_user_name(user_id, name)
    
    if success:
        return MemoryResponse(
            success=True,
            message=f"Nice to meet you, {name}! I'll remember your name."
        )
    else:
        return MemoryResponse(
            success=False,
            message="Could not save the name at this time."
        )


@function_tool
def search_user_memories(
    user_id: Annotated[str, "The unique identifier for the user"],
    query: Annotated[str, "What to search for in the user's memories"]
) -> str:
    """
    Search for specific information in a user's memories.
    Use this to find specific details about a user's past interactions or preferences.
    """
    if not memory.is_available:
        return "Memory system is not available."
    
    results = memory.search_memories(query, user_id, limit=5)
    
    if results.count == 0:
        return f"No memories found for query: '{query}'"
    
    response_parts = [f"Found {results.count} relevant memories:"]
    for mem in results.memories:
        response_parts.append(f"- {mem.memory}")
    
    return "\n".join(response_parts)


# ============================================================================
# Agent Tools - Knowledge Base (Restaurant Info)
# ============================================================================

@function_tool
def get_restaurant_info() -> RestaurantInfoResponse:
    """
    Get general information about the restaurant including name, description, address, and contact details.
    Use this tool when users ask about the restaurant, its location, or how to contact them.
    """
    info = kb.get_restaurant_info_for_agent()
    is_open, status_message = kb.is_restaurant_open()
    
    return RestaurantInfoResponse(
        name=info.name,
        tagline=info.tagline,
        description=info.description,
        address=info.full_address,
        phone=info.phone,
        email=info.email,
        website=info.website,
        is_currently_open=is_open,
        current_status=status_message
    )


@function_tool
def get_operating_hours() -> OperatingHoursResponse:
    """
    Get the restaurant's operating hours for all days of the week.
    Use this tool when users ask about opening hours, when the restaurant is open, or business hours.
    """
    hours_formatted = kb.get_operating_hours_formatted()
    is_open, status_message = kb.is_restaurant_open()
    
    # Get today's hours
    now = datetime.now(ZAGREB_TZ)
    day_name = now.strftime('%A').lower()
    hours = kb.get_operating_hours(day_name)
    day_hours = hours.get(day_name)
    
    today_hours = "Closed" if day_hours.is_closed else f"{day_hours.open} - {day_hours.close}"
    
    return OperatingHoursResponse(
        hours_formatted=hours_formatted,
        is_currently_open=is_open,
        current_status=status_message,
        today_hours=today_hours
    )


@function_tool
def get_restaurant_address() -> str:
    """
    Get the restaurant's address and location information.
    Use this tool when users ask for directions, location, or where the restaurant is located.
    """
    address = kb.get_address()
    contact = kb.get_contact_info()
    
    return f"""Restaurant Address:
{address.full_address}

Google Maps: {address.google_maps_url}

Contact:
Phone: {contact.phone}
Email: {contact.email}
Website: {contact.website}"""


@function_tool
def get_menu_info() -> str:
    """
    Get the restaurant's menu with all categories and items.
    Use this tool when users ask about the menu, what food is available, or prices.
    """
    menu_text = kb.get_menu_formatted()
    
    # Add lunch special info
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


@function_tool
def search_menu(
    query: Annotated[str, "Search term to find menu items (e.g., 'vegetarian', 'fish', 'truffle')"]
) -> MenuSearchResponse:
    """
    Search the menu for specific items by name, description, or dietary tags.
    Use this tool when users ask about specific dishes, ingredients, or dietary options.
    """
    results = kb.search_menu(query)
    
    return MenuSearchResponse(
        query=query,
        results=[
            MenuItemInfo(
                name=item.name,
                description=item.description,
                price=item.price,
                tags=item.tags
            )
            for item in results
        ],
        count=len(results)
    )


@function_tool
def get_about_restaurant() -> str:
    """
    Get the 'About Us' story of the restaurant including history, chef info, and values.
    Use this tool when users ask about the restaurant's story, history, chef, or philosophy.
    """
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


@function_tool
def get_reservation_rules() -> str:
    """
    Get the restaurant's reservation rules and policies.
    Use this tool when users ask about booking policies, guest limits, or reservation requirements.
    """
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


# ============================================================================
# Agent Tools - Reservations
# ============================================================================

@function_tool
def create_reservation(
    user_id: Annotated[str, "Unique identifier for the user (phone number or contact ID)"],
    user_name: Annotated[str, "Name of the guest making the reservation"],
    phone_number: Annotated[str, "Contact phone number for the reservation"],
    number_of_guests: Annotated[int, "Number of guests for the reservation"],
    date: Annotated[str, "Date of the reservation - supports 'today', 'tomorrow', day names like 'friday', or YYYY-MM-DD format"],
    time: Annotated[str, "Time of the reservation - supports both 12-hour (7pm, 7:30pm) and 24-hour (19:00) formats"],
    time_slot: Annotated[float, "Duration of the reservation in hours (default 2.0)"] = 2.0
) -> ReservationResult:
    """
    Create a new table reservation at the restaurant.
    Use this tool after collecting all required information from the guest.
    Date can be provided as 'today', 'tomorrow', a day name like 'friday', or in YYYY-MM-DD format.
    Time can be provided in either 12-hour format (7pm, 7:30pm) or 24-hour format (19:00).
    """
    try:
        # Validate inputs
        settings = kb.get_reservation_settings()
        
        if number_of_guests < settings.min_guests:
            return ReservationResult(
                success=False,
                message=f"Minimum {settings.min_guests} guest required for a reservation."
            )
        
        if number_of_guests > settings.max_guests:
            return ReservationResult(
                success=False,
                message=f"Maximum {settings.max_guests} guests per reservation. {settings.large_party_note}"
            )
        
        # Parse date - supports natural language like 'today', 'tomorrow', 'friday', etc.
        try:
            parsed_date = parse_date_string(date)
        except ValueError as e:
            return ReservationResult(
                success=False,
                message=str(e)
            )
        
        # Parse time - supports both 12-hour (7pm) and 24-hour (19:00) formats
        try:
            parsed_time = parse_time_string(time)
        except ValueError as e:
            return ReservationResult(
                success=False,
                message=str(e)
            )
        
        # Parse date and time
        reservation_datetime = datetime.strptime(f"{parsed_date} {parsed_time}", "%Y-%m-%d %H:%M")
        reservation_datetime = ZAGREB_TZ.localize(reservation_datetime)
        
        # Check if reservation is in the past
        now = datetime.now(ZAGREB_TZ)
        if reservation_datetime <= now:
            return ReservationResult(
                success=False,
                message="Cannot make reservations for past dates/times."
            )
        
        # Check advance booking requirement
        hours_until = (reservation_datetime - now).total_seconds() / 3600
        if hours_until < settings.advance_booking_hours:
            return ReservationResult(
                success=False,
                message=f"Reservations must be made at least {settings.advance_booking_hours} hour(s) in advance."
            )
        
        # Check if restaurant is open on that day/time
        day_name = reservation_datetime.strftime('%A').lower()
        hours = kb.get_operating_hours(day_name)
        day_hours = hours.get(day_name)
        
        if day_hours.is_closed:
            return ReservationResult(
                success=False,
                message=f"Sorry, the restaurant is closed on {day_name.capitalize()}s."
            )
        
        # Check if time is within operating hours
        open_time = datetime.strptime(day_hours.open, "%H:%M").time()
        close_time = datetime.strptime(day_hours.close, "%H:%M").time()
        reservation_time = reservation_datetime.time()
        
        # Handle midnight closing time (00:00 means end of day, not start)
        # If close_time is 00:00, it means the restaurant closes at midnight
        # In this case, any time after open_time is valid
        closes_at_midnight = (close_time.hour == 0 and close_time.minute == 0)
        
        if closes_at_midnight:
            # Restaurant closes at midnight - only check if after opening time
            if reservation_time < open_time:
                return ReservationResult(
                    success=False,
                    message=f"Reservations are only available during operating hours: {day_hours.open} - {day_hours.close} (midnight)"
                )
        else:
            # Normal hours - check both open and close times
            if reservation_time < open_time or reservation_time >= close_time:
                return ReservationResult(
                    success=False,
                    message=f"Reservations are only available during operating hours: {day_hours.open} - {day_hours.close}"
                )
        
        # Get current timestamp for time_created
        time_created = datetime.now(ZAGREB_TZ)
        
        # Create the reservation
        db = DatabaseManager.get_instance()
        reservation = db.create_reservation(
            user_id=user_id,
            user_name=user_name,
            phone_number=phone_number,
            number_of_guests=number_of_guests,
            date_time=reservation_datetime,
            time_slot=time_slot,
            time_created=time_created
        )
        
        # Store reservation in memory for future reference
        if memory.is_available:
            memory.remember_reservation(
                user_id=user_id,
                reservation_id=reservation.id,
                date_time=reservation_datetime.strftime('%Y-%m-%d %H:%M'),
                guests=number_of_guests
            )
            # Also remember the user's name and phone
            memory.remember_user_name(user_id, user_name)
            memory.remember_user_phone(user_id, phone_number)
        
        return ReservationResult(
            success=True,
            message=f"Reservation confirmed! Your reservation ID is #{reservation.id}.",
            reservation=ReservationDetails(
                reservation_id=reservation.id,
                user_name=reservation.user_name,
                phone_number=reservation.phone_number,
                number_of_guests=reservation.number_of_guests,
                date_time=reservation.date_time.strftime('%Y-%m-%d %H:%M'),
                time_slot=reservation.time_slot,
                status=reservation.status
            )
        )
        
    except ValueError as e:
        return ReservationResult(
            success=False,
            message=f"Invalid date or time format. Please use YYYY-MM-DD for date and HH:MM for time."
        )
    except Exception as e:
        logger.error(f"Error creating reservation: {e}")
        return ReservationResult(
            success=False,
            message=f"An error occurred while creating the reservation: {str(e)}"
        )


@function_tool
def get_reservation(
    reservation_id: Annotated[int, "The reservation ID to look up"]
) -> ReservationResult:
    """
    Get details of a specific reservation by its ID.
    Use this tool when a guest wants to check their reservation details.
    """
    try:
        db = DatabaseManager.get_instance()
        reservation = db.get_reservation_by_id(reservation_id)
        
        if not reservation:
            return ReservationResult(
                success=False,
                message=f"No reservation found with ID #{reservation_id}."
            )
        
        return ReservationResult(
            success=True,
            message="Reservation found.",
            reservation=ReservationDetails(
                reservation_id=reservation.id,
                user_name=reservation.user_name,
                phone_number=reservation.phone_number,
                number_of_guests=reservation.number_of_guests,
                date_time=reservation.date_time.strftime('%Y-%m-%d %H:%M'),
                time_slot=reservation.time_slot,
                status=reservation.status
            )
        )
        
    except Exception as e:
        return ReservationResult(
            success=False,
            message=f"An error occurred while retrieving the reservation: {str(e)}"
        )


@function_tool
def get_user_reservations(
    user_id: Annotated[str, "The user ID to look up reservations for"]
) -> ReservationsList:
    """
    Get all reservations for a specific user.
    Use this tool when a guest wants to see all their reservations.
    """
    try:
        db = DatabaseManager.get_instance()
        reservations = db.get_reservations_by_user(user_id)
        
        return ReservationsList(
            reservations=[
                ReservationDetails(
                    reservation_id=r.id,
                    user_name=r.user_name,
                    phone_number=r.phone_number,
                    number_of_guests=r.number_of_guests,
                    date_time=r.date_time.strftime('%Y-%m-%d %H:%M'),
                    time_slot=r.time_slot,
                    status=r.status
                )
                for r in reservations
            ],
            count=len(reservations)
        )
        
    except Exception as e:
        return ReservationsList(reservations=[], count=0)


@function_tool
def cancel_reservation(
    reservation_id: Annotated[int, "The reservation ID to cancel"]
) -> ReservationResult:
    """
    Cancel an existing reservation.
    Use this tool when a guest wants to cancel their reservation.
    """
    try:
        db = DatabaseManager.get_instance()
        reservation = db.get_reservation_by_id(reservation_id)
        
        if not reservation:
            return ReservationResult(
                success=False,
                message=f"No reservation found with ID #{reservation_id}."
            )
        
        if reservation.status == 'cancelled':
            return ReservationResult(
                success=False,
                message=f"Reservation #{reservation_id} is already cancelled."
            )
        
        # Update status to cancelled
        updated = db.update_reservation(reservation_id, status='cancelled')
        
        if updated:
            return ReservationResult(
                success=True,
                message=f"Reservation #{reservation_id} has been cancelled successfully.",
                reservation=ReservationDetails(
                    reservation_id=updated.id,
                    user_name=updated.user_name,
                    phone_number=updated.phone_number,
                    number_of_guests=updated.number_of_guests,
                    date_time=updated.date_time.strftime('%Y-%m-%d %H:%M'),
                    time_slot=updated.time_slot,
                    status=updated.status
                )
            )
        else:
            return ReservationResult(
                success=False,
                message="Failed to cancel the reservation. Please try again."
            )
            
    except Exception as e:
        return ReservationResult(
            success=False,
            message=f"An error occurred while cancelling the reservation: {str(e)}"
        )


@function_tool
def update_reservation(
    reservation_id: Annotated[int, "The reservation ID to update"],
    new_date: Annotated[Optional[str], "New date - supports 'today', 'tomorrow', day names like 'friday', or YYYY-MM-DD format (optional)"] = None,
    new_time: Annotated[Optional[str], "New time - supports both 12-hour (7pm, 7:30pm) and 24-hour (19:00) formats (optional)"] = None,
    new_guests: Annotated[Optional[int], "New number of guests (optional)"] = None
) -> ReservationResult:
    """
    Update an existing reservation with new date, time, or number of guests.
    Use this tool when a guest wants to modify their reservation.
    Date can be provided as 'today', 'tomorrow', a day name like 'friday', or in YYYY-MM-DD format.
    Time can be provided in either 12-hour format (7pm, 7:30pm) or 24-hour format (19:00).
    """
    try:
        db = DatabaseManager.get_instance()
        reservation = db.get_reservation_by_id(reservation_id)
        
        if not reservation:
            return ReservationResult(
                success=False,
                message=f"No reservation found with ID #{reservation_id}."
            )
        
        if reservation.status == 'cancelled':
            return ReservationResult(
                success=False,
                message=f"Cannot update a cancelled reservation. Please make a new reservation."
            )
        
        # Prepare update data
        update_data = {}
        
        if new_guests is not None:
            settings = kb.get_reservation_settings()
            if new_guests < settings.min_guests or new_guests > settings.max_guests:
                return ReservationResult(
                    success=False,
                    message=f"Number of guests must be between {settings.min_guests} and {settings.max_guests}."
                )
            update_data['number_of_guests'] = new_guests
        
        if new_date or new_time:
            # Parse new datetime
            current_date = reservation.date_time.strftime('%Y-%m-%d')
            current_time = reservation.date_time.strftime('%H:%M')
            
            # Parse date - supports natural language like 'today', 'tomorrow', 'friday', etc.
            if new_date:
                try:
                    date_str = parse_date_string(new_date)
                except ValueError as e:
                    return ReservationResult(
                        success=False,
                        message=str(e)
                    )
            else:
                date_str = current_date
            
            # Parse time - supports both 12-hour (7pm) and 24-hour (19:00) formats
            if new_time:
                try:
                    time_str = parse_time_string(new_time)
                except ValueError as e:
                    return ReservationResult(
                        success=False,
                        message=str(e)
                    )
            else:
                time_str = current_time
            
            new_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            new_datetime = ZAGREB_TZ.localize(new_datetime)
            
            # Validate new datetime
            now = datetime.now(ZAGREB_TZ)
            if new_datetime <= now:
                return ReservationResult(
                    success=False,
                    message="Cannot update to a past date/time."
                )
            
            # Check operating hours
            day_name = new_datetime.strftime('%A').lower()
            hours = kb.get_operating_hours(day_name)
            day_hours = hours.get(day_name)
            
            if day_hours.is_closed:
                return ReservationResult(
                    success=False,
                    message=f"Sorry, the restaurant is closed on {day_name.capitalize()}s."
                )
            
            # Check if time is within operating hours
            open_time = datetime.strptime(day_hours.open, "%H:%M").time()
            close_time = datetime.strptime(day_hours.close, "%H:%M").time()
            reservation_time = new_datetime.time()
            
            # Handle midnight closing time (00:00 means end of day, not start)
            closes_at_midnight = (close_time.hour == 0 and close_time.minute == 0)
            
            if closes_at_midnight:
                if reservation_time < open_time:
                    return ReservationResult(
                        success=False,
                        message=f"Reservations are only available during operating hours: {day_hours.open} - {day_hours.close} (midnight)"
                    )
            else:
                if reservation_time < open_time or reservation_time >= close_time:
                    return ReservationResult(
                        success=False,
                        message=f"Reservations are only available during operating hours: {day_hours.open} - {day_hours.close}"
                    )
            
            update_data['date_time'] = new_datetime
        
        if not update_data:
            return ReservationResult(
                success=False,
                message="No changes specified. Please provide new date, time, or number of guests."
            )
        
        # Update the reservation
        updated = db.update_reservation(reservation_id, **update_data)
        
        if updated:
            return ReservationResult(
                success=True,
                message=f"Reservation #{reservation_id} has been updated successfully.",
                reservation=ReservationDetails(
                    reservation_id=updated.id,
                    user_name=updated.user_name,
                    phone_number=updated.phone_number,
                    number_of_guests=updated.number_of_guests,
                    date_time=updated.date_time.strftime('%Y-%m-%d %H:%M'),
                    time_slot=updated.time_slot,
                    status=updated.status
                )
            )
        else:
            return ReservationResult(
                success=False,
                message="Failed to update the reservation. Please try again."
            )
            
    except ValueError:
        return ReservationResult(
            success=False,
            message="Invalid date or time format. Please use YYYY-MM-DD for date and HH:MM for time."
        )
    except Exception as e:
        return ReservationResult(
            success=False,
            message=f"An error occurred while updating the reservation: {str(e)}"
        )


@function_tool
def check_availability(
    date: Annotated[str, "Date to check - supports 'today', 'tomorrow', day names like 'friday', or YYYY-MM-DD format"]
) -> str:
    """
    Check reservation availability for a specific date.
    Use this tool to see what time slots are available or busy on a given date.
    Date can be provided as 'today', 'tomorrow', a day name like 'friday', or in YYYY-MM-DD format.
    """
    try:
        # Parse the date - supports natural language like 'today', 'tomorrow', 'friday', etc.
        try:
            parsed_date = parse_date_string(date)
        except ValueError as e:
            return str(e)
        
        check_date = datetime.strptime(parsed_date, "%Y-%m-%d").date()
        
        # Get operating hours for that day
        day_name = check_date.strftime('%A').lower()
        hours = kb.get_operating_hours(day_name)
        day_hours = hours.get(day_name)
        
        if day_hours.is_closed:
            return f"The restaurant is closed on {day_name.capitalize()}s."
        
        # Get existing reservations for that date
        db = DatabaseManager.get_instance()
        reservations = db.get_reservations_by_date(check_date)
        
        # Filter to only confirmed reservations
        confirmed = [r for r in reservations if r.status == 'confirmed']
        
        summary = f"Availability for {date} ({day_name.capitalize()}):\n"
        summary += f"Operating hours: {day_hours.open} - {day_hours.close}\n\n"
        
        if not confirmed:
            summary += "All time slots are currently available!"
        else:
            summary += f"Current reservations ({len(confirmed)}):\n"
            for r in confirmed:
                end_time = r.date_time.hour + r.time_slot
                summary += f"- {r.date_time.strftime('%H:%M')} - {int(end_time):02d}:{int((end_time % 1) * 60):02d} ({r.number_of_guests} guests)\n"
        
        return summary
        
    except ValueError:
        return "Invalid date format. Please use YYYY-MM-DD format."
    except Exception as e:
        return f"An error occurred while checking availability: {str(e)}"


# ============================================================================
# Restaurant Booking Agent
# ============================================================================

def create_booking_agent() -> Agent:
    """
    Create and return the restaurant booking agent.
    """
    # Get restaurant info from knowledge base
    restaurant_name = kb.get_restaurant_name()
    settings = kb.get_reservation_settings()
    
    # Check if memory is available
    memory_status = "enabled" if memory.is_available else "disabled (MEM0_API_KEY not set)"
    
    instructions = f"""You are a friendly and professional restaurant booking assistant for {restaurant_name}.
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

    return Agent(
        name="Restaurant Booking Agent",
        instructions=instructions,
        tools=[
            # Date/Time tools
            get_current_datetime,
            # Memory tools (Mem0)
            recall_user_info,
            remember_user_preference,
            remember_user_name,
            search_user_memories,
            # Knowledge base tools
            get_restaurant_info,
            get_operating_hours,
            get_restaurant_address,
            get_menu_info,
            search_menu,
            get_about_restaurant,
            get_reservation_rules,
            # Reservation tools
            create_reservation,
            get_reservation,
            get_user_reservations,
            cancel_reservation,
            update_reservation,
            check_availability
        ]
    )


# Create the default booking agent
booking_agent = create_booking_agent()


# ============================================================================
# Async Runner Function
# ============================================================================

async def run_booking_agent(user_message: str, conversation_history: list = None, user_id: str = None) -> tuple[str, list]:
    """
    Run the booking agent with a user message.
    
    Args:
        user_message: The user's message
        conversation_history: Previous conversation history (list of input items)
        user_id: Optional user ID for memory context
    
    Returns:
        Tuple of (agent_response, updated_conversation_history)
    """
    if conversation_history is None:
        conversation_history = []
    
    # Add user message to history
    conversation_history.append({
        "role": "user",
        "content": user_message
    })
    
    try:
        # Run the agent
        result = await Runner.run(
            booking_agent,
            input=conversation_history
        )
        
        # Get the agent's response
        agent_response = result.final_output
        
        # Update conversation history
        updated_history = result.to_input_list()
        
        # Store conversation in memory if user_id is provided and memory is available
        if user_id and memory.is_available:
            memory.store_conversation_memory(user_id, user_message, agent_response)
        
        return agent_response, updated_history
        
    except Exception as e:
        logger.error(f"Error running booking agent: {e}", exc_info=True)
        error_message = f"I apologize, but I encountered an error: {str(e)}. Please try again."
        return error_message, conversation_history


def run_booking_agent_sync(user_message: str, conversation_history: list = None, user_id: str = None) -> tuple[str, list]:
    """
    Synchronous wrapper for run_booking_agent.
    """
    return asyncio.run(run_booking_agent(user_message, conversation_history, user_id))


# ============================================================================
# Test Function
# ============================================================================

if __name__ == "__main__":
    async def test():
        print("Testing Restaurant Booking Agent with Mem0 Memory...")
        print("-" * 50)
        
        # Test getting current datetime
        print("\n1. Testing get_current_datetime tool:")
        dt_info = get_current_datetime()
        print(f"   Current datetime: {dt_info.full_datetime}")
        
        # Test memory availability
        print("\n2. Testing Mem0 Memory:")
        print(f"   Memory available: {memory.is_available}")
        
        # Test knowledge base tools
        print("\n3. Testing get_restaurant_info tool:")
        info = get_restaurant_info()
        print(f"   Restaurant: {info.name}")
        print(f"   Address: {info.address}")
        print(f"   Currently open: {info.is_currently_open}")
        
        print("\n4. Testing get_operating_hours tool:")
        hours = get_operating_hours()
        print(f"   Today's hours: {hours.today_hours}")
        print(f"   Status: {hours.current_status}")
        
        print("\n5. Testing search_menu tool:")
        results = search_menu("truffle")
        print(f"   Found {results.count} items with 'truffle'")
        for item in results.results[:2]:
            print(f"   - {item.name}: EUR {item.price}")
        
        # Test conversation
        print("\n6. Testing agent conversation:")
        response, history = await run_booking_agent("What are your opening hours?")
        print(f"   Agent: {response[:200]}...")
        
    asyncio.run(test())


# ============================================================================
# Chatwoot Integration - Synchronous Message Processing
# ============================================================================

# Store conversation histories by user_id (in production, use Redis or database)
_conversation_histories: dict = {}


def process_booking_message(
    message: str,
    user_id: str,
    user_name: str = None,
    phone_number: str = None
) -> str:
    """
    Process a booking message from Chatwoot webhook.
    
    This function maintains conversation history per user and processes
    messages synchronously for webhook integration.
    
    Args:
        message: The user's message text
        user_id: Unique identifier for the user (phone number or contact ID)
        user_name: User's name (optional, for personalization)
        phone_number: User's phone number (optional)
        
    Returns:
        Agent's response text
    """
    try:
        # Get or create conversation history for this user
        if user_id not in _conversation_histories:
            _conversation_histories[user_id] = []
            logger.info(f"New conversation started for user: {user_id}")
            
            # For new conversations, add context about the user
            if user_name or phone_number:
                context_message = f"[System: User info - ID: {user_id}, Name: {user_name or 'Unknown'}, Phone: {phone_number or 'Unknown'}]"
                _conversation_histories[user_id].append({
                    "role": "system",
                    "content": context_message
                })
        
        conversation_history = _conversation_histories[user_id]
        
        # Run the agent synchronously with user_id for memory
        response, updated_history = run_booking_agent_sync(message, conversation_history, user_id)
        
        # Update stored history
        _conversation_histories[user_id] = updated_history
        
        # Limit history size to prevent memory issues (keep last 20 exchanges)
        if len(_conversation_histories[user_id]) > 40:
            _conversation_histories[user_id] = _conversation_histories[user_id][-40:]
        
        logger.info(f"Agent response generated for user {user_id}: {response[:100]}...")
        return response
        
    except Exception as e:
        logger.error(f"Error processing booking message: {e}", exc_info=True)
        return f"I apologize, but I encountered an error processing your request. Please try again or contact the restaurant directly."


def clear_user_conversation(user_id: str) -> bool:
    """
    Clear conversation history for a specific user.
    
    Args:
        user_id: The user's identifier
        
    Returns:
        True if history was cleared, False if user not found
    """
    if user_id in _conversation_histories:
        del _conversation_histories[user_id]
        return True
    return False


def get_active_conversations() -> list:
    """
    Get list of active conversation user IDs.
    
    Returns:
        List of user IDs with active conversations
    """
    return list(_conversation_histories.keys())
