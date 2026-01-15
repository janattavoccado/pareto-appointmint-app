"""
Staff Chatbot - AI-powered reservation management assistant for restaurant staff
Supports both text and voice input for managing reservations
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Staff chatbot system prompt
STAFF_SYSTEM_PROMPT = """You are a helpful AI assistant for restaurant staff to manage table reservations.
You help staff with the following tasks:

1. **View Reservations**: Show today's reservations, upcoming bookings, or search by name/phone/date
2. **Update Status**: Mark reservations as confirmed, arrived, seated, completed, or cancelled
3. **Modify Details**: Update guest count, time, date, name, phone, or special requests
4. **Quick Info**: Get details about a specific reservation by ID or guest name

Current Date/Time: {current_datetime}

When responding:
- Be concise and professional
- Confirm actions taken
- Show relevant reservation details after updates
- If multiple reservations match, list them and ask for clarification
- Use clear formatting for reservation details

Available status values:
- pending: New reservation, not yet confirmed
- confirmed: Reservation confirmed by staff
- arrived: Guest has arrived
- seated: Guest is seated at table
- completed: Dining completed, guest has left
- cancelled: Reservation cancelled
- no_show: Guest did not arrive

Always respond in a helpful, efficient manner suitable for busy restaurant staff.
"""

# Tools for the staff chatbot
STAFF_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_todays_reservations",
            "description": "Get all reservations for today",
            "parameters": {
                "type": "object",
                "properties": {
                    "status_filter": {
                        "type": "string",
                        "description": "Optional filter by status (pending, confirmed, arrived, seated, completed, cancelled, no_show)",
                        "enum": ["pending", "confirmed", "arrived", "seated", "completed", "cancelled", "no_show"]
                    }
                },
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
                    },
                    "status_filter": {
                        "type": "string",
                        "description": "Optional filter by status",
                        "enum": ["pending", "confirmed", "arrived", "seated", "completed", "cancelled", "no_show"]
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
            "description": "Search reservations by guest name or phone number",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Guest name or phone number to search for"
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
            "description": "Get full details of a specific reservation by ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "reservation_id": {
                        "type": "integer",
                        "description": "The reservation ID number"
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
            "description": "Update the status of a reservation (e.g., mark as arrived, completed, cancelled)",
            "parameters": {
                "type": "object",
                "properties": {
                    "reservation_id": {
                        "type": "integer",
                        "description": "The reservation ID number"
                    },
                    "new_status": {
                        "type": "string",
                        "description": "The new status for the reservation",
                        "enum": ["pending", "confirmed", "arrived", "seated", "completed", "cancelled", "no_show"]
                    }
                },
                "required": ["reservation_id", "new_status"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_reservation_details",
            "description": "Update reservation details like guest count, time, date, name, phone, or notes",
            "parameters": {
                "type": "object",
                "properties": {
                    "reservation_id": {
                        "type": "integer",
                        "description": "The reservation ID number"
                    },
                    "guest_count": {
                        "type": "integer",
                        "description": "New number of guests"
                    },
                    "reservation_time": {
                        "type": "string",
                        "description": "New time in HH:MM format"
                    },
                    "reservation_date": {
                        "type": "string",
                        "description": "New date in YYYY-MM-DD format"
                    },
                    "guest_name": {
                        "type": "string",
                        "description": "Updated guest name"
                    },
                    "guest_phone": {
                        "type": "string",
                        "description": "Updated phone number"
                    },
                    "special_requests": {
                        "type": "string",
                        "description": "Updated special requests or notes"
                    }
                },
                "required": ["reservation_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_reservations",
            "description": "Get upcoming reservations for the next few hours",
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
    },
    {
        "type": "function",
        "function": {
            "name": "get_reservation_stats",
            "description": "Get statistics for today's reservations (total, by status, total guests)",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]


class StaffChatbot:
    """Staff chatbot for managing restaurant reservations"""
    
    def __init__(self, db_manager):
        """Initialize with database manager"""
        self.db = db_manager
        self.conversation_history: Dict[str, List[Dict]] = {}
    
    def get_conversation(self, session_id: str) -> List[Dict]:
        """Get or create conversation history for a session"""
        if session_id not in self.conversation_history:
            self.conversation_history[session_id] = []
        return self.conversation_history[session_id]
    
    def clear_conversation(self, session_id: str):
        """Clear conversation history for a session"""
        if session_id in self.conversation_history:
            del self.conversation_history[session_id]
    
    def format_reservation(self, res: Dict) -> str:
        """Format a reservation for display"""
        status_emoji = {
            'pending': '⏳',
            'confirmed': '✅',
            'arrived': '🚶',
            'seated': '🪑',
            'completed': '✔️',
            'cancelled': '❌',
            'no_show': '👻'
        }
        emoji = status_emoji.get(res.get('status', 'pending'), '📋')
        
        return f"""
{emoji} **Reservation #{res.get('id')}**
• Guest: {res.get('guest_name', 'N/A')}
• Phone: {res.get('guest_phone', 'N/A')}
• Date: {res.get('reservation_date', 'N/A')}
• Time: {res.get('reservation_time', 'N/A')}
• Guests: {res.get('guest_count', 'N/A')}
• Status: {res.get('status', 'pending').upper()}
• Notes: {res.get('special_requests', 'None')}
"""
    
    def execute_tool(self, tool_name: str, args: Dict) -> str:
        """Execute a tool and return the result"""
        logger.info(f"Executing tool: {tool_name} with args: {args}")
        
        try:
            if tool_name == "get_todays_reservations":
                today = datetime.now().strftime('%Y-%m-%d')
                reservations = self.db.get_reservations_by_date(today)
                
                # Apply status filter if provided
                status_filter = args.get('status_filter')
                if status_filter:
                    reservations = [r for r in reservations if r.get('status') == status_filter]
                
                if not reservations:
                    return "No reservations found for today."
                
                result = f"**Today's Reservations ({len(reservations)} total):**\n"
                for res in reservations:
                    result += self.format_reservation(res)
                return result
            
            elif tool_name == "get_reservations_by_date":
                date = args.get('date')
                reservations = self.db.get_reservations_by_date(date)
                
                status_filter = args.get('status_filter')
                if status_filter:
                    reservations = [r for r in reservations if r.get('status') == status_filter]
                
                if not reservations:
                    return f"No reservations found for {date}."
                
                result = f"**Reservations for {date} ({len(reservations)} total):**\n"
                for res in reservations:
                    result += self.format_reservation(res)
                return result
            
            elif tool_name == "search_reservations":
                query = args.get('query', '')
                reservations = self.db.search_reservations(query)
                
                if not reservations:
                    return f"No reservations found matching '{query}'."
                
                result = f"**Search Results for '{query}' ({len(reservations)} found):**\n"
                for res in reservations:
                    result += self.format_reservation(res)
                return result
            
            elif tool_name == "get_reservation_details":
                res_id = args.get('reservation_id')
                reservation = self.db.get_reservation_by_id(res_id)
                
                if not reservation:
                    return f"Reservation #{res_id} not found."
                
                return self.format_reservation(reservation)
            
            elif tool_name == "update_reservation_status":
                res_id = args.get('reservation_id')
                new_status = args.get('new_status')
                
                success = self.db.update_reservation_status(res_id, new_status)
                
                if success:
                    reservation = self.db.get_reservation_by_id(res_id)
                    return f"✅ Status updated successfully!\n{self.format_reservation(reservation)}"
                else:
                    return f"❌ Failed to update reservation #{res_id}. Please check the ID."
            
            elif tool_name == "update_reservation_details":
                res_id = args.get('reservation_id')
                updates = {k: v for k, v in args.items() if k != 'reservation_id' and v is not None}
                
                if not updates:
                    return "No updates provided."
                
                success = self.db.update_reservation(res_id, **updates)
                
                if success:
                    reservation = self.db.get_reservation_by_id(res_id)
                    return f"✅ Reservation updated successfully!\n{self.format_reservation(reservation)}"
                else:
                    return f"❌ Failed to update reservation #{res_id}. Please check the ID."
            
            elif tool_name == "get_upcoming_reservations":
                hours = args.get('hours', 2)
                now = datetime.now()
                end_time = now + timedelta(hours=hours)
                
                today = now.strftime('%Y-%m-%d')
                reservations = self.db.get_reservations_by_date(today)
                
                # Filter to upcoming reservations
                upcoming = []
                for res in reservations:
                    try:
                        res_time = datetime.strptime(f"{today} {res.get('reservation_time')}", '%Y-%m-%d %H:%M')
                        if now <= res_time <= end_time and res.get('status') not in ['completed', 'cancelled', 'no_show']:
                            upcoming.append(res)
                    except:
                        pass
                
                if not upcoming:
                    return f"No upcoming reservations in the next {hours} hours."
                
                result = f"**Upcoming Reservations (next {hours} hours):**\n"
                for res in sorted(upcoming, key=lambda x: x.get('reservation_time', '')):
                    result += self.format_reservation(res)
                return result
            
            elif tool_name == "get_reservation_stats":
                today = datetime.now().strftime('%Y-%m-%d')
                reservations = self.db.get_reservations_by_date(today)
                
                stats = {
                    'total': len(reservations),
                    'pending': 0,
                    'confirmed': 0,
                    'arrived': 0,
                    'seated': 0,
                    'completed': 0,
                    'cancelled': 0,
                    'no_show': 0,
                    'total_guests': 0
                }
                
                for res in reservations:
                    status = res.get('status', 'pending')
                    if status in stats:
                        stats[status] += 1
                    stats['total_guests'] += res.get('guest_count', 0)
                
                return f"""
**Today's Reservation Statistics:**

📊 **Total Reservations:** {stats['total']}
👥 **Total Guests Expected:** {stats['total_guests']}

**By Status:**
• ⏳ Pending: {stats['pending']}
• ✅ Confirmed: {stats['confirmed']}
• 🚶 Arrived: {stats['arrived']}
• 🪑 Seated: {stats['seated']}
• ✔️ Completed: {stats['completed']}
• ❌ Cancelled: {stats['cancelled']}
• 👻 No-show: {stats['no_show']}
"""
            
            else:
                return f"Unknown tool: {tool_name}"
                
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return f"Error: {str(e)}"
    
    def process_message(self, session_id: str, user_message: str) -> str:
        """Process a staff message and return the response"""
        
        # Get conversation history
        conversation = self.get_conversation(session_id)
        
        # Build system prompt with current datetime
        system_prompt = STAFF_SYSTEM_PROMPT.format(
            current_datetime=datetime.now().strftime('%Y-%m-%d %H:%M')
        )
        
        # Add user message to conversation
        conversation.append({
            "role": "user",
            "content": user_message
        })
        
        # Build messages for API call
        messages = [{"role": "system", "content": system_prompt}] + conversation[-10:]  # Keep last 10 messages
        
        try:
            # Call OpenAI API
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages,
                tools=STAFF_TOOLS,
                tool_choice="auto",
                temperature=0.3
            )
            
            assistant_message = response.choices[0].message
            
            # Check if tool calls are needed
            if assistant_message.tool_calls:
                # Execute each tool call
                tool_results = []
                for tool_call in assistant_message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    
                    result = self.execute_tool(tool_name, tool_args)
                    tool_results.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "content": result
                    })
                
                # Add assistant message and tool results to conversation
                conversation.append({
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in assistant_message.tool_calls
                    ]
                })
                
                for tr in tool_results:
                    conversation.append(tr)
                
                # Get final response with tool results
                messages = [{"role": "system", "content": system_prompt}] + conversation[-15:]
                
                final_response = client.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=messages,
                    temperature=0.3
                )
                
                final_content = final_response.choices[0].message.content
                conversation.append({
                    "role": "assistant",
                    "content": final_content
                })
                
                return final_content
            else:
                # No tool calls, just return the response
                content = assistant_message.content
                conversation.append({
                    "role": "assistant",
                    "content": content
                })
                return content
                
        except Exception as e:
            logger.error(f"Error processing staff message: {e}")
            return f"Sorry, I encountered an error: {str(e)}"


# Singleton instance (will be initialized with db_manager)
staff_chatbot_instance: Optional[StaffChatbot] = None


def get_staff_chatbot(db_manager) -> StaffChatbot:
    """Get or create the staff chatbot instance"""
    global staff_chatbot_instance
    if staff_chatbot_instance is None:
        staff_chatbot_instance = StaffChatbot(db_manager)
    return staff_chatbot_instance
