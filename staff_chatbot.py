"""
Staff Chatbot - AI Assistant for Restaurant Staff
Uses OpenAI function calling for natural language reservation management
Uses DatabaseManager pattern for database operations.

VERSION 2.0 - Added logging and update_reservation function for modifying reservation details
"""

import json
import logging
from datetime import datetime, timedelta
import pytz
from openai import OpenAI

# Configure logging
logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI()

# Zagreb timezone
ZAGREB_TZ = pytz.timezone('Europe/Zagreb')

def get_db():
    """Get database manager instance."""
    from models import DatabaseManager
    return DatabaseManager.get_instance()

# Define available functions for the AI
AVAILABLE_FUNCTIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_todays_reservations",
            "description": "Get all reservations for today",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_reservations_by_date",
            "description": "Get reservations for a specific date",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format"
                    }
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_reservations",
            "description": "Search reservations by customer name or phone number",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (name or phone)"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_reservation_details",
            "description": "Get detailed information about a specific reservation by ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "reservation_id": {
                        "type": "integer",
                        "description": "The reservation ID"
                    }
                },
                "required": ["reservation_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_reservation_status",
            "description": "Update the status of a reservation (confirmed, cancelled, completed, no_show, arrived, seated)",
            "parameters": {
                "type": "object",
                "properties": {
                    "reservation_id": {
                        "type": "integer",
                        "description": "The reservation ID"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "confirmed", "cancelled", "completed", "no_show", "arrived", "seated"],
                        "description": "New status for the reservation"
                    }
                },
                "required": ["reservation_id", "status"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_reservation",
            "description": "Update reservation details like guest name, phone number, number of guests, date/time, or special requests. Use this when staff wants to change any reservation information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reservation_id": {
                        "type": "integer",
                        "description": "The reservation ID to update"
                    },
                    "user_name": {
                        "type": "string",
                        "description": "New guest name (optional)"
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "New phone number (optional)"
                    },
                    "number_of_guests": {
                        "type": "integer",
                        "description": "New number of guests (optional)"
                    },
                    "date_time": {
                        "type": "string",
                        "description": "New date and time in YYYY-MM-DD HH:MM format (optional)"
                    },
                    "special_requests": {
                        "type": "string",
                        "description": "New special requests (optional)"
                    }
                },
                "required": ["reservation_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "assign_table",
            "description": "Assign a table number to a reservation",
            "parameters": {
                "type": "object",
                "properties": {
                    "reservation_id": {
                        "type": "integer",
                        "description": "The reservation ID"
                    },
                    "table_number": {
                        "type": "string",
                        "description": "Table number to assign"
                    }
                },
                "required": ["reservation_id", "table_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_statistics",
            "description": "Get reservation statistics (total, today, pending, etc.)",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_reservations",
            "description": "Get upcoming reservations for the next few hours or days",
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {
                        "type": "integer",
                        "description": "Number of hours to look ahead (default 2)"
                    }
                },
                "required": []
            }
        }
    }
]

# Function implementations
def get_todays_reservations():
    """Get all reservations for today"""
    logger.info("Function called: get_todays_reservations")
    db = get_db()
    today = datetime.now(ZAGREB_TZ)
    reservations = db.get_reservations_by_date(today)
    
    if not reservations:
        return "No reservations found for today."
    
    result = f"Today's reservations ({len(reservations)} total):\n\n"
    for res in reservations:
        time_str = res.date_time.strftime('%H:%M') if res.date_time else 'N/A'
        result += f"• #{res.id} - {res.user_name} at {time_str}\n"
        result += f"  Party: {res.number_of_guests} | Status: {res.status}"
        if res.table_number:
            result += f" | Table: {res.table_number}"
        result += "\n"
    
    return result

def get_reservations_by_date(date: str):
    """Get reservations for a specific date"""
    logger.info(f"Function called: get_reservations_by_date(date={date})")
    db = get_db()
    try:
        target_date = datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return f"Invalid date format. Please use YYYY-MM-DD."
    
    reservations = db.get_reservations_by_date(target_date)
    
    if not reservations:
        return f"No reservations found for {date}."
    
    result = f"Reservations for {date} ({len(reservations)} total):\n\n"
    for res in reservations:
        time_str = res.date_time.strftime('%H:%M') if res.date_time else 'N/A'
        result += f"• #{res.id} - {res.user_name} at {time_str}\n"
        result += f"  Party: {res.number_of_guests} | Status: {res.status}\n"
    
    return result

def search_reservations(query: str):
    """Search reservations by name or phone"""
    logger.info(f"Function called: search_reservations(query={query})")
    db = get_db()
    reservations = db.search_reservations(query)
    
    if not reservations:
        return f"No reservations found matching '{query}'."
    
    result = f"Found {len(reservations)} reservation(s) matching '{query}':\n\n"
    for res in reservations:
        date_str = res.date_time.strftime('%Y-%m-%d') if res.date_time else 'N/A'
        time_str = res.date_time.strftime('%H:%M') if res.date_time else 'N/A'
        result += f"• #{res.id} - {res.user_name}\n"
        result += f"  Date: {date_str} at {time_str}\n"
        result += f"  Phone: {res.phone_number} | Party: {res.number_of_guests} | Status: {res.status}\n\n"
    
    return result

def get_reservation_details(reservation_id: int):
    """Get detailed information about a reservation"""
    logger.info(f"Function called: get_reservation_details(reservation_id={reservation_id})")
    db = get_db()
    res = db.get_reservation_by_id(reservation_id)
    
    if not res:
        return f"Reservation #{reservation_id} not found."
    
    date_str = res.date_time.strftime('%Y-%m-%d') if res.date_time else 'N/A'
    time_str = res.date_time.strftime('%H:%M') if res.date_time else 'N/A'
    
    result = f"Reservation #{res.id} Details:\n\n"
    result += f"Customer: {res.user_name}\n"
    result += f"Phone: {res.phone_number}\n"
    result += f"Date: {date_str}\n"
    result += f"Time: {time_str}\n"
    result += f"Party Size: {res.number_of_guests}\n"
    result += f"Status: {res.status}\n"
    if res.table_number:
        result += f"Table: {res.table_number}\n"
    if res.special_requests:
        result += f"Special Requests: {res.special_requests}\n"
    if res.time_created:
        result += f"Created: {res.time_created.strftime('%Y-%m-%d %H:%M')}\n"
    
    return result

def update_reservation_status(reservation_id: int, status: str):
    """Update reservation status"""
    logger.info(f"Function called: update_reservation_status(reservation_id={reservation_id}, status={status})")
    db = get_db()
    res = db.get_reservation_by_id(reservation_id)
    
    if not res:
        logger.warning(f"Reservation #{reservation_id} not found")
        return f"Reservation #{reservation_id} not found."
    
    old_status = res.status
    logger.info(f"Updating reservation #{reservation_id} status from '{old_status}' to '{status}'")
    
    updated = db.update_reservation_status(reservation_id, status)
    
    if updated:
        logger.info(f"Successfully updated reservation #{reservation_id} status to '{status}'")
        return f"✅ Reservation #{reservation_id} status updated from '{old_status}' to '{status}'."
    else:
        logger.error(f"Failed to update reservation #{reservation_id}")
        return f"❌ Failed to update reservation #{reservation_id}."

def update_reservation(reservation_id: int, **kwargs):
    """Update reservation details"""
    logger.info(f"Function called: update_reservation(reservation_id={reservation_id}, kwargs={kwargs})")
    db = get_db()
    res = db.get_reservation_by_id(reservation_id)
    
    if not res:
        logger.warning(f"Reservation #{reservation_id} not found")
        return f"Reservation #{reservation_id} not found."
    
    # Handle date_time conversion if provided
    if 'date_time' in kwargs and kwargs['date_time']:
        try:
            kwargs['date_time'] = datetime.strptime(kwargs['date_time'], '%Y-%m-%d %H:%M')
        except ValueError:
            return f"Invalid date/time format. Please use YYYY-MM-DD HH:MM."
    
    # Filter out None values
    update_data = {k: v for k, v in kwargs.items() if v is not None}
    
    if not update_data:
        return "No changes specified."
    
    logger.info(f"Updating reservation #{reservation_id} with: {update_data}")
    
    updated = db.update_reservation(reservation_id, **update_data)
    
    if updated:
        changes = ", ".join([f"{k}={v}" for k, v in update_data.items()])
        logger.info(f"Successfully updated reservation #{reservation_id}: {changes}")
        return f"✅ Reservation #{reservation_id} updated: {changes}"
    else:
        logger.error(f"Failed to update reservation #{reservation_id}")
        return f"❌ Failed to update reservation #{reservation_id}."

def assign_table(reservation_id: int, table_number: str):
    """Assign table to reservation"""
    logger.info(f"Function called: assign_table(reservation_id={reservation_id}, table_number={table_number})")
    db = get_db()
    res = db.get_reservation_by_id(reservation_id)
    
    if not res:
        return f"Reservation #{reservation_id} not found."
    
    updated = db.update_reservation(reservation_id, table_number=table_number)
    
    if updated:
        logger.info(f"Table {table_number} assigned to reservation #{reservation_id}")
        return f"✅ Table {table_number} assigned to reservation #{reservation_id} ({res.user_name})."
    else:
        return f"❌ Failed to assign table to reservation #{reservation_id}."

def get_statistics():
    """Get reservation statistics"""
    logger.info("Function called: get_statistics")
    db = get_db()
    now = datetime.now(ZAGREB_TZ)
    stats = db.get_reservation_stats(now)
    
    result = "📊 Reservation Statistics (Today):\n\n"
    result += f"Total Reservations: {stats.get('total', 0)}\n"
    result += f"Pending: {stats.get('pending', 0)}\n"
    result += f"Confirmed: {stats.get('confirmed', 0)}\n"
    result += f"Arrived: {stats.get('arrived', 0)}\n"
    result += f"Seated: {stats.get('seated', 0)}\n"
    result += f"Completed: {stats.get('completed', 0)}\n"
    result += f"Cancelled: {stats.get('cancelled', 0)}\n"
    result += f"No-shows: {stats.get('no_show', 0)}\n"
    result += f"Total Guests Expected: {stats.get('total_guests', 0)}\n"
    
    return result

def get_upcoming_reservations(hours: int = 2):
    """Get upcoming reservations"""
    logger.info(f"Function called: get_upcoming_reservations(hours={hours})")
    db = get_db()
    
    now = datetime.now(ZAGREB_TZ)
    today = now.replace(tzinfo=None)  # Remove timezone for comparison
    reservations = db.get_reservations_by_date(today)
    
    # Filter to upcoming only
    upcoming = []
    for res in reservations:
        if res.date_time:
            res_time = res.date_time
            now_naive = now.replace(tzinfo=None)
            if res_time > now_naive and res_time < now_naive + timedelta(hours=hours):
                upcoming.append(res)
    
    if not upcoming:
        return f"No reservations in the next {hours} hour(s)."
    
    result = f"⏰ Upcoming reservations (next {hours} hours):\n\n"
    for res in upcoming:
        time_str = res.date_time.strftime('%H:%M') if res.date_time else 'N/A'
        result += f"• #{res.id} - {res.user_name} at {time_str}\n"
        result += f"  Party: {res.number_of_guests} | Status: {res.status}"
        if res.table_number:
            result += f" | Table: {res.table_number}"
        result += "\n"
    
    return result

# Function dispatcher
FUNCTION_MAP = {
    "get_todays_reservations": lambda args: get_todays_reservations(),
    "get_reservations_by_date": lambda args: get_reservations_by_date(args.get("date")),
    "search_reservations": lambda args: search_reservations(args.get("query")),
    "get_reservation_details": lambda args: get_reservation_details(args.get("reservation_id")),
    "update_reservation_status": lambda args: update_reservation_status(args.get("reservation_id"), args.get("status")),
    "update_reservation": lambda args: update_reservation(
        args.get("reservation_id"),
        user_name=args.get("user_name"),
        phone_number=args.get("phone_number"),
        number_of_guests=args.get("number_of_guests"),
        date_time=args.get("date_time"),
        special_requests=args.get("special_requests")
    ),
    "assign_table": lambda args: assign_table(args.get("reservation_id"), args.get("table_number")),
    "get_statistics": lambda args: get_statistics(),
    "get_upcoming_reservations": lambda args: get_upcoming_reservations(args.get("hours", 2))
}

def process_staff_message(message: str, staff_name: str = "Staff") -> str:
    """
    Process a message from staff and return AI response
    Uses OpenAI function calling for reservation management
    """
    logger.info(f"Processing staff message from {staff_name}: {message[:100]}...")
    
    try:
        # System prompt for the staff assistant
        system_prompt = f"""You are a helpful AI assistant for restaurant staff at AppointMint.
You help staff manage reservations through natural conversation.
Current time: {datetime.now(ZAGREB_TZ).strftime('%Y-%m-%d %H:%M')} (Zagreb time)
Staff member: {staff_name}

You can:
- View today's reservations or reservations for any date
- Search for reservations by customer name or phone
- Get details about specific reservations
- Update reservation status (confirm, cancel, complete, mark no-show, arrived, seated)
- Update reservation details (name, phone, guests, date/time, special requests) using update_reservation
- Assign tables to reservations
- View statistics

IMPORTANT RULES:
1. When asked to update or change a reservation, you MUST call the appropriate function:
   - To change status: use update_reservation_status
   - To change other details (name, phone, guests, time, special requests): use update_reservation
2. Always confirm what action you took after calling a function
3. Be concise and helpful
4. When showing reservations, format them clearly

If asked about something you can't do, politely explain your capabilities."""

        # Initial API call
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            tools=AVAILABLE_FUNCTIONS,
            tool_choice="auto"
        )
        
        assistant_message = response.choices[0].message
        
        # Check if the model wants to call functions
        if assistant_message.tool_calls:
            logger.info(f"AI wants to call {len(assistant_message.tool_calls)} function(s)")
            
            # Process each function call
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
                assistant_message
            ]
            
            for tool_call in assistant_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                logger.info(f"Executing function: {function_name} with args: {function_args}")
                
                # Execute the function
                if function_name in FUNCTION_MAP:
                    function_result = FUNCTION_MAP[function_name](function_args)
                    logger.info(f"Function result: {function_result[:200] if len(function_result) > 200 else function_result}")
                else:
                    function_result = f"Unknown function: {function_name}"
                    logger.warning(f"Unknown function requested: {function_name}")
                
                # Add function result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": function_result
                })
            
            # Get final response with function results
            final_response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages
            )
            
            result = final_response.choices[0].message.content
            logger.info(f"Final response: {result[:200] if len(result) > 200 else result}")
            return result
        
        # No function calls, return direct response
        logger.info("No function calls, returning direct response")
        return assistant_message.content
    
    except Exception as e:
        logger.error(f"Error in process_staff_message: {str(e)}", exc_info=True)
        return f"I encountered an error: {str(e)}. Please try again or contact support."
