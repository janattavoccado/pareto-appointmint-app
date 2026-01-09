"""
Mem0 Memory Manager for Restaurant Booking Agent.
Provides persistent memory across user sessions using Mem0 Platform API.
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import pytz

from pydantic import BaseModel, Field

# Configure logging
logger = logging.getLogger(__name__)

# CET:Zagreb timezone
ZAGREB_TZ = pytz.timezone('Europe/Zagreb')


class MemoryEntry(BaseModel):
    """Represents a single memory entry from Mem0."""
    id: str = Field(description="Unique memory ID")
    memory: str = Field(description="The memory content")
    user_id: Optional[str] = Field(default=None, description="User identifier")
    categories: List[str] = Field(default_factory=list, description="Memory categories")
    created_at: Optional[str] = Field(default=None, description="Creation timestamp")
    score: Optional[float] = Field(default=None, description="Relevance score")


class MemorySearchResult(BaseModel):
    """Result of a memory search operation."""
    query: str = Field(description="The search query")
    memories: List[MemoryEntry] = Field(default_factory=list, description="Found memories")
    count: int = Field(description="Number of memories found")


class UserMemoryProfile(BaseModel):
    """User's memory profile summary."""
    user_id: str = Field(description="User identifier")
    name: Optional[str] = Field(default=None, description="User's name if known")
    phone: Optional[str] = Field(default=None, description="User's phone if known")
    preferences: List[str] = Field(default_factory=list, description="User preferences")
    dietary_restrictions: List[str] = Field(default_factory=list, description="Dietary restrictions")
    past_reservations_count: int = Field(default=0, description="Number of past reservations")
    last_visit: Optional[str] = Field(default=None, description="Last interaction date")
    notes: List[str] = Field(default_factory=list, description="Additional notes")


class Mem0MemoryManager:
    """
    Memory manager using Mem0 Platform API for persistent user memory.
    
    This class handles:
    - Storing user information and preferences
    - Retrieving relevant memories for context
    - Managing conversation history
    - Tracking user interactions across sessions
    """
    
    _instance = None
    _client = None
    _initialized = False
    
    # App identifier for this restaurant booking agent
    APP_ID = "restaurant_booking_agent"
    AGENT_ID = "booking_assistant"
    
    def __new__(cls):
        """Singleton pattern to ensure single Mem0 client instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize the Mem0 client."""
        if self._initialized:
            return
            
        self._api_key = os.getenv('MEM0_API_KEY')
        
        if not self._api_key:
            logger.warning("MEM0_API_KEY not set. Memory features will be disabled.")
            self._client = None
        else:
            try:
                from mem0 import MemoryClient
                self._client = MemoryClient(api_key=self._api_key)
                logger.info("Mem0 client initialized successfully")
            except ImportError:
                logger.error("mem0ai package not installed. Run: pip install mem0ai")
                self._client = None
            except Exception as e:
                logger.error(f"Failed to initialize Mem0 client: {e}")
                self._client = None
        
        self._initialized = True
    
    @classmethod
    def get_instance(cls) -> 'Mem0MemoryManager':
        """Get the singleton instance of the memory manager."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @property
    def is_available(self) -> bool:
        """Check if Mem0 is available and configured."""
        return self._client is not None
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp in Zagreb timezone."""
        return datetime.now(ZAGREB_TZ).isoformat()
    
    # =========================================================================
    # Core Memory Operations
    # =========================================================================
    
    def add_memory(
        self,
        messages: List[Dict[str, str]],
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Add a memory from conversation messages.
        
        Args:
            messages: List of conversation messages with 'role' and 'content'
            user_id: Unique identifier for the user
            metadata: Optional metadata to attach to the memory
            
        Returns:
            Response from Mem0 API or None if failed
        """
        if not self.is_available:
            logger.debug("Mem0 not available, skipping memory add")
            return None
        
        try:
            # Add timestamp to metadata
            meta = metadata or {}
            meta['timestamp'] = self._get_current_timestamp()
            
            response = self._client.add(
                messages,
                user_id=user_id,
                agent_id=self.AGENT_ID,
                app_id=self.APP_ID,
                metadata=meta
            )
            
            logger.info(f"Memory added for user {user_id}")
            return response
            
        except Exception as e:
            logger.error(f"Failed to add memory: {e}")
            return None
    
    def add_user_info(
        self,
        user_id: str,
        info_type: str,
        content: str
    ) -> Optional[Dict[str, Any]]:
        """
        Add specific user information as a memory.
        
        Args:
            user_id: Unique identifier for the user
            info_type: Type of information (e.g., 'name', 'preference', 'dietary')
            content: The information content
            
        Returns:
            Response from Mem0 API or None if failed
        """
        if not self.is_available:
            return None
        
        messages = [
            {"role": "user", "content": content},
            {"role": "assistant", "content": f"I've noted your {info_type}."}
        ]
        
        return self.add_memory(
            messages,
            user_id=user_id,
            metadata={"info_type": info_type, "category": info_type}
        )
    
    def search_memories(
        self,
        query: str,
        user_id: str,
        limit: int = 10
    ) -> MemorySearchResult:
        """
        Search for relevant memories for a user.
        
        Args:
            query: Search query
            user_id: User identifier
            limit: Maximum number of results
            
        Returns:
            MemorySearchResult with found memories
        """
        if not self.is_available:
            return MemorySearchResult(query=query, memories=[], count=0)
        
        try:
            filters = {"user_id": user_id}
            
            results = self._client.search(
                query,
                filters=filters,
                limit=limit
            )
            
            memories = []
            if results and 'results' in results:
                for item in results['results']:
                    memories.append(MemoryEntry(
                        id=item.get('id', ''),
                        memory=item.get('memory', ''),
                        user_id=item.get('user_id'),
                        categories=item.get('categories', []),
                        created_at=item.get('created_at'),
                        score=item.get('score')
                    ))
            
            return MemorySearchResult(
                query=query,
                memories=memories,
                count=len(memories)
            )
            
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            return MemorySearchResult(query=query, memories=[], count=0)
    
    def get_all_memories(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 50
    ) -> List[MemoryEntry]:
        """
        Get all memories for a user.
        
        Args:
            user_id: User identifier
            page: Page number
            page_size: Number of results per page
            
        Returns:
            List of memory entries
        """
        if not self.is_available:
            return []
        
        try:
            filters = {"user_id": user_id}
            
            results = self._client.get_all(
                filters=filters,
                page=page,
                page_size=page_size
            )
            
            memories = []
            if results and 'results' in results:
                for item in results['results']:
                    memories.append(MemoryEntry(
                        id=item.get('id', ''),
                        memory=item.get('memory', ''),
                        user_id=item.get('user_id'),
                        categories=item.get('categories', []),
                        created_at=item.get('created_at'),
                        score=item.get('score')
                    ))
            
            return memories
            
        except Exception as e:
            logger.error(f"Failed to get all memories: {e}")
            return []
    
    def delete_memory(self, memory_id: str) -> bool:
        """
        Delete a specific memory by ID.
        
        Args:
            memory_id: The memory ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available:
            return False
        
        try:
            self._client.delete(memory_id)
            logger.info(f"Memory {memory_id} deleted")
            return True
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return False
    
    def delete_all_user_memories(self, user_id: str) -> bool:
        """
        Delete all memories for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available:
            return False
        
        try:
            self._client.delete_all(user_id=user_id)
            logger.info(f"All memories deleted for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete all memories: {e}")
            return False
    
    # =========================================================================
    # High-Level Memory Operations for Booking Agent
    # =========================================================================
    
    def remember_user_name(self, user_id: str, name: str) -> bool:
        """Remember a user's name."""
        result = self.add_user_info(
            user_id=user_id,
            info_type="name",
            content=f"My name is {name}."
        )
        return result is not None
    
    def remember_user_phone(self, user_id: str, phone: str) -> bool:
        """Remember a user's phone number."""
        result = self.add_user_info(
            user_id=user_id,
            info_type="phone",
            content=f"My phone number is {phone}."
        )
        return result is not None
    
    def remember_dietary_preference(self, user_id: str, preference: str) -> bool:
        """Remember a user's dietary preference or restriction."""
        result = self.add_user_info(
            user_id=user_id,
            info_type="dietary",
            content=f"I have a dietary preference/restriction: {preference}."
        )
        return result is not None
    
    def remember_seating_preference(self, user_id: str, preference: str) -> bool:
        """Remember a user's seating preference."""
        result = self.add_user_info(
            user_id=user_id,
            info_type="seating",
            content=f"I prefer seating: {preference}."
        )
        return result is not None
    
    def remember_reservation(
        self,
        user_id: str,
        reservation_id: int,
        date_time: str,
        guests: int
    ) -> bool:
        """Remember a reservation made by the user."""
        messages = [
            {
                "role": "user",
                "content": f"I made a reservation (ID: {reservation_id}) for {guests} guests on {date_time}."
            },
            {
                "role": "assistant",
                "content": f"I've recorded your reservation #{reservation_id} for {guests} guests on {date_time}."
            }
        ]
        result = self.add_memory(
            messages,
            user_id=user_id,
            metadata={
                "info_type": "reservation",
                "reservation_id": reservation_id,
                "date_time": date_time,
                "guests": guests
            }
        )
        return result is not None
    
    def get_user_context(self, user_id: str) -> str:
        """
        Get a formatted context string with all relevant user memories.
        This is used to provide context to the booking agent.
        
        Args:
            user_id: User identifier
            
        Returns:
            Formatted string with user context
        """
        if not self.is_available:
            return "Memory system not available."
        
        try:
            # Search for various types of user information
            queries = [
                "user name and contact information",
                "dietary preferences and restrictions",
                "seating preferences",
                "past reservations and visits"
            ]
            
            all_memories = set()
            
            for query in queries:
                results = self.search_memories(query, user_id, limit=5)
                for mem in results.memories:
                    all_memories.add(mem.memory)
            
            if not all_memories:
                return "No previous information found for this user. This appears to be a new guest."
            
            context_parts = ["Here's what I remember about this guest:"]
            for memory in all_memories:
                context_parts.append(f"- {memory}")
            
            return "\n".join(context_parts)
            
        except Exception as e:
            logger.error(f"Failed to get user context: {e}")
            return "Unable to retrieve user memories at this time."
    
    def get_user_profile(self, user_id: str) -> UserMemoryProfile:
        """
        Get a structured user profile from memories.
        
        Args:
            user_id: User identifier
            
        Returns:
            UserMemoryProfile with extracted information
        """
        profile = UserMemoryProfile(user_id=user_id)
        
        if not self.is_available:
            return profile
        
        try:
            # Get all memories for the user
            memories = self.get_all_memories(user_id, page_size=100)
            
            for mem in memories:
                memory_text = mem.memory.lower()
                
                # Extract name
                if 'name is' in memory_text or 'called' in memory_text:
                    # Try to extract name from memory
                    profile.notes.append(mem.memory)
                
                # Extract dietary info
                if any(word in memory_text for word in ['vegetarian', 'vegan', 'allergy', 'allergic', 'dietary', 'gluten', 'lactose']):
                    profile.dietary_restrictions.append(mem.memory)
                
                # Extract preferences
                if any(word in memory_text for word in ['prefer', 'like', 'favorite', 'favourite']):
                    profile.preferences.append(mem.memory)
                
                # Count reservations
                if 'reservation' in memory_text:
                    profile.past_reservations_count += 1
                
                # Track last visit
                if mem.created_at and (not profile.last_visit or mem.created_at > profile.last_visit):
                    profile.last_visit = mem.created_at
            
            return profile
            
        except Exception as e:
            logger.error(f"Failed to get user profile: {e}")
            return profile
    
    def store_conversation_memory(
        self,
        user_id: str,
        user_message: str,
        assistant_response: str
    ) -> bool:
        """
        Store a conversation exchange as memory.
        Only stores if the exchange contains memorable information.
        
        Args:
            user_id: User identifier
            user_message: The user's message
            assistant_response: The assistant's response
            
        Returns:
            True if memory was stored, False otherwise
        """
        # Keywords that indicate memorable information
        memorable_keywords = [
            'name is', 'i am', "i'm", 'my phone', 'call me',
            'vegetarian', 'vegan', 'allergy', 'allergic', 'dietary',
            'prefer', 'favorite', 'favourite', 'like', 'don\'t like',
            'birthday', 'anniversary', 'celebration', 'special occasion',
            'reservation', 'book', 'table for', 'guests'
        ]
        
        message_lower = user_message.lower()
        
        # Check if the message contains memorable information
        if any(keyword in message_lower for keyword in memorable_keywords):
            messages = [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_response}
            ]
            result = self.add_memory(messages, user_id=user_id)
            return result is not None
        
        return False


# Create singleton instance
memory_manager = Mem0MemoryManager.get_instance()
