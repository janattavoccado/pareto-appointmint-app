"""
Restaurant Booking Agent using OpenAI Agents SDK.
Handles table reservations with CET:Zagreb timezone support.
Integrates with knowledge base for restaurant information.
"""

import asyncio
from datetime import datetime
from typing import Annotated, Optional, List
import pytz

from pydantic import BaseModel, Field
from agents import Agent, Runner, function_tool

from models import DatabaseManager, Reservation
from knowledgebase_manager import KnowledgeBaseManager


# CET:Zagreb timezone
ZAGREB_TZ = pytz.timezone('Europe/Zagreb')

# Initialize knowledge base
kb = KnowledgeBaseManager.get_instance()


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
    user_id: Annotated[str, "Unique identifier for the user (e.g., phone number or session ID)"],
    user_name: Annotated[str, "Full name of the guest making the reservation"],
    phone_number: Annotated[str, "Contact phone number for the reservation"],
    number_of_guests: Annotated[int, "Number of guests for the reservation (1-20)"],
    reservation_date: Annotated[str, "Date for the reservation in YYYY-MM-DD format"],
    reservation_time: Annotated[str, "Time for the reservation in HH:MM format (24-hour)"],
    time_slot: Annotated[float, "Duration of reservation in hours (default 2.0)"] = 2.0
) -> ReservationResult:
    """
    Create a new table reservation at the restaurant.
    Validates the reservation details and stores them in the database.
    """
    try:
        # Get reservation settings from knowledge base
        settings = kb.get_reservation_settings()
        
        # Parse and validate the datetime
        reservation_datetime_str = f"{reservation_date} {reservation_time}"
        reservation_datetime = datetime.strptime(reservation_datetime_str, '%Y-%m-%d %H:%M')
        
        # Localize to Zagreb timezone
        reservation_datetime = ZAGREB_TZ.localize(reservation_datetime)
        
        # Get current time in Zagreb
        now = datetime.now(ZAGREB_TZ)
        
        # Validate reservation is in the future
        if reservation_datetime <= now:
            return ReservationResult(
                success=False,
                message="Reservation must be for a future date and time.",
                reservation=None
            )
        
        # Validate number of guests using knowledge base settings
        if number_of_guests < settings.min_guests or number_of_guests > settings.max_guests:
            return ReservationResult(
                success=False,
                message=f"Number of guests must be between {settings.min_guests} and {settings.max_guests}.",
                reservation=None
            )
        
        # Validate time slot
        if time_slot < 0.5 or time_slot > 4.0:
            return ReservationResult(
                success=False,
                message="Time slot must be between 0.5 and 4 hours.",
                reservation=None
            )
        
        # Check if restaurant is open at the requested time
        day_name = reservation_datetime.strftime('%A').lower()
        hours = kb.get_operating_hours(day_name)
        day_hours = hours.get(day_name)
        
        if day_hours.is_closed:
            return ReservationResult(
                success=False,
                message=f"Sorry, the restaurant is closed on {day_name.capitalize()}s.",
                reservation=None
            )
        
        # Check if requested time is within operating hours
        req_time = reservation_datetime.strftime('%H:%M')
        close_time = day_hours.close if day_hours.close != '00:00' else '24:00'
        
        if req_time < day_hours.open or req_time >= close_time:
            return ReservationResult(
                success=False,
                message=f"The restaurant is only open from {day_hours.open} to {day_hours.close} on {day_name.capitalize()}s.",
                reservation=None
            )
        
        # Create reservation in database
        db = DatabaseManager.get_instance()
        reservation = db.create_reservation(
            user_id=user_id,
            user_name=user_name,
            phone_number=phone_number,
            number_of_guests=number_of_guests,
            date_time=reservation_datetime,
            time_created=now,
            time_slot=time_slot
        )
        
        # Add note for large parties
        message = f"Reservation successfully created! Your reservation ID is {reservation.id}."
        if number_of_guests >= settings.large_party_threshold:
            message += f" Note: {settings.large_party_note}"
        
        return ReservationResult(
            success=True,
            message=message,
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
            message=f"Invalid date or time format. Please use YYYY-MM-DD for date and HH:MM for time. Error: {str(e)}",
            reservation=None
        )
    except Exception as e:
        return ReservationResult(
            success=False,
            message=f"An error occurred while creating the reservation: {str(e)}",
            reservation=None
        )


@function_tool
def get_reservation(
    reservation_id: Annotated[int, "The unique ID of the reservation to retrieve"]
) -> ReservationResult:
    """
    Retrieve details of a specific reservation by its ID.
    """
    try:
        db = DatabaseManager.get_instance()
        reservation = db.get_reservation_by_id(reservation_id)
        
        if reservation is None:
            return ReservationResult(
                success=False,
                message=f"No reservation found with ID {reservation_id}.",
                reservation=None
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
            message=f"An error occurred while retrieving the reservation: {str(e)}",
            reservation=None
        )


@function_tool
def get_user_reservations(
    user_id: Annotated[str, "The user ID to retrieve reservations for"]
) -> ReservationsList:
    """
    Retrieve all reservations for a specific user.
    """
    try:
        db = DatabaseManager.get_instance()
        reservations = db.get_reservations_by_user(user_id)
        
        reservation_details = [
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
        ]
        
        return ReservationsList(
            reservations=reservation_details,
            count=len(reservation_details)
        )
        
    except Exception as e:
        return ReservationsList(
            reservations=[],
            count=0
        )


@function_tool
def cancel_reservation(
    reservation_id: Annotated[int, "The unique ID of the reservation to cancel"]
) -> ReservationResult:
    """
    Cancel an existing reservation by its ID.
    """
    try:
        db = DatabaseManager.get_instance()
        
        # First check if reservation exists
        reservation = db.get_reservation_by_id(reservation_id)
        if reservation is None:
            return ReservationResult(
                success=False,
                message=f"No reservation found with ID {reservation_id}.",
                reservation=None
            )
        
        if reservation.status == 'cancelled':
            return ReservationResult(
                success=False,
                message=f"Reservation {reservation_id} is already cancelled.",
                reservation=None
            )
        
        # Cancel the reservation
        success = db.cancel_reservation(reservation_id)
        
        if success:
            return ReservationResult(
                success=True,
                message=f"Reservation {reservation_id} has been successfully cancelled.",
                reservation=ReservationDetails(
                    reservation_id=reservation.id,
                    user_name=reservation.user_name,
                    phone_number=reservation.phone_number,
                    number_of_guests=reservation.number_of_guests,
                    date_time=reservation.date_time.strftime('%Y-%m-%d %H:%M'),
                    time_slot=reservation.time_slot,
                    status='cancelled'
                )
            )
        else:
            return ReservationResult(
                success=False,
                message="Failed to cancel the reservation.",
                reservation=None
            )
            
    except Exception as e:
        return ReservationResult(
            success=False,
            message=f"An error occurred while cancelling the reservation: {str(e)}",
            reservation=None
        )


@function_tool
def update_reservation(
    reservation_id: Annotated[int, "The unique ID of the reservation to update"],
    new_date: Annotated[Optional[str], "New date for the reservation in YYYY-MM-DD format"] = None,
    new_time: Annotated[Optional[str], "New time for the reservation in HH:MM format"] = None,
    new_number_of_guests: Annotated[Optional[int], "New number of guests"] = None
) -> ReservationResult:
    """
    Update an existing reservation with new details.
    Only provided fields will be updated.
    """
    try:
        db = DatabaseManager.get_instance()
        settings = kb.get_reservation_settings()
        
        # First check if reservation exists
        reservation = db.get_reservation_by_id(reservation_id)
        if reservation is None:
            return ReservationResult(
                success=False,
                message=f"No reservation found with ID {reservation_id}.",
                reservation=None
            )
        
        if reservation.status == 'cancelled':
            return ReservationResult(
                success=False,
                message=f"Cannot update a cancelled reservation.",
                reservation=None
            )
        
        update_data = {}
        
        # Handle date/time update
        if new_date or new_time:
            current_datetime = reservation.date_time
            new_date_str = new_date if new_date else current_datetime.strftime('%Y-%m-%d')
            new_time_str = new_time if new_time else current_datetime.strftime('%H:%M')
            
            new_datetime_str = f"{new_date_str} {new_time_str}"
            new_datetime = datetime.strptime(new_datetime_str, '%Y-%m-%d %H:%M')
            new_datetime = ZAGREB_TZ.localize(new_datetime)
            
            # Validate new datetime is in the future
            now = datetime.now(ZAGREB_TZ)
            if new_datetime <= now:
                return ReservationResult(
                    success=False,
                    message="New reservation time must be in the future.",
                    reservation=None
                )
            
            # Check if restaurant is open at the new time
            day_name = new_datetime.strftime('%A').lower()
            hours = kb.get_operating_hours(day_name)
            day_hours = hours.get(day_name)
            
            if day_hours.is_closed:
                return ReservationResult(
                    success=False,
                    message=f"Sorry, the restaurant is closed on {day_name.capitalize()}s.",
                    reservation=None
                )
            
            update_data['date_time'] = new_datetime
        
        # Handle number of guests update
        if new_number_of_guests is not None:
            if new_number_of_guests < settings.min_guests or new_number_of_guests > settings.max_guests:
                return ReservationResult(
                    success=False,
                    message=f"Number of guests must be between {settings.min_guests} and {settings.max_guests}.",
                    reservation=None
                )
            update_data['number_of_guests'] = new_number_of_guests
        
        if not update_data:
            return ReservationResult(
                success=False,
                message="No update fields provided.",
                reservation=None
            )
        
        # Update the reservation
        updated_reservation = db.update_reservation(reservation_id, **update_data)
        
        if updated_reservation:
            return ReservationResult(
                success=True,
                message=f"Reservation {reservation_id} has been successfully updated.",
                reservation=ReservationDetails(
                    reservation_id=updated_reservation.id,
                    user_name=updated_reservation.user_name,
                    phone_number=updated_reservation.phone_number,
                    number_of_guests=updated_reservation.number_of_guests,
                    date_time=updated_reservation.date_time.strftime('%Y-%m-%d %H:%M'),
                    time_slot=updated_reservation.time_slot,
                    status=updated_reservation.status
                )
            )
        else:
            return ReservationResult(
                success=False,
                message="Failed to update the reservation.",
                reservation=None
            )
            
    except ValueError as e:
        return ReservationResult(
            success=False,
            message=f"Invalid date or time format. Please use YYYY-MM-DD for date and HH:MM for time. Error: {str(e)}",
            reservation=None
        )
    except Exception as e:
        return ReservationResult(
            success=False,
            message=f"An error occurred while updating the reservation: {str(e)}",
            reservation=None
        )


@function_tool
def check_availability(
    check_date: Annotated[str, "Date to check availability for in YYYY-MM-DD format"]
) -> str:
    """
    Check reservation availability for a specific date.
    Returns information about existing reservations on that date.
    """
    try:
        db = DatabaseManager.get_instance()
        
        # Parse the date
        date_obj = datetime.strptime(check_date, '%Y-%m-%d')
        date_obj = ZAGREB_TZ.localize(date_obj)
        
        # Check if restaurant is open on that day
        day_name = date_obj.strftime('%A').lower()
        hours = kb.get_operating_hours(day_name)
        day_hours = hours.get(day_name)
        
        if day_hours.is_closed:
            return f"The restaurant is closed on {day_name.capitalize()}s."
        
        reservations = db.get_reservations_by_date(date_obj)
        
        summary = f"Availability for {check_date} ({day_name.capitalize()}):\n"
        summary += f"Operating hours: {day_hours.open} - {day_hours.close}\n\n"
        
        if not reservations:
            summary += "No reservations found. The restaurant is available for bookings."
        else:
            summary += f"Current reservations ({len(reservations)}):\n"
            for r in reservations:
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
    
    instructions = f"""You are a friendly and professional restaurant booking assistant for {restaurant_name}.
Your role is to help customers make, view, modify, and cancel table reservations, as well as provide information about the restaurant.

IMPORTANT: At the start of EVERY conversation, you MUST call the get_current_datetime tool to know the current date and time in CET:Zagreb timezone. This is essential for accurate booking.

You have access to the restaurant's knowledge base with information about:
- Restaurant details (name, description, address, contact)
- Operating hours for each day of the week
- Full menu with prices and dietary information
- About us / restaurant story
- Reservation rules and policies

When helping customers with reservations:
1. Always be polite and helpful
2. Collect all necessary information: name, phone number, number of guests, preferred date and time
3. Confirm all details before making a reservation
4. Provide the reservation ID after successful booking
5. For modifications or cancellations, always verify the reservation ID first

Reservation Rules (from knowledge base):
- Minimum {settings.min_guests} guest, maximum {settings.max_guests} guests per reservation
- Default time slot is {settings.default_time_slot_hours} hours
- Reservations must be made at least {settings.advance_booking_hours} hour(s) in advance
- Phone number is required for all reservations
- {settings.large_party_note}

When a user wants to make a reservation:
1. First call get_current_datetime to know the current date/time
2. Ask for their name if not provided
3. Ask for their phone number if not provided
4. Ask for the number of guests if not provided
5. Ask for their preferred date and time if not provided
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

Always respond in a natural, conversational manner while being efficient and helpful.
Only provide information that is available from your tools - do not make up or hallucinate information."""

    return Agent(
        name="Restaurant Booking Agent",
        instructions=instructions,
        tools=[
            # Date/Time tools
            get_current_datetime,
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

async def run_booking_agent(user_message: str, conversation_history: list = None) -> tuple[str, list]:
    """
    Run the booking agent with a user message.
    
    Args:
        user_message: The user's message
        conversation_history: Previous conversation history (list of input items)
    
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
        
        return agent_response, updated_history
        
    except Exception as e:
        error_message = f"I apologize, but I encountered an error: {str(e)}. Please try again."
        return error_message, conversation_history


def run_booking_agent_sync(user_message: str, conversation_history: list = None) -> tuple[str, list]:
    """
    Synchronous wrapper for run_booking_agent.
    """
    return asyncio.run(run_booking_agent(user_message, conversation_history))


# ============================================================================
# Test Function
# ============================================================================

if __name__ == "__main__":
    async def test():
        print("Testing Restaurant Booking Agent...")
        print("-" * 50)
        
        # Test getting current datetime
        print("\n1. Testing get_current_datetime tool:")
        dt_info = get_current_datetime()
        print(f"   Current datetime: {dt_info.full_datetime}")
        
        # Test knowledge base tools
        print("\n2. Testing get_restaurant_info tool:")
        info = get_restaurant_info()
        print(f"   Restaurant: {info.name}")
        print(f"   Address: {info.address}")
        print(f"   Currently open: {info.is_currently_open}")
        
        print("\n3. Testing get_operating_hours tool:")
        hours = get_operating_hours()
        print(f"   Today's hours: {hours.today_hours}")
        print(f"   Status: {hours.current_status}")
        
        print("\n4. Testing search_menu tool:")
        results = search_menu("truffle")
        print(f"   Found {results.count} items with 'truffle'")
        for item in results.results[:2]:
            print(f"   - {item.name}: EUR {item.price}")
        
        # Test conversation
        print("\n5. Testing agent conversation:")
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
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Get or create conversation history for this user
        if user_id not in _conversation_histories:
            _conversation_histories[user_id] = []
            logger.info(f"New conversation started for user: {user_id}")
        
        conversation_history = _conversation_histories[user_id]
        
        # Add context about the user if this is a new conversation
        if not conversation_history and (user_name or phone_number):
            context_message = f"[System: User info - Name: {user_name or 'Unknown'}, Phone: {phone_number or 'Unknown'}]"
            conversation_history.append({
                "role": "system",
                "content": context_message
            })
        
        # Run the agent synchronously
        response, updated_history = run_booking_agent_sync(message, conversation_history)
        
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
