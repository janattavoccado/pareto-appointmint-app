"""
Restaurant Booking Agent using OpenAI Agents SDK.
Handles table reservations with CET:Zagreb timezone support.
"""

import asyncio
from datetime import datetime
from typing import Annotated, Optional
import pytz

from pydantic import BaseModel, Field
from agents import Agent, Runner, function_tool

from models import DatabaseManager, Reservation


# CET:Zagreb timezone
ZAGREB_TZ = pytz.timezone('Europe/Zagreb')


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


# ============================================================================
# Agent Tools
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
        
        # Validate number of guests
        if number_of_guests < 1 or number_of_guests > 20:
            return ReservationResult(
                success=False,
                message="Number of guests must be between 1 and 20.",
                reservation=None
            )
        
        # Validate time slot
        if time_slot < 0.5 or time_slot > 4.0:
            return ReservationResult(
                success=False,
                message="Time slot must be between 0.5 and 4 hours.",
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
        
        return ReservationResult(
            success=True,
            message=f"Reservation successfully created! Your reservation ID is {reservation.id}.",
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
            
            update_data['date_time'] = new_datetime
        
        # Handle number of guests update
        if new_number_of_guests is not None:
            if new_number_of_guests < 1 or new_number_of_guests > 20:
                return ReservationResult(
                    success=False,
                    message="Number of guests must be between 1 and 20.",
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
        
        reservations = db.get_reservations_by_date(date_obj)
        
        if not reservations:
            return f"No reservations found for {check_date}. The restaurant is available for bookings."
        
        # Build availability summary
        summary = f"Reservations for {check_date}:\n"
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

def create_booking_agent(restaurant_name: str = "Our Restaurant") -> Agent:
    """
    Create and return the restaurant booking agent.
    """
    
    instructions = f"""You are a friendly and professional restaurant booking assistant for {restaurant_name}.
Your role is to help customers make, view, modify, and cancel table reservations.

IMPORTANT: At the start of EVERY conversation, you MUST call the get_current_datetime tool to know the current date and time in CET:Zagreb timezone. This is essential for accurate booking.

When helping customers with reservations:
1. Always be polite and helpful
2. Collect all necessary information: name, phone number, number of guests, preferred date and time
3. Confirm all details before making a reservation
4. Provide the reservation ID after successful booking
5. For modifications or cancellations, always verify the reservation ID first

Restaurant Operating Hours:
- Open daily from 10:00 to 22:00 (CET:Zagreb timezone)
- Last reservation at 20:00 (to allow for 2-hour default time slot)

Reservation Rules:
- Minimum 1 guest, maximum 20 guests per reservation
- Default time slot is 2 hours
- Reservations must be made at least 1 hour in advance
- Phone number is required for all reservations

When a user wants to make a reservation:
1. First call get_current_datetime to know the current date/time
2. Ask for their name if not provided
3. Ask for their phone number if not provided
4. Ask for the number of guests if not provided
5. Ask for their preferred date and time if not provided
6. Confirm all details before creating the reservation
7. Use the create_reservation tool to complete the booking

Always respond in a natural, conversational manner while being efficient and helpful."""

    return Agent(
        name="Restaurant Booking Agent",
        instructions=instructions,
        tools=[
            get_current_datetime,
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
        
        # Test conversation
        print("\n2. Testing agent conversation:")
        response, history = await run_booking_agent("Hello! I'd like to make a reservation for tomorrow at 7pm for 4 people.")
        print(f"   Agent: {response}")
        
    asyncio.run(test())
