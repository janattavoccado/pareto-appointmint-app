"""
Staff Chatbot - AI Assistant for Restaurant Staff
Uses OpenAI function calling for natural language reservation management
"""

import json
from datetime import datetime, timedelta
import pytz
from openai import OpenAI

# Initialize OpenAI client
client = OpenAI()

# Zagreb timezone
ZAGREB_TZ = pytz.timezone('Europe/Zagreb')

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
            "description": "Update the status of a reservation (confirmed, cancelled, completed, no-show)",
            "parameters": {
                "type": "object",
                "properties": {
                    "reservation_id": {
                        "type": "integer",
                        "description": "The reservation ID"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "confirmed", "cancelled", "completed", "no-show"],
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
    from models import Reservation
    today = datetime.now(ZAGREB_TZ).date()
    reservations = Reservation.get_by_date(today)
    
    if not reservations:
        return "No reservations found for today."
    
    result = f"Today's reservations ({len(reservations)} total):\n\n"
    for res in reservations:
        result += f"• #{res.id} - {res.customer_name} at {res.reservation_time.strftime('%H:%M')}\n"
        result += f"  Party: {res.party_size} | Status: {res.status}"
        if res.table_number:
            result += f" | Table: {res.table_number}"
        result += "\n"
    
    return result

def get_reservations_by_date(date: str):
    """Get reservations for a specific date"""
    from models import Reservation
    try:
        target_date = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        return f"Invalid date format. Please use YYYY-MM-DD."
    
    reservations = Reservation.get_by_date(target_date)
    
    if not reservations:
        return f"No reservations found for {date}."
    
    result = f"Reservations for {date} ({len(reservations)} total):\n\n"
    for res in reservations:
        result += f"• #{res.id} - {res.customer_name} at {res.reservation_time.strftime('%H:%M')}\n"
        result += f"  Party: {res.party_size} | Status: {res.status}\n"
    
    return result

def search_reservations(query: str):
    """Search reservations by name or phone"""
    from models import Reservation
    reservations = Reservation.search(query)
    
    if not reservations:
        return f"No reservations found matching '{query}'."
    
    result = f"Found {len(reservations)} reservation(s) matching '{query}':\n\n"
    for res in reservations:
        result += f"• #{res.id} - {res.customer_name}\n"
        result += f"  Date: {res.reservation_date} at {res.reservation_time.strftime('%H:%M')}\n"
        result += f"  Phone: {res.customer_phone} | Party: {res.party_size} | Status: {res.status}\n\n"
    
    return result

def get_reservation_details(reservation_id: int):
    """Get detailed information about a reservation"""
    from models import Reservation
    res = Reservation.get_by_id(reservation_id)
    
    if not res:
        return f"Reservation #{reservation_id} not found."
    
    result = f"Reservation #{res.id} Details:\n\n"
    result += f"Customer: {res.customer_name}\n"
    result += f"Phone: {res.customer_phone}\n"
    result += f"Date: {res.reservation_date}\n"
    result += f"Time: {res.reservation_time.strftime('%H:%M')}\n"
    result += f"Party Size: {res.party_size}\n"
    result += f"Status: {res.status}\n"
    if res.table_number:
        result += f"Table: {res.table_number}\n"
    if res.special_requests:
        result += f"Special Requests: {res.special_requests}\n"
    result += f"Created: {res.created_at}\n"
    
    return result

def update_reservation_status(reservation_id: int, status: str):
    """Update reservation status"""
    from models import Reservation
    res = Reservation.get_by_id(reservation_id)
    
    if not res:
        return f"Reservation #{reservation_id} not found."
    
    old_status = res.status
    res.update_status(status)
    
    return f"Reservation #{reservation_id} status updated from '{old_status}' to '{status}'."

def assign_table(reservation_id: int, table_number: str):
    """Assign table to reservation"""
    from models import Reservation
    res = Reservation.get_by_id(reservation_id)
    
    if not res:
        return f"Reservation #{reservation_id} not found."
    
    res.table_number = table_number
    res.save()
    
    return f"Table {table_number} assigned to reservation #{reservation_id} ({res.customer_name})."

def get_statistics():
    """Get reservation statistics"""
    from models import Reservation
    stats = Reservation.get_stats()
    
    result = "Reservation Statistics:\n\n"
    result += f"Total Reservations: {stats.get('total', 0)}\n"
    result += f"Today's Reservations: {stats.get('today', 0)}\n"
    result += f"Pending: {stats.get('pending', 0)}\n"
    result += f"Confirmed: {stats.get('confirmed', 0)}\n"
    result += f"This Week: {stats.get('this_week', 0)}\n"
    
    return result

def get_upcoming_reservations(hours: int = 2):
    """Get upcoming reservations"""
    from models import Reservation
    
    now = datetime.now(ZAGREB_TZ)
    today = now.date()
    reservations = Reservation.get_by_date(today)
    
    # Filter to upcoming only
    upcoming = []
    for res in reservations:
        res_datetime = datetime.combine(res.reservation_date, res.reservation_time)
        res_datetime = ZAGREB_TZ.localize(res_datetime)
        if res_datetime > now and res_datetime < now + timedelta(hours=hours):
            upcoming.append(res)
    
    if not upcoming:
        return f"No reservations in the next {hours} hour(s)."
    
    result = f"Upcoming reservations (next {hours} hours):\n\n"
    for res in upcoming:
        result += f"• #{res.id} - {res.customer_name} at {res.reservation_time.strftime('%H:%M')}\n"
        result += f"  Party: {res.party_size} | Status: {res.status}"
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
    "assign_table": lambda args: assign_table(args.get("reservation_id"), args.get("table_number")),
    "get_statistics": lambda args: get_statistics(),
    "get_upcoming_reservations": lambda args: get_upcoming_reservations(args.get("hours", 2))
}

def process_staff_message(message: str, staff_name: str = "Staff") -> str:
    """
    Process a message from staff and return AI response
    Uses OpenAI function calling for reservation management
    """
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
- Update reservation status (confirm, cancel, complete, mark no-show)
- Assign tables to reservations
- View statistics

Be concise and helpful. When showing reservations, format them clearly.
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
            # Process each function call
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
                assistant_message
            ]
            
            for tool_call in assistant_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                # Execute the function
                if function_name in FUNCTION_MAP:
                    function_result = FUNCTION_MAP[function_name](function_args)
                else:
                    function_result = f"Unknown function: {function_name}"
                
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
            
            return final_response.choices[0].message.content
        
        # No function calls, return direct response
        return assistant_message.content
    
    except Exception as e:
        return f"I encountered an error: {str(e)}. Please try again or contact support."
